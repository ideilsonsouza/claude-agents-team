---
name: backend-standards
description: Padrões gerais de backend da equipe, válidos para Go, Fastify e AdonisJS — design de API HTTP (status codes, erros RFC 9457 Problem Details, paginação por cursor, filtros por allowlist, PATCH com Merge Patch, concorrência com ETag/If-Match, versionamento e depreciação com Deprecation/Sunset, formatos de data, dinheiro e IDs), contrato OpenAPI no CI (lint, breaking change, cliente tipado), segurança pelo OWASP API Top 10 (BOLA, mass assignment, SSRF, limites), autenticação (sessão x JWT, refresh rotativo), senhas com Argon2id, CORS e headers, arquitetura em camadas com DI manual e erros tipados, observabilidade mínima, testes (autorização obrigatória) e checklist de PR.
---

# Padrões de backend

> As convenções que o projeto já tem têm prioridade. Estas regras valem quando o projeto não define.
> Carregue também a skill da stack: `backend-go`, `backend-fastify` ou `backend-adonisjs`.

Fontes verificadas em 15/10/2026: RFC 9110, 9457, 7396, 9745, 8594, 9562, 9700 e 8725; OWASP API Security Top 10 2023 (a edição vigente: a lista "Top 10 2025" é a de aplicações web, outra coisa); OWASP Cheat Sheets; spec OpenAPI. Assuntos tratados em outras skills:
- idempotência, outbox, cache, retry e breaker, rate limit distribuído e multi-tenant/RLS: `architecture-scalability`;
- logs, métricas e traces: `observability`;
- banco: `sql-standards`.

## 1. Design de API HTTP
**Recursos e status codes:**
- Recursos no plural (`/v1/orders/{id}`), JSON e `camelCase` nos payloads.
- Os status codes:

| Situação | Status |
|---|---|
| Criou | **201** + `Location: /v1/orders/{id}` + corpo |
| Aceitou para processar depois (fila) | **202** + `Location` de um recurso de status |
| Sucesso sem corpo (DELETE, PUT) | **204** |
| Malformado: JSON inválido, tipo errado, campo desconhecido (falha de schema) | **400** |
| Sem credencial válida | **401** |
| Autenticado, sem permissão | **403** |
| Não existe, **ou é de outro tenant** (não revele que existe) | **404** |
| Conflito com o estado: unicidade, transição inválida, chave de idempotência em uso | **409** |
| `If-Match` divergente | **412** (ausente quando exigido: **428**) |
| Bem formado, mas viola regra de negócio | **422** |
| Rate limit | **429** + `Retry-After` |

- **Regra da equipe:** falha de schema dá 400 e regra de negócio dá 422. Seja consistente entre as rotas.

**Erros no formato RFC 9457 (Problem Details), sempre.**
```http
HTTP/1.1 422 Unprocessable Content
Content-Type: application/problem+json

{ "type": "https://api.<dominio>/problems/insufficient-balance", "title": "Insufficient balance",
  "status": 422, "code": "INSUFFICIENT_BALANCE", "detail": "Saldo de 10.00 é menor que 25.00",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "errors": [ { "pointer": "/items/0/qty", "code": "too_small", "detail": "must be >= 1" } ] }
```
- Campos:
  - **`type`** (URI estável) e **`title`** (fixo por `type`);
  - **`code`** é a extensão estável que o frontend usa para decidir o que fazer;
  - `errors[]` lista o erro por campo, com `pointer` em JSON Pointer para o body ou `parameter` para query e path;
  - **`traceId`** é o mesmo id que aparece nos logs.
- Nenhum cliente toma decisão com base no texto de `detail` ou `title`.
- Erro 5xx devolve corpo genérico. **Stack trace, SQL e mensagem do banco nunca saem.**
- Um único mapeador, na borda, traduz erro de domínio para Problem Details.

**Paginação e listas:**
- **Toda lista é paginada.**
  - Cursor opaco (base64url de `{sortKey, id}`), com `limit` padrão de 20 e **máximo de 100**.
  - A resposta tem o formato `{ "data": [...], "nextCursor": "..." | null }`.
  - O header `Link` com `rel="next"` é opcional.
- A ordenação é estável, sempre com desempate por `id`.
- `total` exato só quando o cliente pedir: `COUNT` em tabela grande é caro.
- **Filtros e ordenação** por **allowlist** (`?status=open&createdAfter=...&sort=-createdAt`). Campo fora da lista dá 400. Nunca interpole o nome do campo no SQL.
- Busca complexa: `POST /v1/<recurso>/search`. O método `QUERY` virou RFC 10008, mas o suporte em proxies e frameworks ainda é incerto.

**Atualização e concorrência:**
- **PATCH** com **JSON Merge Patch** (RFC 7396, `application/merge-patch+json`):
  - campo ausente fica como está e `null` limpa o campo;
  - o schema diz quais campos aceitam `null`;
  - JSON Patch (RFC 6902) só para operar dentro de arrays.
- **Concorrência otimista** em recurso editado por mais de uma pessoa:
  - o GET devolve `ETag: "v7"`, e a escrita envia `If-Match: "v7"`;
  - o SQL faz `UPDATE ... WHERE id = $1 AND version = $2`. Nenhuma linha afetada dá **412**.
- **Idempotência** em POST com efeito (criar, cobrar, disparar): header `Idempotency-Key` (ver `architecture-scalability`).

**Versionamento e depreciação:**
- **Prefixo `/v1`.** Mudança aditiva (campo novo opcional, rota nova) não muda a versão. Mudança que quebra cria `/v2`, que convive com a versão antiga.
- Depreciação:
  - `Deprecation: @<epoch>` (RFC 9745);
  - `Sunset: <HTTP-date>` (RFC 8594);
  - `Link: <doc>; rel="deprecation"`.
- **No mínimo 90 dias** entre o aviso e o desligamento, com métrica de uso por versão.

**Formatos:**
- **Data e hora:** RFC 3339 em **UTC com `Z`** (`2026-10-15T13:00:00.000Z`). Data pura vai como `2026-10-15`. Nunca hora local sem offset.
  - Fuso de exibição (fuso da planta, do usuário) é problema do cliente, ou campo explícito.
- **Dinheiro:** `{ "amount": "1234.56", "currency": "BRL" }` (string decimal) **ou** inteiro em centavos (`amountMinor`). Escolha um por projeto. **Nunca float.**
- **IDs públicos:** UUIDv7 (RFC 9562) ou ULID. **Não exponha id serial**, porque facilita enumeração e revela volume. O UUIDv7 revela o instante de criação: token secreto usa 32 bytes aleatórios.
- Enums com valores estáveis em `snake_case` ou `UPPER_CASE`.

## 2. Contrato (OpenAPI)
- **OpenAPI 3.1** é o padrão. A 3.2 (09/2025; 3.2.1 em 09/2026) só quando todo o ferramental suportar. O `openapi-typescript` ainda não suporta.
- **Code-first** (schema na rota → `@fastify/swagger`, `oapi-codegen`/huma no Go) é o padrão para API consumida pelo nosso frontend. **Contract-first** quando a API é pública ou de parceiro, ou quando front e back trabalham em paralelo.
- **O `openapi.json` gerado fica versionado no repo.** O CI:
  1. regenera o arquivo e falha se divergir do commitado;
  2. roda lint com `@redocly/cli` 2.x ou `spectral` 6.x. Regras da equipe:
     - `operationId` obrigatório;
     - 4xx e 5xx em `application/problem+json`;
     - `maxLength`/`maxItems` definidos;
     - `security` declarado em toda operação;
  3. roda **`oasdiff breaking`** (1.33) contra a `main`. Breaking sem `/v2` ou sem depreciação reprova.
- **Cliente tipado no frontend:**
  - `openapi-typescript` 7 + `openapi-fetch` (leve, só tipos) é o padrão;
  - `orval` 8 quando quiser hooks TanStack Query e Zod gerados;
  - `@hey-api/openapi-ts` ainda é 0.x: fixe a versão exata.
- Teste que a resposta real valida contra o schema do contrato. Contrato que diverge do runtime é pior que não ter contrato.

## 3. Segurança (OWASP API Security Top 10, 2023)
1. **BOLA (API1):**
   - **toda query por id filtra também por dono ou tenant** (`WHERE id = $1 AND tenant_id = $2`, ou RLS);
   - **teste cruzado obrigatório** (seção 6).
2. **Autenticação quebrada (API2):**
   - rate limit e bloqueio progressivo no login;
   - token de reset de uso único e curto;
   - nada de credencial em URL.
3. **Propriedades (API3):**
   - **allowlist de entrada**: schema com `additionalProperties: false` e DTO explícito, nunca `...body` direto no ORM. `role`, `tenantId`, `price` e `ownerId` nunca vêm do cliente;
   - **allowlist de saída**: schema de resposta.
4. **Consumo de recursos (API4):**
   - limite de body;
   - `limit` máximo;
   - timeout por request;
   - `statement_timeout`;
   - limite de upload e de itens em lote;
   - cota em operações caras (SMS, e-mail, relatório).
5. **Autorização por função (API5):** deny-by-default, permissão declarada na rota e `/admin` com guard e testes próprios.
6. **Fluxos sensíveis (API6):** cota, captcha ou confirmação adicional em cadastro, convite e compra.
7. **SSRF (API7):** URL vinda do usuário passa por:
   - allowlist de esquema e host;
   - **bloqueio de IP privado, loopback e link-local (169.254.169.254) depois de resolver o DNS**;
   - sem seguir redirect;
   - timeout.
8. **Configuração (API8):** headers de segurança, CORS restrito, sem stack trace, métodos não usados desligados e TLS.
9. **Inventário (API9):** o OpenAPI é o inventário. Versões com Sunset são desligadas de fato. Rota de debug não vai para produção.
10. **APIs de terceiros (API10):** valide a resposta com schema, use timeout e não siga redirect às cegas.

**Autenticação:**
- **SPA no mesmo site (padrão):**
  - sessão em cookie `HttpOnly; Secure; SameSite=Lax`, com id opaco e estado no Redis ou no Postgres, o que permite revogação imediata;
  - com `SameSite=None` ou entre subdomínios, use também token CSRF.
- **JWT:** para serviço a serviço, mobile ou IdP externo.
  - Access token de 5 a 15 min, com **refresh rotativo e detecção de reuso**: um refresh reutilizado revoga a família inteira (RFC 9700).
  - **Allowlist de algoritmos** (`EdDSA`, `ES256`, `RS256`). Rejeite `none` e nunca misture HS e RS na mesma chave.
  - Valide `iss`, `aud`, `exp` e `nbf` (tolerância de no máximo 60 s) e `typ`.
  - JWKS com cache e refetch quando aparecer um `kid` desconhecido (`jose` 6, `createRemoteJWKSet`).
  - **Nunca guarde JWT em `localStorage`.**
- **Senhas:**
  - **Argon2id com m = 19 MiB, t = 2, p = 1** (mínimo OWASP). Node: `@node-rs/argon2`. Go: `golang.org/x/crypto/argon2`.
  - Faça rehash no login quando os parâmetros mudarem.
  - bcrypt só em legado (custo ≥ 10). Ele **trunca em 72 bytes**, então limite a entrada.
- **CORS:**
  - allowlist exata de origens;
  - nunca `*` com credenciais;
  - não reflita o `Origin` nem use regex frouxa (`.*example.dev` casa `evilexample.dev`);
  - `Vary: Origin`.
- **Headers:** `Cache-Control: no-store` em respostas sensíveis, `X-Content-Type-Options: nosniff`, `Content-Security-Policy: frame-ancestors 'none'` e HSTS.
- **Rate limit:** por IP em rota anônima e por usuário ou tenant em rota autenticada, com store compartilhado.
- **Segredos:** vêm só do ambiente ou de secret do Swarm, validados no boot. Nunca no repo nem na imagem. Rotação documentada e secret scanning no CI.
- **LGPD nos logs:** redact de `authorization`, `cookie`, `password` e `token`. Não logue CPF, e-mail completo nem corpo de request: use o id do titular.
- **Dependências:**
  - `npm audit --audit-level=high` ou `osv-scanner` 2.x;
  - `govulncheck` no Go;
  - dependência nova precisa de justificativa e versão fixada no lockfile.

## 4. Arquitetura de código
- **Camadas:**
  - **transporte**: parse, auth, mapeamento de erro para HTTP;
  - **serviço ou caso de uso**: orquestra e abre a transação;
  - **repositório**: SQL.
  - O domínio **não importa** nada de HTTP nem do ORM.
- **DI manual na composition root** (`buildApp(config)`, `main.go`): repo → serviço → handler, por construtor. Nada de singleton importado nem `process.env` lido fora do módulo de config.
- **Erros de domínio tipados:**
  - Node: classe com `code` (`class NotFoundError extends DomainError`). Go: sentinel + `errors.Is`/`As`.
  - O mapeamento para Problem Details acontece **só na borda**.
  - Erro inesperado gera 500 genérico e log completo.
- **Validação em duas camadas:** schema na borda cuida da forma, e o domínio protege as invariantes (regras). Uma não substitui a outra.
- **Config 12-factor:** schema validado no boot (Zod, `envconfig`), falha rápida com mensagem clara, sem default silencioso para segredo. Mantenha o `.env.example` atualizado.
- **Trabalho lento ou externo** sai do request: vai para a fila (`backend-bullmq`) e a resposta é 202. Eventos de domínio usam **outbox** na mesma transação (`architecture-scalability`).
- **Feature flags:** OpenFeature (`@openfeature/server-sdk`), com provider por env no começo. Toda flag tem dono e data de remoção.

## 5. Observabilidade mínima
Detalhes em `observability`.
- Aceite e propague o `traceparent`. Devolva `X-Request-Id`. O mesmo id aparece nos logs e no `traceId` do erro.
- Uma linha de log por request: `method`, **template** da rota, `status` e `durationMs`.
- **Health:**
  - `/health/live` olha só o processo. **Nunca checa dependência**: se checasse, uma queda do banco reiniciaria todas as réplicas;
  - `/health/ready` checa banco, Redis e broker com timeout curto, e responde 503 durante o shutdown.
- Métricas RED por template de rota, com 4xx separado de 5xx.

## 6. Testes
- **Pirâmide:**
  - unitários do domínio, sem I/O;
  - **integração com banco real** (Testcontainers + migrations reais);
  - **API/contrato**: a resposta valida contra o OpenAPI, e os erros saem em `application/problem+json`.
- **Autorização é obrigatória em toda rota com id:**
  - usuário do tenant A lendo, alterando ou apagando recurso do tenant B → 404/403;
  - papel sem permissão → 403;
  - sem credencial → 401;
  - payload com `role` ou `tenantId` extra → ignorado ou 400.
- **Factories** (`buildUser({ ...overrides })`) em vez de fixtures globais. Cada teste cria os próprios dados.
- **Determinismo:**
  - relógio e gerador de id injetáveis;
  - nada de `sleep`: espere por condição.
- Cobertura é sinal, não meta. Caminhos de erro e de autorização têm teste, e **todo bug corrigido ganha teste de regressão**.

## 7. Checklist de PR de backend
- [ ] O contrato está atualizado (`openapi.json` commitado), com lint verde e `oasdiff` sem breaking (ou com `/v2` ou depreciação).
- [ ] Status codes corretos e erros em Problem Details com `code` estável.
- [ ] Entrada e saída por allowlist (sem `body` direto no ORM).
- [ ] Toda query filtra por dono ou tenant, **e há teste de BOLA**.
- [ ] Listas têm `limit` máximo e cursor. Filtros e ordenação por allowlist.
- [ ] Há limites de payload e timeouts. Chamadas externas têm timeout. URL vinda do usuário tem proteção contra SSRF.
- [ ] Escrita concorrente usa `If-Match`/versão. POST com efeito aceita `Idempotency-Key`.
- [ ] Transação nas escritas múltiplas, evento via outbox e sem N+1.
- [ ] Sem segredo no código, sem PII nos logs e com redact configurado.
- [ ] Config nova validada no boot e presente no `.env.example`.
- [ ] Testes de unidade, integração e autorização, determinísticos.
- [ ] Dependência nova justificada, auditada e fixada.
- [ ] Migration compatível com a versão anterior do código (`sql-standards`, `cd-practices`).
