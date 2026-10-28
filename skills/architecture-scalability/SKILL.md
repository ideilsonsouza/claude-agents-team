---
name: architecture-scalability
description: Arquitetura e escalabilidade para a stack da equipe (Node/Fastify, Postgres/TimescaleDB, Redis/BullMQ, MQTT, Docker Swarm) — monólito modular em monorepo com processos separados (api/worker/ingest/scheduler), critérios para separar serviço, fronteiras de módulo no CI, serviços sem estado e escala horizontal no Swarm (orçamento de conexões, memória do V8), confiabilidade (outbox/inbox, Idempotency-Key, timeout, retry com jitter, circuit breaker, bulkhead, backpressure, load shedding, rate limit), cache (cache-aside, stampede, invalidação), multi-tenant com RLS, quando adotar Kafka/NATS/Redis Streams e licenças, SLO/capacidade com template de NFRs e checklist de revisão. Usar ao desenhar ou revisar arquitetura, decidir separação de serviços, planejar escala ou escrever a seção de NFRs do design.md.
---

# Arquitetura e escalabilidade

Versões verificadas em 14/10/2026 (npm e GitHub). Esta skill é a referência do `architect`. Para os detalhes de cada ferramenta, consulte:
- banco: `postgres-scaling`, `sql-standards` e `backend-drizzle`;
- filas: `backend-bullmq`;
- MQTT: `mqtt-contract`, `mqtt-broker` e `backend-fastify-mqtt`;
- métricas e carga: `observability`;
- deploy: `cd-practices`.

**Princípio:** a solução mais simples que atende aos NFRs medidos. Toda peça nova de infraestrutura precisa de ADR (`adr-template`) com o custo operacional para uma equipe de 2 a 5 pessoas.

## 1. Monólito modular, vários processos
**Padrão da equipe:** um repositório (monorepo pnpm), um banco e **uma imagem com vários entrypoints**. Cada entrypoint vira um serviço próprio no Swarm, com réplicas, limites e healthcheck separados.
```
apps/
  api/        # Fastify (HTTP)
  worker/     # Workers BullMQ e relay do outbox
  ingest/     # Consumidor MQTT (ack após persistir)
  scheduler/  # upsertJobScheduler no boot (pode ser o próprio worker)
packages/
  <modulo>/   # domínio: src/index.ts é a única API pública ("exports" no package.json)
  platform/   # infra compartilhada: config, logger, db, redis, telemetria (não é lixão de utils)
```
- **Os apps são finos:** só montam os módulos (wiring). Regra de negócio fica nos módulos.
- **O consumidor MQTT nunca roda dentro da API.** Ingestão de 1k a 20k msg/s não pode dividir event loop com o HTTP.
- **Fronteiras:**
  - um módulo importa outro **só pelo `index.ts`**;
  - um módulo **não lê nem grava tabelas de outro**: chama a API pública ou consome um evento (outbox);
  - no CI, o `dependency-cruiser` (18.x) bloqueia `no-circular`, `not-to-unresolvable` e imports de `packages/*/src/internal`. No editor, use o `eslint-plugin-boundaries` (7.x).
- **Ferramentas:** pnpm workspaces com Turborepo (2.x). O Nx (23.x) só se a equipe quiser geradores e `enforce-module-boundaries`.

**Separar em serviço com deploy e banco próprios** só quando houver **pelo menos 2** destes critérios (registre em ADR):
1. escala muito diferente do resto;
2. isolamento de falha necessário;
3. ciclo de release ou dono independente;
4. runtime diferente (CPU-bound, sandbox, outra linguagem).

Não bastam "ficar mais organizado", um time diferente ou "para o futuro".

**Anti-padrão:** microserviços que dividem o mesmo banco formam um **monólito distribuído**, com o pior dos dois mundos.

## 2. Sem estado e escala horizontal (Swarm)
- **Toda réplica é descartável.** Escale com `replicas` no Swarm, com **1 processo Node por contêiner**. **Não use `node:cluster`**: ele duplica pools e esconde processos do orquestrador.
- O que impede escalar, e onde cada coisa deve ficar:

| Estado | Onde fica |
|---|---|
| Sessão e cache | Redis (L1 em memória só com bus de invalidação) |
| Cron | Job scheduler do BullMQ (`upsertJobScheduler`), nunca `setInterval` ou `node-cron` na API |
| Upload e arquivos | Object storage (S3 ou MinIO), nunca o disco do contêiner |
| WebSocket e SSE | Redis pub/sub ou adapter (`@socket.io/redis-streams-adapter`). Sticky cookie no Traefik (`loadbalancer.sticky.cookie=true`) é paliativo |
| Locks | Advisory lock no Postgres ou lock no Redis com TTL |

- **Orçamento de conexões ao banco:** `Σ (réplicas × pool.max)` de todos os processos precisa ficar **abaixo de `max_connections` menos a reserva** (admin, migrations, réplica). Passou de cerca de 100, use PgBouncer (ver `postgres-scaling`). Escalar réplicas sem refazer essa conta derruba o banco.
- **Memória:** fixe o heap do V8 em cerca de **75% do limite do contêiner** (`NODE_OPTIONS=--max-old-space-size=<MB>`) e confira com `v8.getHeapStatistics().heap_size_limit`. Sem isso, o contêiner é morto pelo OOM killer em vez de o GC agir.
- **`UV_THREADPOOL_SIZE`:** o padrão é 4. Aumente (8 a 16) só com muito `crypto` (bcrypt/scrypt), `zlib`, `fs` ou `dns.lookup`, e meça antes.
- **Escalar o quê:**
  - `api`: por CPU e latência;
  - `ingest`: por atraso de ingestão (shared subscription `$share`, `clientId` estável por réplica);
  - `worker`: por idade do job mais antigo.
- **Ordem de ataque a gargalo:** medir → corrigir query, índice ou lote → cache → mais réplicas → separar processo → nova peça de infra.

## 3. Confiabilidade
### Outbox e inbox (padrão para eventos)
- **Dual write é proibido.** Gravar no banco e depois publicar na fila (ou no MQTT) perde ou duplica eventos quando o processo cai entre os dois passos.
- **Outbox:**
  - o evento entra na tabela `outbox(id uuid, aggregate, type, payload jsonb, created_at, published_at)` **na mesma transação** do dado de negócio;
  - um relay no `worker` lê os pendentes em lote (`FOR UPDATE SKIP LOCKED`, `ORDER BY created_at`), publica no BullMQ com **`jobId = outbox.id`** (deduplica) e marca `published_at`;
  - limpe os já publicados por idade.
- **Inbox no consumidor:** `inbox(message_id PK)` gravado **na mesma transação** do efeito. Se o insert der conflito, já foi processado.
- Implemente à mão: são cerca de 100 linhas e as libs (`pg-transactional-outbox` 0.6) ainda estão abaixo da 1.0. Uma fila no próprio Postgres (`pg-boss` 12, `graphile-worker` 0.18) dispensa outbox porque o enqueue é transacional. Essa troca exige ADR, porque o padrão da equipe é BullMQ.

### Idempotência em HTTP
- POST que cria recurso, cobra ou dispara efeito aceita o header **`Idempotency-Key`**. O draft IETF expirou sem virar RFC, mas o padrão de mercado se mantém.
- Guarde `(tenant, key) → hash do corpo, status, resposta` por 24 h.
  - Se a chave chegar de novo, devolva a mesma resposta.
  - Se chegar com outro corpo, ou enquanto o original ainda estiver em processamento, devolva **409**.

### Timeout, retry, breaker e bulkhead
- **Timeout em toda chamada externa:**
  - HTTP: `fetch(url, { signal: AbortSignal.timeout(ms) })` (undici);
  - Postgres: `statement_timeout` por role;
  - Redis: `commandTimeout` no ioredis (produtor);
  - Fastify: timeouts de servidor (ver `backend-fastify`).
- **Retry:**
  - só em operação idempotente e erro transitório;
  - backoff exponencial com **full jitter** e limite de tentativas (`p-retry` 8 ou o backoff do BullMQ);
  - **uma camada de retry só**: retry no cliente, no serviço e na fila ao mesmo tempo gera tempestade.
- **Circuit breaker** em dependência externa instável (ERP, APIs de terceiros):
  - `cockatiel` 4 combina retry, breaker, timeout e bulkhead;
  - `opossum` 10 serve para um breaker simples (exige Node ≥ 22);
  - exporte o estado do breaker como métrica.
- **Bulkhead:**
  - limite de concorrência por dependência (`p-limit` ou o bulkhead do cockatiel);
  - filas BullMQ separadas por classe de carga, para que um relatório pesado não atrase alarmes.

### Backpressure e load shedding
- **API:** `@fastify/under-pressure` 9 com `maxEventLoopDelay` e `maxEventLoopUtilization`. Sob pressão, responde **503 com `Retry-After`** e marca a réplica como não pronta.
- **Ingest:**
  - ack MQTT só depois de persistir;
  - `receiveMaximum` baixo (50 a 200);
  - o broker segura a fila (ver `backend-fastify-mqtt`).
- **Rate limit:** `@fastify/rate-limit` 11 com Redis e `keyGenerator` por tenant ou API key, para que o limite seja o mesmo entre réplicas.
- **Degradação planejada:** defina o que falha "aberto" (dashboard mostra dado em cache marcado como desatualizado) e o que falha "fechado" (comando a máquina sem confirmação não executa). Funções não essenciais ficam atrás de feature flag.

## 4. Cache
- **Só depois de medir.** Primeiro query, índice e continuous aggregate. Cache é a última camada, não a primeira.
- **Padrão:** cache-aside com `bentocache` 1.6. Ele traz L1 em memória + L2 Redis, bus de invalidação entre réplicas, grace period (stale-if-error), proteção contra stampede e timeouts. Alternativas: `cache-manager` 7 + `keyv` 6, ou `async-cache-dedupe` 3 (single-flight).
- **Regras:**
  - **chave sempre com tenant** (`t:<tenantId>:...`);
  - TTL com **jitter** de ±10 a 20%;
  - single-flight ou lock em chave quente;
  - invalide no evento de escrita (consumidor do outbox), e não só por TTL;
  - não guarde erro em cache.
- **HTTP:**
  - `ETag` + `Cache-Control: private, max-age=<s>` em GET de dashboards;
  - CDN **só** para assets e conteúdo público;
  - nunca CDN na frente de resposta autenticada multi-tenant.

## 5. Multi-tenant
- **Padrão: schema compartilhado com `tenant_id` + Row Level Security.**
  - Drizzle: `pgPolicy(...)` ou `pgTable.withRLS(...)`, e `entities: { roles: true }` no `drizzle.config.ts` para gerenciar roles.
  - Policy: `using: sql\`tenant_id = current_setting('app.tenant_id')::uuid\`` + `withCheck`.
- **Contexto por transação:** toda request e todo job abrem uma transação e executam `select set_config('app.tenant_id', $1, true)` (`true` = LOCAL).
  - `SET` de sessão vaza entre requisições no pool e no PgBouncer.
  - Nunca use `sql.raw` para isso.
- **Armadilhas:**
  - o **dono da tabela e superusers ignoram RLS**: a app usa um role sem `BYPASSRLS` e não é dona das tabelas (ou use `FORCE ROW LEVEL SECURITY`);
  - `TRUNCATE` ignora RLS;
  - views precisam de `security_invoker`;
  - jobs BullMQ levam `tenantId` no payload;
  - índices compostos começam por `tenant_id`;
  - teste o isolamento (o tenant A não lê nem grava dados de B) como teste automatizado obrigatório;
  - hypertable com RLS combinada com compressão ou continuous aggregate tem restrições: teste antes de adotar.
- **Outros modelos:**
  - schema por tenant: evite, porque multiplica as migrations;
  - **banco (ou instalação) por tenant:** quando há contrato, regulação, tenant muito grande ou planta on-prem. É o caso natural do edge industrial.
- **Noisy neighbor:** rate limit e cotas por tenant, `statement_timeout` por role e filas por classe de tenant. Grupos por tenant no BullMQ são recurso do BullMQ Pro.

## 6. Mensageria: o que usar
| Necessidade | Padrão |
|---|---|
| Planta → nuvem, telemetria, comandos | **MQTT** (`mqtt-contract`) |
| Trabalho assíncrono, retries, agendamento | **BullMQ** |
| Fan-out simples, notificação entre réplicas | Redis pub/sub (sem garantia) |
| Vários consumer groups com replay curto (horas) | **Redis Streams** |
| Replay de dias, vários consumidores independentes, CDC, event sourcing | **NATS JetStream** (primeira opção) ou Kafka |

- **Adote NATS ou Kafka só com pelo menos 2 destes:**
  - retenção ou replay de dias com vários consumidores;
  - mais de cerca de 50k msg/s sustentados;
  - CDC ou event sourcing entre sistemas;
  - times desacoplados.
- **Para equipe pequena, NATS JetStream** (nats-server 2.15, binário único, Apache-2.0) tem o menor custo operacional. Kafka 4.x (KRaft, Apache-2.0) só com motivo forte. Clientes Kafka: `@platformatic/kafka` ou `@confluentinc/kafka-javascript`. Evite o `kafkajs`, parado desde 2023.
- **Licenças:**
  - Redis 8 é RSALv2/SSPLv1/AGPLv3; o **Valkey 9 (BSD) é a alternativa livre** (confirme a compatibilidade com o BullMQ antes de trocar);
  - Redpanda é BSL e proíbe oferecer serviço de streaming;
  - EMQX é BSL, com cluster pago (ver `mqtt-broker`);
  - registre a licença no ADR.

## 7. Capacidade, SLO e NFRs
- **SLIs (2 ou 3 por serviço):**
  - **API:** disponibilidade (% de respostas não-5xx) e latência p95;
  - **ingest:** atraso de ingestão (`receivedAt − ts` de origem, p99) e taxa de quarentena ou perda (saltos de `seq`);
  - **filas:** idade do job mais antigo.
- **SLO inicial: 99,5% ao mês**, o que dá cerca de 3 h 36 min de error budget. Budget esgotado congela features e prioriza confiabilidade. Os alertas por burn rate estão em `observability`.
- **Lei de Little (L = λ × W):** dimensiona o que fica "em voo". Exemplo: 20k msg/s × 50 ms = 1.000 mensagens em voo, o que define o tamanho de lote, o pool e o `receiveMaximum` somado entre as réplicas.
- **Headroom de 30 a 50% no pico:** CPU abaixo de 60 a 70% e pool abaixo de 70%. Isso exige **evidência de teste de carga** (k6 para HTTP, emqtt-bench para MQTT) num ambiente igual ao de produção.
- **Custo:** estime em R$ por mês, por planta e por tenant (VPS, storage com compressão, backup, tráfego).

Template para o `design.md`:
```markdown
## Requisitos não funcionais
- Carga: pico ___ req/s | ___ msg/s por planta; crescimento ___ %/ano
- Latência: p95 API < ___ ms; atraso de ingestão p99 < ___ s
- Disponibilidade (SLO): ___ %/mês; error budget ___ min
- Durabilidade: RPO ___ / RTO ___; perda MQTT tolerada: ___
- Multi-tenant: modelo (RLS/instância), limites por tenant
- Escala: réplicas por processo; gargalo conhecido; headroom
- Degradação: o que falha aberto x fechado
- Evidência: teste de carga (link) | custo estimado R$ ___/mês
```

## 8. Checklist de revisão de arquitetura
1. As fronteiras de módulo estão explícitas e verificadas no CI?
2. Cada processo (api, worker, ingest, scheduler) escala e falha de forma independente?
3. Não há estado na réplica? Onde ficam sessão, upload, cron e locks?
4. Toda escrita que gera evento usa outbox? Os consumidores são idempotentes (inbox, `jobId`, `(deviceId, seq)`)?
5. Toda dependência externa tem timeout, retry com jitter numa camada só e breaker quando for instável?
6. Existe backpressure (under-pressure, ack MQTT após persistir) e 503 com `Retry-After`?
7. O orçamento de conexões ao banco fecha com o número máximo de réplicas?
8. O tenant está na chave de cache, no job e na transação (RLS)? O role da app não tem BYPASSRLS? Existe teste de isolamento?
9. Há SLIs e SLO definidos, e evidência de carga com headroom?
10. As licenças da infraestrutura são compatíveis com o modelo de negócio?
11. A mudança é compatível com a versão anterior no deploy (expand/contract, jobs antigos na fila; ver `cd-practices`)?
12. Toda decisão estrutural tem ADR?

**Anti-padrões que reprovam o design:**
- monólito distribuído;
- dual write;
- estado em memória;
- cron dentro da API;
- chamada externa sem timeout;
- retry sem idempotência;
- cache sem tenant;
- `SET` de sessão com pool;
- consumidor MQTT dentro da API;
- Kafka "para o futuro";
- pool × réplicas acima de `max_connections`;
- heap sem limite no contêiner.
