# Agregação por tipo de sinal (gauge, contador, estado, evento)

Detalhe da seção 2 de `SKILL.md`: código e regras.

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
