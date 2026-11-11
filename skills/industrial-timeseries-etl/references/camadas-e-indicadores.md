# Indicadores (detalhe) e agregação em camadas

Parte da seção 5 e seção 6 de `SKILL.md`. Fórmulas em `indicadores.md`.

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
