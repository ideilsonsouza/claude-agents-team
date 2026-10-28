---
name: postgres-scaling
description: Escala e operação de PostgreSQL 18 + TimescaleDB 2.30 self-hosted (Docker/Swarm, Coolify/Dokploy) — orçamento de conexões, PgBouncer 1.26 em transaction mode (o que quebra), timeouts por role, tuning base para VPS, autovacuum/bloat/wraparound, diagnóstico (pg_stat_statements, auto_explain, locks, pg_stat_io), réplicas de leitura com Drizzle withReplicas, HA e failover, particionamento (pg_partman) x hypertable, TimescaleDB a fundo (chunk interval, columnstore/hypercore, continuous aggregates, retenção, ingestão em lote), backup físico com PITR (pgBackRest) e restore testado, Redis como cache, checklist operacional e thresholds de alerta. Usar ao dimensionar, configurar, diagnosticar, escalar ou operar um banco Postgres/TimescaleDB, ou ao planejar backup e DR.
---

# PostgreSQL e TimescaleDB em escala

Versões verificadas em 14/10/2026:

| Componente | Versão | Observação |
|---|---|---|
| **PostgreSQL** | **18.6** | EOL em 11/2030. O 14 sai de suporte em **12/11/2026**. O 19 está em beta: não use |
| **TimescaleDB** | **2.30.2** | Suporta PG 16, 17 e 18 |
| **PgBouncer** | **1.26.1** | Lançado em 14/10/2026, corrige 3 CVEs: exija ≥ 1.26.1 |
| **pgBackRest** | **2.59.3** | |
| pg_partman | 5.5.0 | |
| pg_repack | 1.5.3 | |
| postgres_exporter | 0.20.1 | |

Fontes: postgresql.org (versioning, release notes 18), tigerdata.com/docs, GitHub releases.

Não repete o que está em `sql-standards` (modelagem, expand/contract, `CONCURRENTLY`, `NOT VALID`, keyset), em `backend-drizzle` (código) nem em `architecture-scalability` (decisões).

**Ordem para escalar:**
1. Medir com `pg_stat_statements`.
2. Corrigir query e índice.
3. Tuning e autovacuum.
4. Lote e conexões (PgBouncer).
5. Continuous aggregates e compressão.
6. Réplica de leitura.
7. Escala vertical.
8. Particionar.
9. Sharding só em último caso: não se aplica a 20k leituras/s.

## 1. Versão e imagem
- **Padrão:** PG 18 no minor mais recente, com TimescaleDB 2.30. Imagem **`timescale/timescaledb-ha:pg18-ts2.30`**, fixada por tag completa. Ela traz pgBackRest, Patroni e toolkit. A `timescale/timescaledb:2.30.2-pg18` é enxuta (Alpine), mas não traz o pgBackRest.
- **Licença do TimescaleDB:**
  - o núcleo é Apache 2;
  - columnstore, continuous aggregates e policies são **TSL (Community)**: grátis em self-hosted, mas proíbe oferecer o banco como DBaaS;
  - imagens `-oss` **não têm** esses recursos;
  - tiering para S3 é exclusivo do Tiger Cloud.
- **O que o PG 18 traz de útil:**
  - **AIO** (`io_method = worker`, padrão; fique nele em Docker);
  - **`uuidv7()` nativo** para PK ordenada;
  - **skip scan** em B-tree multicoluna: `(tenant_id, ts)` passa a atender filtro só por `ts`;
  - colunas geradas **VIRTUAL por padrão** (use `STORED` para indexar);
  - `pg_upgrade` **preserva as estatísticas** do otimizador;
  - checksums ligados por padrão;
  - MD5 deprecado: use SCRAM.
  - Do PG 17 vem o `transaction_timeout`.
- **Armadilha da imagem `postgres:18` e derivadas:** o volume agora é montado em `/var/lib/postgresql` (o PGDATA fica em `/var/lib/postgresql/18/docker`). Montar no antigo `/var/lib/postgresql/data` quebra. Confira o README da imagem usada.
- **Upgrade de major:**
  - use `pg_upgrade --link`/`--swap` com `--jobs`, ou logical replication para downtime mínimo;
  - se o cluster de origem não tinha checksum, rode o initdb do destino com `--no-data-checksums`;
  - ensaie numa cópia restaurada do backup.

## 2. Conexões
- **Orçamento:** `max_connections ≥ Σ(pool.max × réplicas de todos os processos) + migrator + admin, monitoramento e replicação (~10)`. Cada conexão custa memória e CPU: o normal é `max_connections` de 100 a 200, não milhares.
- **Sem PgBouncer:** pool `pg` com `max` de 5 a 10 por réplica.
- **Com PgBouncer**, que passa a ser o padrão a partir de cerca de 100 conexões ou mais de 4 réplicas: o app pode ter `max` de 20 a 50 e o PgBouncer segura o lado do servidor.
```ini
[pgbouncer]
pool_mode = transaction
max_client_conn = 2000
default_pool_size = 20          ; ~2–4× vCPUs do Postgres
reserve_pool_size = 5
max_prepared_statements = 200   ; prepared statements de protocolo funcionam em transaction mode (≥ 1.21)
query_wait_timeout = 30
auth_type = scram-sha-256
```
- **O que quebra em transaction mode:**
  - `SET` de sessão: use `SET LOCAL` ou `set_config(..., true)`;
  - **advisory lock de sessão**: use `pg_advisory_xact_lock`;
  - `LISTEN/NOTIFY`, `PREPARE` em SQL, cursor `WITH HOLD` e tabela temporária que atravessa transações.
- **Migrator, `LISTEN` e o lock de migração vão por conexão direta (5432)**, não pelo PgBouncer.
- Depois de uma migration com DDL, o PgBouncer pode devolver *"cached plan must not change result type"*: rode `RECONNECT` no console admin.
- Alternativas: PgDog (0.x, ativo, Rust) e Supavisor (pesado). **O PgCat está abandonado** (sem commits desde 02/2025).
- **Timeouts por role:** não afetam o migrator e protegem o banco de uma query ruim.
```sql
ALTER ROLE app      SET statement_timeout = '15s';
ALTER ROLE app      SET lock_timeout = '3s';
ALTER ROLE app      SET idle_in_transaction_session_timeout = '30s';
ALTER ROLE app      SET transaction_timeout = '60s';      -- PG17+
ALTER ROLE ingest   SET statement_timeout = '60s';
ALTER ROLE migrator SET lock_timeout = '5s';              -- migration com retry
```
- **Roles separados:**
  - `migrator`: dono das tabelas, faz DDL;
  - `app` e `ingest`: DML, sem `BYPASSRLS`;
  - `readonly`: relatórios e réplica;
  - `monitor`: `pg_monitor`.
  - A aplicação **não** conecta como dona das tabelas.

## 3. Tuning base
Ponto de partida para uma VPS de 8 GB e 4 vCPU com SSD (escale proporcionalmente). Ajuste com PGTune ou `timescaledb-tune`, que a imagem roda no initdb lendo o limite do cgroup.
```conf
shared_buffers = 2GB                 # 25% da RAM
effective_cache_size = 6GB           # 75%
work_mem = 16MB                      # vale POR nó de sort/hash POR conexão: cuidado
maintenance_work_mem = 512MB
autovacuum_work_mem = 256MB
max_wal_size = 8GB
min_wal_size = 1GB
checkpoint_timeout = 15min
checkpoint_completion_target = 0.9
wal_compression = zstd
random_page_cost = 1.1               # SSD
effective_io_concurrency = 200
huge_pages = try
max_worker_processes = 16            # o Timescale usa background workers
timescaledb.max_background_workers = 8
shared_preload_libraries = 'timescaledb,pg_stat_statements,auto_explain'
```
- **Em Docker/Swarm:**
  - **`shm_size: 1g`** (com o padrão de 64 MB, parallel query falha com *could not resize shared memory segment*);
  - volume nomeado em **disco local** (nunca NFS);
  - **`stop_grace_period: 120s`**, para o checkpoint de shutdown terminar;
  - `placement constraint` fixando o nó;
  - limite de memória definido.
- Não publique a 5432 na internet. Acesso por rede interna ou VPN, com `pg_hba` em `scram-sha-256`.

## 4. Autovacuum, bloat e wraparound
- **Tabelas OLTP com muito UPDATE** (status, sessões, contadores, outbox):
```sql
ALTER TABLE outbox SET (fillfactor = 80,                         -- espaço para HOT update
  autovacuum_vacuum_scale_factor = 0.02, autovacuum_vacuum_threshold = 1000,
  autovacuum_analyze_scale_factor = 0.02, autovacuum_vacuum_cost_limit = 2000);
```
- **Global:**
  - `autovacuum_max_workers` de 4 a 6 (no PG 18 é ajustável em runtime até `autovacuum_worker_slots`);
  - `autovacuum_vacuum_cost_limit` de 1000 a 2000;
  - `autovacuum_vacuum_max_threshold` (PG 18) para tabelas enormes.
- **HOT update** só acontece se nenhuma coluna indexada mudar e houver espaço na página. Meta: `n_tup_hot_upd / n_tup_upd` acima de 0,9 nas tabelas quentes. Não indexe a coluna de status que muda o tempo todo sem necessidade.
- **Transação longa e `idle in transaction`** seguram o vacuum de **todo o banco**. Eles são a causa nº 1 de bloat.
- **Hypertable** é append-only e quase não tem bloat. Dado antigo sai por retention policy (drop de chunk), **nunca por `DELETE`**.
- **Bloat:**
  - medir com `pgstattuple_approx`;
  - corrigir online com **pg_repack 1.5.3**, que exige PK e cerca de 2× o espaço da tabela;
  - em hypertable não use pg_repack: use `add_reorder_policy`/`reorder_chunk`.
```sql
-- wraparound (alerta em 500M, crítico em 1B)
SELECT datname, age(datfrozenxid) FROM pg_database ORDER BY 2 DESC;
-- dead tuples e HOT
SELECT relname, n_dead_tup, n_live_tup, last_autovacuum,
       n_tup_hot_upd * 100 / nullif(n_tup_upd, 0) AS hot_pct
FROM pg_stat_user_tables ORDER BY n_dead_tup DESC LIMIT 20;
```

## 5. Diagnóstico
- **Ligado sempre:**
  - `pg_stat_statements` (`track = top`, `max = 10000`);
  - `log_min_duration_statement = 500ms`;
  - `auto_explain.log_min_duration = '2s'` com `log_analyze` e `log_buffers`;
  - `log_lock_waits = on`, `log_temp_files = 0`, `log_checkpoints = on`, `log_autovacuum_min_duration = 1s`.
```sql
-- top por tempo total
SELECT queryid, calls, round(total_exec_time) AS ms, round(mean_exec_time, 1) AS avg_ms, rows, left(query, 120)
FROM pg_stat_statements ORDER BY total_exec_time DESC LIMIT 15;
-- quem bloqueia quem
SELECT pid, pg_blocking_pids(pid) AS blocked_by, wait_event_type, state, now() - xact_start AS dur, left(query, 100)
FROM pg_stat_activity WHERE cardinality(pg_blocking_pids(pid)) > 0;
-- transações longas
SELECT pid, usename, state, now() - xact_start AS dur, left(query, 100)
FROM pg_stat_activity WHERE xact_start < now() - interval '5 min' ORDER BY dur DESC;
-- índices nunca usados (revise antes de dropar: confira réplicas e estatística recém-zerada)
SELECT relname, indexrelname, pg_size_pretty(pg_relation_size(indexrelid)) FROM pg_stat_user_indexes WHERE idx_scan = 0;
-- I/O por backend (PG16+, bytes no PG18)
SELECT backend_type, object, context, reads, read_bytes, writes, write_bytes FROM pg_stat_io WHERE reads + writes > 0;
```
- **Plano:** `EXPLAIN (ANALYZE, BUFFERS)`, que no PG 18 já inclui buffers. Procure seq scan em tabela grande, estimativa muito diferente do real (rode `ANALYZE` ou crie extended statistics) e sort ou hash em disco (aumente o `work_mem` só naquela sessão).
- **Ferramentas:**
  - **postgres_exporter 0.20** + Grafana, com o role `pg_monitor` (ver `observability`);
  - **pgBadger 13** sobre os logs;
  - **PgHero** como painel simples;
  - pganalyze (pago) se o orçamento permitir.

## 6. Escala de leitura e alta disponibilidade
- **Réplica de leitura:** streaming replication física com `hot_standby_feedback = on` e `max_standby_streaming_delay = 30s`.
  - **Drizzle:** `const db = withReplicas(primary, [replica])`. A leitura vai para a réplica, a escrita para o primário, e `db.$primary` força o primário.
  - **Read-your-writes:** depois de escrever, leia pelo `$primary` na mesma requisição. Para o rigor máximo, compare LSN.
  - Mande dashboards e relatórios para a réplica, e CRUD e ingestão para o primário.
  - Lag: `pg_stat_replication.replay_lag` no primário e `now() - pg_last_xact_replay_timestamp()` na réplica.
- **HA para equipe pequena:**
  - primário + **standby assíncrono** + **runbook de failover manual** testado a cada trimestre;
  - o runbook: `SELECT pg_promote()`, troca do host no PgBouncer e reconstrução do antigo primário com `pg_rewind`;
  - Patroni 4 (exige etcd) só quando o **RTO exigido for menor que 5 min**, com ADR. Não encaixa bem em Coolify/Dokploy.
- **Particionamento:**
  - **telemetria e séries temporais:** hypertable, não particionamento manual;
  - **tabelas OLTP grandes com retenção** (auditoria, eventos, outbox histórico): particionamento declarativo por range de tempo com **pg_partman 5.5**. Na 5.5, o background worker roda como o role `partman_maintainer` (CVE-2026-61821), que precisa ser criado **antes** de atualizar;
  - a chave de partição entra em toda PK ou unique.
- **Sharding (Citus, PgDog):** só depois de esgotar tudo o que vem antes, com vários TB quentes ou escrita acima do que um nó NVMe aguenta. Requer ADR.

## 7. TimescaleDB a fundo
```sql
CREATE TABLE readings (
  ts        timestamptz NOT NULL,
  device_id int         NOT NULL,
  metric    smallint    NOT NULL,
  value     double precision,
  quality   smallint,
  seq       bigint,
  UNIQUE (device_id, metric, ts)               -- toda PK/unique inclui a coluna de tempo
) WITH (tsdb.hypertable, tsdb.partition_column = 'ts', tsdb.chunk_interval = '1 day',
        tsdb.segmentby = 'device_id', tsdb.orderby = 'ts DESC');   -- sintaxe 2.20+

CALL remove_columnstore_policy('readings');   -- a policy padrão vem com after = chunk_interval
SELECT add_columnstore_policy('readings', after => INTERVAL '2 days');
SELECT add_retention_policy('readings', drop_after => INTERVAL '400 days');
```
- **Chunk interval:**
  - o chunk ativo, com índices, deve caber em cerca de **25% do `shared_buffers`**;
  - com 1k linhas/s, 1 dia funciona; com 10k linhas/s (cerca de 50 GB/dia sem compressão), use de 1 a 6 h numa VPS de 8 GB;
  - o padrão de 7 dias é grande demais para telemetria;
  - revise mensalmente contra o volume real.
- **Columnstore (hypercore), API atual:** `add_columnstore_policy`, `convert_to_columnstore` e `convert_to_rowstore`. As APIs **`add_compression_policy` e `timescaledb.compress` estão deprecadas desde a 2.18**: não use em código novo.
  - `segmentby` = a coluna pela qual se filtra (device), com cardinalidade moderada. Usar a chave única ou um id quase único anula a compressão.
  - `orderby` = `ts DESC`.
  - `tsdb.direct_compress` ainda é tech preview e não funciona com unique.
- **Dado atrasado:**
  - insert ou `ON CONFLICT` em chunk já convertido em columnstore descompacta segmentos e fica caro;
  - por isso o **`after` da policy deve ser maior que o atraso máximo do store-and-forward dos gateways** (ex.: buffer de 24 h no Node-RED pede `after` de 2 dias).
- **Continuous aggregates:**
```sql
CREATE MATERIALIZED VIEW readings_1m WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS
SELECT time_bucket('1 minute', ts) AS bucket, device_id, metric,
       avg(value) AS avg, min(value) AS min, max(value) AS max, count(*) AS n
FROM readings GROUP BY 1, 2, 3 WITH NO DATA;
SELECT add_continuous_aggregate_policy('readings_1m',
  start_offset => INTERVAL '2 hours', end_offset => INTERVAL '1 minute', schedule_interval => INTERVAL '1 minute');
```
  - **A agregação em tempo real vem desligada por padrão.** Declare `materialized_only = false` quando o dashboard precisar dos últimos minutos.
  - Monte uma hierarquia (1 min → 1 h → 1 dia), com retenção mais longa nos níveis agregados que no bruto. Dashboards nunca leem o bruto em janelas longas.
  - O `start_offset` deve cobrir o atraso dos dados que chegam tarde.
- **Ingestão:**
  - INSERT multi-row ou `unnest` em lotes de 1.000 a 10.000 linhas, com `ON CONFLICT DO NOTHING` (idempotência);
  - **poucas conexões de ingestão (2 a 4) com lotes grandes** rendem mais que muitas pequenas;
  - o `COPY` é mais rápido, mas não aceita `ON CONFLICT`. Para isso, use COPY para uma tabela staging seguido de `INSERT ... SELECT ... ON CONFLICT`.
- **Última leitura por sensor:** a 2.30 otimiza `ORDER BY ts DESC LIMIT 1` por device (`DeferredChunkAppend`). Para o dashboard ao vivo, mantenha também uma tabela `latest_readings` (upsert) ou um cache no Redis.
- **Operação:**
  - `ALTER EXTENSION timescaledb UPDATE` precisa ser **o primeiro comando de uma sessão nova** (`psql -X`), e a versão da imagem tem que ser igual à da extensão;
  - falhas de job: `SELECT * FROM timescaledb_information.job_stats WHERE last_run_status <> 'Success'`;
  - compressão: `hypertable_columnstore_stats('readings')`.
- **RLS em hypertable** combinada com columnstore ou continuous aggregate tem restrições: teste antes de adotar (ver `architecture-scalability`).

## 8. Backup e DR
- **Padrão: pgBackRest 2.59** (≥ 2.59.3) com repositório S3 ou compatível (R2, B2, MinIO em **outro** host ou provedor), criptografado, com **WAL archiving contínuo e PITR**.
```ini
[global]
repo1-type=s3
repo1-s3-bucket=pg-backup
repo1-s3-endpoint=<endpoint>
repo1-s3-region=<regiao>
repo1-path=/prod
repo1-retention-full=2
repo1-cipher-type=aes-256-cbc
compress-type=zst
archive-async=y
start-fast=y
[main]
pg1-path=/var/lib/postgresql/18/docker
```
```conf
archive_mode = on
archive_command = 'pgbackrest --stanza=main archive-push %p'
```
- **Agenda:** full semanal e diff diário. O WAL contínuo dá **RPO de segundos a minutos**. O RTO é o tempo do restore medido no teste.
- **O backup nativo do Coolify e do Dokploy é só `pg_dump`.** Não tem PITR, e o restore deles não chama `timescaledb_pre_restore()`/`post_restore()`. Sirva-se dele **só como complemento** (dump lógico semanal das tabelas OLTP).
- **Dump lógico de banco com Timescale:**
  - origem e destino com o mesmo major de PG e de Timescale;
  - restore com `timescaledb_pre_restore()` e `timescaledb_post_restore()`, **sem `pg_restore -j`**;
  - só é viável abaixo de cerca de 100 GB.
- **Restore testado todo mês** num contêiner descartável:
  1. `pgbackrest restore --type=time --target='<timestamp>'`;
  2. validar contagens e `SELECT max(ts)`;
  3. anotar o tempo, que é o RTO real.
  - Backup sem restore testado não conta como backup.
- **Alerta crítico:** `pg_stat_archiver.failed_count` subindo ou `pg_wal` crescendo. O WAL parado lota o disco e derruba o banco.

## 9. Redis como cache na frente do Postgres
- **Vale para:**
  - dado quente, lido demais e tolerante a atraso: config do tenant, permissões, último valor por device para o dashboard ao vivo, agregados caros usados em muitas telas;
  - rate limit.
- **Não substitui** índice, continuous aggregate nem dado que exige consistência forte.
- **Redis de cache separado do Redis do BullMQ.** O BullMQ exige `noeviction`, e cache usa `allkeys-lru`: são instâncias distintas.
- **Materialized view x continuous aggregate:** a MV recalcula tudo a cada refresh (`CONCURRENTLY` exige unique index) e serve para relatórios OLTP pequenos. O cagg é incremental e é o padrão para séries temporais.

## 10. Rotina operacional e alertas
**Diário (automatizado):**
- backup e archive ok;
- lag da réplica;
- jobs do Timescale;
- disco;
- top 10 do `pg_stat_statements`.

**Semanal:**
- dead tuples, bloat e % de HOT;
- índices não usados;
- relatório do pgBadger;
- taxa de compressão.

**Mensal:**
- restore com PITR;
- atualizar os minors (PG, PgBouncer, Timescale, pgBackRest);
- revisar o chunk interval.

**Trimestral:** drill de failover.

| Sinal | Aviso | Crítico |
|---|---|---|
| Conexões / `max_connections` | 70% | 90% |
| Sessões `idle in transaction` > 1 min | 1 | 5 |
| Transação mais antiga | 5 min | 30 min |
| `age(datfrozenxid)` | 500 M | 1 B |
| Lag da réplica | 30 s | 5 min |
| Falha de archive | 1 | `pg_wal` > 10 GB |
| Disco usado | 75% | 85% |
| Cache hit (`blks_hit`) | < 99% | < 95% |
| `checkpoints_req` / total | > 10% | > 30% |
| PgBouncer `cl_waiting` > 0 | 30 s | 2 min |
| Job do Timescale falhando | 1 falha | 3 seguidas |
| Deadlocks/min | > 0 | > 5 |
| p95 da query de ingestão | 2× o baseline | 5× o baseline |

## Pendências a validar no primeiro projeto
- Se o Drizzle 0.45 com `pg` usa statements nomeados só com `.prepare('nome')`. Isso define se o `max_prepared_statements` entra em jogo.
- `io_uring` no Docker (o seccomp pode bloquear): por isso o padrão é `io_method = worker`.
- O padrão de `materialized_only` no TimescaleDB 2.30: declare sempre explicitamente.
