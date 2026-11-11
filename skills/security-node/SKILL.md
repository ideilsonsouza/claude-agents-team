---
name: security-node
description: "Segurança de Node.js/TypeScript (Fastify, AdonisJS, BullMQ): flags de runtime, timeouts, prototype pollution, crypto, injeção, SSRF, headers, segredos no boot, imagem non-root e CVEs do Fastify. Usar ao blindar, auditar ou revisar código Node."
---

# Blindagem em Node.js

Fontes verificadas em **23/10/2026**: Node.js Security Best Practices e threat model (nodejs.org),
nodejs.org/en/about/previous-releases, OWASP NPM Security Cheat Sheet, docs.npmjs.com.
Base: `security-hardening`. Dependência e CI: `security-supply-chain`.
Padrões de API, authz, JWT, CORS, rate limit e senha: `backend-standards`.
Plugins e CVEs do Fastify: `backend-fastify`. Filas: `backend-bullmq`.

## 1. Versão
| Linha | Versão | Uso |
|---|---|---|
| 26.x | 26.12.1 | Current — só desenvolvimento/teste |
| **24.x (Krypton)** | **24.22.1** | **padrão de produção (LTS)** |
| 22.x (Jod) | 22.23.4 | LTS em manutenção; migre |
| 25.x, 20.x | — | **mortas em mar/2026** |

Produção só em Active/Maintenance LTS, sempre no **último patch** — as correções de segurança saem
por patch. A partir da 27 o ciclo é anual (LTS com ~30 meses de correção crítica).
Fixe a versão em três lugares coerentes: `engines`, `.nvmrc`/`packageManager` e `FROM` do Dockerfile.

## 2. O modelo de ameaças do Node (o que o core *não* protege)
Para o Node, **dependência é código confiável**: pacote malicioso não é vulnerabilidade do core.
Logo, a blindagem é sua. Qualquer pacote pode ler o disco, abrir socket e chamar `eval`.
Também ficam do seu lado: prototype pollution com entrada do atacante, poluição de caminho de
módulo e DoS por configuração de servidor ausente.

## 3. Permission model (o controle mais subaproveitado)
Estável desde a 22.13. Fecha o estrago de dependência maliciosa e de RCE:
```bash
node --permission \
     --allow-fs-read=/app,/etc/ssl \
     --allow-fs-write=/tmp \
     --allow-net \
     ./dist/server.js
# sem --allow-child-process, --allow-worker e --allow-addons: processo não executa binário nem addon
```
- Comece em homologação com os `--allow-*` largos, colete o que falha, aperte.
- Serviço HTTP típico **não precisa** de `child_process`, `worker` nem addon. Se precisa de worker
  (BullMQ sandboxed processor), libere só ele.
- As flags variam por linha do Node — confira `node --help` da sua versão antes de fixar no Compose.
- Não substitui contêiner non-root/read-only (seção 11): são camadas diferentes.

## 4. Flags de runtime
| Flag | Por quê |
|---|---|
| `--disable-proto=throw` | mata o vetor clássico de prototype pollution via `__proto__` |
| `--secure-heap=N` | limita vazamento por overrun de ponteiro (não existe no Windows) |
| `--frozen-intrinsics` | congela built-ins contra monkey patching (**experimental**: teste antes) |
| `--env-file=.env` | carrega env sem `dotenv` em runtime (ainda: segredo não vai no repo) |
| ~~`insecureHTTPParser`~~ | **nunca**: habilita request smuggling |
| ~~`--inspect`~~ | **nunca em produção**: DNS rebinding alcança o inspector |
Se o inspector é usado em dev, registre `process.on('SIGUSR1', …)` para não abrir por sinal.

## 5. DoS e timeouts no servidor
```ts
const server = app.server;              // http.Server
server.headersTimeout  = 10_000;        // cabeçalho lento (Slowloris)
server.requestTimeout  = 30_000;        // request inteira
server.keepAliveTimeout = 72_000;       // > idle timeout do Traefik, senão 502 esporádico
server.maxRequestsPerSocket = 1000;
server.maxHeadersCount = 100;
```
- Cliente HTTP: `AbortSignal.timeout(ms)` em **toda** chamada `fetch`/`undici`, e limite de socket
  (`maxSockets`, `maxTotalSockets`) no Agent/Pool.
- Servidor TCP cru (`net.createServer`): **sempre** `socket.on('error', …)` — sem isso um pacote
  malformado derruba o processo.
- Limite de body (`bodyLimit` no Fastify), de upload e de itens em lote. Payload de JSON profundo é
  DoS: valide com schema, não com merge recursivo.
- Atrás de proxy: `trustProxy` apontando só para o proxy real, senão o IP do rate limit é falsificável.

## 6. Prototype pollution e objeto não confiável
```ts
const bag = Object.create(null);                 // sem protótipo
if (Object.hasOwn(obj, key)) { /* ... */ }       // nunca obj.hasOwnProperty(key)
Object.freeze(MyClass.prototype);
```
- **Nunca** merge recursivo de entrada do usuário (`lodash.merge`, `deepmerge`) — é o CVE clássico.
  Monte o objeto campo a campo a partir do DTO validado.
- Valide com JSON Schema/Zod **antes** de qualquer merge, com `additionalProperties: false`.
- Chave vinda do usuário em acesso dinâmico (`obj[key]`): allowlist de chaves, e rejeite
  `__proto__`, `constructor`, `prototype`.

## 7. Injeção e execução
- **Nunca** `eval`, `new Function`, `setTimeout("string")`, `require(variável)`,
  `import(variável do usuário)`.
- Comando externo: `execFile`/`spawn` com **array de argumentos**, `shell: false` (default),
  binário por caminho absoluto, `timeout` e env mínimo. `exec`/`shell: true` com entrada do usuário
  é RCE.
- Caminho de arquivo: resolva e confine.
```ts
const base = path.resolve('/app/uploads');
const target = path.resolve(base, userName);
if (target !== base && !target.startsWith(base + path.sep)) throw new Error('fora da base');
```
  `path.join` sozinho **não** protege (`../` normaliza antes). Nome de arquivo salvo deve ser gerado
  pelo servidor.
- SQL: só parâmetro (`$1`) — ver `sql-standards` e `backend-drizzle`. Nada de template string.
- **`vm`/`vm2` não são sandbox.** Para rodar código não confiável use `isolated-vm`
  (skill `sandbox-isolated-vm`) ou processo separado com permission model e limites.

## 8. SSRF (A01 em 2025)
```ts
const res = await fetch(url, { redirect: 'manual', signal: AbortSignal.timeout(5000) });
```
Antes de chamar: allowlist de esquema (`https:`) e de host; **resolva o DNS e rejeite IP privado,
loopback e link-local (169.254.169.254)**; não siga redirect; timeout curto. Revalide a cada
redirect se precisar segui-los. Detalhe em `backend-standards` §3.

## 9. Criptografia e segredo
- Senha: **`@node-rs/argon2`** com Argon2id m=19456, t=2, p=1. `bcrypt` só em legado (trunca em
  72 bytes). `crypto.scrypt` é alternativa da stdlib.
- Comparação de segredo/HMAC: `crypto.timingSafeEqual` (iguale o tamanho antes, ele lança se difere).
- Aleatório: `crypto.randomBytes`, `crypto.randomUUID`. **Nunca `Math.random`** para token, id,
  senha temporária ou nonce.
- JWT: `jose` (allowlist de algoritmo, `createRemoteJWKSet` com cache). No Fastify, fixe
  `fast-jwt ≥ 6.3.4` — o range `^6.2.4` aceita versão vulnerável.
- Segredo: só `process.env`, **validado com Zod no boot** (falhe o boot se faltar), nunca
  `dotenv` em produção, nunca no bundle, nunca em log/URL/erro.

## 10. Headers, cookie e resposta
- `helmet` 8.3 (Express) ou `@fastify/helmet`: HSTS, `nosniff`, `frame-ancestors`, Referrer-Policy.
  CSP começa em `report-only` e fecha depois — detalhe em `frontend-standards`.
- Cookie de sessão: `httpOnly`, `secure`, `sameSite: 'lax'`, `path: '/'`, com id opaco e estado no
  servidor.
- `Cache-Control: no-store` em resposta autenticada.
- Erro: handler global devolvendo Problem Details (RFC 9457) sem stack trace; detalhe só no log com
  `requestId`. Desligue `X-Powered-By`.
- Desserialização: só JSON. `js-yaml` v4 (`load` seguro por default) para YAML; **jamais**
  `node-serialize`, `funcster` ou `eval` de JSON.

## 11. Imagem e processo
```dockerfile
FROM node:24.22.1-slim AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci --ignore-scripts
COPY . .
RUN npm run build && npm prune --omit=dev

FROM gcr.io/distroless/nodejs24-debian12:nonroot
ENV NODE_ENV=production
WORKDIR /app
COPY --from=build --chown=nonroot:nonroot /app/node_modules ./node_modules
COPY --from=build --chown=nonroot:nonroot /app/dist ./dist
USER nonroot
CMD ["dist/server.js"]
```
- `.dockerignore` com `.env`, `.git`, `*.pem`, `node_modules`.
- Runtime: `read_only: true` + tmpfs em `/tmp`, `cap_drop: [ALL]`,
  `security_opt: [no-new-privileges:true]`, limites de memória/CPU, banco e Redis em rede interna.
- Signal handling: Node como PID 1 **precisa** tratar SIGTERM (close-with-grace) ou usar init.
  Ver `cd-practices`.
- `--max-old-space-size` coerente com o limite do contêiner: OOM kill é indisponibilidade.

## 12. Ferramentas
```bash
npm audit --audit-level=high           # CVE conhecida (não pega pacote malicioso novo)
osv-scanner scan source -r .
semgrep --config p/javascript --config p/secrets --error --metrics=off
npx eslint .                           # com eslint-plugin-security
```
ESLint: `eslint-plugin-security` e, no front, `eslint-plugin-no-unsanitized`.
TypeScript estrito ajuda, mas **não** é controle de segurança: `any` em borda de entrada e `as`
depois de `JSON.parse` escondem exatamente o que você quer validar.

## 13. Testes de segurança
- **Authz cruzado obrigatório**: token do tenant A pedindo recurso de B → 404 (não 403).
- Entrada hostil por rota: `__proto__` no body, campo extra (deve ser rejeitado por
  `additionalProperties: false`), id de outro tenant, payload no limite do `bodyLimit`.
- Caminho de falha: simule Postgres/Redis indisponíveis (porta fechada ou host inválido; nunca derrube serviço compartilhado) e verifique que **nega** e não vaza erro.
- Upload: arquivo maior que o limite (recurso liberado?), extensão dupla, nome com `../`.
- Rode `npm audit`/`osv-scanner` em schedule semanal, não só no PR.
