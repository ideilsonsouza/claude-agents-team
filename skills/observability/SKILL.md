---
name: observability
description: "Observabilidade e performance de serviços Node.js (Fastify, BullMQ, MQTT.js, Postgres): OpenTelemetry, Grafana/Prometheus/Loki/Tempo, métricas, logs pino, alertas por SLO, k6, profiling. Usar ao instrumentar serviço, montar monitoramento, escrever alertas ou investigar lentidão e vazamento."
---

# Observabilidade e performance

Versões verificadas em 14/10/2026 (npm, GitHub releases, Docker Hub):

| Componente | Versão |
|---|---|
| OTel JS: pacotes estáveis do SDK | **2.12** |
| OTel JS: pacotes experimentais (`sdk-node`, exporters) | **0.223** |
| OTel JS: `auto-instrumentations-node` | **0.81** |
| OTel JS: `@opentelemetry/api` | **1.9** |
| `@fastify/otel` | 0.21 |
| `bullmq-otel` | 2.0 |
| pino | 10.4 |
| Collector contrib | 0.162.0 |
| Grafana | 13.1 |
| Prometheus | 3.15 (LTS 3.13) |
| Loki | 3.7 |
| Tempo | 3.1 |
| Alloy | 1.20 |
| Alertmanager | 0.34 |
| k6 | 2.3 |

- **O OTel JS 3.0 está em RC** (canary): não adote ainda. Fixe a linha 2.x/0.22x.
- Liga com: `backend-fastify` (logger e health), `backend-bullmq` (telemetria), `backend-fastify-mqtt` (métricas do consumidor), `postgres-scaling` (alertas do banco), `architecture-scalability` (SLOs) e `cd-practices` (verificação pós-deploy).

## 1. Padrão da equipe
```
apps (OTel SDK) ──OTLP──► OTel Collector ──► Tempo (traces)
                                         └─► Prometheus 3 (métricas, receiver OTLP)
contêineres (stdout JSON) ──► Alloy ──► Loki (logs)
exporters (postgres, redis, node, cAdvisor) ◄── scrape do Prometheus
Prometheus ──► Alertmanager ──► Telegram/Slack/e-mail      Grafana lê tudo
Uptime externo (Gatus) fora da VPS de produção
```
- **A stack de observabilidade roda numa VPS separada da produção**, com cerca de 3 a 4 GB de RAM para Grafana, Prometheus, Loki, Tempo, Collector e Alloy. Se ela cair junto com a produção, ninguém fica sabendo.
- **Alternativa enxuta:** VictoriaMetrics + VictoriaLogs (Apache-2.0, menos de 1,5 GB) com Grafana. Para UI única, SigNoz (ClickHouse, cerca de 8 GB). A escolha vai num ADR.
- **Licenças:** Grafana, Loki e Tempo são AGPLv3. Não há problema em uso interno sem modificação; registre no ADR.
- A imagem `grafana/otel-lgtm` serve **só para dev e CI**.
- **O Promtail chegou ao EOL em 03/2026.** Use **Grafana Alloy** (`discovery.docker` + `loki.source.docker`). Para migrar: `alloy convert --source-format=promtail`.

## 2. OpenTelemetry no serviço
```ts
// src/telemetry.ts → carregado ANTES do app: node --import ./dist/telemetry.js dist/server.js
import { register } from 'node:module';
register('@opentelemetry/instrumentation/hook.mjs', import.meta.url);   // ESM
import { NodeSDK } from '@opentelemetry/sdk-node';
import { getNodeAutoInstrumentations } from '@opentelemetry/auto-instrumentations-node';
import FastifyOtelInstrumentation from '@fastify/otel';

export const sdk = new NodeSDK({
  instrumentations: [
    getNodeAutoInstrumentations({
      '@opentelemetry/instrumentation-fs': { enabled: false },
      '@opentelemetry/instrumentation-dns': { enabled: false },
      '@opentelemetry/instrumentation-net': { enabled: false },
      '@opentelemetry/instrumentation-pino': { disableLogSending: true },  // logs seguem por stdout
    }),
    new FastifyOtelInstrumentation({ registerOnInitialization: true }),
  ],
});
sdk.start();
```
- **Configure por variável de ambiente:**
  - `OTEL_SERVICE_NAME` (api, worker, ingest);
  - `OTEL_RESOURCE_ATTRIBUTES=service.version=<tag da imagem>,deployment.environment.name=<env>`;
  - `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318`;
  - `OTEL_METRIC_EXPORT_INTERVAL=15000` (o padrão é 60 s).
- **ESM:** a doc oficial ainda usa `--experimental-loader=@opentelemetry/instrumentation/hook.mjs`. O `register()` acima funciona na prática, mas **valide no primeiro projeto** que os spans de `pg` e `ioredis` aparecem. Se o build for CJS, use `--require`, que é o mais estável.
- **Fastify:** use **`@fastify/otel`**, o plugin oficial. O `@opentelemetry/instrumentation-fastify` está deprecado e saiu do bundle. O `@fastify/otel` depende do `instrumentation-http`, que vem no bundle. Para tirar health e metrics do trace, use `config: { otel: false }` na rota.
- **No bundle:**
  - `pg` e `ioredis`, com a semconv **estável** de DB (`db.system.name`, `db.query.text`, `db.query.summary`);
  - `undici` (fetch);
  - `pino`, que injeta `trace_id`/`span_id` no log;
  - `runtime-node` (event loop, heap, GC);
  - HTTP com a semconv estável (`http.server.request.duration`).
- **BullMQ:** `telemetry: new BullMQOtel({ tracerName, meterName, enableMetrics: true })` no Queue e no Worker (`bullmq-otel` ≥ 2).
  - O gauge `bullmq.queue.jobs` só existe se **um** processo chamar `queue.recordJobCountsMetric()` a cada 15 a 30 s, por exemplo no `scheduler`.
- **MQTT** não tem instrumentação: propague o W3C `traceparent` pelas **User Properties** do MQTT 5.
```ts
// publicador (comandos)
const carrier: Record<string, string> = {};
propagation.inject(context.active(), carrier);
client.publish(topic, payload, { qos: 1, properties: { userProperties: carrier } });
// consumidor
const parent = propagation.extract(ROOT_CONTEXT, packet.properties?.userProperties ?? {});
await tracer.startActiveSpan('ingest telemetry', { kind: SpanKind.CONSUMER }, parent, async (span) => {
  try { /* persistir */ } finally { span.end(); }
});
```
  - O nome do span usa o **template** do tópico (`telemetry`), nunca o tópico cru.
  - Lote com mensagens de vários gateways usa **span links**, não parent.
  - Gateway sem `traceparent`: o trace começa no consumidor, e isso é aceitável.
- **Shutdown:** `await sdk.shutdown()` **depois** de fechar app, worker e cliente MQTT, para fazer o flush. Chame no `onClose` final do Fastify ou no fim do handler de SIGTERM, dentro do `stop_grace_period`.
- **Sampling:**
  - no app, `parentbased_traceidratio` com `OTEL_TRACES_SAMPLER_ARG=1` (volume baixo);
  - o corte fica no Collector, por **tail sampling**: mantenha erros, traces lentos e uma amostra de cerca de 10% do resto.

## 3. Collector
```yaml
receivers:
  otlp: { protocols: { grpc: { endpoint: 0.0.0.0:4317 }, http: { endpoint: 0.0.0.0:4318 } } }
processors:
  memory_limiter: { check_interval: 1s, limit_percentage: 80, spike_limit_percentage: 20 }
  tail_sampling:
    decision_wait: 10s
    policies:
      - { name: errors, type: status_code, status_code: { status_codes: [ERROR] } }
      - { name: slow,   type: latency,     latency: { threshold_ms: 1000 } }
      - { name: rest,   type: probabilistic, probabilistic: { sampling_percentage: 10 } }
  batch: {}
exporters:
  otlp_grpc/tempo: { endpoint: tempo:4317, tls: { insecure: true } }
  otlp_http/prom:  { endpoint: http://prometheus:9090/api/v1/otlp }
extensions: { health_check: { endpoint: 0.0.0.0:13133 } }
service:
  extensions: [health_check]
  pipelines:
    traces:  { receivers: [otlp], processors: [memory_limiter, tail_sampling, batch], exporters: [otlp_grpc/tempo] }
    metrics: { receivers: [otlp], processors: [memory_limiter, batch], exporters: [otlp_http/prom] }
```
- Imagem `otel/opentelemetry-collector-contrib:0.162.0`, com a **tag fixada**.
- A ordem dos processors importa: `memory_limiter` → sampling → `batch`.
- Os exporters foram renomeados para `otlp_grpc`/`otlp_http`. Exemplos antigos ainda usam `otlp/<nome>`.
- **Swarm:**
  - **uma réplica**, porque o tail sampling exige todos os spans do trace na mesma instância;
  - limite de memória com `GOMEMLIMIT` em cerca de 80% dele;
  - rede overlay interna, **sem publicar 4317 e 4318**;
  - a imagem é distroless (sem curl): faça o healthcheck pela extensão `health_check` a partir de fora.
- Para que os gateways da fábrica enviem traces, exponha o OTLP com TLS e autenticação (extensão `bearertokenauth`) ou use a VPN.
- **Prometheus 3:**
  - `--web.enable-otlp-receiver`;
  - `otlp.promote_resource_attributes: [service.name, service.namespace, service.version, deployment.environment.name]`;
  - `storage.tsdb.out_of_order_time_window: 30m`.
  - A métrica OTel `http.server.request.duration` vira `http_server_request_duration_seconds_*`.

## 4. Métricas
- **Padrão:** métricas pelo **OTel SDK**, com push OTLP para o Collector e dele para o Prometheus. É um pipeline só, e o BullMQ e o runtime já falam OTel.
- **O `prom-client` foi deprecado** e substituído por `@prometheus-io/client` 0.16 (Node 22+). Use o modelo pull (`/metrics` + `fastify-metrics` 14, que já usa o pacote novo) só se houver motivo.
- **O que todo serviço expõe:**

| Camada | Métricas |
|---|---|
| HTTP (RED) | `http.server.request.duration` por `http.route`, método e status |
| Runtime | `nodejs.eventloop.delay.p99`, `nodejs.eventloop.utilization`, `v8js.memory.heap.used`, `v8js.gc.duration` |
| BullMQ | `bullmq.queue.jobs{state}`, `bullmq.job.duration`, taxa de `bullmq.jobs.failed`, idade do job mais antigo |
| Consumidor MQTT (próprias) | `mqtt_messages_received_total{class}`, `mqtt_messages_quarantined_total{reason}`, `mqtt_reconnects_total`, `mqtt_connected` (0/1), histograma `mqtt_ingest_lag_seconds` (`receivedAt − ts`), `mqtt_seq_gaps_total`, `mqtt_gateway_last_seen_timestamp_seconds{gateway}` |
| Infra (scrape) | `node_exporter`, cAdvisor, `postgres_exporter` 0.20 (role `pg_monitor`), `redis_exporter` 1.93 |
| Broker | EMQX: `/api/v5/prometheus/stats` (exige API key na 6.3). Mosquitto: sem exporter mantido; o consumidor assina `$SYS/broker/#` com um usuário só-leitura e expõe gauges |

- **Cardinalidade:**
  - **nunca** use como label `deviceId`, `userId`, `tenantId` (salvo poucos tenants conhecidos), `jobId`, tópico cru, URL crua ou mensagem de erro;
  - `gateway` só é aceitável como label se o inventário for pequeno e fechado (dezenas);
  - para investigar um device, use traces e logs, não métricas.
- **Histogramas:** buckets explícitos alinhados ao SLO (ex.: 0,05 / 0,1 / 0,3 / 0,5 / 1 / 2,5 / 5 s). Native histograms (estáveis no Prometheus 3.8+) são opcionais, e recording rules por `le` não funcionam com eles.

## 5. Logs
- **pino 10** com JSON no stdout. **Nunca use `pino-pretty` em produção.**
  - O `trace_id` é injetado pela instrumentação.
  - O nível vem de `LOG_LEVEL`.
  - Um log por evento relevante, não por mensagem MQTT recebida.
- **LGPD e segredos:** o melhor é **não logar**. O `redact` é a rede de segurança:
```ts
pino({ redact: { paths: ['req.headers.authorization', 'req.headers.cookie', '*.password', '*.token', '*.secret', '*.cpf', '*.email'], censor: '[REDACTED]' } })
```
- **Coleta:** use Alloy → Loki. Labels do Loki só de baixa cardinalidade (`service`, `env`, `level`); o resto é campo JSON, que se consulta com `| json`.
- **Docker:** driver `json-file` com `max-size: 10m` e `max-file: 3`. Sem isso, o disco da VPS enche.
- **Retenção:**
  - logs, 7 a 14 dias (`retention_period` + compactor);
  - traces, 7 dias;
  - métricas, 15 a 30 dias;
  - acima disso, use recording rules ou downsampling.

## 6. Alertas e SLO
- **Alerte sobre sintoma, não sobre causa.** Pagine (acordar alguém) só por SLO queimando ou risco de perda de dado. O resto vira ticket ou fica no dashboard.
- **Burn rate multi-window** (SRE Workbook). Para um SLO de 99,5% (`budget = 0.005`):

| Burn rate | Janelas (longa e curta) | Budget gasto | Ação |
|---|---|---|---|
| 14,4× | 1 h e 5 min | 2% | page |
| 6× | 6 h e 30 min | 5% | page |
| 1× | 3 d e 6 h | 10% | ticket |

- **Gere as regras com Sloth** (0.16), a partir de um YAML de SLO versionado. Pyrra (0.10) é a alternativa com UI.
- Regras base, ajustando os nomes das métricas ao que aparece no Prometheus:
```yaml
- alert: ApiErrorBudgetBurnFast
  expr: |
    (sum by (job)(rate(http_server_request_duration_seconds_count{http_response_status_code=~"5.."}[1h]))
      / sum by (job)(rate(http_server_request_duration_seconds_count[1h])) > 14.4 * 0.005)
    and
    (sum by (job)(rate(http_server_request_duration_seconds_count{http_response_status_code=~"5.."}[5m]))
      / sum by (job)(rate(http_server_request_duration_seconds_count[5m])) > 14.4 * 0.005)
  labels: { severity: page }
- alert: ApiLatencyP99High
  expr: histogram_quantile(0.99, sum by (job, le)(rate(http_server_request_duration_seconds_bucket[5m]))) > 1
  for: 10m
- alert: IngestLagHigh
  expr: histogram_quantile(0.99, sum by (le)(rate(mqtt_ingest_lag_seconds_bucket[5m]))) > 30
  for: 10m
- alert: MqttGatewayOffline
  expr: time() - mqtt_gateway_last_seen_timestamp_seconds > 120
- alert: MqttConsumerDisconnected
  expr: max by (job)(mqtt_connected) == 0
  for: 2m
  labels: { severity: page }
- alert: QueueBacklogGrowing
  expr: bullmq_queue_jobs{state="waiting"} > 1000 and deriv(bullmq_queue_jobs{state="waiting"}[15m]) > 0
  for: 15m
- alert: DiskFillingIn24h
  expr: predict_linear(node_filesystem_avail_bytes{mountpoint="/var/lib/docker"}[6h], 24 * 3600) < 0
- alert: ServiceMetricsAbsent
  expr: absent(up{job="ingest"} == 1)
  for: 5m
  labels: { severity: page }
```
- Alertas do Postgres (wraparound, archive, lag, conexões): use a tabela da `postgres-scaling`.
- **Roteamento:** Alertmanager com `telegram_configs`, `slack_configs` ou `email_configs`. Regras em arquivo, no git, versionam melhor que o Grafana Alerting. Cada alerta que pagina leva o link de um **runbook de uma página**.
- **Uptime externo:** **Gatus** v5 (config YAML no git) ou Uptime Kuma 2. Ele roda **fora** da VPS de produção, checa o domínio público e o `/health/ready`, e avisa por um canal diferente.

## 7. Teste de carga
- **k6 2.x** (AGPLv3) para HTTP. A 2.0 removeu `k6 login`, `externally-controlled` e `k6/experimental/redis`. Use **modelo aberto** (`constant-arrival-rate`) para não mascarar latência (coordinated omission).
```js
export const options = {
  scenarios: { steady: { executor: 'constant-arrival-rate', rate: 200, timeUnit: '1s', duration: '10m', preAllocatedVUs: 100 } },
  thresholds: { http_req_failed: ['rate<0.01'], http_req_duration: ['p(95)<300', 'p(99)<800'] },  // falha o job
};
```
- **MQTT:**
  - `grafana/xk6-mqtt` 0.3 (experimental; monte o binário com `xk6` se a extensão não for resolvida automaticamente) para simular gateways com payload do contrato;
  - **emqtt-bench** para a capacidade do broker (ver `mqtt-broker`);
  - meça de ponta a ponta: msg/s gravadas no banco e `mqtt_ingest_lag_seconds`, não só a vazão do broker.
- **Tipos de teste:**
  - **smoke** no CI (`k6 run --once`);
  - **carga** em staging no pico esperado e no dobro dele;
  - **soak** de 2 a 8 h antes do primeiro release, para pegar vazamento de memória, crescimento de fila e bloat;
  - **spike** de 0 a 5× em 30 s.
- **Regras:**
  - metas vêm do SLO e dos NFRs do `design.md`;
  - a carga é gerada de **outra máquina**;
  - aqueça de 1 a 2 min e descarte esse trecho;
  - use dados realistas (`deviceId`s variados, payload real, banco com volume);
  - **nunca rode contra produção** sem combinar;
  - guarde o resultado como evidência no PR ou no ADR.
- `autocannon` 8 só para microbenchmark local de uma rota (sem release desde 2024). Artillery 2 é a alternativa em Node.

## 8. Profiling e diagnóstico
- **Event loop lento:** `nodejs.eventloop.delay.p99` acima de 100 ms por 5 min é o sinal. Faça o flamegraph da réplica afetada.
- **Ferramentas:**
  - **`@platformatic/flame`** 1.7 (Node ≥ 22.6): CPU e heap, flamegraph HTML, controle por `SIGUSR2`;
  - nativas: `node --cpu-prof --cpu-prof-dir=/tmp/prof`, `--heap-prof`, `--heapsnapshot-signal=SIGUSR2`, `--heapsnapshot-near-heap-limit=2`;
  - 0x 6 como alternativa;
  - **o Clinic.js não é mais mantido** (desde 06/2023): evite.
- **Vazamento de memória:**
  - confirme no soak (`v8js.memory.heap.used` só sobe);
  - tire dois heap snapshots com carga constante e compare *Retained size* no Chrome DevTools;
  - o snapshot congela o processo e usa cerca de 2× o heap: **tire a réplica do balanceador antes** (readiness 503).
- **Profiling contínuo** (opcional, quando houver problema recorrente): Pyroscope 2.4 (AGPLv3) + `@pyroscope/nodejs` 0.6. O Tempo 3 liga perfil a span.
- **Lentidão no banco:** `pg_stat_statements` e `EXPLAIN (ANALYZE, BUFFERS)` (ver `postgres-scaling`). O span `pg` mostra a query (`db.query.summary`) e o tempo, e indica qual endpoint chama qual query.

## 9. Checklist "serviço observável" (antes de produção)
1. `telemetry` carregado via `--import`/`--require` antes do app, com `OTEL_SERVICE_NAME`, `service.version` = tag da imagem e o ambiente definidos.
2. Traces de HTTP, `pg`, `ioredis`, `undici` e BullMQ ativos, e contexto propagado no MQTT (User Properties).
3. Logs JSON no stdout com `trace_id`, `redact` configurado, `LOG_LEVEL` por variável e rotação do Docker.
4. Métricas RED, de runtime e de domínio (fila, MQTT, lag de ingestão), sem labels de alta cardinalidade.
5. `/health/live` e `/health/ready` reais (DB, Redis, MQTT) e fora do tracing.
6. SLO definido, alertas de burn rate, alerta de ausência (`absent`) e runbook por alerta que pagina.
7. Dashboard por serviço (RED, runtime, fila/MQTT) versionado no git (JSON ou provisioning).
8. `sdk.shutdown()` no fim do graceful shutdown.
9. Monitor de uptime externo apontando para o domínio público.
10. Teste de carga com thresholds no CI e soak feito antes do primeiro release, com o resultado anexado.
