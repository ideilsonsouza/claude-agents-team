---
name: deploy-cloudflare
description: "Publicar frontend (SPA Vite ou site Astro) na Cloudflare como Worker com Static Assets (`wrangler deploy`), não Pages: wrangler.jsonc, headers, CI no GitHub Actions, domínio, rollback e migração de Pages. Usar ao ouvir \"Cloudflare Pages\", \"wrangler\", \"workers.dev\", \"publicar frontend\" ou \"SPA\"."
---

# Frontend na Cloudflare: Worker com Static Assets

Levantado em 2026-11-10 na doc oficial (developers.cloudflare.com) e no molde da casa (apps já em produção). Wrangler estável conferido via `npm view wrangler version`: 4.160.0. Fontes e datas: `fontes.md`. Workflow completo: `workflow-modelo.md`.

## 0. Regra de decisão (leia primeiro)
- **Padrão: Worker com Static Assets**, publicado com `wrangler deploy`. O dono rejeitou o Pages: "não quero mais este erro quando falarmos de publicar páginas na Cloudflare".
- **Nunca** escreva `wrangler pages deploy`, `pages_build_output_dir`, `wrangler pages project create` nem `cloudflare/pages-action` em projeto novo. Pages só entra se o dono pedir **explicitamente** ("use o Pages", "mantenha no Pages"). Se vier só no briefing do orchestrator, trate como dúvida e pergunte antes.
- "Hospedar no Cloudflare Pages", "subir na Cloudflare", "publicar o site na Cloudflare" ditos informalmente = Workers Static Assets. Se houver dúvida real, pergunte ao orchestrator no relatório; não escolha Pages por conta própria.
- Por que: a Cloudflare diz "If you are starting a new project, use Workers instead of Pages" e "Pages continues to work, but new features and optimizations are focused on Workers" (Workers Best Practices, 12/10/2026). Pages não foi descontinuado, mas o investimento está no Workers (blog, 08/04/2025).
- Requisições a assets estáticos são gratuitas e ilimitadas; só requisição que invoca o Worker é cobrada (Billing, consultado em 2026-11-10).

## 1. Escolha da forma
| Caso | Config |
|---|---|
| Site estático (Astro `output: static`, HTML puro) | Só `assets`, **sem `main`**. `not_found_handling: "404-page"` |
| SPA (Vue/React/Vite com router no navegador) | Só `assets`, `not_found_handling: "single-page-application"` |
| SPA ou site que precisa responder 404 real em caminhos sensíveis (`/.env`, `/.git/*`, `*.map`) | Worker mínimo (`main`) + `run_worker_first` como **lista** de padrões |
| Painel com login, proxy `/api/*`, cron, KV | Worker completo (`main`) e `run_worker_first: true` se **todo** asset exige sessão |

Regras:
- Sem `main` não há custo de Worker e não há código para manter. Só ponha `main` se houver motivo de segurança ou de lógica.
- `run_worker_first: true` manda **toda** requisição ao Worker (cobrada; no Free, estourado o limite, volta 429 em vez de servir asset). Prefira a lista: só os caminhos listados invocam o Worker, o resto sai direto dos assets (Billing).
- `binding: "ASSETS"` só faz sentido com `main` e só se o código chamar `env.ASSETS.fetch()`. Sem Worker, remova (Migration guide, passo 4).
- `name` precisa ser o do Worker que vai receber o deploy (`meuapp-web`): `a-z`, `0-9` e `-`, sem `_`, até 63 caracteres se usar workers.dev (Wrangler config).
- `compatibility_date`: a data de hoje em projeto novo; atualize de tempos em tempos (Best Practices).
- `.assetsignore` na pasta de assets exclui arquivos do upload (sintaxe `.gitignore`). Pages ignorava `node_modules`/`.git` sozinho; o Workers não.

## 2. `wrangler.jsonc` modelos
SPA ou site estático, só assets (sem Worker):
```jsonc
{
  "name": "meuapp-web",
  "compatibility_date": "2026-11-10", // hoje
  "assets": {
    "directory": "./dist",
    // SPA: rota sem arquivo devolve /index.html com 200 (o router resolve no navegador).
    // Site estático: "404-page" (serve o 404.html mais próximo, com status 404).
    "not_found_handling": "single-page-application"
  },
  "routes": [{ "pattern": "meuapp.example.com", "custom_domain": true }],
  "workers_dev": false,
  "preview_urls": false
}
```
SPA com Worker mínimo (404 real em caminhos ocultos e source maps):
```jsonc
{
  "name": "meuapp-app",
  "main": "./edge/worker.ts",
  "compatibility_date": "2026-11-10",
  "assets": {
    "directory": "./dist",
    "not_found_handling": "single-page-application",
    // Só estes caminhos invocam o Worker. `!` devolve o caminho aos assets (negativo vence o positivo; ordem não importa; máx. 100).
    // `*` cruza barras: "/.*" pega /.env, /.git/config, /.well-known/...
    "run_worker_first": ["/.*", "!/.well-known/security.txt", "/*.map"]
  },
  "routes": [{ "pattern": "app.example.com", "custom_domain": true }],
  "workers_dev": false,
  "preview_urls": false
}
```
```ts
// edge/worker.ts: só o default é exportado (export nomeado fora de handler é recusado).
export default {
  fetch(): Response {
    return new Response('Não encontrado.\n', {
      status: 404,
      headers: {
        'content-type': 'text/plain; charset=utf-8',
        'cache-control': 'no-store',
        'x-content-type-options': 'nosniff',
        // Resposta do Worker NÃO recebe o _headers: se precisar de HSTS etc., ponha aqui.
      },
    })
  },
}
```
- Padrões de `run_worker_first` começam com `/` ou `!/`. `run_worker_first` em lista exige Wrangler 4.20.0 ou mais novo.
- Com SPA e **sem** `run_worker_first`, navegação (`Sec-Fetch-Mode: navigate`) nunca invoca o Worker (compat date 2025-04-01 ou mais nova). Com `run_worker_first` a detecção automática é desligada e valem só os padrões (SPA doc).
- Navegar direto para uma rota de API devolve o HTML da SPA; API fica em outro host ou em Worker próprio.

## 3. Headers de segurança
- `_headers` vai em **`public/`** (ou na pasta de assets). O build o copia para `dist/`; o arquivo não é servido, o Workers o interpreta (Headers doc).
- Modelo (sintaxe: caminho na linha, headers indentados; até 100 regras, 2.000 caracteres por linha):
```
/*
  Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self' https://api.example.com; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'
  X-Content-Type-Options: nosniff
  X-Frame-Options: DENY
  Referrer-Policy: no-referrer
  Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=(), usb=()
  Strict-Transport-Security: max-age=31536000; includeSubDomains
  Cross-Origin-Opener-Policy: same-origin

/index.html
  Cache-Control: no-cache

/assets/*
  Cache-Control: public, max-age=31536000, immutable
```
- Onde vale: **só em resposta de asset**. Resposta gerada por Worker (`run_worker_first`, SSR, 404 do Worker mínimo) **não** recebe `_headers`; o header vai no código do Worker (Headers doc).
- **Fallback de SPA:** a doc não diz se o `_headers` se aplica. Foi **observado** (2026-11-10, no molde da casa) que `/*` vale na resposta 200 do fallback. Não confie: o passo de verificação (§5) testa uma rota inexistente.
- Redirect (`_redirects`) é aplicado antes do header; `_redirects` também só vale para asset (até 2.000 estáticos + 100 dinâmicos; `200` só com caminho relativo).
- Preço de erro: header múltiplo na mesma regra se combina com vírgula; para remover um default, `! Nome-Do-Header`.
- CSP com valor dependente de ambiente (URL da API): troque um placeholder no build (plugin do Vite) em vez de editar à mão; teste a CSP gerada em teste unitário.
- Teste unitário que lê `public/_headers` e exige CSP, HSTS e `nosniff` impede regressão silenciosa.

## 4. CI e deploy
**CI (sem credencial):** `npm ci --ignore-scripts`, typecheck/lint/test, `npm run build`, depois `npx --no-install wrangler deploy --dry-run`.
- O `--dry-run` compila o Worker e valida o config e os assets sem publicar ("compiles without actually deploying"). A doc não diz se exige login; no molde da casa roda no CI **sem** secrets.
- `wrangler` entra em `devDependencies` com versão exata no lockfile; use `npx --no-install` para nunca baixar versão solta. Dependabot cuida da atualização.
- Build do CI usa URLs placeholder; o build publicado usa as variáveis reais do deploy.

**Deploy (GitHub Actions)** (YAML completo em `workflow-modelo.md`):
- Gatilho `workflow_dispatch`, sempre manual. Job `prepare` recusa: ref que não seja `main`, SHA fora da história da `main`, commit sem o check `ci-ok` verde. O portão é de convenção no plano Free; veja `cicd-github-actions` §0.
- Job de deploy: `permissions: contents: read`, `timeout-minutes`, `concurrency: deploy-<app>` com `cancel-in-progress: false`, checkout com `ref: <sha do prepare>` e `persist-credentials: false`.
- Secrets `CLOUDFLARE_API_TOKEN` e `CLOUDFLARE_ACCOUNT_ID` (no Free: secrets do repositório; com environment, só se o plano permitir). Variáveis do build (`VITE_*`, `PUBLIC_*`) em `vars`, nunca segredo: tudo que vai ao bundle é público.
- Actions pinadas por SHA (conferido em 2026-11-10: `actions/checkout` v7.0.1 `3d3c42e5aac5ba805825da76410c181273ba90b1`, `actions/setup-node` v7.1.0 `949feb2413d6458794dcd2491c4babbbce0c15c1`). Prefira `npx --no-install wrangler deploy` à `cloudflare/wrangler-action`: uma action de terceiro receberia o token. Se usar a action, fixe por SHA, não por `@v4`.
- Captura da URL: `WRANGLER_OUTPUT_FILE_PATH=$RUNNER_TEMP/wrangler-out.ndjson` (ND-JSON, uma linha por evento). A linha `type: "deploy"` traz nome do Worker, ID da versão e URLs em `targets`. O formato exato de `targets` não foi verificado: confira no primeiro run.
- Token com o menor privilégio (§6).

## 5. Verificação pós-deploy (obrigatória)
Depois do `wrangler deploy`, com `curl` na URL **pública** (domínio próprio):
1. **Status:** `curl -fsS -o /dev/null -w '%{http_code}' <url>/` = 200.
2. **Bundle novo:** o `dist/index.html` local referencia `assets/index-<hash>.js`; o HTML servido precisa conter o mesmo nome (`curl -fsS <url>/ | grep -q "$ENTRY"`). Com retry (`--retry 10 --retry-delay 3 --retry-all-errors`).
3. **Headers:** `curl -sI <url>/` contém `content-security-policy`, `strict-transport-security` e `x-content-type-options: nosniff`.
4. **Fallback de SPA:** `curl -sI <url>/rota-inexistente` devolve 200 **com os mesmos headers** (se a CSP faltar no fallback, o `_headers` não está valendo ali).
5. **Caminho oculto** (se houver Worker mínimo): `/.env` devolve 404 `text/plain`.
Falhou: o job falha e o deploy fica sinalizado; avalie rollback (§7).

## 6. Token, domínio e URLs
**Token da API** (conta própria da Cloudflare, token de conta, só o necessário; fonte: Workers roles and permissions, 15/09/2026):
- Atualizar Worker existente: `Editor` do Worker (o template "Edit Cloudflare Workers" cobre o CI).
- **Criar** Worker novo: exige `Admin` do produto Workers. Por isso o primeiro deploy costuma falhar com token de Editor; o dono cria o Worker (ou dá Admin só para o primeiro deploy).
- Criar/alterar rota ou custom domain no deploy: além do Editor, `Zone > Workers Routes > Write` na zona afetada. Depois que o domínio existe, deploy de versão nova só precisa de Editor.
- Escopo: só a conta e só a zona do projeto. Token só em secret do CI; nunca em arquivo.

**Domínio:**
- Custom domain (`routes` com `custom_domain: true`) exige que a **zona esteja na Cloudflare** (nameservers dela); o Workers não atende domínio externo, ao contrário do Pages.
- O `wrangler deploy` cria o registro DNS e o certificado do hostname sozinho. **Hostname com CNAME existente bloqueia a criação**: o dono apaga o CNAME antes. A doc não diz o que ocorre com A/AAAA existentes: **não verificado**; peça ao dono para conferir o DNS do hostname antes do primeiro deploy.
- Apex e subdomínio funcionam; wildcard não (Custom Domains são por hostname exato). `routes` sem `custom_domain` casa caminhos (`example.com/api/*`) e exige registro DNS proxied.
- Deixe o domínio ser ligado pelo dono quando o hostname já estiver em uso: essa troca derruba/muda produção.

**workers.dev e previews:**
- `workers_dev` vale `true` se o config não tem `routes` e `false` se tem. Seja explícito.
- `preview_urls`: se omitido, o Wrangler não altera o que já existe; Version URLs são **públicas**. Para app com login ou atrás de Access, ponha `workers_dev: false` e `preview_urls: false`, senão sobra uma URL fora da proteção.
- Site público sem segredo pode manter `workers_dev: true` como URL de apoio.

## 7. Rollback
- `npx wrangler rollback [<VERSION_ID>] --message "motivo"` (sem ID, volta à versão anterior à última). Cria um novo deploy imediato em **todas** as rotas. Painel: Workers & Pages, Worker, Deployments, Rollback. Só as 100 últimas versões.
- Rollback de frontend não mexe em API, banco, KV, secrets. Se o contrato da API mudou, volte a API antes (ou depois) na ordem certa: skill `cd-practices` §4.
- Rollback manual só com ok do dono. Alternativa sem credencial local: workflow `workflow_dispatch` que roda `wrangler rollback`, com o token do CI.
- Gradual deploy (`wrangler versions upload` + `versions deploy`) existe, mas a doc de gradual não trata assets: sem validação, **não use** em frontend.

## 8. Migração Pages para Workers
1. Congele: o dono confirma o domínio, o nome do projeto Pages e o que está em produção.
2. Crie `wrangler.jsonc` (modelos §2): troque `pages_build_output_dir` por `assets.directory`; defina `not_found_handling` explícito (o Pages inferia por `index.html`/`404.html`); `.assetsignore` se preciso.
3. `_headers` e `_redirects` continuam em `public/`. `_routes.json` some: o Worker serve asset primeiro, `run_worker_first` substitui.
4. Funções: `functions/` ou `_worker.js` viram `main` (ver o guia). Sem funções, só assets.
5. Substitua `wrangler pages deploy` por `wrangler deploy` no workflow; secrets e vars do build migram para o repositório do CI.
6. Nome do Worker: **pode ser igual** ao do projeto Pages (a doc permite). Pages e Workers são produtos separados; o conflito real é o **hostname**.
7. Primeiro deploy sem `routes` (só `workers.dev`), valide com `curl` e o checklist §5. Depois o dono tira o domínio do projeto Pages (e apaga o CNAME dele) e o `wrangler deploy` com `routes` liga o domínio ao Worker.
8. Só **depois** de Worker no ar, domínio movido e verificado, o **dono** apaga o projeto Pages (painel ou `wrangler pages project delete`). Agente não apaga projeto Pages. Desligue o auto-deploy do Pages antes.
9. Previews: `preview_urls: true` + `previews` (se o time usa). Variáveis de build do Workers Builds são à parte.

## 9. Armadilhas conhecidas
- **Pages por engano** (`wrangler pages deploy`): é o erro que originou esta skill. Corrija o workflow, não o dono.
- `run_worker_first: true` sem necessidade: todo asset vira requisição de Worker e é cobrado (Billing).
- `_headers` não vale em resposta do Worker nem em redirect; CSP/HSTS faltam no 404 do Worker mínimo (observado 2026-11-10).
- `not_found_handling` ausente: default `"none"` e 404 em rota da SPA ao recarregar.
- `Range` em asset volta 200 com o arquivo inteiro, não 206 (Billing and limitations): vídeo/áudio com seek exige Worker.
- Limites: 20.000 arquivos (Free) ou 100.000 (Paid) por versão e 25 MiB por arquivo; Wrangler 4.34.0+ para os 100.000 (Limits, 29/10/2026).
- `assets.bucket is a required field`: Wrangler velho (< 3.78.10).
- Cron, KV e secrets: `wrangler deploy` sobrescreve `vars` do painel (use `--keep-vars` se o dono edita no painel); secrets nunca são apagados.
- Source maps e variáveis `VITE_*` vão ao bundle: nada de segredo no frontend.

## 10. Checklist final
- [ ] `wrangler.jsonc` com `name`, `compatibility_date` de hoje, `assets.directory` e `not_found_handling` explícito; sem `main` salvo motivo.
- [ ] Nenhum `pages deploy`/`pages_build_output_dir` no repo e no workflow.
- [ ] `_headers` em `public/` com CSP e HSTS; teste cobre o arquivo.
- [ ] `workers_dev` e `preview_urls` explícitos; custom domain definido e acordado com o dono.
- [ ] CI com `npm ci --ignore-scripts`, build e `wrangler deploy --dry-run` sem credencial.
- [ ] Deploy manual com portão (main + `ci-ok`), `concurrency` sem cancelar, secrets do CI, actions por SHA.
- [ ] Verificação pós-deploy (§5) no workflow; rollback descrito no README do deploy.
- [ ] Doc do painel para o dono: criar o Worker (ou token Admin no 1º deploy), DNS do hostname, secrets do repositório.

## 11. Proibições
- **Agente não roda `wrangler` com credencial local** (`wrangler login`, token no shell) **nem consulta a API da Cloudflare** fora da esteira. `wrangler deploy --dry-run` e `wrangler types` locais, sem credencial, são permitidos.
- Deploy em produção, rollback, mudança de DNS/domínio e apagar projeto Pages ou Worker só com o ok do dono (ou do `deploy` com autorização).
- Nunca token ou ID de conta em arquivo, log, `wrangler.jsonc`, PR ou relatório.
- A skill descreve o painel; quem muda o painel é o dono.
