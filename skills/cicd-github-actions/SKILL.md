---
name: cicd-github-actions
description: "CI/CD com GitHub Actions para Node.js/TypeScript com Docker: workflows CI/release/deploy, reusable workflows, cache, GHCR, release-please, segurança (permissions, pinning por SHA, Dependabot) e environments. Usar ao criar ou revisar .github/workflows, dependabot.yml ou a esteira de release."
---

# CI/CD com GitHub Actions

Levantado em 2026-10-13 a partir da doc oficial (docs.github.com, docs.docker.com) e de `gh api .../releases/latest`. Versões e SHAs mudam: **confira antes de usar** (`gh api repos/<owner>/<action>/releases/latest`, `pinact`) e não copie SHA sem verificar.

## 0. Antes de escrever: o que o plano do GitHub permite
Org no plano **Free** com repos **privados** (confira com `gh api orgs/<org> --jq .plan.name`). Em repo privado:

| Recurso | Free | Team | Enterprise |
|---|---|---|---|
| Environments, secrets/vars de environment, branch/tag policy | não | sim | sim |
| Required reviewers / wait timer em environment | não | **não** (só repo público) | sim |
| Branch protection, rulesets (branch e tag), CODEOWNERS efetivo | não | sim | sim |
| Secrets/variables de organização em repo privado | não | sim | sim |
| Merge queue, artifact attestations (`actions/attest`) | não | não | sim |
| CodeQL, dependency-review, secret scanning | add-on pago | add-on pago | add-on pago |
| Dependabot alerts e security updates | sim | sim | sim |

Consequências: no Free **não há barreira imposta pelo GitHub** entre quem tem escrita e os secrets de deploy. Proponha o Team (US$ 4/usuário/mês) quando o projeto exigir portão de produção; sem ele, documente que o controle é por convenção. Antes de propor environment, ruleset ou CODEOWNERS, confirme o plano.

## 1. Estrutura
- `ci.yml`: roda em `pull_request` e em `push` na `main`. Faz `npm ci`, typecheck, lint (se existir), testes e `docker build` sem push.
- `release.yml`/`cd.yml`: roda em tag `v*` (ou no `release_created` do release-please) e em `workflow_dispatch`. Faz build e push no GHCR, deploy em staging e promoção para produção.
- Encadeie com **`needs`** no mesmo workflow. Evite `workflow_run`: roda no contexto da branch padrão com secrets e é gatilho de baixa confiança. Se usar, filtre `conclusion == 'success' && event == 'push'`.
- Reaproveitamento na org (funciona no Free): coloque os **reusable workflows** (`on: workflow_call`) num repo privado (ex.: `minha-org/ci-workflows`) e marque "Accessible from repositories in the organization". Chame com `uses: org/repo/.github/workflows/x.yml@<SHA>`. O chamado só pode **reduzir** permissions.
- Para sequências de steps dentro de um job, use composite action.
- **Um único check obrigatório**, `ci-ok`, agregando os jobs com `if: always()` e `needs`. Nomes de job com matrix ou path filter mudam e travam PR.
- `timeout-minutes` em **todo** job (o padrão é 360).
- `concurrency`: no CI, `group: ci-${{ github.workflow }}-${{ github.head_ref || github.run_id }}` com `cancel-in-progress: true`. No deploy, `group: deploy-<ambiente>` com `cancel-in-progress: false`, porque **nunca se cancela deploy no meio**.
- Runner: fixe `ubuntu-24.04`. O `ubuntu-latest` migra para 26.04 entre 19/10 e 19/11/2026.
- Path filter em `on.pull_request.paths` deixa o check obrigatório em Pending. Prefira `dorny/paths-filter` dentro do job, junto com o `ci-ok`.

## 2. Versões atuais (todas em runtime Node 24; o Node 20 saiu dos runners)
| Action | Major | SHA conferido em 2026-10-13 |
|---|---|---|
| actions/checkout | v7.0.1 | `3d3c42e5aac5ba805825da76410c181273ba90b1` |
| actions/setup-node | v7.1.0 | `949feb2413d6458794dcd2491c4babbbce0c15c1` |
| docker/setup-buildx-action | v4.4.1 | `f87e5991a6d7451dcb8d9637bfbc97413f497069` |
| docker/login-action | v4.6.0 | `dbcb813823bdd20940b903addbd779551569679f` |
| docker/metadata-action | v6.2.0 | `dc802804100637a589fabce1cb79ff13a1411302` |
| docker/build-push-action | v7.4.0 | `c3c9e263c25d99ce0380d002d59b67737d91b0dc` |
| docker/setup-qemu-action | v4.4.0 | `99012661954931238ded8c8b007157a8430204e1` |
| googleapis/release-please-action | v5.0.0 | `45996ed1f6d02564a971a2fa1b5860e934307cf7` |
| aquasecurity/trivy-action | v0.36.0 | `ed142fd0673e97e23eac54620cfb913e5ce36c25` (foi comprometida em 03/2026: **só por SHA**) |
| actions/create-github-app-token | v3.3.0 | `64ab729a6294000f5aa4a4bc0b73d1f32bc45510` |

Notas: o checkout v7 recusa PR de fork em `pull_request_target`/`workflow_run`. Use `persist-credentials: false` quando o job não precisar fazer push.

## 3. CI Node (modelo)
```yaml
name: ci
on:
  pull_request:
  push: { branches: [main] }
permissions: { contents: read }
concurrency:
  group: ci-${{ github.workflow }}-${{ github.head_ref || github.run_id }}
  cancel-in-progress: true
jobs:
  verify:
    runs-on: ubuntu-24.04
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with: { persist-credentials: false }
      - uses: actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1 # v7.1.0
        with: { node-version: 24, cache: npm }
      - run: npm ci
      - run: npm run typecheck
      - run: npm test
  docker:
    runs-on: ubuntu-24.04
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with: { persist-credentials: false }
      - uses: docker/setup-buildx-action@f87e5991a6d7451dcb8d9637bfbc97413f497069 # v4.4.1
      - uses: docker/build-push-action@c3c9e263c25d99ce0380d002d59b67737d91b0dc # v7.4.0
        with:
          push: false
          cache-from: type=gha,scope=${{ github.event.repository.name }}
          cache-to: type=gha,scope=${{ github.event.repository.name }},mode=max
  ci-ok:
    if: always()
    needs: [verify, docker]
    runs-on: ubuntu-24.04
    steps:
      - run: '[[ "${{ contains(needs.*.result, ''failure'') || contains(needs.*.result, ''cancelled'') }}" == "false" ]]'
```
- Fixe a versão major (`24`). Não use `node-version-file: package.json` com `engines: ">=24"`: a faixa aberta pode resolver para uma major mais nova que a da imagem.
- **Addon nativo** (ex.: isolated-vm) **com imagem Alpine e runner Ubuntu**: os testes no runner rodam em glibc e a imagem em musl. O job `docker` é o que prova que a imagem carrega. Mantenha no Dockerfile um passo que falhe se o addon não carregar.
- Repo sem script de lint: não invente step de lint.

## 4. Cache
- `setup-node` com `cache: npm` guarda o `~/.npm` com chave do lockfile. Em workflow de **release**, avalie `package-manager-cache: false`, porque a v7 documenta risco de envenenamento de cache.
- Buildx `type=gha`: sempre com `scope=<imagem>`, senão imagens se sobrescrevem. `mode=max` exporta os estágios intermediários do multi-stage.
- Limites: 10 GB por repo (passar disso exige plano pago) e entradas sem acesso há 7 dias são removidas. PR só lê o cache da própria branch, da base ou da padrão.
- Alternativa que não disputa os 10 GB: `type=registry,ref=ghcr.io/<org>/<app>:buildcache,mode=max,image-manifest=true,oci-mediatypes=true`.
- `RUN --mount=type=cache` **não** é exportado pelo `type=gha`.

## 5. Imagem no GHCR (build once, deploy many)
```yaml
  image:
    runs-on: ubuntu-24.04
    timeout-minutes: 30
    permissions: { contents: read, packages: write }
    outputs: { digest: ${{ steps.build.outputs.digest }} }
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with: { persist-credentials: false }
      - id: meta
        uses: docker/metadata-action@dc802804100637a589fabce1cb79ff13a1411302 # v6.2.0
        with:
          images: ghcr.io/${{ github.repository }}
          tags: |
            type=semver,pattern={{version}}
            type=sha,format=long
      - uses: docker/login-action@dbcb813823bdd20940b903addbd779551569679f # v4.6.0
        with: { registry: ghcr.io, username: ${{ github.actor }}, password: ${{ secrets.GITHUB_TOKEN }} }
      - uses: docker/setup-buildx-action@f87e5991a6d7451dcb8d9637bfbc97413f497069 # v4.4.1
      - id: build
        uses: docker/build-push-action@c3c9e263c25d99ce0380d002d59b67737d91b0dc # v7.4.0
        with:
          push: true
          platforms: linux/amd64
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          provenance: mode=max
          sbom: true
          cache-from: type=gha,scope=${{ github.event.repository.name }}
          cache-to: type=gha,scope=${{ github.event.repository.name }},mode=max
```
- O nome da imagem no GHCR precisa estar **em minúsculas**. Se o repo tiver maiúsculas, normalize.
- O formato da tag depende da plataforma. `type=sha,format=long` gera `sha-<40 hex>`. O **rollback pela UI do Coolify só lista tags hex puras** (7 a 128 caracteres): para Coolify, gere também `type=sha,format=long,prefix=` (sem o prefixo `sha-`). Detalhes na skill `deploy-coolify`.
- A promoção **não rebuilda**: `docker buildx imagetools create -t <img>:v1.2.3 -t <img>:production <img>@sha256:<digest>`.
- Faça o deploy por tag imutável (semver ou sha) ou por digest. Nunca use `latest` ou `main` como versão de produção.
- Pacote novo nasce privado e ligado ao repo. Para o **servidor puxar**, use um PAT **classic** só com `read:packages` (o GHCR não aceita fine-grained), de preferência de um usuário bot, com expiração.
- O SBOM e a proveniência do BuildKit (dentro da imagem) funcionam no Free. Proveniência `mode=max` grava os build args, então **segredo nunca vai em `build-args`**; use `secrets:` ou secret mount.
- Multi-arch só se algum servidor for ARM (runner `ubuntu-24.04-arm` nativo é mais rápido que QEMU).

## 6. Release
- **release-please** (combina com Conventional Commits): abre um PR de release com CHANGELOG e bump. O merge cria a tag `vX.Y.Z`.
- Armadilha: tag criada com `GITHUB_TOKEN` **não dispara** `on: push: tags`. Duas saídas: rode build e deploy no mesmo workflow com `if: needs.rp.outputs.release_created == 'true'`, ou use um token de GitHub App (`actions/create-github-app-token`).
- Rollback = redeploy do digest/tag anterior pela API da plataforma, sem rebuild. Reverter commit é correção posterior, não rollback.

## 7. Deploy a partir do Actions
- O job de deploy tem `concurrency: deploy-<ambiente>` sem cancelamento, `permissions: contents: read` e secrets só nele (environment, no Team).
- Ele precisa **disparar e acompanhar** até o estado final (polling com timeout) e depois fazer **smoke test** com `curl -fsS --retry 30 --retry-delay 5 --retry-all-errors --max-time 5 <url>/health`.
- O ideal é o `/health` expor a versão ou SHA e o smoke test confirmar que é a nova. Sem isso, o teste não distingue versão nova de antiga.
- A API específica de cada plataforma está nas skills `deploy-coolify` e `deploy-dokploy`. Não há action oficial confiável para nenhuma das duas: use `curl` + `jq` ou a CLI oficial fixada em versão. Uma action de terceiro receberia o token do painel.
- Os runners hospedados não têm IP fixo, então a API do painel precisa estar acessível por HTTPS. Para fechar a rede, use VPN no job (ex.: Tailscale) ou runner self-hosted isolado.
- Notifique falha com um step `if: failure()`.

## 8. Segurança (obrigatório)
- No topo do workflow, `permissions: { contents: read }`. Eleve por job: `packages: write`, `id-token: write` e `security-events: write` só onde for usado.
- **Actions fixadas por SHA completo**, com comentário `# vX.Y.Z`. O Dependabot (`package-ecosystem: github-actions`) atualiza o SHA e o comentário.
- Nunca interpole `${{ github.event.* }}` dentro de `run:`. Passe por `env:` e use `"$VAR"`.
- Evite `pull_request_target`. Para validar PR, use `pull_request`.
- Rode `actionlint` e `zizmor` nos workflows (template injection, permissions, pin, `persist-credentials`).
- Scan de imagem: Trivy (por SHA) com `severity: CRITICAL,HIGH`, `ignore-unfixed: true` e `exit-code: '1'`. Comece informativo (`continue-on-error`) se houver dívida.
- npm: `npm audit --omit=dev --audit-level=high` (informativo enquanto houver dívida) e `npm audit signatures`.
- O `harden-runner` não monitora nada em repo privado sem o plano pago da StepSecurity. Não adicione esperando proteção.
- Secrets: o mínimo, um por ambiente. Nunca embutidos em JSON. Valores derivados (base64) também viram secret.

`dependabot.yml` base:
```yaml
version: 2
updates:
  - package-ecosystem: github-actions
    directory: /
    schedule: { interval: weekly }
    groups: { actions: { patterns: ['*'] } }
  - package-ecosystem: npm
    directory: /
    schedule: { interval: weekly }
    groups: { minor-patch: { update-types: [minor, patch] } }
  - package-ecosystem: docker
    directory: /
    schedule: { interval: weekly }
```

## 9. Custos
- Repo privado no Free tem 2.000 min/mês. O Linux 2-core custa US$ 0,006/min acima disso.
- Para economizar:
  - cancele runs de PR substituídos;
  - use cache do Buildx;
  - só faça push de imagem na `main` ou em tag;
  - ponha `timeout-minutes` em todo job.
- Configure um budget.
- Runner self-hosted: em repo privado, qualquer pessoa com escrita executa código nele. Só use runner efêmero e isolado da rede de produção.

## 10. Checklist de revisão de workflow
- [ ] `permissions` mínimas no topo e por job; actions por SHA.
- [ ] `timeout-minutes` em todos os jobs; `concurrency` correto (CI cancela, deploy não).
- [ ] Um único check obrigatório (`ci-ok`).
- [ ] Imagem gerada uma vez, deploy por tag imutável ou digest; nada de segredo em build-args.
- [ ] Deploy acompanha o estado final e faz smoke test; falha notifica.
- [ ] Recursos de plano (environment, ruleset, CODEOWNERS) usados só se o plano da org tiver.
- [ ] `actionlint`/`zizmor` sem achados.
