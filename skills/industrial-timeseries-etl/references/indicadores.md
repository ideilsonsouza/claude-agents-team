# Indicadores industriais: fórmulas e armadilhas

Definições padrão e genéricas. A operação define o que é "planejado", "falha" e "refugo": registre na spec da métrica.

## Tempos (base de tudo)

| Termo | Definição |
|---|---|
| Janela | intervalo `[t0, t1)` de cálculo (duração `W`) |
| Tempo coberto | parte de `W` com dado válido (`C ≤ W`) |
| Tempo planejado de produção (`P`) | tempo em que se esperava produzir (exclui paradas programadas, feriados, sem turno) |
| Tempo rodando (`R`) | tempo com o equipamento em estado de produção |
| Tempo parado (`S`) | tempo planejado parado (falha, setup, falta de material) |
| Tempo sem cobertura (`W − C`) | desconhecido; **não** é parada nem produção |

`R + S ≤ C ≤ W`. Se `P` vem de calendário de turnos, calcule a interseção janela × turno antes de comparar com `R` e `S`.

## Disponibilidade

`A = R / P`  (0 a 1). Variante com cobertura: `A = R / (R + S)` quando o planejado só é conhecido pelo estado.
- Armadilhas: paradas programadas dentro do denominador reduzem artificialmente `A`; buraco de comunicação contado como parada; micro-paradas (abaixo do limiar) contadas ou não em `R` sem a spec dizer.
- Rollup: `A = ΣR / ΣP`, nunca a média das disponibilidades.

## MTBF e MTTR

- `MTBF = tempo operando / nº de falhas`
- `MTTR = tempo total de reparo / nº de falhas`
- `A_inerente = MTBF / (MTBF + MTTR)` (relação teórica, só vale com as mesmas definições de falha).
- Armadilhas: sem falha, MTBF é `null`; falha = parada não programada acima do limiar (definir); o início da parada conta na janela em que começa (ver SKILL, seção 2.3); rollup é `Σ tempo operando / Σ falhas`, com os dois somados como fatos.

## OEE

`OEE = Disponibilidade × Desempenho × Qualidade`
- `Desempenho = (tempo de ciclo ideal × quantidade total) / R = taxa real / taxa nominal`
- `Qualidade = quantidade boa / quantidade total`
- Equivalente: `OEE = (tempo de ciclo ideal × quantidade boa) / P`.
- Armadilhas:
  - Desempenho truncado em 100% (acima disso o nominal está errado ou a contagem inflada).
  - Qualidade exige contagem de refugo/retrabalho; sem ela, não publique OEE completo (publique disponibilidade × desempenho e diga isso).
  - Taxa nominal é da ordem/produto em andamento, não uma constante da planta.
  - Em processo contínuo (mineração, caldeira), "qualidade" costuma ser teor/especificação, não contagem de peças; defina na spec.
  - Rollup: recalcule com `ΣR`, `ΣP`, `Σquantidade total`, `Σquantidade boa`, `Σ(ciclo ideal × quantidade)`; nunca média dos OEE.
  - TEEP (OEE sobre todo o tempo de calendário) é outro indicador; não misturar com OEE.

## Produção e vazão

- `produção = Σ deltas positivos do totalizador` na janela (turno/dia = soma das janelas horárias).
- `vazão média rodando = produção / (R / 60)` (unidade da produção por hora, com `R` em minutos).
- `vazão média na janela = produção / (W / 3600000 h)` (inclui as paradas; é outro indicador, nomeie diferente).
- `produção por turno/dia`: fronteira de turno em UTC resolvida pelo host (fuso da planta).
- **Reconciliação taxa × totalizador**: `∫ taxa dt ≈ Δ totalizador`. Diferença acima da tolerância indica escala errada, totalizador congelado, deadband agressivo ou buraco.
- Em dúvida, o totalizador é a referência da produção; a taxa é diagnóstico.

## Consumo específico

`consumo específico = consumo do insumo (kWh, litros, kg de combustível) / produção` no mesmo período e com a mesma cobertura. Se a cobertura de um dos dois é baixa, o indicador sai `null` ou parcial. Rollup por soma de numerador e denominador.

## Mineração e britagem (conceitos gerais)

- Balança de correia: peso por metro × velocidade da correia = taxa (t/h); totalizador integra a taxa. Correia vazia/parada com taxa pequena diferente de zero (deriva de zero) é ruído: aplique corte de taxa mínima só se a spec definir.
- Rodando = correia em movimento (velocidade/estado) **e** taxa acima do corte; defina qual regra vale.
- Utilização = tempo rodando / tempo calendário planejado; disponibilidade física = tempo disponível (não em manutenção) / planejado. São indicadores diferentes.

## Caldeiras (conceitos gerais)

- Produção específica de vapor = `vapor produzido (kg) / combustível consumido (kg)`.
- Eficiência pelo método direto = `calor útil no vapor / calor do combustível` (exige entalpia e poder calorífico; os de referência vêm da spec).
- Pressão e temperatura: média ponderada no tempo, mínimo e máximo; vazões acumuladas por soma de deltas.

## Balanças estáticas

Evento por pesagem estável: `líquido = bruto − tara`; um ticket = um evento; soma por janela do instante da pesagem; tara fora de faixa ou líquido negativo → evento marcado como suspeito (não somar sem decisão da spec).

## Exemplo resolvido (para o conjunto dourado)

Janela de 1 h (60 min). Estado: rodando 00:00-00:40, parado 00:40-00:50 (10 min, acima do limiar de 3 min), rodando 00:50-00:55, parado 00:55-00:57 (2 min, micro-parada), rodando 00:57-01:00.
- `R = 40 + 5 + 3 = 48 min`, `S = 12 min`, `stops = 1`, `micro_stops = 1`, `P = 60 min`.
- `A = 48/60 = 0,80`; `MTTR = 10 min` (falhas acima do limiar) ou `12 min` (se micro-paradas contarem como falha: a spec decide).
- Totalizador 1000 → 1048 t: `produção = 48 t`; `vazão rodando = 48 / (48/60) = 60 t/h`; vazão na janela = `48 t/h`.
- Segunda hora: `R = 60`, produção 120 t. Rollup de 2 h: `produção = 168 t`, `R = 108`, `vazão rodando = 168/(108/60) = 93,3 t/h` (a média simples de 60 e 120, 90 t/h, está errada).
