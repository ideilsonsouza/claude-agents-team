---
name: backend-fastify
description: Padrões para backend em Fastify 5 (Node.js/TypeScript) — estrutura buildApp/server, encapsulamento e fastify-plugin, decorators da v5, ciclo de vida e hooks, validação e serialização com type provider Zod/TypeBox (allowlist de resposta), erros, logging pino e LogController, produção atrás do Traefik (trustProxy, keepAliveTimeout, timeouts, shutdown), segurança e CVEs, ecossistema @fastify/* com versões, testes com inject/Vitest/serviços locais e preparação para a v6.
---

# Backend em Fastify

Versão de referência: **Fastify 5.12.x**. Exija **≥ 5.12.6**, porque entre agosto e outubro de 2026 saíram oito advisories, quatro deles high. A v6 está em alpha (Node ≥ 24); o que for depreciado na v5 já fica fora do código novo. Docs: https://fastify.dev/docs/latest/. **As convenções do projeto têm prioridade** sobre esta skill.

## Estrutura
```
src/
  config.ts          # loadConfig(): Zod sobre process.env → Config tipado (falha no boot)
  app.ts             # buildApp(config) → FastifyInstance, sem listen (usado nos testes)
  server.ts          # loadConfig + buildApp + listen + close-with-grace
  plugins/           # infraestrutura com fastify-plugin: db, redis, auth, swagger, mqtt
  modules/<dominio>/ # routes.ts (encapsulado, com prefix), schemas.ts, service.ts, repository.ts
```
- TypeScript estrito e ESM. Imports explícitos são mais previsíveis que `@fastify/autoload` em TypeScript.
- **Config:** valide o `process.env` com Zod em `loadConfig()` e passe o resultado para `buildApp(config)`. Isso dispensa o `@fastify/env`.
```ts
// server.ts
const config = loadConfig();
const app = await buildApp(config);
closeWithGrace({ delay: 25_000 }, async ({ signal, err }) => {
  if (err) app.log.error({ err }, 'fatal'); else app.log.info({ signal }, 'shutting down');
  await app.close(); // preClose → drena requisições → onClose (pool, redis, workers, mqtt)
});
await app.listen({ host: '0.0.0.0', port: config.PORT }); // v5: listen só aceita objeto
```
- O `delay` do `close-with-grace` deve ser **menor** que o `stop_grace_period` do contêiner (ver `cd-practices`).

## Encapsulamento e plugins
- Todo `register` cria um contexto filho. Decorators, hooks, `setErrorHandler`, `setNotFoundHandler` e parsers valem só no contexto e nos filhos.
- **`fastify-plugin` só em infraestrutura** que precisa ser visível ao pai (db, redis, auth, mqtt, config). **Módulos de rota não usam `fp`**: ficam encapsulados com o próprio `prefix`, hooks e error handler.
- Plugin de infraestrutura: `await` na inicialização, `decorate` do recurso e `onClose` para fechar.
```ts
export default fp(async (app, opts: { url: string }) => {
  const pool = new Pool({ connectionString: opts.url });
  app.decorate('db', drizzle({ client: pool, schema }));   // Drizzle 1.0: { client: pool, relations }
  app.addHook('onClose', async () => { await pool.end(); });
}, { name: 'db' });
declare module 'fastify' { interface FastifyInstance { db: Db } }
```
- **Decorators na v5:** `decorateRequest`/`decorateReply` com objeto ou array **lança erro** (a referência seria compartilhada entre requisições). Inicialize com `null` e atribua num hook, ou use `{ getter() {} }`. Prefira `getDecorator`/`setDecorator` (5.3+), que validam a existência.
- **`await app.register(x)` antes de usar o que `x` decora.** `await app.ready()` carrega a árvore sem `listen`.

## Ciclo de vida
- **Requisição:** `onRequest` → `preParsing` → parsing → `preValidation` → validação (400) → `preHandler` → handler → `preSerialization` → `onSend` → `onResponse`.
  - Laterais: `onError` (só observa), `onTimeout` e `onRequestAbort`.
- **Aplicação:**
  - `onReady`: antes de aceitar requisições, para conectar e aquecer recursos.
  - `onListen`.
  - `preClose`: requisições ainda ativas; feche WebSockets e pare consumidores aqui.
  - `onClose`: depois do drain; feche pool, redis e workers.
- Auth em `onRequest` ou `preHandler` (via `@fastify/auth` ou decorator `authenticate`), aplicada **por escopo** e não repetida em cada rota.
- Hook `async` sem `await` custa uma promise por requisição. Registre hooks só no escopo que precisa.

## Validação e serialização
- **Padrão: Zod com `@fastify/type-provider-zod`** (oficial, Zod ≥ 4.2), porque a equipe já usa Zod. Use **TypeBox** (`@fastify/type-provider-typebox` 6 + o pacote `typebox` 1.x) quando o projeto já usar ou quando a performance de serialização for crítica (`fast-json-stringify`).
```ts
import { serializerCompiler, validatorCompiler, type ZodTypeProvider } from '@fastify/type-provider-zod';
const app = Fastify(opts).withTypeProvider<ZodTypeProvider>();
app.setValidatorCompiler(validatorCompiler);
app.setSerializerCompiler(serializerCompiler);

app.get('/v1/users/:id', {
  schema: {
    params: z.object({ id: z.uuid() }),
    response: { 200: userOut },   // allowlist: campo fora do schema não sai
  },
}, async (req) => app.users.findById(req.params.id));
```
- **Toda rota tem schema de `body`, `params`, `querystring` e `response`.** O schema de resposta é a **allowlist** que impede vazar `password_hash` e colunas internas.
- Na v5, JSON Schema precisa ser **completo** (`type: 'object', properties`). O `jsonShorthand` foi removido.
- Defaults do Ajv: `coerceTypes: 'array'`, `useDefaults`, `removeAdditional` (só com `additionalProperties: false`). **Não ligue `allErrors`** (risco de DoS).
- Em formatos de data/hora com Ajv, `date-time` exige timezone.
- **Não decida autorização com `request.headers` cru.** Use o dado validado (houve CVEs de bypass por header e Content-Type na 5.12.x).
- `bodyLimit` padrão é 1 MiB. Ajuste por rota (`bodyLimit` na rota) para endpoints de lote.

## Erros
```ts
app.setErrorHandler((err, req, reply) => {           // v5.6+: err é unknown. Formato: RFC 9457 (ver backend-standards)
  const problem = (status: number, code: string, title: string, extra = {}) =>
    reply.code(status).type('application/problem+json')
      .send({ type: `https://api.example.com/problems/${code.toLowerCase()}`, title, status, code, traceId: req.id, ...extra });
  if (hasZodFastifySchemaValidationErrors(err))
    return problem(400, 'VALIDATION_FAILED', 'Invalid request', { errors: err.validation.map((v) => ({ pointer: v.instancePath, detail: v.message })) });
  const status = (err as { statusCode?: number }).statusCode ?? 500;
  if (status >= 500) { req.log.error({ err }, 'unhandled'); return problem(500, 'INTERNAL', 'Internal error'); }
  return problem(status, (err as { code?: string }).code ?? 'ERROR', (err as Error).message);
});
```
- Erros de domínio: `@fastify/error` (`createError('USER_NOT_FOUND', 'User %s not found', 404)`) ou `@fastify/sensible` (`reply.notFound()`, `app.httpErrors`). O formato de resposta segue `backend-standards`.
- O error handler é **encapsulado**. Na v6, registrar dois no mesmo escopo lança erro, então use um por escopo.
- **Handler async:** retorne o valor **ou** `return reply.send(...)`. Nunca os dois, e nunca deixe o handler terminar sem resposta (a requisição fica pendurada).
- Lance sempre `Error`, nunca string.
- Nunca sirva dado protegido a partir de `setNotFoundHandler` (houve bypass de auth por esse caminho, CVE-2026-76169).

## Logging
```ts
Fastify({
  logger: { level: config.LOG_LEVEL, redact: { paths: ['req.headers.authorization', 'req.headers.cookie', '*.password'], censor: '[REDACTED]' },
            ...(config.NODE_ENV === 'development' && { transport: { target: 'pino-pretty' } }) },
  genReqId: (req) => validRequestId(req.headers['x-request-id']) ?? randomUUID(),
  logController: new LogController({ disableRequestLogging: (req) => req.url.startsWith('/health') }),
});
```
- Opções do pino vão em `logger`; instância pronta vai em **`loggerInstance`** (v5).
- Use **`LogController`** (5.10+) no lugar de `disableRequestLogging`/`requestIdLogLabel` (depreciados, saem na v6).
- `requestIdHeader` vem `false` por padrão. Se aceitar o id do cliente, valide o formato.
- Use `req.log` (child logger com `reqId`). Nada de `console.log`. Em produção, JSON no stdout e `pino-pretty` só em dev.

## Produção atrás do Traefik (Coolify/Dokploy)
```ts
Fastify({
  trustProxy: config.TRUSTED_PROXIES,  // CIDR da rede do proxy, ex.: '10.0.0.0/8,172.16.0.0/12'
  keepAliveTimeout: 95_000,            // maior que o idleConnTimeout do Traefik (90 s); senão, 502 intermitente
  handlerTimeout: 30_000,              // 5.8+: 503 e req.signal abortado. Repasse req.signal ao driver
  bodyLimit: 1_048_576,
});
```
- **`trustProxy`:**
  - **Nunca use número.** Desde a 5.12.1 o valor numérico vira "não confia em ninguém", sem erro. O `req.ip` passa a ser o IP do Traefik e o rate-limit trata todos como um só cliente.
  - `true` só se a porta do app não for publicada fora da rede do proxy.
- `return503OnClosing` (padrão `true`) e `forceCloseConnections: 'idle'` (padrão) dão um shutdown limpo junto com o `close-with-grace`.
- `@fastify/under-pressure` vem com todos os limites desligados (0). Configure `maxEventLoopDelay` e `maxHeapUsedBytes` se for usar.
- Healthchecks: `/health/live` (só o processo) e `/health/ready` (db, redis, broker), fora do log.

## Segurança
- `@fastify/helmet`.
- **`@fastify/cors` v11:** por padrão libera só `GET,HEAD,POST`. Declare `methods` para PUT, PATCH e DELETE.
- `@fastify/rate-limit` com `redis` quando houver mais de uma réplica. Depende de `trustProxy` correto. Para dispositivos, use `keyGenerator` pelo id do dispositivo.
- `@fastify/jwt` + `@fastify/auth`. **Fixe `fast-jwt` ≥ 6.3.4** no lockfile ou via `overrides`: houve muitos advisories críticos em 2026, e o range `^6.2.4` aceita versões vulneráveis.
- Evite `@fastify/middie`/`@fastify/express` (bypass crítico em 2026). Mantenha `@fastify/static` ≥ 10.1.6 e `@fastify/multipart` atualizado.
- Dependabot ligado. `npm audit` no CI (ver `cicd-github-actions`).

## Ecossistema (versões em out/2026)
| Necessidade | Pacote |
|---|---|
| OpenAPI | `@fastify/swagger` 9 + `@fastify/swagger-ui` 6 ou `@scalar/fastify-api-reference`; com Zod, `jsonSchemaTransform` |
| Banco | Drizzle com plugin `fp` próprio (`decorate('db')` + `pool.end()` no `onClose`); ver `backend-drizzle` |
| Redis | `@fastify/redis` 9 (ioredis 6) |
| Filas | BullMQ com plugin `fp` (`worker.close()` no `onClose`); ver `backend-bullmq` |
| MQTT | plugin próprio com `mqtt` (MQTT.js); ver `backend-fastify-mqtt` |
| Upload / WebSocket | `@fastify/multipart` 10, `@fastify/websocket` 11 (feche os sockets no `preClose`) |
| Traces | `@fastify/otel` (oficial, 0.x). O `@opentelemetry/instrumentation-fastify` está **deprecado** |
| Métricas | OTel SDK com push OTLP (padrão; ver `observability`). Modelo pull: `fastify-metrics` 14 (usa `@prometheus-io/client`; o `prom-client` foi deprecado) |
| Scaffold | `fastify-cli generate` (v8, template TS ESM). **Não use `create-fastify`** (abandonado) |

## Testes
```ts
let app: FastifyInstance;
beforeAll(async () => { app = await buildApp(testConfig({ DATABASE_URL: pg.getConnectionUri() })); await app.ready(); });
afterAll(async () => { await app?.close(); });   // sem close, o Vitest fica pendurado (onClose não roda)
it('GET /v1/users/:id → 404', async () => {
  const res = await app.inject({ method: 'GET', url: `/v1/users/${randomUUID()}` });
  expect(res.statusCode).toBe(404);
});
```
- Use `app.inject()`, sem porta. Vitest (ou `node:test`).
- Banco real: localmente, o Postgres de `/worksapce/opt` (regra "Serviços locais" do `CLAUDE.md`) com banco `test_<projeto>_<id>` criado no `beforeAll` e apagado no `afterAll`, mesmo se o teste falhar; no CI, o serviço da esteira. Rode as migrations reais no `beforeAll`. Não use Testcontainers nem crie containers.
- Teste também os caminhos de erro (400 de validação, 401, 404, 409) e verifique que a resposta não contém campos fora do schema.
- Verificação: `npm run lint && npm run typecheck && npm test` (ajuste aos scripts do projeto).

## Preparar para a v6 (já no código novo)
- Node 24 nas imagens novas.
- `routerOptions: {...}` no lugar de opções de router no topo.
- `logController` no lugar de `disableRequestLogging`/`requestIdLogLabel`.
- Um `setErrorHandler` por escopo.
- Tipos `FastifyBaseLogger` (não `FastifyLoggerInstance`) e `FastifyPluginAsync` (não `FastifyPlugin`).
- Não escreva em `reply.sent`: use `reply.hijack()`.
