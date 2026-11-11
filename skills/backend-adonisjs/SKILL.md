---
name: backend-adonisjs
description: "Padrões para backend em AdonisJS 7 (Node 24, TypeScript, ESM): estrutura e barrels, rotas, VineJS, Lucid (N+1, transação, forUpdate, hooks), auth, Bouncer, erros RFC 9457, env, BullMQ, eventos, pino, testes Japa, portão e armadilhas. Usar ao criar ou alterar projetos com @adonisjs/core."
---

# AdonisJS

Padrões gerais de API: `backend-standards`. Banco: `sql-standards`. Filas: `backend-bullmq`. Telemetria: `observability`. Armadilhas transversais: `backend-pitfalls` e `backend-pitfalls/references/node.md`. As convenções que o projeto já tem têm prioridade.

## Versões (fontes: docs.adonisjs.com v7 via context7 `/adonisjs/v7-docs` e `/adonisjs/lucid` 22.x; registry npm; consultados em 2026-11-10)
| Pacote | Versão | Observação |
|---|---|---|
| `@adonisjs/core` | **7.6.0** (latest) | exige Node >= 24 (`engines`); mínimo seguro 7.5.2 |
| `@adonisjs/lucid` | 22.4.2 | |
| `@vinejs/vine` | 4.4.0 | |
| `@adonisjs/auth` / `bouncer` | 10.1.0 / 4.0.1 | |
| `@adonisjs/limiter` | 3.0.1 | peer `@adonisjs/redis` **^10** |
| `@adonisjs/redis` | 11.0.0 (latest) | com `limiter`, fixe `^10`; `@adonisjs/queue` 0.7 já aceita 11 |
| `@adonisjs/otel` / `@japa/runner` | 1.2.4 / 5.4.0 | |
| `@adonisjs/queue` | 0.7.0 | experimental: só com ADR |

- Projeto novo: `npm init adonisjs@latest <app>` (kit `api`). Projeto na v6: siga as convenções dele; checklist em `references/upgrade-v7.md`.
- Versões mínimas seguras (advisories): `references/seguranca-versoes.md`. Confira o lockfile, não só o `package.json`.

## Estrutura e convenções
```
app/{controllers,services,models,validators,transformers,policies,middleware,exceptions,events,listeners}
database/{migrations,schema.ts (gerado),schema_rules.ts}
start/{routes,kernel,env,validator,health}.ts   config/   providers/   bin/server.ts
.adonisjs/   # gerado (barrels, tipos do cliente): não editar
```
- **Imports por subpath** (`#controllers/*`, `#services/*`, `#models/*`, `#generated/*`, `#transformers/*`, `#database/*`) declarados em `imports` no `package.json`.
- **Barrel files:** `#generated/controllers` (e `events`, `listeners`, `policies`) são gerados pelo hook `indexEntities()` do `adonisrc.ts`, no dev e no build. Não escreva barrel à mão e não edite `.adonisjs/`.
- **Controllers finos:** validam, chamam um service, devolvem via transformer. Regra de negócio em `app/services`. O domínio não importa HTTP.
- **IoC:** `@inject()` na classe ou no método do controller; sem o decorator a dependência não resolve. Fora do HTTP: `await app.container.make(Service)`. Em teste: `app.container.swap(Service, () => fake)`.
- **Providers:** `register, boot, start, ready, shutdown`. Conexões próprias (MQTT, BullMQ) abrem no `ready` e fecham no `shutdown` (ordem reversa na v7).

## Rotas e controllers
```ts
import { controllers } from '#generated/controllers'
import { middleware } from '#start/kernel'
router.group(() => {
  router.get('orders/:id', [controllers.Orders, 'show'])
  router.post('orders', [controllers.Orders, 'store']).use(middleware.throttle())
}).prefix('/api/v1').use(middleware.auth())
```
- Rotas de controller **ganham nome automático**; dois verbos no mesmo método colidem no boot: use `.as('nome')`. URLs: `urlFor('orders.show', { id })` (`@adonisjs/core/services/url_builder`).
- Middleware em `start/kernel.ts`: `server.use` (toda requisição, inclusive 404), `router.use` (só rotas achadas), `router.named` (por rota).
- Prefixo `/api/v1`, plural, status codes e paginação: `backend-standards`.

## Validação (VineJS 4)
```ts
export const createOrderValidator = vine.create({
  customerId: vine.string().uuid(),
  items: vine.array(vine.object({ sku: vine.string().maxLength(64), qty: vine.number().min(1).max(10_000) })).minLength(1).maxLength(500),
  notes: vine.string().maxLength(2000).optional(),
})
const payload = await request.validateUsing(createOrderValidator)   // tipado; falha vira erro de validação
```
- **Não envolva em try/catch**: o handler global responde. Valida também `params`, `qs`, `headers` e `cookies` se o schema declarar.
- **Limite tudo** (`maxLength`, tamanho de array, `min`/`max`): defesa de consumo de recursos.
- `unique`/`exists` do Vine **não substituem** UNIQUE e FK do banco (corrida): trate `23505` como 409.
- Contexto (tenant, usuário): `.withMetaData<{ tenantId: string }>()` e `validateUsing(v, { meta })`.
- Falha de schema = 400 e regra de negócio = 422 (`backend-standards`) e o mapeamento é feito no handler (veja a seção Erros); confira o status que o projeto devolve hoje.

## Lucid 22 e migrations
- **Schema classes geradas:** migrations geram `database/schema.ts` e o model estende a classe gerada. Nunca edite `schema.ts`; ajustes em `database/schema_rules.ts`.
- **N+1:** `.preload('customer')`, `withCount`/`withAggregate` (valores em `$extras`). Nunca acesse relação em loop sem preload.
- **Transação:** `{ client: trx }` em **toda** operação de dentro; model lido via `trx` herda a transação. Efeito de domínio via outbox na mesma transação (`architecture-scalability`).
```ts
await db.transaction(async (trx) => {
  const order = await Order.query({ client: trx }).where('id', id).forUpdate().firstOrFail()   // trava a linha
  if (order.status !== 'open') throw new InvalidTransition()      // revalide sob a trava
  order.useTransaction(trx); order.status = 'paid'; await order.save()
  await Outbox.create({ type: 'order.paid', payload: { id } }, { client: trx })
})
```
  `forUpdate()`, `forShare()`, `skipLocked()` e `noWait()` existem no query builder (docs Lucid 22.x). Mesma ordem de travas em fluxos irmãos (`backend-pitfalls` seção 1).
- **Hooks** (`@beforeSave`, `@afterCreate`, `@beforeFind`...): só para invariantes locais (hash de senha com `$dirty.password`). **Não** faça I/O externo nem escrita em outras tabelas em hook: roda sem controle da transação e não cobre escrita feita pelo query builder (`query().update()`), que não passa pelo hook de instância.
- **Multi-tenant:** todo `query()` filtra por `tenantId` (escopo ou service base); teste de BOLA obrigatório.
- **Mass assignment:** `create`/`merge` só com payload validado, nunca `request.all()`. `tenantId`, `role`, `ownerId` vêm do contexto de auth.
- **Paginação:** `paginate(page, perPage)` com teto; tabela grande, keyset.
- **Pool** (knex): `pool: { min: 0, max: 10, acquireTimeoutMillis: 30_000 }`. Total = max x réplicas x processos (api + worker) cabe no `max_connections`/PgBouncer. PgBouncer em transaction mode: sem `SET` de sessão, advisory lock de sessão ou `LISTEN`.
- **Migrations:** na equipe, **migration é do `dba`**; o backend pede coluna/índice no relatório e não cria. Em produção, `node ace migration:run --force` como etapa própria do deploy, nunca no boot de cada réplica; rollback desligado (`disableRollbacksInProduction`), corrija com migration nova (`sql-standards`). Índice `CONCURRENTLY` exige `static disableTransactions = true`.

## Respostas: Transformers (v7)
```ts
export default class OrderTransformer extends BaseTransformer<Order> {
  toObject() {
    return { ...this.pick(this.resource, ['id', 'status', 'createdAt']),
      customer: CustomerTransformer.transform(this.whenLoaded(this.resource.customer)) }
  }
}
return serialize(OrderTransformer.transform(order))
```
- **Toda resposta passa por transformer** (allowlist de saída); nunca devolva o model. Transformer não faz query; `withCount` lança se o valor não foi carregado, `whenCounted`/`whenAggregated` são opcionais.

## Auth, Bouncer e rate limit
- **Guards** (`node ace add @adonisjs/auth --guard=session|access_tokens|basic_auth`): `session` para SPA no mesmo site (padrão de `backend-standards`); `access_tokens` (opaco, hash no banco) para mobile e integração. Sem guard JWT oficial: ADR.
```ts
const user = await User.verifyCredentials(email, password)   // tempo constante
const token = await User.accessTokens.create(user, ['*'], { expiresIn: '30 days' })
```
- **Bouncer 4:** policies em `app/policies` (`indexPolicies()`); `await bouncer.with(OrderPolicy).authorize('update', order)` em toda ação sobre recurso, deny-by-default. Anti-escalada vale em toda rota que concede papel.
- **Hash:** prefira argon2id (driver `argon2`; parâmetros em `backend-standards`).
- **Limiter 3** com store `redis`: `limiter.allowRequests(60).every('1 minute').usingKey(ctx.auth.user?.id ?? ctx.request.ip())`; login com `.blockFor('15 mins')`. Sem `trustProxy`, `request.ip()` é o do proxy e o balde é único.

## Erros (RFC 9457)
- Handler global `app/exceptions/handler.ts` (`ExceptionHandler`): `handle` monta a resposta, `report` só loga (nunca responde). Exceções de domínio: `node ace make:exception`, com `status` e `code`.
- O Adonis **não** tem Problem Details nativo: sobrescreva `handle` e responda `application/problem+json` (formato em `backend-standards`), com `code` estável e `traceId`.

| Erro | Resposta |
|---|---|
| `E_VALIDATION_ERROR` | 400/422 com `errors[]` (`pointer`) |
| `E_UNAUTHORIZED_ACCESS` | 401 |
| `E_AUTHORIZATION_FAILURE` | 403 (404 se recurso de outro tenant) |
| `E_ROW_NOT_FOUND` | 404 |
| `E_TOO_MANY_REQUESTS` | 429 + `Retry-After` |

- 5xx: corpo genérico. `debug = !app.inProduction`. Status pages só valem para HTML.

## Config e env tipado
- `start/env.ts`: `Env.create(new URL('../', import.meta.url), { PORT: Env.schema.number(), APP_KEY: Env.schema.secret(), DB_HOST: Env.schema.string({ format: 'host' }), ... })`. Falha no boot se faltar.
- `Env.schema.secret()` e a classe `Secret` (`@adonisjs/core/helpers`) saem como `[redacted]` no log. O prefixo `file:` lê o valor de arquivo (Docker secrets).
- Leia config via `env.get`/`config/*.ts`, nunca `process.env` solto. Mantenha o `.env.example` em dia.

## Filas e eventos
- **Filas: BullMQ direto** (`backend-bullmq`), worker em processo separado (comando ace ou entrypoint sem HTTP). `@adonisjs/queue` é experimental; `@rlanz/bull-queue` não suporta a v7.
- **Eventos in-process:** `emitter` (`@adonisjs/core/services/emitter`) com classes `node ace make:event` (`BaseEvent`) e listeners. Efeito que precisa sobreviver a falha vai por outbox + fila, não por `emitter`. Em teste: `using fake = emitter.fake()` e `fake.assertEmitted(events.X)`.

## Logs (pino)
- `config/logger.ts`: JSON no stdout, `level` por env, `redact: { paths: ['password', '*.password', 'authorization', 'cookie', 'token'] }` (fast-redact). Não logue CPF, e-mail completo nem corpo de request. Correlação e métricas: `observability`.

## Testes (Japa)
```ts
// tests/bootstrap.ts: assert(), pluginAdonisJS(app), apiClient(), authApiClient(app), dbAssertions(app)
runnerHooks.setup = [() => testUtils.db().migrate()]
group.each.setup(() => testUtils.db().wrapInGlobalTransaction())   // rollback a cada teste
test('tenant A não lê pedido de B', async ({ client }) => {
  (await client.get(`/api/v1/orders/${orderOfB.id}`).loginAs(userOfA)).assertStatus(404)
})
```
- **Banco real** (Postgres local ou da esteira, banco próprio por execução) e factories do Lucid. **Sem mock de banco.**
- A transação global **não vale** para código que abre outra conexão (worker, fila, `forUpdate` concorrente): use `testUtils.db().truncate()` e dados próprios.
- Obrigatórios por rota com id: BOLA entre tenants, 401, 403 por papel, payload com `role`/`tenantId` extra. Relógio injetável.

## Portão
```bash
npx tsc --noEmit            # typecheck (ou npm run typecheck, se existir)
npm run lint                # eslint
node ace test               # Japa, banco de teste
node ace build              # produz build/
```
- Rode também `~/.claude/scripts/portao.sh <dir>` e cole a última linha no relatório. Script ausente no `package.json`: diga "não existe no projeto".

## Armadilhas do Adonis
Gerais: `backend-pitfalls` e `references/node.md` dela. Específicas:
1. **Esquecer `{ client: trx }`** (ou `useTransaction`) em um passo: a escrita sai da transação e não faz rollback.
2. **`@inject()` ausente:** dependência chega `undefined` em runtime.
3. **`request.all()` no model** (mass assignment) e, na v7, ele inclui arquivos.
4. **Model devolvido direto** em vez de transformer: vaza coluna nova.
5. **Hook com efeito externo**, ou esperando que ele rode em `query().update()`.
6. **`validateUsing` em try/catch** engole o 422/400 e quebra o Problem Details.
7. **`trustProxy` ausente:** rate limit e logs veem o IP do proxy.
8. **`@adonisjs/redis` 11 com `limiter` 3:** peer exige ^10.
9. **Migration no boot** de cada réplica, ou rollback em produção.
10. **`APP_KEY` diferente entre réplicas:** cookie e dado cifrado não abrem.
11. **Healthcheck do contêiner apontando para `ready`:** queda do banco reinicia tudo.

Produção (Docker, Swarm, Traefik, health, shutdown, OTel): `references/producao.md`.

## Checklist de PR (AdonisJS)
- [ ] `@adonisjs/core` >= 7.5.2 e Node 24. Validator com limites, UNIQUE/FK no banco.
- [ ] Resposta via transformer com preload (sem N+1). `{ client: trx }` na transação; `forUpdate` com revalidação sob a trava.
- [ ] Bouncer e filtro por tenant em toda ação sobre recurso, com teste de BOLA.
- [ ] Erros em Problem Details; rate limit com Redis e `trustProxy`.
- [ ] Migration pedida ao `dba`; etapa separada no deploy, sem rollback em produção.
- [ ] Portão verde: typecheck, lint, `node ace test`, `node ace build`.
