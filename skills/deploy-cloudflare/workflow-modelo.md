# Workflow de deploy modelo (Worker com Static Assets)

Molde genérico. Ajuste `app`, caminhos e variáveis. Confira as versões e os SHAs das actions antes de copiar (`gh api repos/actions/checkout/releases/latest`, `gh api repos/actions/checkout/git/ref/tags/<tag>`). Conferidos em 2026-11-10: `actions/checkout` v7.0.1 e `actions/setup-node` v7.1.0.

```yaml
name: Deploy do web
on:
  workflow_dispatch:
    inputs:
      sha:
        description: 'Commit (40 caracteres, na história da main). Vazio = HEAD da main'
        type: string
        default: ''
permissions:
  contents: read

jobs:
  prepare:
    runs-on: ubuntu-24.04
    timeout-minutes: 5
    permissions: { contents: read, checks: read }
    outputs:
      sha: ${{ steps.pre.outputs.sha }}
    steps:
      - id: pre
        env:
          GH_TOKEN: ${{ github.token }}
          REPO: ${{ github.repository }}
          REF: ${{ github.ref }}
          INPUT_SHA: ${{ inputs.sha }}
        run: |
          set -euo pipefail
          [ "$REF" = refs/heads/main ] || { echo "::error::só a main publica"; exit 1; }
          sha="${INPUT_SHA:-$(gh api "repos/$REPO/commits/main" --jq .sha)}"
          [[ "$sha" =~ ^[0-9a-f]{40}$ ]] || { echo "::error::sha inválido"; exit 1; }
          # o commit precisa estar na história da main
          st=$(gh api "repos/$REPO/compare/$sha...main" --jq .status)
          [ "$st" = identical ] || [ "$st" = ahead ] || { echo "::error::sha fora da main"; exit 1; }
          # CI verde: check agregado `ci-ok`
          ok=$(gh api "repos/$REPO/commits/$sha/check-runs?check_name=ci-ok" --jq '[.check_runs[] | select(.conclusion=="success")] | length')
          [ "$ok" -ge 1 ] || { echo "::error::commit sem ci-ok verde"; exit 1; }
          echo "sha=$sha" >> "$GITHUB_OUTPUT"

  deploy-web:
    needs: prepare
    runs-on: ubuntu-24.04
    timeout-minutes: 15
    concurrency:
      group: deploy-web
      cancel-in-progress: false
    defaults:
      run:
        working-directory: apps/web
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          ref: ${{ needs.prepare.outputs.sha }}
          persist-credentials: false
      - uses: actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1 # v7.1.0
        with:
          node-version: 24
          cache: npm
          cache-dependency-path: apps/web/package-lock.json
          package-manager-cache: false # job com secret: sem cache de npm
      - run: npm ci --ignore-scripts
      - run: npm run build
        env:
          VITE_API_URL: ${{ vars.VITE_API_URL }} # público: vai ao bundle
      - name: Publica o Worker
        run: npx --no-install wrangler deploy --message "deploy ${{ needs.prepare.outputs.sha }}"
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
          WRANGLER_OUTPUT_FILE_PATH: ${{ runner.temp }}/wrangler-out.ndjson
          WRANGLER_SEND_METRICS: 'false'
      - name: URLs publicadas
        run: |
          jq -r 'select(.type=="deploy") | .targets[]?' "$RUNNER_TEMP/wrangler-out.ndjson" | tee -a "$GITHUB_STEP_SUMMARY"
      - name: Verifica o deploy
        env:
          PUBLIC_URL: ${{ vars.WEB_PUBLIC_URL }} # ex.: https://meuapp.example.com
        run: |
          set -euo pipefail
          : "${PUBLIC_URL:?configure WEB_PUBLIC_URL}"
          entry=$(grep -oE 'assets/index-[A-Za-z0-9_-]+\.js' dist/index.html | head -1)
          [ -n "$entry" ] || { echo "::error::dist/index.html sem bundle de entrada"; exit 1; }
          curl_r=(--fail --silent --show-error --retry 10 --retry-delay 3 --retry-all-errors --max-time 10)
          # bundle novo no ar
          curl "${curl_r[@]}" "$PUBLIC_URL/" | grep -q "$entry" || { echo "::error::HTML servido não referencia $entry"; exit 1; }
          # headers na raiz e no fallback de SPA
          for path in / /rota-inexistente-verificacao; do
            h=$(curl "${curl_r[@]}" -I "$PUBLIC_URL$path" | tr -d '\r' | tr 'A-Z' 'a-z')
            for want in content-security-policy strict-transport-security 'x-content-type-options: nosniff'; do
              grep -q "^$want" <<<"$h" || { echo "::error::$path sem $want"; exit 1; }
            done
          done
      - name: Falha do deploy
        if: failure()
        run: echo "::error::deploy-web falhou. Avalie rollback (wrangler rollback) com o ok do dono."
```

Notas:
- `package-manager-cache: false` segue a recomendação da skill `cicd-github-actions` §4 para job com secret.
- `curl --fail` com `-I` usa HEAD; se o fallback de SPA falhar com 404 a verificação quebra (desejado quando `not_found_handling` é `single-page-application`; em site estático com `404-page`, troque a rota inexistente por esperado 404 e tire `--fail` desse passo).
- `targets` em `deploy`: formato exato não verificado; ajuste o `jq` no primeiro run.
- O CI roda `npx --no-install wrangler deploy --dry-run` sem credencial (ver SKILL.md §4).
