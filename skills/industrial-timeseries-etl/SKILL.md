---
name: industrial-timeseries-etl
description: "Análise de dados brutos e lógicas de curadoria (ETL) de séries temporais industriais: agregação por tipo de sinal, qualidade, tempo/UTC, OEE, MTBF/MTTR, reprocessamento e testes. Usar ao analisar dado de sensores/PLC, definir indicador, escrever ou revisar lógica de curadoria ou ETL de telemetria."
---

# ETL de séries temporais industriais (lógicas de curadoria)

Padrão da equipe, genérico. Fórmulas dos indicadores em `references/indicadores.md`. O detalhe (código, exemplos, seções longas) fica em `references/`; o gatilho de cada arquivo está na seção 'Referências' abaixo.
- Se existir contrato da plataforma do projeto (skill de projeto ou `team-state/<slug>/curadoria.md`: entrada, saída, limites, nomes), ele manda no formato. Esta skill manda no **método**; a seção 11 traz o contrato típico de uma lógica em sandbox e o template.
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


Regras por tipo (código e detalhe em `references/agregacao-por-tipo.md`): gauge = média ponderada no tempo com teto de buraco e cobertura; contador = soma de deltas (rollover só perto do topo, reset contado, salto impossível descartado); estado = duração recortada na janela, parada conta onde começa; evento = deduplicado por chave e bloqueio.

## 3-4. Qualidade, tempo e janelas (resumo; completo em `references/qualidade-e-tempo.md`)
- Só `good` entra; `uncertain` fora por padrão; sentinelas e fora de faixa = `bad`; descarte sempre contado por motivo.
- UTC em ms; janela `[t0, t1)`; recorte antes de somar; amostra anterior fecha a borda; teto `maxGapMs` para buraco; ordene por `t`; dado atrasado recalcula a janela; fuso e turno ficam no host.

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


Métrica com efeito **fiscal, financeiro ou contratual** passa por validação humana antes de ativar. Balança de correia, caldeira e pesagem estática: ver `references/camadas-e-indicadores.md`.

## 6. Agregação em camadas (resumo)
Fato por janela (hora) calculado do bruto; rollup soma os **aditivos** (toneladas, kWh, minutos, nº de paradas) e **recalcula** os não aditivos (médias, %, OEE, MTBF). **Nunca** média de médias. Saída com `valor`, `unidade`, `cobertura`, `amostras_usadas`, `descartes`, `versao_logica`; nomes `snake_case` estáveis. Código e exemplo: `references/camadas-e-indicadores.md`.

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

## 9. Testes (resumo; completo em `references/testes-da-logica.md`)
Dourado à mão, uma borda por teste, gerador com semente, propriedades (aditividade, invariância, idempotência), reconciliação com cálculo independente e com o bruto.

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
- [ ] Testada no sandbox real da plataforma (12 casos da seção 11), simulada com dado real e com plano de recálculo e reversão.

## Referências (abrir só quando o gatilho ocorrer)
- `references/agregacao-por-tipo.md`: ao escrever ou revisar o código de gauge, contador, estado ou evento.
- `references/qualidade-e-tempo.md`: ao definir qualidade, sentinelas, janelas, atraso, fuso ou turno.
- `references/camadas-e-indicadores.md`: ao fazer rollup, definir saída ou indicador de mineração/caldeira/pesagem.
- `references/indicadores.md`: ao calcular disponibilidade, MTBF/MTTR, OEE e afins.
- `references/testes-da-logica.md`: ao escrever testes, gerador ou reconciliação, ou revisar lógica.
- `references/sandbox-contrato-e-template.md` (seção 11) e `references/template-logica.js`: ao escrever lógica para sandbox, simular ou ativar.
- `references/fontes.md`: ao citar norma ou fonte a cliente.
