# Algoritmos de referência do gateway de borda

Pseudocódigo neutro de linguagem. A implementação em Rust segue a skill `rust-standards`.

## 1. Delta de contador

Configuração por tag: `max` (valor máximo antes de virar: 65535, 4294967295 ou teto decimal), `tol` (regressão tratada como ruído, ex.: 2 unidades), `taxa_max` (unidades por segundo plausíveis) e `janela` (quanto perto do máximo e do zero conta como rollover, ex.: `taxa_max × intervalo × 3`).

```
fn processar_contador(estado: Option<Ref>, atual: u64, dt_s: Option<f64>, cfg) -> Resultado
    # estado vem do SQLite (counter_state), não da memória: sobrevive a reboot
    se estado é None:                       # tag nova, sem referência persistida
        retorna { delta: 0, nova_ref: atual, q: good, evento: "counter.baseline" }

    ant = estado.last_raw
    se atual >= ant:
        d = atual - ant
        se dt_s conhecido e d > cfg.taxa_max * dt_s:
            # salto implausível: não soma ao total, mas a referência avança
            # (o servidor tem raw e decide; se for real, recalcula)
            retorna { delta: 0, nova_ref: atual, q: uncertain, evento: "counter.jump" }
        retorna { delta: d, nova_ref: atual, q: good }

    regressao = ant - atual
    se regressao <= cfg.tol:
        # ruído: NÃO move a referência, senão a produção é contada de novo na volta
        retorna { delta: 0, nova_ref: ant, q: good }

    se ant >= cfg.max - cfg.janela e atual <= cfg.janela:
        retorna { delta: (cfg.max - ant) + atual + 1, nova_ref: atual, q: good, evento: "counter.rollover" }

    # reset do equipamento (zerou e já contou `atual` desde então)
    retorna { delta: atual, nova_ref: atual, q: good, evento: "counter.reset" }
```

- `dt_s` vem do relógio monotônico dentro do mesmo boot. Depois de um reboot do gateway, use a diferença de relógio de parede só se `timeOk`; senão, pule a checagem de plausibilidade e envie `q: uncertain` se o delta for grande.
- `total += delta` e `last_raw = nova_ref` são gravados **na mesma transação** que enfileira a leitura.
- A ordem das checagens importa: ruído antes de rollover, rollover antes de reset.
- Reset ambíguo (o equipamento pode ter sido zerado e não ter recomeçado do zero) fica a critério de configuração por tag: `delta = atual` (padrão) ou `delta = 0` + evento para revisão. Em ambos os casos o `raw` vai ao servidor.

## 2. Fila local (SQLite)

```sql
PRAGMA journal_mode = WAL;
PRAGMA synchronous = FULL;          -- durável em queda de energia
PRAGMA busy_timeout = 5000;
PRAGMA journal_size_limit = 67108864;

CREATE TABLE IF NOT EXISTS meta (
  key   TEXT PRIMARY KEY,           -- device_id, next_seq, schema_local
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS outbox (
  id       INTEGER PRIMARY KEY,     -- ordem FIFO
  seq      INTEGER NOT NULL UNIQUE,
  boot_id  TEXT    NOT NULL,
  kind     TEXT    NOT NULL CHECK (kind IN ('analog', 'counter', 'event')),
  ts       TEXT,                    -- UTC ISO 8601; pode ser corrigido após sincronizar o relógio
  mono_ns  INTEGER NOT NULL,
  time_ok  INTEGER NOT NULL,        -- 0/1
  body     TEXT    NOT NULL         -- leitura serializada (JSON)
);

CREATE TABLE IF NOT EXISTS counter_state (
  tag      TEXT PRIMARY KEY,
  last_raw INTEGER NOT NULL,
  total    INTEGER NOT NULL,
  cfg_rev  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS dead_letter (
  id      INTEGER PRIMARY KEY,
  seq     INTEGER NOT NULL,
  body    TEXT    NOT NULL,
  reason  TEXT    NOT NULL,
  at      TEXT    NOT NULL
);
```

**Ciclo de leitura (uma transação):**
```
BEGIN
  para cada leitura do ciclo:
    seq = meta.next_seq; meta.next_seq += 1
    INSERT INTO outbox (...)
    se contador: UPSERT counter_state (last_raw, total, cfg_rev)
  UPDATE meta SET value = next_seq WHERE key = 'next_seq'
COMMIT
```

**Envio:**
```
lote = SELECT id, body FROM outbox ORDER BY id LIMIT N   # e corta por bytes
resp = POST /ingest (lote) com timeout
se 2xx com ack:
  BEGIN
    INSERT INTO dead_letter ... para cada item em ack.rejected
    DELETE FROM outbox WHERE id IN (ids do lote)
  COMMIT
  tentativa = 0
senão se 401/403: pausa envio, sinaliza credencial no heartbeat
senão: espera = aleatório(0, min(teto, base * 2^tentativa)); tentativa += 1
       (usa Retry-After se vier)
```

**Overflow (quando passa do limite):**
```
DELETE FROM outbox WHERE id IN (
  SELECT id FROM outbox WHERE kind = 'analog' ORDER BY id LIMIT :excesso)
-- só depois, se ainda faltar espaço: counter (o mais recente já carrega o total), por último event
-- registra queue.overflow com a quantidade descartada
```

## 3. Payload de telemetria (HTTPS)

Nomes em camelCase, alinhados com `mqtt-contract`. Siga a convenção do contrato do projeto se ele já existir.

```json
{
  "schema": 2,
  "deviceId": "gw-0042",
  "bootId": "6f1c2a0e-3d4b-4f5a-9e8d-7c6b5a4f3e2d",
  "firmware": "1.8.3",
  "sentAt": "2026-11-08T13:05:02.120Z",
  "readings": [
    { "seq": 184223, "tag": "linha1.temp", "ts": "2026-11-08T13:05:00.000Z", "timeOk": true,
      "cfgRev": 17, "raw": 824, "v": 82.4, "unit": "Cel", "q": "good" },
    { "seq": 184224, "tag": "linha1.contador", "ts": "2026-11-08T13:05:01.000Z", "timeOk": true,
      "cfgRev": 17, "raw": 3, "v": 3, "delta": 6, "total": 1203345, "unit": "count", "q": "good" }
  ]
}
```
No exemplo, o contador virou de 65533 para 3 (rollover de 16 bits): `delta = (65535 − 65533) + 3 + 1 = 6`.

**Ack do servidor (2xx):**
```json
{ "accepted": 1, "duplicates": 1, "rejected": [] }
```
`rejected` lista `{ "seq": 184230, "reason": "tag desconhecida" }` para quarentena local. Duplicata é sucesso.

**Snapshot de configuração** (no boot e a cada `cfgRev` nova):
```json
{ "schema": 1, "deviceId": "gw-0042", "cfgRev": 17, "at": "2026-11-08T12:00:00Z",
  "tags": [ { "tag": "linha1.contador", "proto": "modbus-tcp", "unitId": 1, "addr": 40010,
              "type": "u16", "wordOrder": "big", "scale": 1, "offset": 0, "unit": "count",
              "counter": { "max": 65535, "tol": 2, "taxaMax": 50 } } ] }
```

## 4. Servidor: gravação idempotente (SQL)

```sql
CREATE UNIQUE INDEX IF NOT EXISTS ux_reading_origin
  ON reading (device_id, boot_id, seq);

INSERT INTO reading (device_id, boot_id, seq, tag, ts, time_ok, cfg_rev, raw, v, received_at)
VALUES (...)
ON CONFLICT (device_id, boot_id, seq) DO NOTHING;
-- linhas afetadas = accepted; o restante do lote = duplicates
```
Em banco já em produção, crie o índice único sem bloquear escrita (`CONCURRENTLY` no PostgreSQL) e confira antes se não há duplicatas que façam a criação falhar (ver `sql-standards`).
