# Fontes consultadas (2026-11-10)

Documentação oficial da Cloudflare (data = "última atualização" mostrada na página, quando houver):

| Afirmação | Fonte |
|---|---|
| Workers recomendado para projeto novo; Pages continua funcionando; `compatibility_date` = hoje (12/10/2026) | https://developers.cloudflare.com/workers/best-practices/workers-best-practices/ |
| Pages segue com suporte, investimento no Workers (08/04/2025) | https://blog.cloudflare.com/full-stack-development-on-cloudflare-workers |
| Guia de migração Pages para Workers: passos, `.assetsignore`, previews, domínios fora da Cloudflare não suportados, nome pode ser igual, apagar o Pages depois (12/10/2026) | https://developers.cloudflare.com/workers/static-assets/migration-guides/migrate-from-pages/ |
| `assets`: `directory`, `binding`, `run_worker_first` (booleano ou lista com `!`, máx. 100), `not_found_handling` (`single-page-application`, `404-page`, `none`), `html_handling`; `workers_dev`, `preview_urls`, `compatibility_date`, `routes`, regras de `name` | https://developers.cloudflare.com/workers/wrangler/configuration/ e https://developers.cloudflare.com/workers/static-assets/binding/ |
| Roteamento Worker x assets (assets primeiro; `run_worker_first`) | https://developers.cloudflare.com/workers/static-assets/routing/worker-script/ |
| SPA: fallback 200, navegação, interação com `run_worker_first` (Wrangler 4.20.0+) | https://developers.cloudflare.com/workers/static-assets/routing/single-page-application/ |
| `_headers`: só em asset, não em resposta de Worker; 100 regras; 2.000 caracteres por linha; redirect antes de header | https://developers.cloudflare.com/workers/static-assets/headers/ |
| `_redirects`: só em asset; 2.000 estáticos + 100 dinâmicos; proxy 200 relativo | https://developers.cloudflare.com/workers/static-assets/redirects/ |
| Cobrança: assets gratuitos e ilimitados; Worker cobrado; `run_worker_first` e 429 no Free; `Range` sem 206 | https://developers.cloudflare.com/workers/static-assets/billing-and-limitations/ |
| Limites: 20.000/100.000 arquivos, 25 MiB por arquivo, Worker 64 MiB (29/10/2026) | https://developers.cloudflare.com/workers/platform/limits/ |
| Custom Domains x Routes; CNAME existente bloqueia; certificado automático; sem wildcard | https://developers.cloudflare.com/workers/configuration/routing/custom-domains/ |
| Version URLs, `preview_urls`, `workers_dev`; URLs públicas; Access | https://developers.cloudflare.com/workers/configuration/previews/ |
| Permissões: Editor (existente), Admin (criar), Workers Routes Write por zona (15/09/2026) | https://developers.cloudflare.com/workers/authorization/workers/ |
| Token "Edit Cloudflare Workers", secrets do CI, `wrangler-action@v4` | https://developers.cloudflare.com/workers/ci-cd/external-cicd/github-actions/ |
| `wrangler deploy` (`--dry-run`, `--message`, `--keep-vars`, `--var`), `rollback`, `versions`, `deployments list` | https://developers.cloudflare.com/workers/wrangler/commands/workers/ |
| `WRANGLER_OUTPUT_FILE_PATH` (ND-JSON, tipo `deploy` com `targets`) | https://developers.cloudflare.com/workers/wrangler/system-environment-variables/ |
| Rollback: 100 últimas versões, novo deploy imediato, bloqueios (Durable Objects, KV/R2 removido) | https://developers.cloudflare.com/workers/configuration/versions-and-deployments/rollbacks/ |
| Gradual deployments (sem menção a assets) | https://developers.cloudflare.com/workers/configuration/versions-and-deployments/gradual-deployments/ |

Outras fontes:
- Molde da casa (apps de frontend já em produção): `wrangler.jsonc`, Worker mínimo, `_headers`, trechos do CI e do deploy; observação por `curl` em 2026-11-10 de que o `_headers` `/*` vale no fallback de SPA e que o 404 do Worker não leva CSP/HSTS.
- `gh api` em 2026-11-10: `actions/checkout` v7.0.1 e `actions/setup-node` v7.1.0 (SHAs no SKILL.md); `npm view wrangler version` = 4.160.0.

Não verificado na doc: se `wrangler deploy --dry-run` exige credencial (no molde roda sem); formato exato de `targets`; efeito de registros A/AAAA existentes sobre custom domain; se `_headers` vale no fallback de SPA (só observado); gradual deployment com assets.
