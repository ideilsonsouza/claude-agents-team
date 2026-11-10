---
name: industrial-timeseries-etl
description: Análise de dados brutos e escrita de lógicas de curadoria (ETL) sobre séries temporais industriais — tipos de sinal e como agregar cada um (gauge por média ponderada no tempo, contador por soma de deltas com reset e rollover, estado por duração e paradas, eventos com deduplicação), qualidade (bom/incerto/ruim, sentinelas, ausência não é zero), tempo (UTC, janelas tumbling, amostra anterior à janela, recorte, teto para buracos, atraso, duplicata, fuso e horário de verão), indicadores (disponibilidade, MTBF/MTTR, OEE, produção, vazão, consumo específico), agregação em camadas (numerador e denominador, nunca média de médias), determinismo e reprocessamento, limites de sandbox, testes (conjunto dourado, borda, reconciliação, propriedades) e checklist "lógica pronta para ativar". Usar ao analisar dado bruto de sensores/PLC, definir métrica ou indicador, escrever ou revisar lógica de curadoria, ou desenhar ETL de telemetria.
---

# ETL de séries temporais industriais (lógicas de curadoria)

Padrão da equipe, genérico. Fórmulas dos indicadores e exemplos de cálculo em `references/indicadores.md`. Fontes ao fim.
- Se existir skill de projeto com o contrato da plataforma (ex.: `<projeto>-curation-logic`: entrada, saída, limites, nomes), ela manda no formato. Esta skill manda no **método**.
- Testes em geral: `test-strategy`. Execução de script não confiável: `sandbox-isolated-vm`. Consulta analítica em ClickHouse: `clickhouse-best-practices`. Origem do dado no campo: `edge-gateway`.

## 1. Princípios

1. **Perfile antes de escrever.** Intervalo real entre amostras, chaves, faixas, qualidade, resets, buracos e atrasos vêm de uma amostra real, não do manual do equipamento.
2. **Ausência não é zero.** Sem dado, a saída é `null` com a cobertura registrada; nunca `0`.
3. **A lógica é uma função pura**: `(janela, amostras, parâmetros) → fatos`. Mesma entrada, mesma saída.
4. **Guarde numerador e denominador**, não só o percentual. Toda saída tem unidade e diagnóstico (cobertura, descartes).
5. **Meça contra o bruto.** Métrica sem reconciliação independente não é ativada.

## 2. Tipos de sinal e como agregar

| Tipo | Exemplo | Agregação correta | Erro comum |
|---|---|---|---|
| Gauge (instantâneo) | vazão, temperatura, corrente | **média ponderada no tempo** (sample-and-hold), mín, máx | média simples (enviesa quando a amostragem é irregular ou por deadband) |
| Contador/totalizador | toneladas acumuladas, kWh, peças | **soma de deltas positivos** | `último − primeiro` (perde reset e rollover) |
| Estado/status | rodando, parado, alarme | **duração por estado**, transições, paradas | contar amostras em vez de tempo |
| Evento | RFID, apontamento, pesagem | contagem, **deduplicação**, janela | contar leitura repetida como evento novo |

### 2.1 Gauge: média ponderada no tempo

Cada amostra vale desde o seu instante até a próxima, limitada a um teto (`maxGapMs`). Só amostra boa contribui; o intervalo sem cobertura fica fora do denominador.

```js
// samples: [{t: msUTC, v: number, q: 'good'|'uncertain'|'bad'}] ordenadas por t; pode ter 1 amostra antes de t0
function twa(samples, t0, t1, maxGapMs) {
  let num = 0, den = 0;
  for (let i = 0; i < samples.length; i++) {
    const s = samples[i];
    if (s.q !== 'good') continue;                       // incerto/ruim não entra (ver seção 3)
    const next = i + 1 < samples.length ? samples[i + 1].t : t1; // a próxima amostra, qualquer qualidade, encerra a validade
    const start = Math.max(s.t, t0);                    // recorte: não conta fora da janela
    const end = Math.min(next, s.t + maxGapMs, t1);     // teto para buraco
    if (end > start) { num += s.v * (end - start); den += end - start; }
  }
  return { avg: den > 0 ? num / den : null, coveredMs: den, windowMs: t1 - t0 };
}
```

`coveredMs / windowMs` é a **cobertura**. Abaixo de um mínimo definido na spec (ex.: 80%), a saída é `null` ou sai marcada como parcial.

### 2.2 Contador/totalizador: soma de deltas

```js
// política de reset: 'skip' (conservador) ou 'fromZero' (assume que o contador zerou logo antes da amostra)
function counterSum(samples, t0, t1, { modulo = null, maxRatePerS = Infinity, onReset = 'skip' } = {}) {
  let sum = 0, prev = null; const d = { resets: 0, rollovers: 0, rejected: 0, frozenSteps: 0, used: 0 };
  for (const s of samples) {
    if (s.q === 'bad' || !Number.isFinite(s.v)) continue;   // contador é cumulativo: pular amostra ruim não perde produção
    if (prev && s.t >= t0 && s.t < t1) {                    // o delta pertence à janela da amostra mais nova
      let delta = s.v - prev.v;
      if (delta < 0) {
        if (modulo && prev.v > 0.9 * modulo && s.v < 0.1 * modulo) { delta += modulo; d.rollovers++; }
        else { d.resets++; delta = onReset === 'fromZero' ? s.v : 0; }
      }
      if (delta > maxRatePerS * (s.t - prev.t) / 1000) { d.rejected++; delta = 0; } // salto impossível (glitch)
      if (delta === 0) d.frozenSteps++;
      sum += delta; d.used++;
    }
    prev = s;
  }
  return { value: d.used > 0 ? sum : null, ...d };
}
```

Regras:
- **Rollover**: contador de 16 bits vira em 65536 (`modulo`), 32 bits em 4294967296. Só trate como rollover se o valor anterior estava perto do topo **e** o novo perto de zero; senão é reset.
- **Reset** (queda sem rollover: troca de turno manual, reinício do PLC, troca de equipamento): decida na spec entre ignorar o intervalo (`skip`) e assumir que o valor novo foi produzido desde o reset (`fromZero`). Registre quantos resets ocorreram.
- **Totalizador congelado**: delta zero por muito tempo com o estado "rodando" indica totalizador travado ou comunicação mascarada. Não corrija; sinalize em diagnóstico (`frozenSteps`) e decida na spec.
- **Salto impossível**: delta acima da taxa física máxima (`maxRatePerS`) é descartado e contado.
- O delta é atribuído à janela da amostra mais nova. Ele cobre o buraco inteiro entre as duas amostras (vantagem do contador sobre o gauge), mas isso pode concentrar produção de vários minutos numa hora. Se a spec exigir distribuição, reparta o delta pro-rata pelo tempo e documente.
- Escala (fator, offset) aplica-se ao **valor** antes do delta, com o fator vigente na época (versão de configuração).

### 2.3 Estado: duração, transições e paradas

```js
function stateRuns(samples, t0, t1, maxGapMs) {            // trechos contínuos de um mesmo estado, recortados na janela
  const runs = [];
  for (let i = 0; i < samples.length; i++) {
    const s = samples[i];
    if (s.q === 'bad') continue;
    const next = i + 1 < samples.length ? samples[i + 1].t : t1;
    const start = Math.max(s.t, t0), end = Math.min(next, s.t + maxGapMs, t1);
    if (end <= start) continue;
    const last = runs[runs.length - 1];
    if (last && last.state === s.v && last.end === start) last.end = end;
    else runs.push({ state: s.v, start, end, openStart: s.t < t0 });
  }
  return runs;
}

function stateFacts(runs, { runningStates, minStopMs }) {
  const f = { run_ms: 0, stopped_ms: 0, other_ms: 0, stops: 0, micro_stops: 0, transitions: Math.max(0, runs.length - 1) };
  for (const r of runs) {
    const dur = r.end - r.start;
    if (runningStates.includes(r.state)) f.run_ms += dur;
    else if (r.state === 'stopped') {
      f.stopped_ms += dur;
      if (!r.openStart) (dur >= minStopMs ? f.stops++ : f.micro_stops++);   // parada conta na janela em que começa
    } else f.other_ms += dur;
  }
  return f;
}
```

- **Limiar mínimo de parada** (`minStopMs`): parada mais curta é micro-parada. Defina o limiar com a operação (valores típicos: 1 a 5 minutos). Micro-paradas reduzem o desempenho no OEE; paradas acima do limiar reduzem a disponibilidade. O tempo das duas entra em `stopped_ms`.
- Estado derivado de gauge (ex.: "rodando" se corrente > limiar): use **histerese** (limiar de entrada diferente do de saída) e tempo mínimo de permanência para não gerar centenas de transições com ruído.
- Parada que atravessa a janela: o tempo é repartido pelas janelas; o **contador de paradas** conta só na janela onde ela começou (`openStart` marca o trecho herdado). Isso mantém a soma de janelas igual ao total.
- Estados desconhecidos (código fora do mapa) entram em `other_ms`; nunca presuma "parado" nem "rodando".

### 2.4 Eventos (RFID, apontamento, pesagem)

- Chave de deduplicação: o identificador do evento (`ticket`, `tag + sequência`); sem identificador, `(origem, tag, instante arredondado ao período de re-leitura)`.
- Leitura repetida da mesma tag dentro de um período de **bloqueio** (ex.: 5 s) é a mesma passagem.
- Conte por janela do **instante do evento** (relógio do equipamento, quando confiável; senão o de recebimento, registrando qual foi usado).
- Evento atrasado cai na janela do seu instante e obriga o recálculo dela (seção 5).
- Pesagem estática: use só leitura **estável** (flag do indicador ou variação abaixo de X por Y s); líquido = bruto − tara; dedupe por ticket.

```js
function dedupe(events, keyFn, blockMs) {                   // ordena por t e mantém o 1º de cada chave dentro do bloqueio
  const lastSeen = new Map(), out = [];
  for (const e of [...events].sort((a, b) => a.t - b.t || (a.id > b.id ? 1 : -1))) {
    const k = keyFn(e), prev = lastSeen.get(k);
    if (prev === undefined || e.t - prev >= blockMs) { out.push(e); lastSeen.set(k, e.t); }
  }
  return out;
}
```

## 3. Qualidade do dado

| Qualidade | Tratamento padrão |
|---|---|
| Boa (`good`) | entra |
| Incerta (`uncertain`) | **fora** por padrão; entra só se a spec disser (ex.: sensor com substituição de valor) e fica contada em diagnóstico |
| Ruim (`bad`) | fora; encerra a validade do valor anterior |

- Mapeie os códigos do equipamento/protocolo para os três níveis **na spec** (ex.: OPC UA: bit 6-7 do StatusCode; Modbus não tem qualidade, então derive de timeout, faixa e frescor).
- **Sentinelas**: `-1`, `9999`, `65535`, `0xFFFF`, `NaN`, `null`, `-32768` marcam "sem leitura" em muitos equipamentos. Liste as do equipamento na spec e trate como `bad`, nunca como valor.
- **Faixa física**: fora de `[min, max]` do instrumento → `bad` (ou saturação, se for comportamento conhecido). Salto impossível entre amostras consecutivas (taxa de variação) → suspeito.
- **Valor congelado** (idêntico por muito tempo): normal para estado, setpoint e temperatura estável; suspeito para vazão em processo rodando, contador de equipamento em operação e qualquer sinal com ruído natural. Só aceite congelado quando a spec disser que é esperado e por quanto tempo; senão marque como incerto.
- **Zero legítimo × ausência**: vazão zero com equipamento parado é dado; ausência de amostra é buraco. Sem cobertura, `null`.
- Registre **contagem de amostras descartadas por motivo** (`bad`, faixa, sentinela, duplicata, fora de ordem). Descarte sem contagem esconde problema de campo.

## 4. Tempo e janelas

- **UTC no armazenamento e no cálculo**, em milissegundos inteiros (`number`). Fuso é só apresentação e fronteira de dia/turno.
- **Janela tumbling por hora, `[t0, t1)`**: início fechado, fim aberto. Amostra em `t1` pertence à janela seguinte. `t0 = Math.floor(t / 3600000) * 3600000`.
- **Amostra anterior à janela** fecha a borda: a última amostra antes de `t0` segura o valor até a primeira da janela (sujeita ao teto). Sem ela, o início da janela fica sem cobertura. A lógica recebe uma margem de lookback (ex.: `maxGapMs` antes de `t0`).
- **Recorte (clip)**: cada intervalo é recortado em `[t0, t1)` antes de somar (`max(s.t, t0)` e `min(next, t1)`); assim o mesmo segundo nunca conta em duas janelas.
- **Teto para buracos**: `maxGapMs = fator × intervalo_típico` (fator 2 a 5, definido pelo perfil). Além do teto o valor não é segurado; o tempo vira "sem cobertura". Não preencha buraco por conveniência.
- **Fora de ordem**: ordene por `t` dentro da lógica; não presuma ordem de chegada.
- **Duplicata por timestamp**: mesmo `t` com valores diferentes → regra explícita (ex.: a última recebida vence; igualdade exata é descartada) e contagem em diagnóstico.
- **Dado atrasado**: chega depois de a janela ser calculada. A lógica não sabe disso; o pipeline recalcula a janela quando chega dado com `t` nela. Exija idempotência (seção 6).
- **Relógio do equipamento × recebimento**: PLC sem NTP deriva. Se o gateway carimba o instante de leitura, prefira-o; compare com o recebimento e sinalize deriva acima de um limite. Instante no futuro (além de tolerância) é `bad`.
- **Dia e turno por fuso**: a lógica recebe janelas já resolvidas em UTC; a conversão (fuso da planta, horário de verão, turnos) fica fora do script, no host. Não dependa de `Intl` dentro do sandbox. Por isso a **base é a hora em UTC**: um dia com 23 ou 25 horas continua somando janelas horárias corretamente. Fuso com deslocamento de 30/45 min não alinha com a hora cheia em UTC; use janelas de 15 min ou confirme com a spec.
- Turno que atravessa a meia-noite pertence ao dia em que **começa**, salvo definição contrária da área.

## 5. Indicadores industriais (resumo; fórmulas em `references/indicadores.md`)

| Indicador | Definição curta | Armadilha |
|---|---|---|
| Disponibilidade | tempo rodando ÷ tempo planejado de produção | planejado é definição da operação (paradas programadas saem do denominador); sem cobertura não é parada |
| MTBF / MTTR | tempo operando ÷ nº de falhas; tempo de reparo ÷ nº de falhas | zero falhas: MTBF indefinido (`null`), não infinito; micro-parada não é falha |
| OEE | Disponibilidade × Desempenho × Qualidade | produto de percentuais; desempenho truncado em 100%; sem contagem de refugo, qualidade fica indefinida |
| Produção | soma de deltas do totalizador por hora/turno/dia | `último − primeiro`; fuso do dia |
| Vazão média rodando | massa ÷ tempo rodando | dividir pela janela inteira mistura parada com taxa |
| Taxa nominal | capacidade de projeto/ordem | desempenho > 100% costuma indicar nominal errado |
| Consumo específico | energia ou insumo ÷ produção | numerador e denominador no mesmo período e cobertura |

Mineração e britagem: balança de correia entrega taxa instantânea (t/h) e totalizador (t). Produção = soma de deltas do **totalizador**; a taxa serve para diagnóstico e para a vazão quando rodando. Os dois devem reconciliar (integral da taxa ≈ delta do totalizador, dentro de tolerância). Caldeira: produção específica de vapor (kg de vapor por kg de combustível), pressão e temperatura por média ponderada no tempo. Balança estática: eventos de pesagem (seção 2.4).

Métrica com efeito **fiscal, financeiro ou contratual** (faturamento, comissão, bonificação, imposto) passa por validação humana antes de ativar.

## 6. Agregação em camadas

1. **Fato por janela** (hora), calculado do bruto. Cada fato é **aditivo** (soma entre janelas) ou **não aditivo** (precisa dos componentes).
2. **Rollup** (turno, dia, mês) soma os **aditivos** e recalcula os não aditivos.

| Aditivo (guardar e somar) | Não aditivo (recalcular) |
|---|---|
| toneladas, kWh, peças, minutos rodando/parado/cobertos, nº de paradas | média, vazão média, disponibilidade, OEE, % qualquer, MTBF, MTTR |

```js
function rollup(hourFacts) {
  const sum = k => hourFacts.reduce((a, f) => a + (f[k] ?? 0), 0);
  const tons = sum('tons'), runMin = sum('run_min'), plannedMin = sum('planned_min'), stops = sum('stops');
  return {
    tons, run_min: runMin, planned_min: plannedMin, stops,
    tph_running: runMin > 0 ? tons / (runMin / 60) : null,          // recalculado do numerador e denominador
    availability: plannedMin > 0 ? runMin / plannedMin : null,
    mttr_min: stops > 0 ? sum('stopped_min') / stops : null,
  };
}
```

**Nunca** tire média de médias nem de percentuais: 2 h a 100 t/h e 10 min a 200 t/h não dão 150 t/h. Guarde `numerador` e `denominador` como fatos de cada janela (ex.: `tons` e `run_min`), e o percentual como conveniência.

**Saída de cada fato**: `valor`, `unidade`, e atributos de diagnóstico: `cobertura` (0 a 1), `amostras_usadas`, `descartes` por motivo, `resets`, `versao_logica`. Nomes em `snake_case` com a unidade no nome (`tons`, `run_min`, `tph`), estáveis (renomear quebra consumidores).

## 7. Determinismo, idempotência e reprocessamento

- **Mesma entrada, mesma saída.** Proibido `Date.now()`, `new Date()` sem argumento, `Math.random()` e dependência de ordem de iteração de objeto ou da ordem de chegada. O "agora" vem como parâmetro (`ctx.now`) e só decide se a janela está fechada.
- **Idempotência**: a saída é função da janela. Reprocessar a janela corrente (aberta) várias vezes sobrescreve o fato anterior e nunca acumula (`fato[janela] = f(bruto da janela)`, não `fato += ...`). Se a lógica emite incrementos, a chave de idempotência inclui janela e versão.
- **Janela aberta**: o resultado é provisório; marque `parcial: true` quando `t1 > ctx.now`.
- **Versionamento**: a lógica carrega `VERSION`. Mudou regra (limiar, política de reset, qualidade) → versão nova, e o recálculo histórico é decisão explícita (backfill) com comparação antes × depois. Fato guarda a versão que o gerou.
- **Escala e parâmetros** vêm da configuração versionada; nada de constante escondida no código sem constar na spec.
- Arredondamento só na apresentação; guarde precisão cheia. Some em ordem estável (ordenada por `t`) para evitar variação de ponto flutuante entre execuções.

## 8. Limites de sandbox

- Sem I/O: sem rede, disco, `require`, `fetch`, timers e relógio real. Tudo entra por parâmetro e sai pelo retorno. Código síncrono.
- Orçamento de memória e de tempo: a janela horária de um sinal a 1 Hz tem 3.600 amostras; a 10 Hz, 36.000. Percorra uma vez (O(n)); **evite O(n²)** (`find`/`filter` dentro de laço, `indexOf` em array grande). Use `Map` para chaves e ordene uma vez.
- Valide a forma da entrada no início (array, números finitos, `t` inteiro) e falhe com erro curto, não com `NaN` propagado.
- Evite `Intl`, `toLocaleString`, `Date` com fuso e regex pesada; use aritmética de milissegundos.
- **Log curto e útil**: uma linha de resumo por janela (`h=2025-03-01T10Z n=3598 cov=0.99 drop=2 resets=0 tons=412.3`). Nada de log por amostra.
- Falhe de forma explícita: erro de dados vira `null` + diagnóstico; só exceção para entrada malformada.

## 9. Testes da lógica

1. **Conjunto dourado**: janela pequena, escrita à mão, resultado calculado à mão e comentado (o leitor refaz a conta). É o contrato de comportamento.
2. **Casos de borda** (um teste cada): parada total, buraco maior que o teto, reset, rollover, amostra ruim e sentinela, janela vazia, amostra exatamente em `t0` e em `t1`, amostra anterior à janela, dado atrasado (resultado igual ao com dado em ordem), duplicata de timestamp, fora de ordem, uma única amostra, valor congelado, estado desconhecido.
3. **Gerador determinístico** (PRNG com semente) para volume e propriedades:

```js
function mulberry32(a) { return () => { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a);
  t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }

function genGauge(seed, t0, t1, meanStepMs) {                // amostragem irregular, com buracos e ruins
  const r = mulberry32(seed), out = []; let t = t0 - meanStepMs;
  while (t < t1) { t += Math.floor(meanStepMs * (0.2 + 1.6 * r())) + (r() < 0.02 ? 10 * meanStepMs : 0);
    out.push({ t, v: 100 * r(), q: r() < 0.03 ? 'bad' : 'good' }); }
  return out;
}
```

4. **Propriedades** (rode para centenas de sementes):
   - `run_min + stopped_min + other_min ≤ duração da janela` (e `= cobertura × duração`).
   - `tons ≥ 0`; `0 ≤ cobertura ≤ 1`; `mín ≤ média ≤ máx`.
   - **Aditividade**: fato(`[a,c)`) = fato(`[a,b)`) + fato(`[b,c)`) para os campos aditivos (vale se o lookback é o mesmo).
   - **Invariância**: embaralhar a ordem da entrada ou duplicar amostras não muda a saída.
   - **Idempotência**: executar duas vezes dá o mesmo resultado.
5. **Reconciliação com cálculo independente**: reimplemente de forma ingênua e diferente e compare dentro de tolerância. Exemplo, TWA por reamostragem a cada segundo:

```js
function twaBruteForce(samples, t0, t1, maxGapMs) {          // lento e simples, só para teste
  let num = 0, den = 0;
  for (let t = t0; t < t1; t += 1000) {
    let cur = null;                                          // última amostra com s.t <= t
    for (const s of samples) if (s.t <= t && (!cur || s.t >= cur.t)) cur = s;
    if (cur && cur.q === 'good' && t - cur.t < maxGapMs) { num += cur.v; den++; }
  }
  return den ? num / den : null;
}
```
   (Funciona com amostras em múltiplos de 1 s; para o resto, use tolerância.) Para produção, reconcilie também o fato contra o **bruto no banco**: `SUM(delta)` por consulta direta na fonte (ClickHouse/Postgres), em janela fechada, e contra a leitura do totalizador do equipamento.
6. **Revisão de lógica (checklist para o `reviewer`)**: sem não determinismo; bordas `[t0, t1)`; recorte; teto de buraco; `null` em vez de 0; qualidade e sentinelas na spec; reset/rollover; unidade; idempotência; complexidade O(n); log curto.

## 10. Checklist: lógica pronta para ativar

- [ ] Pergunta de negócio e dono da métrica registrados; efeito fiscal/financeiro validado por humano.
- [ ] Amostra real perfilada (intervalo, qualidade, resets, buracos, atrasos) e o perfil anotado na spec.
- [ ] Spec da métrica: definição, unidade, borda de janela, qualidade, buracos, resets, atrasos, `null`, versão.
- [ ] Lógica pura e determinística, sem I/O, O(n), dentro do orçamento de memória/tempo do sandbox.
- [ ] Testes: dourado, bordas, propriedades e aditividade, todos verdes.
- [ ] Reconciliação com cálculo independente e com o bruto, dentro da tolerância definida (diferença e causa documentadas).
- [ ] Saída com unidade, cobertura e diagnóstico; numerador e denominador guardados.
- [ ] Idempotente ao reprocessar a janela corrente; plano de recálculo/backfill e de reversão (desativar versão).
- [ ] Ativação em sombra (compara com a anterior ou com a reconciliação) antes de virar oficial, quando a plataforma permitir.
- [ ] Catálogo de métricas atualizado (nome, definição, unidade, fonte, versão, limitações).

## Fontes

Definições de conhecimento consolidado; **não reverificadas online nesta sessão**. Confirme valores normativos antes de citá-los a cliente.
- ISO 22400-2:2014, *Key performance indicators for manufacturing operations management* (disponibilidade, eficácia, OEE e taxa de qualidade).
- Nakajima, S. *Introduction to TPM* (1988): origem do OEE e das seis grandes perdas.
- IEC 60050-192 (Vocabulário Eletrotécnico Internacional, confiabilidade): MTBF, MTTR, disponibilidade.
- OPC Foundation, *OPC UA Part 4* (StatusCode: Good/Uncertain/Bad) e *Part 13* (Aggregates: TimeAverage, Interpolative, Stepped, Start/End bound).
- Documentação de historiadores de processo (ex.: AVEVA/OSIsoft PI, "time-weighted average") para a média ponderada no tempo com amostra de borda.
- Modbus Application Protocol Specification V1.1b3 (registradores de 16 bits, base do rollover em 65536).
