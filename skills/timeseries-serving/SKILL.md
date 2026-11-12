---
name: timeseries-serving
description: "Padrões de historian para servir séries temporais industriais: último valor (snapshot) separado do histórico, heartbeat/tempo máximo sem gravar, banda morta (exceção na borda e compressão no servidor), janelas e a diferença latest x last, só qualidade boa nos agregados, dado atrasado com invalidação e lookback, agregação em tempo real e agregação por turno a partir de blocos. Usar ao desenhar ou revisar tabela de valor atual, painel ao vivo, 'tag parece desatualizada', agregados contínuos (TimescaleDB), visões materializadas (ClickHouse) ou indicadores por turno, mesmo que o pedido não use a palavra historian."
---

# Servir séries temporais industriais (padrões de historian)

Complementa `industrial-timeseries-etl` (método da lógica de curadoria), `clickhouse-best-practices` (regras do ClickHouse), `postgres-scaling` (TimescaleDB) e `edge-gateway` (como o dado nasce na borda). Fontes ao fim; o que veio de blog ou fórum está marcado como "prática de campo".

**Princípio:** separar **valor atual**, **histórico bruto** e **agregados**. Cada um tem armazenamento e regra de atualização próprios; nenhum é derivado apagando linhas do outro.

## 1. Último valor (snapshot)
- O PI mantém o **snapshot** (valor atual por ponto) separado do arquivo histórico; o histórico só recebe o que passa na compressão.
- Equivalente moderno: tabela de último valor por `(equipamento, tag)` mantida pela própria base, **sem DELETE por lote**:
  - ClickHouse: visão materializada para `AggregatingMergeTree` com `argMaxState(valor, ts)` por chave, lida com `argMaxMerge`; ou, a partir da 25.6, `CoalescingMergeTree` (guarda o último não nulo de cada coluna no merge; leia com `FINAL` ou `argMax`, porque antes do merge há várias linhas por chave).
  - Postgres/TimescaleDB: tabela `UPSERT ... ON CONFLICT (chave) DO UPDATE ... WHERE excluded.ts > tabela.ts` (dado atrasado não sobrescreve o atual).
- O valor atual leva `ts` da leitura e `qualidade`; a tela mostra a idade (`agora − ts`).

## 2. Tag constante que "parece desatualizada" (heartbeat)
- PI: **exceção** na borda (`ExcDev`, `ExcMax`) e **compressão** no servidor (`CompDev`, `CompMax`). `ExcMax`/`CompMax` força o envio/gravação depois de um tempo máximo mesmo sem mudança. Exemplo da AVEVA em apresentação: `CompMax` de 8 h para tag de estado 0/1 (exemplo, não padrão). Por padrão, exceção vem desligada (0) em pontos novos.
- Ignition: **Max Time** entre amostras ignora a banda morta (não a taxa de amostragem); mudança de qualidade é registrada.
- Regra: gravar/enviar **quando muda além da banda morta OU quando passou o tempo máximo** (heartbeat). A tela distingue "constante e viva" (heartbeat recente) de "sem dado" (idade > tempo máximo + folga). Isso é melhor que reconsultar a fonte periodicamente.
- Contador acumulado não usa banda morta que descarte produção (ver `edge-gateway` §2).

## 3. Janelas e semântica de agregação
- AWS IoT SiteWise: janelas tumbling com `offset` configurável; os agregados e métricas **só consomem dado de qualidade GOOD** (ignoram UNCERTAIN e BAD).
- `last(x)` = último valor **dentro** da janela `(início, fim]`; `latest(x)` = último valor **até o fim** da janela, incluindo antes dela (carrega o estado anterior). Use `latest` para sinal de estado (a máquina estava ligada desde antes) e `last` para medição da própria janela.
- Escreva na spec de cada métrica qual das duas vale, a borda da janela e o tratamento de qualidade.

## 4. Dado atrasado: invalidação e lookback
- TimescaleDB, agregados contínuos: a política de refresh recalcula só os buckets dentro de `[agora − start_offset, agora − end_offset]`. Dado que chega mais velho que `start_offset` só entra com `refresh_continuous_aggregate` manual.
  - `start_offset` cobre o atraso máximo esperado (gateway offline por dias = lookback de dias, ou refresh manual ao drenar fila grande).
  - `end_offset` ≥ 1 bucket atrás do presente; o bucket aberto fica para a agregação em tempo real.
  - Retenção do bruto **maior** que `start_offset`, senão o recálculo perde dado.
- Padrão genérico ("bloco sujo"): ao ingerir dado com `ts` antigo, marque os blocos afetados e reprocesse por agenda. A lógica precisa ser idempotente.

## 5. Agregação em tempo real
- TimescaleDB real-time aggregates: junta o materializado com o bruto após a marca d'água na hora da consulta (`timescaledb.materialized_only = false`). O padrão mudou entre versões (relatos indicam desligado por padrão desde a 2.13): confira na versão em uso.
- Dado histórico inserido num bucket já materializado **não** aparece até o próximo refresh.

## 6. Turno e períodos longos
- Não grave o turno como janela fixa: agregue blocos pequenos (ex.: 1 a 15 min) na consulta, com o calendário de turnos como dimensão. Mudança de calendário não exige reprocessar o bruto.
- Bloco que atravessa a troca de turno: use blocos que dividam o turno ou reparta proporcionalmente; documente.

## 7. Checklist de revisão
1. Valor atual separado do histórico, atualizado sem DELETE por lote e protegido contra dado atrasado?
2. Heartbeat (tempo máximo) definido por tipo de tag e a tela distingue "constante viva" de "sem dado"?
3. Banda morta só em analógico, nunca descartando produção de contador?
4. Cada métrica declara `last` x `latest`, borda da janela e regra de qualidade?
5. Lookback/`start_offset` cobre o atraso máximo da fila do gateway? Retenção maior que o lookback?
6. Agregação em tempo real decidida conscientemente (ligada ou não) e documentada?
7. Turno agregado de blocos na consulta, não gravado?

## Fontes
- AVEVA, Exception/Compression e impacto no PI (apresentação 2023): https://cdn.osisoft.com/osi/presentations/2023-AVEVA-San-Francisco/UC23NA-3PGK04-AVEVA_Bregenzer_Brent-Exception-Compression-and-their-Impacts-On-PI-System-Performance.pdf
- AVEVA PI Server, atributos de exceção e compressão: https://docs.aveva.com/bundle/pi-server-da-admin/page/1021696.html
- Ignition, Configuring Tag History (8.1 e 8.3): https://docs.inductiveautomation.com/docs/8.1/ignition-modules/tag-historian/configuring-tag-history ; https://docs.inductiveautomation.com/docs/8.3/ignition-modules/tag-historian/configuring-tag-history
- AWS IoT SiteWise, métricas e funções temporais: https://docs.aws.amazon.com/iot-sitewise/latest/userguide/metrics.md ; https://docs.aws.amazon.com/iot-sitewise/latest/userguide/expression-temporal-functions.html
- ClickHouse 25.6, CoalescingMergeTree: https://clickhouse.com/blog/clickhouse-25-6-coalescingmergetree ; https://clickhouse.com/docs/reference/engines/table-engines/mergetree-family/coalescingmergetree.md
- ClickHouse, visão materializada com argMaxState (newsletter 2022): https://clickhouse.com/blog/clickhouse-newsletter-june-2022-materialized-but-still-real-time
- Tinybird, dados de IoT no ClickHouse (prática de campo): https://www.tinybird.co/blog/clickhouse-iot-data
- TimescaleDB, refresh policies e real-time aggregates: https://docs.timescale.com/use-timescale/latest/continuous-aggregates/refresh-policies ; https://www.tigerdata.com/blog/real-time-analytics-for-time-series-continuous-aggregates ; https://www.tigerdata.com/blog/how-retention-policies-silently-break-continuous-aggregates
