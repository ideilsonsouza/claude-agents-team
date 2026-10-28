---
name: backend-adonisjs
description: Padrões para backend em AdonisJS 7 (Node 24, TypeScript, ESM) — estrutura e barrel files #generated, rotas e middleware, IoC com @inject, env validado, VineJS 4 (vine.create, validateUsing), Lucid 22 (schema classes geradas, transações com client trx, preload, migrations em produção), Transformers para respostas, auth com access tokens e Bouncer, limiter com Redis, exception handler e Problem Details, produção em Docker atrás do Traefik (trustProxy, APP_KEY, health checks, shutdown, @adonisjs/otel), filas com BullMQ, testes com Japa, advisories e versões mínimas seguras, upgrade v6→v7. Usar ao criar ou alterar código em projetos com @adonisjs/core.
---

# AdonisJS

Referência: **AdonisJS 7** (7.0.0 de 25/02/2026; latest **`@adonisjs/core` 7.6.0**). Requer **Node ≥ 24** e TypeScript 5.9 ou 6.0. Fontes: docs.adonisjs.com (v7), `adonisjs/starter-kits` e GitHub Security Advisories, verificados em 15/10/2026.
- Projeto ainda na v6: siga as convenções dele e use o checklist de upgrade no fim desta skill.
- Padrões gerais de API: `backend-standards`. Banco: `sql-standards` e `postgres-scaling`.

## Versões dos pacotes (out/2026)
| Pacote | Versão | Pacote | Versão |
|---|---|---|---|
| `@adonisjs/core` | **≥ 7.5.2** (7.6) | `@adonisjs/lucid` | 22.4 |
| `@vinejs/vine` | 4.4 | `@adonisjs/auth` | 10.1 |
| `@adonisjs/bouncer` | 4.0 | `@adonisjs/limiter` | 3.0 |
| `@adonisjs/redis` | **^10** (ver armadilha) | `@adonisjs/otel` | 1.2 |
| `@adonisjs/cors` / `shield` | 3.0 / 9.0 | `@japa/runner` | 5.4 |

- **`@adonisjs/redis` 11 ainda não é aceito como peer** pelo `limiter` 3 nem pelo `queue`. Fixe `^10` até eles atualizarem.
- Projeto novo: `npm init adonisjs@latest <app>`. Para API, escolha o kit `api` (ou `api-monorepo`). Os repositórios antigos de starter kit estão arquivados.

## Segurança: versões mínimas
- **`@adonisjs/core` ≥ 7.5.2.** É a primeira que puxa `@adonisjs/http-server` ^9.3.1 e `@adonisjs/bodyparser` ^11.0.4, cobrindo:
  - path traversal, prototype pollution e DoS no bodyparser/multipart;
  - XSS refletido no exception handler;
  - ReDoS;
  - open redirect.
- `@adonisjs/lucid` ≥ 22.0 (mass assignment), `@adonisjs/ally` ≥ 6.3.1 (bypass do `state` OAuth), `@adonisjs/inertia` ≥ 5.0.4.
- Confira o lockfile, e não só o `package.json`: `npm ls @adonisjs/http-server @adonisjs/bodyparser`.

## Estrutura
```
app/{controllers,services,models,validators,transformers,policies,middleware,exceptions}
database/{migrations,schema.ts (gerado),schema_rules.ts}
start/{routes,kernel,env,validator,health}.ts   config/   providers/   bin/server.ts
.adonisjs/   # gerado (barrels, tipos do cliente): não editar
```
- **Imports por subpath** (`#controllers/*`, `#services/*`, `#models/*`, `#generated/*`, `#transformers/*`, `#database/*`), declarados em `imports` no `package.json`.
- **Controllers finos:** validam a entrada, chamam um service e devolvem a resposta via transformer. A regra de negócio fica em `app/services`.
- **Rotas com barrel gerado** (o controller continua lazy-loaded):
```ts
import { controllers } from '#generated/controllers'
import { middleware } from '#start/kernel'
router.group(() => {
  router.get('orders/:id', [controllers.Orders, 'show'])
  router.post('orders', [controllers.Orders, 'store']).use(middleware.throttle())
}).prefix('/api/v1').use(middleware.auth())
```
  - O barrel é gerado pelo hook `indexEntities()` do `adonisrc.ts` (no dev e no build).
  - Na v7, rotas de controller **ganham nome automático**: dois verbos apontando para o mesmo método colidem e dão erro no boot. Use `.as('nome')`.
  - URLs: `urlFor('orders.show', { id })` (de `@adonisjs/core/services/url_builder`), que substitui o `router.makeUrl`.
- **Middleware** (`start/kernel.ts`):
  - `server.use`: toda requisição, inclusive 404;
  - `router.use`: só rotas encontradas (bodyparser, auth init, shield);
  - `router.named`: por rota (`middleware.auth()`).
  - O kit API já traz `force_json_response`.
- **IoC:** `@inject()` na classe (injeção por construtor) ou no método do controller. Sem o decorator, a dependência não é resolvida. Fora do HTTP, use `await app.container.make(Service)`. Em teste, `app.container.swap(Service, () => fake)`.
- **Providers:** ciclo `register → boot → start → ready → shutdown`. Conexões próprias (cliente MQTT, BullMQ) **abrem no `ready` e fecham no `shutdown`**. Na v7, os shutdown hooks rodam em **ordem reversa**.
- **Env validado no boot** (`start/env.ts`):
```ts
export default await Env.create(new URL('../', import.meta.url), {
  NODE_ENV: Env.schema.enum(['development', 'production', 'test'] as const),
  HOST: Env.schema.string({ format: 'host' }),
  PORT: Env.schema.number(),
  APP_KEY: Env.schema.secret(),
  APP_URL: Env.schema.string({ format: 'url', tld: false }),
  DB_HOST: Env.schema.string({ format: 'host' }),
  REDIS_HOST: Env.schema.string({ format: 'host' }),
})
```
  - `Env.schema.secret()` impede que o valor apareça em log.
  - O modificador `file:` lê o valor de um arquivo, o que funciona com Docker secrets.

## Validação (VineJS 4)
```ts
export const createOrderValidator = vine.create({
  customerId: vine.string().uuid(),
  items: vine.array(vine.object({ sku: vine.string().maxLength(64), qty: vine.number().min(1).max(10_000) })).minLength(1).maxLength(500),
  notes: vine.string().maxLength(2000).optional(),
})
const payload = await request.validateUsing(createOrderValidator)   // tipado; falha → 422
```
- Use `vine.create` (v7). O `vine.compile(vine.object(...))` ainda funciona.
- O `validateUsing` também valida `params`, `qs`, `headers` e `cookies` quando o schema declara essas chaves. **Não envolva em try/catch**: o handler global responde 422.
- **Limite tudo:** `maxLength`, `maxLength` de array e `min`/`max`. Isso é a defesa de consumo de recursos (API4 do OWASP).
- `unique`/`exists` do Vine **não substituem** a constraint UNIQUE e a FK do banco, porque há corrida entre a checagem e o insert. Trate o erro `23505` do banco como 409.
- Contexto como tenant ou usuário: `.withMetaData<{ tenantId: string }>()` e `validateUsing(v, { meta: { tenantId } })`, usados no `filter` do `unique`/`exists`.
- Na v4, o erro de `confirmed` sai no campo de confirmação, e schemas customizados precisam de `dataTypeValidator`.

## Lucid 22
- **Schema classes geradas (v7):** as migrations geram `database/schema.ts`, e o model estende a classe gerada. **Nunca edite `schema.ts`.** Ajustes de tipo ficam em `database/schema_rules.ts` (`schemaGeneration` em `config/database.ts`).
```ts
export default class Order extends compose(OrderSchema, SoftDeletes) {
  @belongsTo(() => Customer) declare customer: BelongsTo<typeof Customer>
}
```
- **Transações:** passe `{ client: trx }` em **toda** operação de dentro. Um model lido via `trx` herda a transação.
```ts
await db.transaction(async (trx) => {
  const order = await Order.create({ ...data, tenantId }, { client: trx })
  await OrderItem.createMany(items.map((i) => ({ ...i, orderId: order.id })), { client: trx })
  await Outbox.create({ type: 'order.created', payload: { id: order.id } }, { client: trx })
})
```
- **N+1:** use `.preload('customer')` e `withCount`/`withAggregate` (os valores vêm em `$extras`). Nunca acesse relação em loop sem preload.
- **Multi-tenant:** todo `query()` filtra por `tenantId` (escopo `withScopes` ou um service base). O teste de BOLA é obrigatório (`backend-standards`).
- **Mass assignment:** `create`/`merge`/`fill` **só com o payload já validado**. Nunca com `request.all()`. `tenantId`, `role` e `ownerId` vêm do contexto de auth.
- **Paginação:** `paginate(page, perPage)` com `perPage` máximo. Em tabela grande, use keyset (`where('id', '<', cursor)`).
- **Migrations:**
  - em produção, `node ace migration:run --force` como **etapa própria do deploy**, nunca no boot de cada réplica;
  - o Lucid usa lock e transação, mas a etapa separada evita espera e corrida;
  - **rollback em produção fica desligado** (`disableRollbacksInProduction`): corrija com uma migration nova (`sql-standards`, forward-only);
  - índice em tabela grande: `this.defer(async (db) => db.rawQuery('CREATE INDEX CONCURRENTLY ...'))` não resolve, porque roda em transação. Use migration sem transação (`static disableTransactions = true`) ou um script à parte.
- **Pool** (formato knex): `pool: { min: 0, max: 10, acquireTimeoutMillis: 30_000 }`. O total é **max × réplicas × processos** (api + worker), e precisa caber no `max_connections` ou no PgBouncer. Com PgBouncer em transaction mode, não use `SET` de sessão, advisory lock de sessão nem `LISTEN`.

## Respostas: Transformers (v7)
```ts
export default class OrderTransformer extends BaseTransformer<Order> {
  toObject() {
    return {
      ...this.pick(this.resource, ['id', 'status', 'createdAt']),
      customer: CustomerTransformer.transform(this.whenLoaded(this.resource.customer)),
    }
  }
}
return serialize(OrderTransformer.transform(order))
return serialize(OrderTransformer.paginate(page.all(), page.getMeta()))
```
- **Toda resposta passa por transformer.** É a allowlist de saída. Não devolva o model direto.
- Transformer **não faz query**. Relação sem preload vira erro: use `whenLoaded` quando ela for opcional.
- Variantes com `.useVariant('detail')`. Os tipos do cliente são gerados em `.adonisjs/client`.

## Auth, autorização e rate limit
- **Guards oficiais:** `session` (SPA no mesmo site, que é o padrão de `backend-standards`), `access_tokens` (token opaco com hash no banco, para mobile e integrações) e `basic`. **Não há guard JWT oficial**; se precisar de JWT, faça ADR.
```ts
const user = await User.verifyCredentials(email, password)   // tempo constante
const token = await User.accessTokens.create(user, ['*'], { expiresIn: '30 days' })
return { token: token.value!.release() }
```
- **Bouncer 4:** policies em `app/policies` (hook `indexPolicies()`). Use `await bouncer.with(OrderPolicy).authorize('update', order)` em toda ação sobre um recurso, com deny-by-default.
- **Hash:** o padrão do kit é scrypt. **Prefira argon2id** (driver `argon2`, parâmetros OWASP em `backend-standards`).
- **Limiter 3** com store `redis`:
```ts
export const throttle = limiter.define('api', (ctx) =>
  limiter.allowRequests(60).every('1 minute').usingKey(ctx.auth.user?.id ?? ctx.request.ip()).store('redis'))
```
  Login com `.blockFor('15 mins')` depois de N falhas. **Sem `trustProxy`, o `request.ip()` é o IP do Traefik**, e o limite passa a valer para todos os usuários juntos.

## Erros
- Handler global em `app/exceptions/handler.ts`. Exceções de domínio com `node ace make:exception`, cada uma com `static status` e `code`.
- **Formato:** o AdonisJS não tem Problem Details nativo. Sobrescreva o `handle` para responder `application/problem+json` (RFC 9457, formato em `backend-standards`), mapeando:

| Erro | Resposta |
|---|---|
| `E_VALIDATION_ERROR` | 400/422 com `errors[]` |
| `E_UNAUTHORIZED_ACCESS` | 401 |
| `E_AUTHORIZATION_FAILURE` | 403 (ou 404 para recurso de outro tenant) |
| `E_ROW_NOT_FOUND` | 404 |
| `E_TOO_MANY_REQUESTS` | 429 |

- Erro 5xx devolve corpo genérico com `traceId`. `debug = !app.inProduction`.
- Status pages só valem para HTML. Requisições `Accept: application/json` recebem JSON.

## Produção (Docker, Swarm, Traefik)
- **Build:** `node ace build` gera `build/` standalone, sem `.env`. Dockerfile multi-stage:
  1. deps: `npm ci`;
  2. build: `node ace build`;
  3. runtime: `node:24-<variante>` fixado, `COPY --from=build /app/build ./`, `npm ci --omit=dev`, `USER node`, `CMD ["node", "bin/server.js"]` (forma JSON, para o SIGTERM chegar ao Node).
- **Env:** `HOST=0.0.0.0`, `PORT=3333`, `NODE_ENV=production` e **`APP_KEY` igual em todas as réplicas**, porque ele cifra cookies e dados. O `APP_KEY` vem do secret do Swarm, nunca da imagem.
- **Proxy:** em `config/app.ts`, `trustProxy: proxyAddr.compile(['loopback', 'uniquelocal'])` (a overlay do Swarm é rede privada). `keepAliveTimeout` **maior** que o idle timeout do Traefik.
- **Health:** `node ace configure health_checks` cria `/health/live` e `/health/ready`.
  - O `ready` usa `DbCheck`, `RedisCheck` e `DiskSpaceCheck`.
  - **O healthcheck do contêiner aponta para `live`.** O `ready` fica para o Traefik e o deploy; se o contêiner checasse `ready`, uma queda do banco reiniciaria tudo.
  - O relatório completo do `ready` expõe pid e versão: proteja com header secreto ou rede interna.
- **Shutdown:** o `bin/server.ts` já chama `app.terminate()` no SIGTERM. A limpeza fica no `shutdown()` dos providers. O `stop_grace_period` do Swarm deve ser maior que o tempo de drenagem (`cd-practices`).
- **Logs:** pino em JSON no stdout (`observability`).
- **Traces:** `node ace add @adonisjs/otel`, que cria `bin/otel.ts`, importado no topo do `server.ts`. Configure com as variáveis `OTEL_*`.
- **Filas:** **BullMQ direto** (`backend-bullmq`), com o worker em processo separado (comando ace ou entrypoint próprio, sem HTTP).
  - `@adonisjs/queue` (0.6, sobre `@boringnode/queue`) é **experimental**: só com ADR e versão exata.
  - O `@rlanz/bull-queue` não suporta a v7.

## Testes (Japa)
```ts
// tests/bootstrap.ts: plugins assert(), pluginAdonisJS(app), apiClient(), authApiClient(app), dbAssertions(app)
runnerHooks.setup = [() => testUtils.db().migrate()]
// em cada grupo:
group.each.setup(() => testUtils.db().wrapInGlobalTransaction())   // v7: wrapInGlobalTransaction
test('tenant A não lê pedido de B', async ({ client }) => {
  const res = await client.get(`/api/v1/orders/${orderOfB.id}`).loginAs(userOfA)
  res.assertStatus(404)
})
```
- A transação global **não enxerga** código que abre outra conexão (worker, fila). Nesses testes, use `testUtils.db().truncate()`.
- Use banco real (Postgres em contêiner) e factories do Lucid. Rode `node ace test`, `npm run typecheck` e `npm run lint` no CI.

## Upgrade v6 → v7 (checklist)
1. Node 24 no local, no CI e na imagem.
2. Atualize todos os `@adonisjs/*`, o `@vinejs/vine` e os plugins `@japa/*`.
3. Troque `ts-node`/`@swc/core` por `@poppinss/ts-exec` (import no `ace.js`) e instale `youch` como dev.
4. `adonisrc.ts`: `hooks.init: [indexEntities()]`, remova `assetsBundler`, globs de teste `*.spec.{ts,js}` e hooks do assembler renomeados (`onBuildCompleted` virou `buildFinished`).
5. Remova `appKey` de `config/app.ts` e crie `config/encryption.ts` com o driver **`legacy`** para ler dados cifrados na v6.
6. `router.makeUrl` vira `urlFor`; `getDirname` vira `import.meta.dirname`; `cuid` vira UUID.
7. Adicione os imports `#generated/*`, `#transformers/*` e `#database/*` no `package.json`.
8. Revise nomes de rota que colidem, `request.all()` (agora inclui arquivos) e a ordem dos shutdown hooks.
9. Migre as respostas para transformers e os validators para `vine.create`, aos poucos.
10. Valide com `node ace build`, `npm run dev` e `node ace test`.

## Checklist de PR (AdonisJS)
- [ ] `@adonisjs/core` ≥ 7.5.2 no lockfile e Node 24.
- [ ] Validator com limites em todos os campos, e constraint no banco para unicidade e FK.
- [ ] Resposta via transformer, com preload antes (sem N+1).
- [ ] `{ client: trx }` em toda operação da transação. Evento via outbox.
- [ ] Policy do Bouncer e filtro por tenant em toda ação sobre recurso, com teste de BOLA.
- [ ] Erros em Problem Details, sem stack em produção.
- [ ] Rate limit com Redis e `trustProxy` correto.
- [ ] Migration em etapa separada, sem rollback em produção.
- [ ] `node ace test`, typecheck, lint e build verdes.
