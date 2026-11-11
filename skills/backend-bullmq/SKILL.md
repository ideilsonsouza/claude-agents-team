---
name: backend-bullmq
description: "Padrões para filas e workers com BullMQ 6 (Node/TypeScript sobre Redis): conexão, retries, idempotência, job schedulers, concorrência, rate limit, stalled jobs, graceful shutdown e migração v5→v6. Usar ao criar ou alterar Queue, Worker, FlowProducer ou jobs com bullmq."
---

# BullMQ

Versão de referência: **BullMQ 6.3.x** (a 6.0.0 é de 30/07/2026; a linha 5 recebe correções na dist-tag `release-v5.x`). Fontes: https://docs.bullmq.io (em especial "Going to production") e o guia `guide/migrations/migrate-from-v5-to-v6.md`. Verifique a versão no `package.json` do projeto: as diferenças entre v5 e v6 estão marcadas abaixo.

## Instalação (v6)
- **`ioredis` não vem mais junto:** virou peer dependency opcional. **Instale explicitamente** com `npm i bullmq ioredis`. Sem ele, a conexão Redis falha.
- Também são peers opcionais `redis` (node-redis v5, via `createNodeRedisClient`), `pg` (backend PostgreSQL) e `bullmq-otel` (≥ 2, telemetria).
- **Backend PostgreSQL** (v6, via `createPostgresBackend`) existe, mas é novo. O Redis continua sendo o mais testado e é o **padrão da equipe**. Use Postgres só com ADR.

## Conexão (ioredis)
- **Worker:** `maxRetriesPerRequest: null` (obrigatório; o BullMQ força e avisa). Deixe `enableOfflineQueue` no padrão (`true`).
- **Queue (produtor em API HTTP):** `enableOfflineQueue: false`, para falhar rápido em vez de enfileirar comandos com o Redis fora.
- `retryStrategy` com backoff exponencial (mínimo ~1 s, máximo ~20 s; é o padrão das conexões criadas pelo BullMQ).
- **Redis com `maxmemory-policy noeviction`** (qualquer outra política corrompe as filas) e AOF ligado (`appendfsync everysec`). Verifique isso no compose ou na infra.
- Use `prefix` por ambiente ou serviço quando o Redis for compartilhado.
- Workers e QueueEvents duplicam a conexão internamente (comandos bloqueantes). Reaproveitar uma instância `IORedis` ainda abre mais de uma conexão.
- **v6:** `Queue#client`, `Queue#redisVersion`, `Worker#blockingClient` e `FlowProducer#client` foram removidos. Para acesso cru ao Redis, mantenha a sua própria instância `IORedis` (ou use `getBackend()`). `Worker#waitUntilReady()` resolve `void`.

## Produzindo jobs
- O payload fica **em texto claro no Redis**: envie IDs e referências, não segredos. Se precisar de dado sensível, criptografe.
- Defina os padrões em `defaultJobOptions` da Queue:
```ts
const queue = new Queue('emails', {
  connection,
  defaultJobOptions: {
    attempts: 5,
    backoff: { type: 'exponential', delay: 1000, jitter: 0.5 },
    removeOnComplete: { age: 86_400, count: 1_000 },
    removeOnFail: { age: 7 * 86_400 },
  },
});
```
- **Sempre** configure `removeOnComplete` e `removeOnFail`. Sem isso o Redis cresce sem limite.
- Valide o payload (ex.: Zod) no produtor **e** no processor. O tipo genérico `Job<Data>` não valida nada em runtime.
- `defaultJobOptions` não se aplica a jobs criados por `FlowProducer`: passe as opções em cada nó.
- **v6:** nós de flow sem `opts.jobId` recebem **UUID** (antes eram ids incrementais). Não dependa do formato do id.

## Jobs recorrentes: Job Schedulers
- **v6 removeu os repeatable jobs legados:** saíram `add(..., { repeat })`, `addBulk` com `repeat`, `getRepeatableJobs`, `removeRepeatable`, `removeRepeatableByKey` e a classe `Repeat`. Use **job schedulers** (disponíveis desde a 5.16):
```ts
await queue.upsertJobScheduler(
  'relatorio-diario',                                   // id estável: o upsert evita duplicação entre réplicas e deploys
  { pattern: '0 15 3 * * *', tz: 'America/Sao_Paulo' }, // ou { every: 60_000 }; UTC = tz: 'UTC' (o "utc: true" saiu)
  { name: 'relatorio', data: { tipo: 'diario' }, opts: { attempts: 3, removeOnFail: 1000 } },
);
// await queue.getJobSchedulers();  await queue.removeJobScheduler('relatorio-diario');
```
- **Rode o `upsertJobScheduler` no boot.** É idempotente e vale para várias réplicas: o job é criado **uma vez por cluster**. Este é o jeito padrão de fazer cron com várias réplicas.
- O próximo job só é gerado quando o anterior **começa** a ser processado. Fila lotada atrasa a recorrência.
- Jobs de scheduler não aceitam `jobId` customizado: diferencie pelo `name`.
- O `RepeatOptions` não aceita mais `currentDate`, `utc` e `nthDayOfWeek`.

## Retries e erros
- Retry só acontece com `attempts > 1`. Lance sempre instâncias de `Error`.
- **Erro permanente** (dado inválido, recurso inexistente): `throw new UnrecoverableError(msg)` vai direto para failed, sem gastar tentativas. **Na v6, `job.discard()` foi removido**: use `UnrecoverableError`.
- `backoff`: `fixed` ou `exponential` (`2^(attempts-1) * delay`). Estratégia própria via `settings.backoffStrategy` no Worker.

## Idempotência e deduplicação
- O processor **deve ser idempotente**: o job pode rodar mais de uma vez (retry, stall, crash).
- Para evitar duplicatas na entrada:
  - `jobId` customizado: o job é ignorado se já existir um com o mesmo id.
  - `deduplication: { id }` (simple): ignora enquanto o original não terminar.
  - `deduplication: { id, ttl }` (throttle).
  - `deduplication: { id, ttl, extend: true, replace: true }` + `delay` (debounce).
  - `deduplication: { id, keepLastIfActive: true }`: se já houver um job **ativo** com o mesmo id, guarda os dados mais recentes e cria **um** novo job quando o ativo terminar. No máximo 1 ativo e 1 esperando, e o dado mais recente vence. Bom para sync e recálculo.
- **v6:** a opção `debounce`, o `Job#debounceId` e o evento `debounced` foram removidos. Use `deduplication`, `Job#deduplicationId` e o evento `deduplicated` (em `QueueEvents`).
- Deduplicação **não é permitida em nós pai** de flow (v6).
- `job.remove()` manual desliga a deduplicação daquele id. Também há `queue.removeDeduplicationKey(id)` e `queue.getDeduplicationJobId(id)`.
- Efeitos externos (gravar, cobrar, enviar) usam chave de idempotência ou upsert no destino.

## Worker e concorrência
```ts
const worker = new Worker<Data>('emails', processor, {
  connection, concurrency: 10, limiter: { max: 100, duration: 1000 },
});
worker.on('failed', (job, err) => log.error({ jobId: job?.id, err }, 'job failed'));
worker.on('error', (err) => log.error({ err }, 'worker error'));
```
- `concurrency` só ajuda em processor **assíncrono / I/O-bound**. Para escalar, prefira mais instâncias de worker.
- Limite global entre todas as instâncias: `queue.setGlobalConcurrency(n)`. O `limiter` já é global por fila.
- Rate limit dinâmico (ex.: 429 de API externa): `await worker.rateLimit(ms); throw Worker.RateLimitError();`.
- Registre listener de `error` em Worker e Queue. Sem ele, erros de conexão podem derrubar o processo.
- **v6:** `pause()`/`resume()` ficaram assíncronos. Sempre use `await worker.resume()` / `await queue.resume()`.
- **v6:** o estado `paused` saiu de `JobType` e de `getJobCounts()`. Jobs de fila pausada aparecem como `waiting`. Ajuste dashboards e métricas que liam `paused`.

## Stalled jobs e CPU
- Um job fica stalled quando o worker não renova o lock a tempo (event loop bloqueado). Depois de `maxStalledCount` ele vai para failed.
- Trabalho CPU-bound: use **sandboxed processor** (arquivo separado passado ao `Worker`, de preferência com `useWorkerThreads: true`) ou quebre o trabalho em partes menores. Não aumente `lockDuration`/`stalledInterval` como primeira solução. Sandboxed processors não têm acesso ao contexto do app (DI, pools): crie as conexões no próprio arquivo.
- Job longo: atualize o progresso com `job.updateProgress()` (na v6.2+, `Job<Data, Result, Name, Progress>` tipa o progresso) e respeite timeouts próprios.

## Graceful shutdown
```ts
for (const sig of ['SIGINT', 'SIGTERM'] as const) {
  process.once(sig, async () => { await worker.close(); await queue.close(); await connection.quit(); process.exit(0); });
}
```
- `worker.close()` para de pegar jobs e **espera os ativos terminarem, sem timeout próprio**. Garanta que o `stop_grace_period` do contêiner seja maior que o job típico. O job que não terminar vira stalled e é reprocessado por outro worker (por isso, idempotência).
- No Fastify, feche no hook `onClose` do plugin (ver `backend-fastify`).
- Trate `unhandledRejection` e `uncaughtException` com log e saída controlada.

## Telemetria e monitoramento
- OpenTelemetry com `bullmq-otel` (≥ 2 para BullMQ 6): `new Queue(name, { connection, telemetry: new BullMQOtel('svc') })`, e o mesmo no Worker.
- **v6:** os atributos usam `JobState` (saíram `JobStatus` e `JobFinishedTimestamp`), as métricas falam em `state` e não `status`, e o `clean()` reporta só a contagem. **Adaptador de telemetria próprio precisa implementar `Meter#createGauge()`** (agora obrigatório).
- Alerte sobre: jobs `failed` crescendo, `waiting` acumulando (worker parado ou lento), stalled frequentes e `error` de conexão.

## Migração v5 → v6 (checklist)
1. Atualize para a última v5 (`release-v5.x`).
2. Troque todo `repeat` por `upsertJobScheduler`. **Ainda na v5**, migre os dados: leia `getRepeatableJobs()`, crie o scheduler equivalente, confira com `getJobSchedulers()` e remova o legado com `removeRepeatableByKey()`. **A v6 lança erro se encontrar metadados de repeatable legado no Redis.**
3. Troque `debounce`/`debounceId`/`debounced` por `deduplication`/`deduplicationId`/`deduplicated`, e `job.discard()` por `UnrecoverableError`.
4. Instale `ioredis` explicitamente. Remova usos de `queue.client`, `worker.blockingClient` e `redisVersion`.
5. Adicione `await` em `resume()`. Revise código que lê o estado `paused` e ids numéricos de flow.
6. Atualize `bullmq-otel` para ≥ 2 e revise adaptadores de telemetria próprios.
7. Faça o deploy da v6 só quando **todos** os produtores e workers estiverem prontos.

## Testes
- Use Redis real (container ou db dedicado, ex.: `/15`). Limpe com `queue.obliterate({ force: true })` entre suítes.
- Teste o processor como função pura recebendo um `Job` fake. Teste a integração Queue→Worker à parte, aguardando os eventos `completed`/`failed` via `QueueEvents`.
- Feche worker, queue, queueEvents e a conexão no `afterAll`, ou o Vitest fica pendurado.
