---
name: deploy-coolify
description: "Deploy em Coolify v4 self-hosted: Dockerfile x Docker Image, auto-deploy desligado e disparo pelo CI, API (tokens, /deploy, rollback), GHCR privado, healthcheck e armadilhas. Usar ao escrever pipeline que publica no Coolify, configurar um app nele ou executar deploy/rollback."
---

# Deploy no Coolify (v4)

Levantado em 2026-10-13. Versão estável mais recente: **v4.4.6** (09/10/2026). Fontes: coolify.io/docs e o código em `github.com/coollabsio/coolify` (tag v4.4.6). A doc às vezes está atrasada em relação ao código: **na dúvida, confira `routes/api.php` da versão instalada** e a versão do painel antes de afirmar algo.

## 1. Modelo recomendado
O CI gera a imagem no GHCR e o app no Coolify é do tipo **Docker Image**, com auto-deploy desligado. O CI dispara o deploy pela API, acompanha até o fim e faz smoke test. A própria doc recomenda Docker Image quando o CI faz o build.

| Tipo | Quando usar | Observação |
|---|---|---|
| **Docker Image** | CD com imagem do CI (padrão) | Só faz pull e sobe. Não clona, não builda, não tem auto-deploy por git |
| Dockerfile (git) | Sem CI de imagem | Builda no servidor. Deploy pela API usa o **HEAD da branch**, não o commit testado (não existe parâmetro `commit` em `/deploy`) |
| Docker Compose | Vários serviços acoplados | **Sem rolling update** |
| Nixpacks / Railpack | Evitar | Nixpacks em maintenance; Railpack em beta |

## 2. Configuração do app
- **Auto-deploy**: em Advanced > Deployment, marque "Manual deployments only" (`is_auto_deploy_enabled=false`). O deploy pela API continua funcionando. O Coolify **não espera o CI** antes do deploy por push; não existe integração com checks.
- **Registry privado (GHCR)**: na página Registries (v4.4+) ou Servers > Registries, faça o login com PAT classic `read:packages`. O Coolify roda `docker login` no servidor e o token fica em `~/.docker/config.json`. Faça isso **em todo servidor que faz pull**.
- **Tag**: `docker_registry_image_name` + `docker_registry_image_tag`. A tag vazia vira `latest`, que é proibido em produção. Regex da tag: `^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$`, e `$VAR` não é aceito.
- **Rolling update** (Dockerfile e Docker Image): sobe o novo, espera o healthcheck e remove o antigo. Se o novo ficar unhealthy, o antigo continua. **É desligado em silêncio** (o motivo aparece só no log) quando:
  - há **Port Mappings** para o host;
  - o nome de container é consistente ou custom;
  - há `--ip`;
  - o recurso é preview ou Compose.
- **Healthcheck**:
  - O `HEALTHCHECK` do Dockerfile **tem precedência** sobre o do painel.
  - O check HTTP roda dentro do container e exige `curl` ou `wget` na imagem. Expected code e expected text são ignorados: só vale o exit code.
  - O CMD não aceita `; | & $() > <`; para lógica, use script (`node healthcheck.js`).
  - **Sem healthcheck, "iniciou" já conta como pronto.** Sempre defina um.
- **Stop Grace Period** (Advanced > Operations, `stop_grace_period`): padrão 30 s, faixa de 1 a 3600. Precisa ser maior que o tempo de drenagem: o job mais longo, mais o fechamento do HTTP, mais margem.
- **Porta interna**: a porta do domínio é a do container e não publica no host. Serviço interno = sem domínio e sem Port Mappings, acessado por Network Alias na rede `coolify`. Worker sem HTTP: "Ports Exposes" vazio é válido, com healthcheck CMD.
- **Escala**: réplicas só existem com Swarm, que está **deprecated** (removido na v5; na 4.4 só se ativa para quem já usa). O caminho atual é multi-server com a mesma imagem via registry, sem Compose e sem volume.
- **Ambientes**: Projeto > Ambientes (`staging`, `production`), com variáveis por ambiente. **O isolamento de permissão só existe por time.** Um token de deploy dispara qualquer app do time; para isolar produção de verdade, use outro time ou outra instância.

## 3. Variáveis de ambiente
- Toda variável nova nasce **disponível no build e no runtime**. Segredo de runtime deve ser marcado como "Not available during build".
- No tipo Dockerfile, o Coolify **injeta `ARG <KEY>` depois de cada `FROM`**. Para desligar, use "Build arguments: Managed manually in Dockerfile" (`inject_build_args_to_dockerfile=false`).
- **NODE_ENV=production no build** faz o `npm ci` pular as devDependencies, e o `tsc` falha. Correção: NODE_ENV "Runtime only", ou forçar `ENV NODE_ENV=development` no estágio builder e `production` só no final. O mesmo vale para `NPM_CONFIG_PRODUCTION`. Com Docker Image o problema não existe.
- Segredo de build: use "Docker BuildKit secrets" (`use_build_secrets`), nunca ARG.
- Variáveis compartilhadas: `{{team.X}}`, `{{project.X}}`, `{{environment.X}}`, `{{server.X}}`. Cofres (v4.4): `{{vault.KEY}}` com Doppler, Infisical ou Vault.
- Mudança de runtime pede só Restart; mudança de build pede novo deploy. **O Restart também faz pull de novo**, então numa tag mutável ele pode trocar a imagem.

## 4. API (`https://<coolify>/api/v1`, `Authorization: Bearer <id>|<segredo>`)
**Pré-requisito**: ligar em Settings > Advanced > API access. Restrinja com "Allowed API IPs" quando der. Os runners do GitHub não têm IP fixo.

**Desde a v4.2.0, tudo que muda estado é POST.** `GET /deploy` responde 405, embora a página de webhooks da doc ainda mande usar GET.

**Permissões do token** (presas ao time; expiração de 7 dias a "nunca"):

| Permissão | Para quê |
|---|---|
| `read` | **Obrigatória para acompanhar o deploy**. Só `deploy` recebe 403 em `GET /deployments/{uuid}` |
| `read:sensitive` | Ver logs no JSON e listar registries |
| `deploy` | Disparar, cancelar, rollback, start, stop e restart |
| `write` | PATCH do app (inclusive trocar a tag) |
| `root` | Nunca no CI |

- Só admin ou owner pode usar `deploy`, `write` ou `root`. O papel Member é só leitura.
- Se a senha do dono mudar, os tokens dele são revogados.

**Endpoints:**

| Operação | Chamada | Permissão |
|---|---|---|
| Deploy | `POST /deploy` com `uuid` (aceita lista por vírgula) ou `tag`, e `force` (rebuild sem cache). Parâmetros em query ou JSON | deploy |
| Status | `GET /deployments/{deployment_uuid}` → `status`: `queued`, `in_progress`, `finished`, `failed`, `cancelled-by-user` | read |
| Histórico | `GET /deployments/applications/{uuid}?skip=&take=` → `{count, deployments}` (o OpenAPI documenta errado) | read |
| Cancelar | `POST /deployments/{uuid}/cancel` | deploy |
| Rollback | `POST /applications/{uuid}/rollback` com `{"commit":"<tag>"}`; no Docker Image o valor é a tag | deploy |
| Imagens disponíveis | `GET /applications/{uuid}/rollback-images` | read |
| Alterar app | `PATCH /applications/{uuid}` (ex.: `docker_registry_image_tag`, `is_auto_deploy_enabled`, `stop_grace_period`) | write |
| Envs | `GET`/`POST`/`PATCH /applications/{uuid}/envs`, `PATCH .../envs/bulk` com `{"data":[...]}` | read/write |
| Logs de runtime | `GET /applications/{uuid}/logs` | read:sensitive |
| Registries | `GET`/`POST /servers/{uuid}/registries`, `POST .../{registry}/check` | read:sensitive/write |

- **Resposta do deploy**: `{"deployments":[{"message","resource_uuid","deployment_uuid"}]}`.
  - 404 `No resources found.` para UUID errado.
  - 429 com `Retry-After: 60` se a fila estiver cheia.
  - Rate limit de 200 req/min.
- **UUID do app**: está na URL da UI, na aba Webhooks e em `GET /applications`.
- **Não há "esperar terminar"** nem na API nem na CLI (`coolify deploy ...`). O polling é do pipeline.
- Armadilhas lidas no código, não testadas:
  - Deploy duplicado na fila responde `Deployment already queued for this commit.` com um `deployment_uuid` que **não existe**, e o polling recebe 404. Trate como "já em andamento" e consulte `/deployments/applications/{uuid}`.
  - `PATCH` com `instant_deploy` não devolve `deployment_uuid`. Faça PATCH e depois `POST /deploy`.

## 5. Promoção de versão: duas opções
| | A. Tag fixa por ambiente + retag no CI | B. Tag = SHA via API |
|---|---|---|
| Como | O app aponta para `:production`. O CI roda `docker buildx imagetools create -t img:production img@sha256:...` e depois `POST /deploy` | `PATCH /applications/{uuid}` com `docker_registry_image_tag=<sha>` e depois `POST /deploy` |
| Token | `deploy` + `read` (menor privilégio) | `write`, que altera qualquer recurso do time |
| Rastreio no Coolify | Só vê `:production` | Vê a versão exata |
| Rollback pela UI | Não lista SHAs | Funciona, com tag **hex pura** |

- **Rollback pela UI**: só oferece tags hex de 7 a 128 caracteres ou `pr-N`, entre as imagens **locais** do servidor (por padrão mantém 2, `docker_images_to_keep`). Tags `sha-<hex>` do metadata-action não aparecem.
- O rollback **não altera a tag salva**: o próximo deploy volta para ela. Rollback não desfaz migration.
- **Não confirmado**: se o rollback pela API faz pull do GHCR quando a tag não está no servidor.
- Rollback da opção A: retag do digest anterior para `:production` e `POST /deploy`. O CI precisa guardar o digest de cada release (output do job, release notes).

## 6. Step de deploy com acompanhamento
```yaml
      - name: Deploy no Coolify e acompanhar
        env:
          URL: ${{ vars.COOLIFY_URL }}
          APP: ${{ vars.COOLIFY_APP_UUID }}
          TOKEN: ${{ secrets.COOLIFY_TOKEN }}   # deploy + read
        run: |
          set -euo pipefail
          resp=$(curl -fsS -X POST "$URL/api/v1/deploy" -H "Authorization: Bearer $TOKEN" \
            -H 'Content-Type: application/json' -d "{\"uuid\":\"$APP\",\"force\":false}")
          echo "$resp"
          dep=$(jq -r '.deployments[0].deployment_uuid // empty' <<<"$resp")
          [ -n "$dep" ] || exit 1
          end=$((SECONDS+900))
          while :; do
            code=$(curl -sS -o d.json -w '%{http_code}' -H "Authorization: Bearer $TOKEN" "$URL/api/v1/deployments/$dep")
            [ "$code" = 429 ] && { sleep 60; continue; }
            [ "$code" = 200 ] || { echo "HTTP $code"; cat d.json; exit 1; }
            st=$(jq -r .status d.json); echo "status=$st"
            case "$st" in finished) break;; failed|cancelled-by-user) exit 1;; esac
            [ $SECONDS -lt $end ] || { echo "timeout"; exit 1; }
            sleep 10
          done
```
Em seguida, rode o smoke test (skill `cicd-github-actions` §7).

## 7. Armadilhas e issues abertas (out/2026)
- **#8627**: o rolling update gera 502/503 de 18 a 31 s. Mitigação: no SIGTERM, o `/health` passa a falhar e o app espera alguns segundos antes de fechar o servidor.
- #7942 (Caddy derruba websockets a cada restart), #3520 (scheduled task durante o redeploy), #11063 (Stop às vezes não para), #6579 (deploy preso em `queued`), #11890 (auto-update falha por rate limit do GHCR), #10642 (`$VAR` na tag).
- No rolling update, as duas versões ficam no ar ao mesmo tempo por alguns instantes. Worker de fila: jobs idempotentes e contrato compatível com N-1 e N+1.
- Preview de PR roda código do PR no servidor: nunca com credencial de produção, e só para membros do repo.

## 8. Segurança
- Um token por integração e por ambiente, com expiração e rotação. `deploy`+`read` no CD; `write` só se usar a opção B.
- Painel e API só por HTTPS; restrinja os IPs da API quando possível.
- Auditoria: Team > Audit Log ou `GET /audit-events`.
- Notificações: eventos `deployment_success` e `deployment_failed` por Slack, Discord, Telegram, e-mail ou webhook.
