# Panorama de cibersegurança para quem escreve aplicações — out/2026

Investigação feita em **23/10/2026**. Serve de base para as skills `security-hardening`,
`security-supply-chain`, `security-node`, `security-go` e `security-python`.
Versões e datas conferidas nesta data; releases de ferramenta foram lidos direto das APIs
do npm, PyPI e GitHub.

> Confiabilidade: o que vem de fonte primária (OWASP, nodejs.org, go.dev, docs.python.org,
> pnpm.io, Comissão Europeia, RFCs) está marcado como tal. Onde só havia blog de fornecedor,
> o texto diz "relato de fornecedor" — trate como indício, não como fato.

---

## 1. Resumo executivo

Cinco coisas mudaram o jogo desde 2024:

1. **A cadeia de suprimentos virou risco de primeira classe.** O OWASP Top 10:2025 criou a
   categoria **A03 Software Supply Chain Failures** (antes era só "componentes vulneráveis") e
   ela entrou direto em 3º lugar. Em 2026 houve ataque a pacote npm popular praticamente todo mês.
2. **Credencial roubada não é mais o único vetor.** O worm "Mini Shai-Hulud" (mai/2026) publicou
   pacotes maliciosos **sem roubar token**: envenenou o cache de CI e usou o endpoint OIDC de
   trusted publishing do npm — gerando pacote malicioso **com proveniência SLSA Build L3 válida**.
   Proveniência prova *de onde veio*, não que é seguro.
3. **Os registries reagiram mudando o default.** npm 12 (jul/2026) **não roda mais install scripts**;
   pnpm segura versão nova por 24 h (`minimumReleaseAge`); PyPI tem atestação de publicação (PEP 740).
   Isso quebra builds antigos — e é a melhor notícia de segurança do ano.
4. **Agente de IA é superfície de ataque nova e sua.** O OWASP publicou o
   **Top 10 for Agentic Applications (ASI01–ASI10)** em dez/2025. Quem roda agentes com acesso a
   repo, shell e MCP (o caso do Orca IDE) tem que tratar isso como componente de produção.
5. **Virou obrigação legal na UE.** O **Cyber Resilience Act** está com as obrigações de reporte
   **em vigor desde 11/09/2026**: 24 h para alerta inicial de vulnerabilidade explorada ativamente.
   O resto das obrigações entra em 11/12/2027.

O que **não** mudou: a maioria dos incidentes ainda nasce de controle de acesso quebrado,
configuração errada e credencial exposta. Blindagem começa aí, não em criptografia exótica.

---

## 2. OWASP Top 10:2025 (edição vigente para aplicações web)

Fonte primária: <https://top10.owasp.org/2025/>. A edição 2021 está marcada como *superseded*.

| # | Categoria | Movimento |
|---|---|---|
| A01 | Broken Access Control | 1º de novo; **SSRF foi absorvido aqui** |
| A02 | Security Misconfiguration | subiu de 5º para 2º |
| A03 | **Software Supply Chain Failures** | **nova**; expande "Vulnerable and Outdated Components" |
| A04 | Cryptographic Failures | caiu de 2º para 4º |
| A05 | Injection | caiu de 3º para 5º |
| A06 | Insecure Design | caiu de 4º para 6º |
| A07 | Authentication Failures | 7º; renomeada (era "Identification and Authentication Failures") |
| A08 | Software or Data Integrity Failures | 8º; agora é integridade **abaixo** da cadeia de suprimentos |
| A09 | Security Logging & Alerting Failures | 9º; renomeada para enfatizar **alerta**, não só log |
| A10 | **Mishandling of Exceptional Conditions** | **nova**: erro mal tratado, logic error, *fail open* |

**Metodologia** (importa para não superinterpretar o ranking): dados de mais de 2,8 milhões de
aplicações, 13 organizações contribuintes; 589 CWEs analisadas, 248 agrupadas nas 10 categorias
(máx. 40 CWEs por categoria). Oito categorias vêm dos dados; duas vêm de pesquisa com a comunidade,
para capturar risco que teste automatizado ainda não mede. Prevalência = % de aplicações com ao
menos uma ocorrência, não número de ocorrências. Exploitability/impact vêm de CVSS v2/v3 (v4 foi
descartado por mudança de modelo de score).

### A03 — o que a categoria cobre
Não é só "dependência com CVE". Cobre alteração maliciosa por fornecedor ou pacote confiável,
comprometimento de build/distribuição/atualização, fraqueza em ferramenta de dev, IDE, CI/CD,
repositório de artefato, componente sem manutenção e falta de rastreio de mudança / separação de
responsabilidade. Exemplos citados pela própria OWASP: SolarWinds, roubo da carteira Bybit,
worm Shai-Hulud no npm, Log4Shell, Struts.
Prevenção recomendada: SBOM e inventário contínuo (inclusive transitivas), SCA + advisories
(CVE/NVD/OSV), origem confiável e pacote assinado, vigiar componente abandonado, manter CI/CD e
ferramenta de dev atualizados, rollout em estágios/canário, rastrear mudança de configuração de
CI/repo/registry, endurecer repo + estação do dev (MFA) + build server + artefato (assinatura e
proveniência), e plano contínuo de triagem para toda a vida do produto.

### A10 — a categoria que pega todo mundo
Três formas de falhar: não prevenir a condição anormal, não detectá-la, ou responder mal depois.
Causas: validação ausente, `try/catch` alto demais na pilha (longe de onde o erro nasce),
estado inesperado do ambiente, tratamento inconsistente de exceção, exceção não tratada.
Cenários da própria OWASP: upload que estoura e deixa recurso preso → DoS; erro verboso de banco
que entrega detalhe para refinar SQLi; transação multi-etapa interrompida sem rollback completo →
dinheiro duplicado por *race condition*.
Prevenção: tratar o erro onde ele nasce, handler global como rede de segurança, **fail closed**,
rollback completo em vez de recuperação parcial, limite/quota/throttling, tratamento e alerta
centralizados, monitorar erro repetido como sinal de ataque (agregue, não inunde o log),
validação estrita de entrada.

### APIs continuam com lista própria
Para API HTTP, a lista vigente é o **OWASP API Security Top 10 2023** (BOLA, mass assignment,
consumo de recurso, SSRF, inventário). A skill `backend-standards` já cobre item por item.
"Top 10 2025" é a lista de aplicações web — outra coisa.

---

## 3. ASVS 5.0 — o padrão para dizer "está blindado"

ASVS **5.0.0** saiu em 30/05/2025 (<https://asvs.dev>), com ~350 requisitos em **17 capítulos** e
3 níveis de verificação. Reestruturação grande: requisitos reagrupados por ciclo de vida e camada
de arquitetura, IDs novos (`v5.0.0-3.2.1`), mapeamento bidirecional com a 4.x publicado, e Nível 1
rebaixado para servir de porta de entrada.

| | Capítulo | | Capítulo |
|---|---|---|---|
| V1 | Encoding and Sanitization | V10 | OAuth and OIDC |
| V2 | Validation and Business Logic | V11 | Cryptography |
| V3 | Web Frontend Security | V12 | Secure Communication |
| V4 | API and Web Service | V13 | Configuration |
| V5 | File Handling | V14 | Data Protection |
| V6 | Authentication | V15 | Secure Coding and Architecture |
| V7 | Session Management | V16 | Security Logging and Error Handling |
| V8 | Authorization | V17 | WebRTC |
| V9 | Self-contained Tokens | | |

Uso prático: o Top 10 diz *o que* dá errado; o ASVS dá a lista de requisitos verificáveis. Use o
Top 10 para priorizar e o ASVS para fechar o escopo de uma auditoria ("este serviço atende V6 e V8
no nível 2").

---

## 4. Cadeia de suprimentos: o que aconteceu de verdade

Cronologia (fontes: alerta da CISA, pesquisa JFrog/Unit 42/Akamai/StepSecurity — as contagens
variam entre fornecedores, trate como aproximadas):

| Quando | Evento |
|---|---|
| set/2025 | **Shai-Hulud**: worm auto-replicante no npm, 500+ pacotes, mira token do GitHub, chave de cloud e credencial de dev. Alerta da CISA. |
| nov/2025 | **Shai-Hulud 2.0**. npm acelera trusted publishing (OIDC), 2FA e varredura pós-publicação. |
| mar/2026 em diante | Onda quase mensal de pacote popular comprometido. |
| 11/05/2026 | **Mini Shai-Hulud** (TeamPCP) atinge a árvore do TanStack **sem credencial roubada**: envenenamento de cache de CI + endpoint OIDC do npm. Primeiro caso documentado de worm publicando com **proveniência SLSA Build L3 válida**. |
| 12/05/2026 | Código do worm publicado → cópias e atribuição confusa. Uma onda publicou ~639 versões maliciosas em 323 pacotes em cerca de 1 h. |
| ago/2026 | Variante que colhe credencial, se publica em todo pacote com permissão de escrita e planta hook de execução em repositório do GitHub (JFrog). |

### Lições que viram regra
- **Proveniência ≠ confiança.** Verifique assinatura/proveniência *e* segure versão nova (cooldown).
- **O alvo é a máquina do dev e o runner de CI**, não o servidor de produção. Token de longa vida
  em `~/.npmrc`, `~/.aws`, env de CI e cache de CI são o prêmio.
- **`npm audit` não detecta pacote malicioso novo** — não existe advisory ainda. Audit é para CVE
  conhecida; cooldown + script desligado + revisão de diff é o que pega malware.
- **OIDC sem escopo estreito é token de longa vida com outro nome.** Confie no workflow
  específico (`repo:org/repo:ref:refs/tags/*`), não na organização inteira.

### O que os gerenciadores mudaram
- **npm 12** (08-09/07/2026): `allowScripts` **off por padrão** — lifecycle script de dependência,
  inclusive build implícito do node-gyp, não roda sem allowlist no `package.json`
  (`npm approve-scripts --allow-scripts-pending`). Dependência via git e tarball https remoto
  passam a ser bloqueadas (`--allow-git`, `--allow-remote`). `min-release-age` existe desde
  11.10.0, mas **vem desligado**. Token granular que furava 2FA está sendo aposentado.
  Trusted publishing exige `id-token: write`, npm ≥ 11.5.1 e Node ≥ 22.14.
- **pnpm**: v10 já desligou `postinstall` por padrão; v11 removeu `onlyBuiltDependencies` em favor
  de **`allowBuilds`** (mapa pacote→bool) e trouxe `minimumReleaseAge` com default de **1440 min**,
  `blockExoticSubdeps`, `trustPolicy: no-downgrade` e `verifyDepsBeforeRun: install`;
  v12 (set/2026, reescrita em Rust) deixa `minimumReleaseAgeStrict` verdadeiro sempre que
  `minimumReleaseAge` é configurado explicitamente, adiciona `bootConfig` e verifica assinatura do
  gerenciador de pacote instalado. Config do pnpm vive em `pnpm-workspace.yaml`, **não** no `.npmrc`.
- **PyPI**: **PEP 740** (atestação de publicação — diz *qual workflow publicou*, não que o conteúdo
  é seguro) e **PEP 751** (`pylock.toml`, lockfile padronizado, já lido pelo `pip-audit` 2.9+).
  Armadilha: **nem pip nem uv verificam a identidade da atestação na instalação** — hoje é sinal de
  revisão, não portão.
- **Go** é o ecossistema mais protegido por default: module proxy + **checksum database**
  (`sum.golang.org`) tornam troca silenciosa de conteúdo detectável, e não existe install script.
  O risco sobra em `GOPRIVATE`/`GONOSUMDB`, replace apontando para fork, e ação de CI.

---

## 5. CI/CD e estação de trabalho

Consenso das fontes (guias de fornecedor, sem norma oficial de 2026):
- **Pinar ação por SHA completo**, não por tag — tag é móvel e pode ser repontada para código
  malicioso que roda com os seus secrets. Dependabot atualiza os SHAs.
- **`permissions` read-only por padrão** no workflow, ampliando por job
  (`contents: write`, `id-token: write`, `attestations: write` só no job de publicação).
- **OIDC em vez de chave de cloud guardada**: token de curta duração por execução.
- **zizmor** (v1.31.1) como linter de workflow: pega ação não pinada, injeção de script,
  trigger perigoso (`pull_request_target`) e versão vulnerável de ação.
- Cuidado com cache de CI: foi o vetor do Mini Shai-Hulud. Chave de cache não deve ser
  influenciável por PR não confiável.

---

## 6. Contêiner e runtime

- **Base mínima** (distroless, Chainguard, Docker Hardened Images) reduz CVE herdada; promessa de
  "zero CVE" é marketing, não verifique por ela — verifique com scanner.
- **Non-root não vem de graça**: `USER 65532:65532`, sem shell.
- **Root FS read-only é configuração de runtime**, não da imagem: `--read-only` /
  `readOnlyRootFilesystem: true`, com `/tmp` em tmpfs `noexec,nosuid`.
- **Scanner como portão**: Trivy ou Grype falhando o CI em HIGH/CRITICAL **com fix disponível**,
  mais rescan contínuo (CVE nova aparece em imagem que já passou).
- **SBOM + assinatura**: Syft gera SPDX/CycloneDX, `cosign attest` anexa, `docker buildx`
  gera proveniência (`--sbom=true --provenance=true`); verificação pina a identidade do workflow
  (`cosign verify --certificate-identity-regexp --certificate-oidc-issuer`).
- No appliance on-premise (Docker/Compose), o equivalente é `user`, `read_only`, `cap_drop: [ALL]`,
  `security_opt: no-new-privileges:true` — já descrito na skill `appliance-docker` — mais pacote
  assinado com minisign (`appliance-offline-package`).

---

## 7. Criptografia e segredos

**Senha** (OWASP Password Storage Cheat Sheet, fonte primária):
- **Argon2id**: mínimo **m = 19 MiB (19456 KiB), t = 2, p = 1**. Equivalentes: 46 MiB/t=1,
  12 MiB/t=3, 9 MiB/t=4, 7 MiB/t=5 (sempre p=1). Faça benchmark no hardware alvo.
- scrypt (sem Argon2id): N=2^17 (128 MiB), r=8, p=1.
- bcrypt só em legado: custo ≥ 10 e **limite de 72 bytes** na entrada.
- PBKDF2 só quando FIPS exige: HMAC-SHA256 com 600 000 iterações (SHA-512: 220 000).
- **Pepper** fora do banco (vault/HSM), como defesa em profundidade; trocar pepper obriga reset.
- Guarde algoritmo+parâmetros junto do hash (formato PHC) e **rehash no login** quando mudar.

**TLS e pós-quântico**: a troca de chave híbrida foi padronizada — **RFC 9954** (desenho híbrido
para TLS 1.3, jul/2026) e **RFC 10024** (`X25519MLKEM768`, ago/2026). Já é default em navegadores
recentes, no OpenSSL 3.5+ e no `crypto/tls` do Go desde a 1.24; relato da Cloudflare indica mais de
2/3 do tráfego TLS humano em abr/2026. Custo: ClientHello maior (~1,2 KB de key share) quebra
middlebox antigo. **Atenção ao limite**: híbrido protege confidencialidade (inclusive contra
"colher agora, decifrar depois"); **certificado continua com assinatura clássica** — migração de
assinatura é problema separado e mais difícil.

**Segredos**: para equipe pequena sem servidor, **SOPS + age** em git é o melhor custo-benefício
(cifra só os valores, então o diff ainda mostra qual chave mudou; o risco operacional é perder a
chave privada age). Centralizado: **OpenBao** (fork MPL-2.0 do Vault na Linux Foundation, 2.7.x em
out/2026, adotado pelo GitLab) ou **Infisical** (core MIT, mas rotação e SSO são pagos).
Varredura de segredo no pre-commit e no CI: **gitleaks** ou **trufflehog**. Rotação com prazo
definido (ex.: PAT 90 dias) e procedimento escrito.

---

## 8. Agentes de IA, MCP e a sua própria ferramenta

O **OWASP Top 10 for Agentic Applications 2026** (GenAI Security Project, 09/12/2025):

| ID | Risco | ID | Risco |
|---|---|---|---|
| ASI01 | Agent Goal Hijack | ASI06 | Memory and Context Poisoning |
| ASI02 | Tool Misuse and Exploitation | ASI07 | Insecure Inter-Agent Communication |
| ASI03 | Identity and Privilege Abuse | ASI08 | Cascading Failures |
| ASI04 | Agentic Supply Chain Vulnerabilities | ASI09 | Human-Agent Trust Exploitation |
| ASI05 | Unexpected Code Execution (RCE) | ASI10 | Rogue Agents |

No LLM Top 10 2025, **LLM01 é prompt injection** — em sistema agêntico o impacto é maior porque o
modelo tem ferramenta: manda e-mail, altera arquivo, chama API.

Mitigação com consenso (ainda guia de fornecedor, não norma): separar instrução de sistema, entrada
do usuário e **conteúdo externo**; conteúdo recuperado nunca sobrepõe instrução; restringir quais
ferramentas o modelo alcança; **aprovação humana para ação irreversível**; validar argumento de
ferramenta antes de executar; proxy/wrapper de menor privilégio entre modelo e backend; red team com
payload de injeção. Há também um OWASP MCP Top 10 em andamento, e taxonomia acadêmica (MCP-38)
argumentando que o LLM Top 10 não cobre o modelo de confiança do protocolo nem ataque composto por
cadeia de ferramentas.

Tradução para o seu fluxo (Orca IDE + agentes + MCP + skills): servidor MCP e skill instalada são
**dependência de produção com acesso a shell e repositório**. Fixe commit ao instalar skill de
terceiro (a skill `find-skills` já faz isso), leia o conteúdo inteiro antes, trate issue do Jira,
log de CI e página web como dado não confiável, e não deixe agente com token de longa vida.

---

## 9. Regulação (o que obriga, não o que é boa prática)

- **Cyber Resilience Act (UE)**: obrigações de **reporte em vigor desde 11/09/2026**; demais
  obrigações em **11/12/2027**. Guia prático da Comissão publicado em 27/07/2026. Fabricante é
  quem desenvolve ou manda desenvolver produto com elemento digital e o coloca no mercado **sob o
  próprio nome** — pago, monetizado ou gratuito; componente colocado no mercado separadamente faz
  do fornecedor um fabricante (atinge biblioteca open source comercializada).
  Gatilhos: vulnerabilidade **explorada ativamente** e incidente severo.
  Prazos: **alerta inicial em 24 h**, notificação detalhada em **72 h**, relatório final em
  **14 dias** após medida corretiva disponível (vulnerabilidade explorada) ou **1 mês** após a
  notificação (incidente severo). Submissão pela Single Reporting Platform da ENISA.
  (As fontes divergem sobre a plataforma estar 100% operacional na data — confirme antes de precisar.)
- **LGPD**: minimização nos logs (sem CPF, e-mail completo, corpo de request), base legal para o
  dado coletado, e trilha de auditoria de acesso a dado pessoal. Já tratado em `observability`.
- **NIS2** atinge o cliente operador de serviço essencial — vira requisito contratual (SLA de
  patch, prazo de notificação, SBOM) mesmo para fornecedor pequeno.

---

## 10. Ferramental — versões lidas em 23/10/2026

| Camada | Ferramenta | Versão |
|---|---|---|
| Vulnerabilidade em dependência (multi-linguagem) | `osv-scanner` | v2.7.0 |
| Imagem e filesystem | `trivy` / `grype` | v0.76.1 / v0.121.0 |
| SBOM / assinatura / licença | `syft` / `cosign` / `grant` | v1.55.0 / v3.1.4 / v0.6.8 |
| Segredo no repo | `gitleaks` / `trufflehog` | v8.30.1 / v3.99.4 |
| Workflow do GitHub Actions | `zizmor` | v1.31.1 |
| SAST multi-linguagem | `semgrep` | 1.182.1 |
| Go | `gosec` / `golangci-lint` | v2.30.0 / v2.15.0 |
| Python | `bandit` / `pip-audit` / `ruff` / `uv` | 1.9.4 / 2.10.1 / 0.17.2 / 0.13.5 |
| Node | `npm` / `pnpm` / `helmet` | 12.2.1 / 12.15.0 / 8.3.0 |
| Segredo centralizado | OpenBao / SOPS | 2.7.x / v3.13.3 |

**Runtimes suportados hoje:**
- **Node.js**: v26.12.1 (Current), **v24.22.1 (LTS Krypton)**, v22.23.4 (LTS Jod).
  v25 e v20 morreram em mar/2026. A partir da 27 o ciclo passa a ser anual; LTS garante correção
  crítica por ~30 meses. Produção só em Active/Maintenance LTS.
- **Python**: 3.15.1 e 3.14.9 atuais; 3.13.17, 3.12.15, 3.11.17 ainda suportadas.
  **3.10 chegou ao fim da vida em 01/10/2026** — se ainda roda 3.10, isso é o item nº 1.
- **Go**: 1.27.x e 1.26.x (as duas suportadas). Go só corrige na versão mais recente de cada linha.

---

## 11. Onde as fontes são fracas

- Contagem de pacotes afetados em cada onda de worm npm varia por fornecedor; use como ordem de
  grandeza.
- Guias de hardening de contêiner, GitHub Actions e Python de 2026 são majoritariamente blog de
  fornecedor. As práticas convergem, mas número e flag específicos precisam ser conferidos na doc
  oficial da ferramenta antes de entrar em pipeline.
- Parâmetro de Argon2id aparece inflado em blog (64 MiB/t=3). O mínimo oficial do OWASP é
  19 MiB/t=2/p=1; subir é legítimo, mas meça a latência de login.
- Status operacional da plataforma de reporte da ENISA é relatado de forma contraditória.
- CVE-ID de 2026 citado em blog (ex.: Django, tarfile) nem sempre bate com registro no NVD/OSV.
  Confirme no OSV antes de citar em relatório para cliente.

## 12. Fontes principais

OWASP Top 10:2025 <https://top10.owasp.org/2025/> · ASVS 5.0 <https://asvs.dev> ·
OWASP Cheat Sheets (Password Storage, NPM Security) <https://cheatsheetseries.owasp.org> ·
OWASP GenAI / Agentic Top 10 <https://genai.owasp.org> ·
Node.js Security Best Practices <https://nodejs.org/en/learn/getting-started/security-best-practices> ·
Node.js releases <https://nodejs.org/en/about/previous-releases> ·
Go Security Best Practices <https://go.dev/doc/security/best-practices> ·
pnpm supply chain <https://pnpm.io/supply-chain-security> ·
PEP 740 <https://peps.python.org/pep-0740/> · PEP 751 · PEP 706 ·
docs.python.org/3/library/tarfile.html ·
Cyber Resilience Act <https://digital-strategy.ec.europa.eu/en/policies/cyber-resilience-act> ·
RFC 9954, RFC 10024 ·
pesquisa de incidente: CISA, JFrog Security Research, Unit 42, Akamai, StepSecurity, Socket.
