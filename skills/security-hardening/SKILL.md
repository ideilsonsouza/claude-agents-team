---
name: security-hardening
description: "Ponto de entrada de segurança (Node, Go, Python): OWASP Top 10:2025, ASVS 5.0, modelo de ameaças, auditoria, portões de CI, criptografia, segredos, hardening e runbook de incidente. Usar ao blindar ou auditar serviço, revisar segurança de PR ou reagir a vazamento ou CVE crítica."
---

# Blindagem de aplicação

Fontes verificadas em **23/10/2026**: OWASP Top 10:2025, ASVS 5.0, OWASP Cheat Sheets,
nodejs.org, go.dev, docs.python.org, pnpm.io, RFC 9106/9954/10024, Comissão Europeia (CRA).
Panorama completo da investigação: `references/panorama-2026.md`.

**Carregue junto com a skill da linguagem:** `security-node`, `security-go` ou `security-python`.
Cadeia de suprimentos e CI: `security-supply-chain`.
Já tratado em outras skills — **não duplique aqui**:
- API HTTP, authz (BOLA), JWT, CORS, rate limit, senha, SSRF: `backend-standards`;
- XSS, CSP, cookie, segredo no bundle: `frontend-standards` e `ui-review`;
- SQL, grants, LGPD no banco: `sql-standards`; conexão e timeout: `postgres-scaling`;
- pipeline, pin de ação, OIDC: `cicd-github-actions`; log e alerta: `observability`;
- appliance (Docker/Compose, pacote assinado): `appliance-docker`, `appliance-offline-package`.

## 1. Critério: o que "blindado" significa
Use o **Top 10:2025** para priorizar e o **ASVS 5.0** para fechar escopo.

| | Categoria 2025 | Onde atacar no nosso código |
|---|---|---|
| A01 | Broken Access Control (**SSRF entrou aqui**) | filtro por tenant/dono em toda query, deny-by-default, teste cruzado |
| A02 | Security Misconfiguration | headers, CORS, debug/docs em produção, default de imagem e broker |
| A03 | **Software Supply Chain Failures** | `security-supply-chain` |
| A04 | Cryptographic Failures | senha, TLS, chave, dado em repouso |
| A05 | Injection | parâmetro em SQL, comando, template, log |
| A06 | Insecure Design | limite de negócio, idempotência, fluxo sensível |
| A07 | Authentication Failures | sessão, refresh rotativo, bloqueio progressivo |
| A08 | Software or Data Integrity Failures | desserialização, update sem assinatura, webhook sem HMAC |
| A09 | Security Logging & **Alerting** Failures | evento de segurança logado **e** alertado |
| A10 | **Mishandling of Exceptional Conditions** | seção 7 (fail closed) |

**Níveis de blindagem** (defina o nível no `design.md` e audite contra ele):

| Nível | Quando | Exigência extra |
|---|---|---|
| **L1 interno** | só rede interna, sem dado pessoal | ASVS L1, portões de CI da seção 5 |
| **L2 exposto** | internet, autenticado, dado de cliente | ASVS L2, teste de authz cruzado, rate limit, WAF/proxy, rotação de segredo documentada |
| **L3 crítico** | multi-tenant, dado pessoal sensível, pagamento, chão de fábrica | ASVS L3, RLS, trilha de auditoria imutável, revisão de modelo de ameaças por release, pentest |

## 2. Modelo de ameaças em 5 perguntas
Responda por escrito no `design.md` antes de implementar (15 min, não 15 páginas):
1. **Quais são as fronteiras?** Quem fala com quem (internet → proxy → API → banco/broker/worker).
   Toda flecha que cruza fronteira precisa de autenticação, limite e timeout.
2. **Qual entrada não é confiável?** Body, query, header, arquivo, tópico MQTT, mensagem de fila,
   webhook, resposta de API de terceiro, issue do Jira, log, página web, saída de LLM. **Tudo isso.**
3. **O que o atacante ganha?** Dado de outro tenant, credencial, execução de comando, parada da
   linha de produção. Ordene por isso, não por CVSS.
4. **Qual é o segredo mais valioso aqui** e o que acontece se vazar hoje? Se a resposta não for
   "roda o runbook de rotação em 30 min", conserte isso primeiro.
5. **Como isso falha?** Se o banco cai, o Redis some, o token expira: **nega** ou **libera**?
   Tem que negar (seção 7).

## 3. Procedimento de auditoria (a "blindagem")
Rode nesta ordem. Cada passo tem comando e o que fazer com o resultado.
Trabalhe em worktree da tarefa; nada de alterar produção durante auditoria.

```bash
# 0. inventário: o que é este serviço, quem expõe, qual nível
rg -n "listen\(|ListenAndServe|uvicorn|gunicorn" --type-add 'cfg:*.{yml,yaml,toml,json}' -g '!**/node_modules/**'
cat Dockerfile docker-compose*.yml 2>/dev/null | head -60

# 1. segredo no repo e no histórico  (nunca ignore achado em histórico: o commit é público)
gitleaks detect --redact --no-banner
gitleaks detect --redact --no-banner --log-opts="--all"   # histórico inteiro
rg -n "(?i)(api[_-]?key|secret|passwo?rd|token|BEGIN (RSA|EC|OPENSSH) PRIVATE)" -g '!*.lock' -g '!**/node_modules/**' | head -40

# 2. dependência vulnerável (multi-linguagem, lê o lockfile)
osv-scanner scan source -r .

# 3. SAST
semgrep --config p/security-audit --config p/secrets --error --metrics=off
#    + linter de segurança da linguagem: ver security-node / security-go / security-python

# 4. workflow de CI
zizmor .github/workflows/

# 5. imagem e filesystem
trivy fs --scanners vuln,misconfig,secret --severity HIGH,CRITICAL --ignore-unfixed .
trivy image --severity HIGH,CRITICAL --ignore-unfixed <imagem>:<tag>

# 6. configuração exposta em runtime (staging, nunca produção sem combinar)
curl -sSI https://staging.exemplo/ | grep -iE "strict-transport|content-security|x-content-type|x-frame|server|x-powered-by"
curl -sS -o /dev/null -w '%{http_code}\n' https://staging.exemplo/docs https://staging.exemplo/metrics https://staging.exemplo/debug
```

**7. Autorização (o passo que ferramenta não faz).** Leia rota por rota e responda:
a query filtra por `tenant_id`/`owner_id`? O schema de entrada tem allowlist
(`additionalProperties: false`) e o de saída também? Existe teste com **usuário A pedindo recurso
de B esperando 404**? Sem esse teste, A01 está aberto. Detalhe em `backend-standards` §3 e §6.

**8. Falha e erro.** Force a queda da dependência (pare o Postgres/Redis no compose) e confira:
nega acesso, não vaza stack trace, não deixa recurso preso, loga **um** evento agregado.

### Formato do relatório de achados
Uma linha por achado, ordenado por severidade; sem achado inventado para encher lista.

```
[CRÍTICO] A01 · src/modules/orders/routes.ts:84
  GET /orders/:id busca por id sem filtrar tenant_id — qualquer usuário autenticado lê pedido de
  outro cliente.
  Correção: WHERE id = $1 AND tenant_id = $2 + teste cruzado em test/orders.authz.test.ts.
  Evidência: curl com token do tenant B retornou 200.
```
Severidade: **CRÍTICO** (explorável agora, dado de outro tenant/credencial/RCE) ·
**ALTO** (explorável com pré-condição) · **MÉDIO** (defesa em profundidade ausente) ·
**BAIXO** (higiene). Achado sem correção concreta não é achado, é opinião.

## 4. Portões mínimos de CI
Nenhum portão novo entra sem baseline limpa — senão vira alarme ignorado.

| Portão | Comando | Falha quando |
|---|---|---|
| Segredo | `gitleaks detect --redact` | qualquer achado |
| Dependência | `osv-scanner scan source -r .` | vulnerabilidade com fix disponível |
| SAST | `semgrep --config p/security-audit --error` | achado novo (use baseline no legado) |
| Workflow | `zizmor .github/workflows/` | achado de severidade alta |
| Imagem | `trivy image --severity HIGH,CRITICAL --ignore-unfixed` | HIGH/CRITICAL com fix |
| Linguagem | `govulncheck` · `npm audit --audit-level=high` · `pip-audit` | ver skill da linguagem |
| Teste de authz | suíte de teste | teste cruzado faltando ou vermelho |

Rode também **semanalmente em schedule**, não só no PR: CVE nova aparece em código que não mudou.

## 5. Criptografia (A04)
- **Senha: Argon2id, m = 19 MiB (19456 KiB), t = 2, p = 1, salt de 16 B** (mínimo OWASP).
  Alternativas equivalentes: 46 MiB/t=1, 12 MiB/t=3, 9 MiB/t=4, 7 MiB/t=5. Meça: login não deve
  passar de ~500 ms. Guarde no formato PHC (algoritmo+parâmetros no hash) e **rehash no login**
  quando subir parâmetro. bcrypt só em legado (custo ≥ 10, trunca em 72 bytes). PBKDF2-HMAC-SHA256
  com 600 000 iterações só quando FIPS exigir. Pepper, se usar, fora do banco.
- **Aleatoriedade**: só CSPRNG — `crypto.randomBytes`/`randomUUID` (Node), `crypto/rand` (Go),
  `secrets` (Python). Nunca `Math.random`, `math/rand`, `random`.
- **Comparação de segredo**: tempo constante — `crypto.timingSafeEqual`,
  `subtle.ConstantTimeCompare`, `hmac.compare_digest`.
- **Token opaco**: ≥ 32 bytes de CSPRNG; guarde **hash** do token, não o token.
- **TLS 1.2 mínimo, 1.3 preferido**, terminado no proxy (Traefik). Troca híbrida pós-quântica
  (`X25519MLKEM768`, RFC 10024) já é default em OpenSSL 3.5+ e Go 1.24+ — deixe ligado; o custo é
  ClientHello maior. Certificado continua clássico: isso protege contra "colher agora, decifrar
  depois", não contra falsificação de certificado.
- **Nada de criptografia caseira**: nem modo de bloco escolhido à mão, nem JWT assinado na mão.
  Para dado em repouso use AEAD (AES-GCM, ChaCha20-Poly1305) com nonce único por mensagem.

## 6. Segredos
- Segredo vem **só** do ambiente ou de secret do orquestrador, validado no boot (falhe o boot se
  faltar). Nunca no repo, no `Dockerfile`, no bundle do front, no log, na URL, no erro.
- Em git: **SOPS + age** (cifra valor, não arquivo inteiro — o diff continua revisável). Perder a
  chave age é perder os segredos: guarde-a fora do repo, com cópia.
- Centralizado quando houver mais de um ambiente ou pessoa: **OpenBao** (MPL-2.0) ou Infisical
  (rotação é paga). Não precisa disso para projeto solo — SOPS resolve.
- `gitleaks` no pre-commit **e** no CI (histórico inteiro na primeira vez).
- **Rotação com prazo escrito** no `tech.md`: token de CI e PAT ≤ 90 dias; chave de assinatura e
  credencial de banco com procedimento testado. Segredo sem procedimento de rotação é incidente
  futuro.

## 7. Falhar fechado (A10)
- **Deny-by-default**: autorização, allowlist de host no SSRF, allowlist de algoritmo no JWT,
  feature flag, política de fila. Timeout/erro de dependência de autorização = **negar**.
- Trate o erro **onde ele nasce**; handler global só como rede de segurança.
- **Transação multi-etapa**: rollback completo. Nunca recuperação parcial "melhor que nada".
  Toda operação externa com efeito precisa de `Idempotency-Key` (ver `architecture-scalability`).
- **Libere recurso em `finally`**: conexão, arquivo, lock, stream de upload. Upload que estoura
  limite tem que liberar o recurso — é o cenário de DoS que a OWASP cita.
- **Resposta de erro ao cliente**: mensagem curta e estável (RFC 9457 Problem Details), sem stack
  trace, sem SQL, sem caminho de arquivo, sem nome de biblioteca. Detalhe vai para o log com
  `requestId`.
- **Limite tudo**: body, upload, itens em lote, `limit` de paginação, profundidade de JSON, timeout
  por request e `statement_timeout`.
- Erro repetido é sinal de ataque: **agregue** (contador + amostra), alerte por taxa, não inunde.

## 8. Contêiner e processo
- **Imagem**: multi-stage, base mínima (distroless/slim/scratch), **`USER` não-root** (ex.: 65532),
  sem shell nem gerenciador de pacote na imagem final, sem `.env`/chave/`.git` (use `.dockerignore`),
  tag por digest em produção, healthcheck.
- **Runtime**: `read_only: true` + tmpfs em `/tmp` com `noexec,nosuid`, `cap_drop: [ALL]`,
  `no-new-privileges:true`, limite de CPU/memória/pids, rede interna para banco e broker
  (nunca porta de banco publicada), `stop_grace_period` coerente com o shutdown da aplicação.
- **Bare metal/appliance com systemd**: `User=`, `NoNewPrivileges=yes`, `ProtectSystem=strict`,
  `ProtectHome=yes`, `PrivateTmp=yes`, `ReadWritePaths=` só o necessário,
  `RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX`, `MemoryMax=`. Serviço bindado em `127.0.0.1`
  ou socket Unix quando o proxy está na mesma máquina.
- Scanner de imagem no CI **e** rescan periódico do que já está em produção.

## 9. Log e alerta de segurança (A09)
Logue como evento estruturado, com `requestId`, ator, recurso e resultado — **e crie alerta**:
login falho em série, bloqueio de conta, troca de senha/e-mail/2FA, concessão ou perda de papel,
acesso negado por authz (403 em sequência = varredura), uso de token inválido/expirado/revogado,
rate limit disparado, falha de validação de assinatura/HMAC, erro 5xx em série, deploy e rollback,
acesso a dado pessoal em L3.
**Nunca logue**: senha, token, cookie, `authorization`, chave, CPF, e-mail completo, corpo de
request. `redact` no pino/slog/logging — ver `observability`. Retenção definida; log de segurança
não é lixo de debug.

## 10. Incidente
Runbooks completos em `references/runbooks-incidente.md`. Resumo:
- **Segredo vazou** → rotacione primeiro, investigue depois; revogue o antigo; procure uso indevido
  no log; reescrever histórico do git **não** desvaza — considere comprometido para sempre.
- **Dependência maliciosa** → não dê `npm install` de novo; fixe a última versão boa, limpe cache e
  `node_modules`, rotacione **todo** segredo que a máquina/CI alcançava, varra o repo por hook
  plantado (`.github/workflows`, `postinstall`, `.git/hooks`).
- **CVE crítica** → é alcançável pelo nosso código? (`govulncheck`, `osv-scanner`); patch > mitigação
  > WAF temporário; registre a decisão.
- **Dado pessoal exposto** → LGPD: comunique o encarregado; não apague evidência.
- **UE / CRA** (desde 11/09/2026, se o produto é colocado no mercado europeu sob nome próprio):
  **24 h** alerta inicial, **72 h** notificação, **14 dias** relatório final (vulnerabilidade
  explorada ativamente) ou **1 mês** (incidente severo), pela plataforma da ENISA.

## 11. Checklist de PR
- [ ] Toda query por id filtra por tenant/dono, e tem teste cruzado (A ↔ B → 404)
- [ ] Entrada validada com allowlist; resposta com schema (sem campo vazando)
- [ ] Nada de segredo novo no diff (`gitleaks` limpo); segredo novo veio do ambiente e falha no boot
- [ ] Dependência nova: justificada, fixada no lockfile, sem install script, versão com ≥ 1 dia
- [ ] Erro trata onde nasce, libera recurso, não vaza detalhe; caminho de falha **nega**
- [ ] Limite e timeout em toda chamada externa e todo upload
- [ ] Evento de segurança novo está logado e com alerta
- [ ] Portões de CI verdes, incluindo SAST e scanner de dependência
- [ ] Rota nova exposta → documentada no OpenAPI e com authz declarada
