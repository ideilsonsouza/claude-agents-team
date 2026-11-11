# Testes da lógica

Seção 9 de `SKILL.md`, completa.

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
