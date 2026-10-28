---
name: security-supply-chain
description: Cadeia de suprimentos (OWASP A03:2025) para npm/pnpm, Go e PyPI — lições dos worms de npm 2025–2026, install scripts e cooldown, lockfile reprodutível, trusted publishing por OIDC, SBOM, proveniência e cosign, hardening de GitHub Actions, scanners de CI e resposta a pacote comprometido. Usar ao adicionar ou atualizar dependência, publicar pacote/imagem ou revisar workflow de CI.
---

# Cadeia de suprimentos

Fontes verificadas em **23/10/2026**: OWASP Top 10:2025 A03, OWASP NPM Security Cheat Sheet,
nodejs.org, docs.npmjs.com, pnpm.io, go.dev, PEP 740/751, docs.astral.sh/uv, e pesquisa de
incidente (CISA, JFrog, Unit 42, Akamai, StepSecurity). Cronologia e números:
`../security-hardening/references/panorama-2026.md` §4.
Pipeline e deploy: `cicd-github-actions`, `cd-practices`. Pacote do appliance:
`appliance-offline-package`.

## 1. O modelo de ameaça real (leia antes de escolher ferramenta)
O alvo **não é o servidor de produção**: é a máquina do dev e o runner de CI, onde moram token do
npm/PyPI, PAT do GitHub, chave de cloud e credencial de banco.

Quatro fatos de 2025–2026 que mudam a defesa:
1. **Worm auto-replicante funciona.** Shai-Hulud (set/2025, 500+ pacotes) roubava credencial e se
   publicava em todo pacote que o mantenedor podia escrever.
2. **Credencial roubada não é mais necessária.** O Mini Shai-Hulud (mai/2026) publicou via
   **envenenamento de cache de CI + endpoint OIDC** do npm.
3. **Proveniência válida não é atestado de segurança.** Aquele worm gerou pacote com
   **SLSA Build L3 válido**. Proveniência responde "de onde veio", não "é seguro".
4. **`npm audit` não detecta pacote malicioso novo** — não existe advisory ainda. O que pega é
   **cooldown + install script desligado + revisão de diff**.

Conclusão prática: **atrasar a adoção de versão nova é o controle mais barato e mais eficaz** que
existe hoje. O malware costuma ser descoberto e despublicado em horas.

## 2. Política de dependência (vale para as três linguagens)
- **Dependência nova precisa de justificativa** no PR: o que resolve, por que não é stdlib, quantas
  transitivas traz, quando foi o último release, quantos mantenedores.
- Prefira **menos dependência**. Pacote de uma função (`is-odd`, `left-pad`) é dívida de segurança.
- **Nunca** instale de git/tarball/URL em produção. Se precisar de fork, publique no registry
  privado da org ou vendore com commit fixado.
- **Cooldown ≥ 1 dia** (ideal 7 dias em projeto exposto), com exceção explícita para correção de
  segurança.
- **Lockfile commitado e instalação reprodutível** em CI e imagem: `npm ci`, `pnpm install
  --frozen-lockfile`, `uv sync --frozen`, `go mod download` com `-mod=readonly`.
- Pacote abandonado (sem release há >18 meses e com issue de segurança aberta) é item de backlog,
  não "funciona, deixa". A03 cobra componente sem manutenção.
- Verifique **licença** junto (`grant`, `license-checker`): risco jurídico mora no mesmo lugar.

## 3. Node — npm e pnpm
**npm 12** (jul/2026) já traz os defaults certos; a dor é migrar:
```bash
npm approve-scripts --allow-scripts-pending   # revisa e grava a allowlist no package.json
```
- Install script de dependência **não roda** por padrão (inclui build implícito do node-gyp).
  Allowlist no `package.json`, commitada e revisada no PR.
- Dependência de git e tarball https remoto bloqueadas (`--allow-git`, `--allow-remote`).
- `min-release-age` existe desde o npm 11.10.0, **mas vem desligado** — ligue:
```ini
# .npmrc do projeto (commitado)
min-release-age=1440
audit-level=high
ignore-scripts=true          # redundante no 12, protege quem ainda roda 11
```
- Em npm ≤ 11: `npm config set ignore-scripts true` + `@lavamoat/allow-scripts` para a allowlist.
  Armadilha: dependência de git pode trazer `.npmrc` próprio reativando script.

**pnpm** (v12 atual, defaults já bons):
```yaml
# pnpm-workspace.yaml  — config do pnpm NÃO vale mais no .npmrc
minimumReleaseAge: 10080          # 7 dias; default do pnpm é 1440 (1 dia)
minimumReleaseAgeStrict: true     # no pnpm 12 liga sozinho quando o valor é explícito
blockExoticSubdeps: true          # barra transitiva de git/tarball
trustPolicy: no-downgrade         # barra pacote que perdeu nível de confiança entre releases
allowBuilds:                      # substitui onlyBuiltDependencies (removido no pnpm 11)
  esbuild: true
  sharp: true
```
Nunca `dangerouslyAllowAllBuilds`. `verifyDepsBeforeRun: install` (default) quebra ambiente
offline/VPN — se for o seu caso, mude consciente, não por tentativa.

**Publicação**: trusted publishing por OIDC (npm ≥ 11.5.1, Node ≥ 22.14, `id-token: write`).
Remova token de longa vida do CI e do `~/.npmrc`. Publique com `--provenance`.

## 4. Go — o ecossistema mais protegido, onde ainda dá errado
Default já forte: module proxy + **checksum database** (`sum.golang.org`) tornam troca silenciosa de
conteúdo detectável, e **não existe install script**.
```bash
go mod verify                      # confere o que está no cache contra o go.sum
go mod tidy -diff                  # falha se go.mod/go.sum estão fora de sincronia (CI)
GOFLAGS=-mod=readonly go build ./...
govulncheck ./...                  # alcance real por caminho de chamada
```
- **`GOPRIVATE`/`GONOSUMDB`/`GONOSUMCHECK` desligam a verificação** para os padrões listados.
  Liste o mínimo (`GOPRIVATE=github.com/minha-org/*`), nunca `*`.
- `replace` apontando para fork ou caminho local **não passa pelo sumdb** — revise todo `replace`
  no PR; nenhum `replace` para caminho local deve chegar na `main`.
- `GOTOOLCHAIN` baixa toolchain automaticamente: fixe (`toolchain go1.27.2`) e não deixe o CI
  resolver sozinho.
- Ferramenta como dependência (`go get -tool`) fixa versão no `go.mod` — faça isso com govulncheck,
  goose, sqlc e golangci-lint.
- Build: `-trimpath`, `-buildvcs=true`, `CGO_ENABLED=0` quando possível (menos superfície e imagem
  `scratch`/distroless).

## 5. Python — o elo mais frágil
Diferente do npm, **não existe `--ignore-scripts`**: instalar sdist executa `setup.py`.
```bash
uv sync --frozen                                   # instala exatamente o uv.lock
uv export --format requirements-txt --no-emit-project > requirements.lock  # com hashes
pip install --require-hashes --no-deps -r requirements.lock
pip-audit -r requirements.lock                     # ou: pip-audit (lê pylock.toml/pyproject)
osv-scanner scan source -r .
```
- **Só wheel** onde der: `--only-binary :all:` evita executar build de sdist.
  Quando precisar de sdist, saiba qual pacote e por quê.
- **`--require-hashes` exige todas as versões pinadas com `==`** e o grafo completo — lock
  incompleto falha (é o comportamento desejado).
- **PEP 740** (atestação) diz **qual workflow publicou**, não que o conteúdo é seguro; e
  **nem pip nem uv verificam identidade de atestação na instalação**. Use como sinal na revisão do
  diff do lock, não como portão.
- `pylock.toml` (PEP 751) é o lockfile padronizado; `pip-audit` 2.9+ lê. `uv.lock` já traz hash.
- Índice privado: configure `index-strategy = "unsafe-best-match"` **com cuidado** — o default
  (`first-index`) é o que protege contra **dependency confusion**. Nunca aponte o índice público
  como fallback de um privado sem fixar namespace.
- Cooldown: `uv` tem `--exclude-newer <data>` para resolver "como estava em X" — use em pipeline
  reprodutível; não há equivalente direto de `minimumReleaseAge`, então revise release recente no PR.

## 6. CI/CD — onde o worm entrou
```yaml
permissions:
  contents: read            # default do workflow inteiro
jobs:
  build:
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@08c6903cd8c0fde910a37f88322edcfb5dd907a8  # v5.0.1
  publish:
    permissions:
      contents: write
      id-token: write       # OIDC: trusted publishing / cosign keyless
      attestations: write
```
- **Pin por SHA completo** com comentário de versão. Tag é móvel: `@v3` pode ser repontado para
  código malicioso que roda com os seus secrets. Dependabot atualiza os SHAs.
- `permissions` mínimo por job; nada de `write-all`.
- **OIDC** em vez de chave estática, com trust policy estreita: workflow e ref específicos
  (`repo:org/repo:ref:refs/tags/*`), nunca a organização inteira.
- **Cache é vetor** (foi o do Mini Shai-Hulud): chave de cache não pode ser influenciada por PR não
  confiável; nada de restaurar cache em job que publica.
- `pull_request_target` e `workflow_run` com checkout do código do PR = execução de código de
  terceiro com secret. Se precisar, não dê checkout no head do PR, ou use environment com aprovação.
- `zizmor .github/workflows/` no CI pega ação não pinada, injeção de script em `run:` com
  `${{ github.event.* }}`, trigger perigoso e ação vulnerável conhecida.
- Runner self-hosted **nunca** em repo público nem para PR de fora: é execução arbitrária na sua rede.
- Secret por environment com reviewer obrigatório no job de publicação.

## 7. Artefato: SBOM, assinatura e verificação
```bash
syft <imagem>:<tag> -o cyclonedx-json > sbom.json       # ou spdx-json
cosign attest --predicate sbom.json --type cyclonedx <imagem>@<digest>   # keyless via OIDC
cosign verify <imagem>@<digest> \
  --certificate-identity-regexp 'https://github.com/minha-org/.+/\.github/workflows/.+' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
docker buildx build --provenance=true --sbom=true ...
```
- **SBOM por release, guardada** (vira exigência de cliente e do CRA). CycloneDX ou SPDX, tanto faz
  — escolha uma e padronize.
- **Deploy por digest**, nunca por tag móvel. O portão de deploy verifica assinatura e proveniência
  e **pina a identidade do workflow** — verificar "está assinado" sem checar por quem não vale nada.
- Appliance offline: minisign/cosign com chave pública embutida no instalador
  (`appliance-offline-package`).

## 8. Portões de CI
| Portão | Comando | Falha quando |
|---|---|---|
| Lock íntegro | `npm ci` · `pnpm install --frozen-lockfile` · `uv sync --frozen` · `go mod tidy -diff` | lock fora de sincronia |
| Vulnerabilidade | `osv-scanner scan source -r .` | achado com fix disponível |
| Por linguagem | `npm audit --audit-level=high` · `govulncheck ./...` · `pip-audit` | ver skill da linguagem |
| Workflow | `zizmor .github/workflows/` | severidade alta |
| Imagem | `trivy image --severity HIGH,CRITICAL --ignore-unfixed` | HIGH/CRITICAL com fix |
| Licença | `grant check` | licença fora da política |
| Segredo | `gitleaks detect --redact` | qualquer achado |

Rode também em **schedule semanal**: CVE nova aparece sem o código mudar.
Dependabot/Renovate agrupando patch, com PR de major separado e revisão humana.

## 9. Estação de trabalho do dev
- MFA no GitHub, npm e PyPI; **nenhum token de longa vida no `~/.npmrc`/`~/.pypirc`** (use OIDC no CI
  e login interativo local).
- Disco cifrado, tela bloqueada, chave SSH com passphrase ou em agente com confirmação.
- Extensão de IDE, servidor MCP e skill de terceiro são **dependência com acesso a shell e repo**:
  instale fixando commit, leia o conteúdo antes (a skill `find-skills` já faz isso) e revise o que
  pede permissão.
- `gitleaks` no pre-commit. Não cole segredo em chat, issue ou prompt.

## 10. Quando um pacote seu é comprometido
Runbook completo em `../security-hardening/references/runbooks-incidente.md` §2.
Resumo: pare as instalações → fixe a última versão boa → limpe cache e árvore → **rotacione todo
segredo alcançável pela máquina e pelo CI** → procure persistência (`.github/workflows`,
`postinstall`, `.git/hooks`, chave SSH, versão publicada no seu nome) → reconstrua as imagens.
