---
name: deploy-dokploy
description: "Deploy em Dokploy self-hosted (Swarm + Traefik): Application com imagem do GHCR, auto-deploy desligado e disparo pelo CI, API/CLI, Swarm settings, rollback e armadilhas. Usar ao escrever pipeline que publica no Dokploy, configurar um app nele ou executar deploy/rollback."
---

# Deploy no Dokploy

Levantado em 2026-10-13. Versão estável mais recente: **v0.30.8** (29/09/2026). A branch padrão do repo é `canary`. Fontes: docs.dokploy.com, código em `github.com/Dokploy/dokploy` e o `openapi.json` de `github.com/Dokploy/cli`. **A doc está defasada em vários pontos** (citados abaixo). Para endpoint e campo, a referência é o `/swagger` da própria instância (só admin) ou o OpenAPI da CLI na versão instalada. A API muda entre versões: fixe a versão do Dokploy e da CLI e teste os scripts a cada upgrade.

## 1. Modelo recomendado
O CI gera a imagem no GHCR (tag imutável). O Dokploy usa um **Application** com fonte **Docker**, sem auto-deploy. O CI faz `application.update` (nova `dockerImage`), depois `application.deploy`, acompanha por `deployment.all` e **confirma a saúde por conta própria** (ver §6).

- Cada Application é um **serviço Docker Swarm**. O Traefik roteia pela rede overlay `dokploy-network` até `<appName>:<porta>`.
- Use Application, não Compose, para APIs e workers. As Swarm settings (healthcheck, update, rollback) valem para Application.
- A doc de produção recomenda fazer o build no CI, não no servidor, porque o build pesado pode travar o host. O build server remoto existe, mas é dispensável com CI.
- Deploys do mesmo app são enfileirados em FIFO. A concorrência por servidor é 1 por padrão.

## 2. Fonte, auto-deploy e webhooks
- Fontes possíveis: `github` (GitHub App), `gitlab`, `bitbucket`, `gitea`, `git` (SSH), `docker` e `drop`.
- O auto-deploy por push vem **ligado** no GitHub App. Desligue o toggle "Auto Deploy" ou chame `application.update {autoDeploy:false}`. O `application.deploy` pela API **ignora `autoDeploy`**, então continua funcionando.
- Com a fonte `docker`, nenhum push de git dispara deploy. É o desenho mais simples para CD controlado.
- **Webhook de refresh token**: `POST /api/deploy/<refreshToken>` (Compose: `/api/deploy/compose/<token>`).
  - **Não tem assinatura**: o token na URL é o único segredo.
  - Com `autoDeploy=false`, responde 400.
  - Para rotacionar: `application.refreshToken`.
  - Prefira a API com `x-api-key`.

## 3. Registry (GHCR privado)
- O app de fonte docker usa **credenciais próprias** (`username`, `password`, `registryUrl=ghcr.io` em `application.saveDockerProvider`). Elas viram o `authconfig` do serviço Swarm e chegam a todos os nós.
- O registry de Settings > Registries **não** é usado como authconfig da fonte docker. Em cluster, ponha as credenciais no app.
- Use PAT classic só `read:packages`. A doc pede `write:packages`, o que é mais do que precisa.
- **Issue #2759 (aberta)**: o login no GHCR pode não valer em remote server. Contorno: `docker login ghcr.io` manual no servidor ou credencial no app.
- A senha do docker provider e a do registry ficam em coluna de texto sem criptografia aparente, ao contrário dos envs, que são criptografados.

## 4. Variáveis
- Há três níveis: projeto `${{project.VAR}}`, ambiente `${{environment.VAR}}` e serviço `${{VAR}}`. Staging e produção podem ser dois ambientes de um projeto, cada um com seu Application e seu `applicationId`. Para isolar permissões, use projetos separados.
- Os envs, build args e build secrets são **criptografados no banco** com chave derivada de `BETTER_AUTH_SECRET`. **Sem esse segredo, o restore não lê os envs**: inclua-o no backup.
- Com build no CI, os `buildArgs`/`buildSecrets` do Dokploy não se aplicam.
- **`application.saveEnvironment` substitui o conjunto inteiro** e todos os campos são obrigatórios. Nunca use no CI para "adicionar uma variável".
- Cofres externos: `${{vault.<provider>.<path>:<KEY>}}` (Vault/OpenBao, Infisical, AWS SM/Parameter Store, Doppler, Azure KV).

## 5. Zero downtime (Advanced > Cluster Settings > Swarm Settings)
- **Todas as durações em nanossegundos**, memória em bytes e CPU em nanoCPUs. Valores como `30s` ou `1024m` **quebram o deploy**.
- Sem configuração, o código usa `UpdateConfig {Parallelism:1, Order:"start-first", FailureAction:"rollback"}`. A página "Zero Downtime" diz o contrário (stop-first) e está defasada. Mesmo assim, **sem HealthCheck o start-first não sabe quando o novo container está pronto**.
- Exemplo para Node na porta 4090 (as imagens alpine têm o `wget` do busybox, não `curl`):
```json
// healthCheckSwarm
{ "Test": ["CMD-SHELL","wget -qO- http://127.0.0.1:4090/health >/dev/null || exit 1"],
  "Interval": 10000000000, "Timeout": 5000000000, "StartPeriod": 20000000000, "Retries": 3 }
// updateConfigSwarm
{ "Parallelism": 1, "Delay": 5000000000, "Order": "start-first",
  "FailureAction": "rollback", "Monitor": 60000000000, "MaxFailureRatio": 0 }
// stopGracePeriodSwarm (número, ns)
60000000000
```
- `Monitor` precisa ser maior que `StartPeriod + Interval × Retries`. Senão, o Swarm declara o update concluído antes do veredito do healthcheck.
- O padrão do `StopGracePeriod` no Swarm é 10 s. Para worker de fila, use mais que o job mais longo mais a drenagem.
- **Worker de fila**: com `start-first`, as versões velha e nova consomem a fila ao mesmo tempo, então os jobs precisam ser idempotentes e compatíveis. Para não ter sobreposição, use `"Order":"stop-first"`; a fila segura os jobs enquanto o worker está parado.
- Réplicas: campo `replicas` (Cluster Settings).
- **Depois de mudar as Swarm settings, é preciso Redeploy.**
- Porta interna: o "Container Port" do domínio não publica no host; a publicação real fica em Advanced > Ports. Worker sem HTTP fica sem domínio e sem Ports.

## 6. API (`https://<painel>/api/<router>.<procedure>`, header `x-api-key`)
- Queries são `GET` com query string; mutations são `POST` com JSON.
- O token é criado em Settings > Profile > API/CLI, com expiração e organização. **Não tem escopo próprio: herda o papel do usuário.**

| Chamada | Uso |
|---|---|
| `GET project.all` | Árvore projetos → ambientes → apps, com IDs |
| `GET application.one?applicationId=` | `applicationStatus`: `idle`, `running`, `done`, `error` |
| `GET application.search?name=...` | Achar o `applicationId` |
| `POST application.update` | `{applicationId, dockerImage}` para trocar a imagem; também `autoDeploy`, `replicas`, `healthCheckSwarm`, `updateConfigSwarm`, `stopGracePeriodSwarm`... |
| `POST application.deploy` | `{applicationId, title?, description?}`. Para a fonte docker, faz login e **pull**. Use este, não `redeploy` (que pula o pull) |
| `GET deployment.all?applicationId=` | Lista em ordem decrescente de `createdAt`, com `status`: `running`, `done`, `error`, `cancelled` |
| `GET deployment.readLogs?deploymentId=&tail=` | Logs do deploy |
| `GET application.readLogs?applicationId=&tail=` | Logs de runtime |
| `GET deployment.allByType?type=application&id=` | Inclui o `rollbackId` de cada deploy |
| `POST rollback.rollback {rollbackId}` | Rollback nativo (ver §7) |
| `POST application.cleanQueues` / `application.killBuild` | Destravar. O `cancelDeployment` **só funciona no Cloud** |

- **O deploy é assíncrono e não devolve `deploymentId`.** Para acompanhar: grave `T0`, chame o deploy e consulte `deployment.all` até aparecer um item com `createdAt > T0` e status final.
- **Bug #3987 (aberto; correção no PR #5218, sem merge em 06/10/2026)**: o deploy vira `done` assim que o Swarm aceita o update, **sem esperar o healthcheck**. Se o Swarm fizer rollback, a UI e a notificação mostram sucesso. **O CI precisa confirmar a versão no ar**, de preferência com o `/health` devolvendo o SHA ou a versão, ou conferindo os logs.
- **CLI oficial**: `@dokploy/cli` (fixe a versão), com `DOKPLOY_URL` + `DOKPLOY_API_KEY`. Exemplo: `dokploy application deploy --applicationId X --json`. A página de CLI da doc cita comandos antigos (`dokploy app deploy`); a referência é o README do repo. Há também o SDK `@dokploy/sdk`.
- **Não existe GitHub Action oficial.** A doc "going production" cita `dokploy/dokploy-action@v1`, que não existe. Actions de terceiros recebem o token do painel: prefira `curl` + `jq` ou a CLI fixada.

## 7. Rollback
- **Por tag (padrão)**: repita a promoção com a tag anterior (`application.update` + `application.deploy`). Fica auditável no Actions.
- **Nativo ("Registry-based Rollbacks")**: com `rollbackActive=true` e `rollbackRegistryId`, cada deploy é retaggeado como `<appName>:v<N>` num registry de rollback. Para voltar: `rollback.rollback {rollbackId}`. Atenção: o contexto salvo inclui as credenciais do registry e os envs no banco do Dokploy.
- **Automático do Swarm**: `FailureAction: "rollback"` com healthcheck volta sozinho, mas **o Dokploy vai mostrar "done"** (#3987).

## 8. Step de deploy com acompanhamento
```yaml
      - name: Deploy no Dokploy e acompanhar
        env:
          URL: ${{ vars.DOKPLOY_URL }}
          APP: ${{ vars.DOKPLOY_APP_ID }}
          KEY: ${{ secrets.DOKPLOY_API_KEY }}
          IMG: ghcr.io/org/app:sha-${{ github.sha }}   # minúsculas
        run: |
          set -euo pipefail
          H=(-H "x-api-key: $KEY" -H 'Content-Type: application/json')
          curl -fsS "${H[@]}" -X POST "$URL/api/application.update" \
            -d "{\"applicationId\":\"$APP\",\"dockerImage\":\"$IMG\"}" >/dev/null
          T0=$(date -u +%Y-%m-%dT%H:%M:%S)
          curl -fsS "${H[@]}" -X POST "$URL/api/application.deploy" \
            -d "{\"applicationId\":\"$APP\",\"title\":\"$IMG\"}" >/dev/null
          S=pending
          for i in $(seq 1 90); do
            S=$(curl -fsS "${H[@]}" "$URL/api/deployment.all?applicationId=$APP" \
              | jq -r --arg t "$T0" '[.[]|select(.createdAt>$t)]|sort_by(.createdAt)|last|.status // "pending"')
            echo "status=$S"
            case "$S" in done) break;; error|cancelled) exit 1;; esac
            sleep 10
          done
          [ "$S" = done ] || { echo "timeout"; exit 1; }
          # "done" não garante saúde (#3987): o smoke test a seguir precisa confirmar a versão nova
```
- A comparação `createdAt > T0` é textual em ISO 8601. Confira o formato que a sua versão devolve (pode incluir milissegundos e `Z`) antes de confiar no filtro.

## 9. Segurança e operação
- **Usuário dedicado para o CI**, papel Member, acesso só aos serviços necessários, "Access to API/CLI" e token com expiração. Um token de admin ou owner é quase root no host.
- Para trocar `dockerImage`, o Member precisa da permissão "Create Services", que também permite criar serviços. Alternativa de menor privilégio: o app aponta para uma tag mutável (`:production`), o CI faz o retag no GHCR e chama só `application.deploy`. O custo é perder a tag imutável no spec.
- Feche a porta 3000 do painel e sirva por domínio com TLS ou VPN. Ative 2FA, use `ufw-docker` e nunca exponha o socket do Docker.
- Backup do Dokploy (Postgres + `/etc/dokploy`) para S3, mais o `BETTER_AUTH_SECRET`.
- O monitoramento embutido tem documentação contraditória para self-hosted. Não dependa dele; use `/metrics` e logs externos.
- Notificações: App Deploy e App Build Error por Slack, Discord, Telegram, e-mail ou webhook. A de sucesso sofre do mesmo #3987.
