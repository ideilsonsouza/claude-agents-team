---
name: mining-aggregates-kpis
description: "Vocabulário e KPIs de mineração de calcário e agregados (pedreira, britagem, moagem, peneiramento, correias, balança de correia, pilhas, expedição) e de processos com contagem de itens e pesagem em esteira. Use sempre que for definir, nomear ou criticar indicador (t/h, disponibilidade física, utilização, OEE, kWh/t, parada por motivo, MTBF/MTTR), interpretar totalizador de balança de correia, reconciliar balança de correia x balança rodoviária x inventário, ou avaliar o que operador, supervisor e gestor precisam ver numa tela de produção, mesmo que o pedido não cite mineração."
---

# KPIs e vocabulário: mineração de calcário e agregados

Skill de domínio compartilhada pelos agentes de consulta `mining-process`, `production-manager` e `data-analyst`. Serve para falar a língua do setor e para separar **fato com fonte** de **prática de campo** e de **opinião**. Fórmulas gerais de OEE e de agregação por tipo de sinal ficam em `industrial-timeseries-etl` e `shop-floor`; aqui entra o que é específico de pedreira e esteira.

## Como usar
1. Leia só a referência do assunto (tabela abaixo); não carregue tudo.
2. Cada número ou fórmula leva a marca **[fonte]**, **[campo]** (prática de planta, vendor ou fórum; confirmar na planta) ou **[não verificado]**. Fórmula varia por empresa: diga qual variante usou e peça a da planta. Nunca invente meta ou faixa típica de t/h e kWh/t: elas dependem de equipamento, rocha e abertura; devolva a pergunta para a planta.
3. Dado de cliente (volumes, metas, nomes) não entra em exemplo; use números sintéticos.

| Assunto | Arquivo |
|---|---|
| Circuito, equipamentos, rocha, produto (calcário agrícola/cal), pilha, expedição | `references/processo-e-vocabulario.md` |
| Balança de correia: zero, span, teste de material, deriva, totalizador, reconciliação | `references/balanca-de-correia.md` |
| Contagem de itens em esteira e checkweigher | `references/contagem-de-itens.md` |
| KPIs, definições, variantes e o que cada público precisa ver | `references/kpis-e-publicos.md` |
| Fontes e grau de confiança | `references/fontes.md` |

## Regras de ouro (porquê de cada uma)
- **t/h tem denominador de tempo de operação, não de calendário.** Misturar os dois faz a mesma planta parecer dois valores; sempre diga qual.
- **Totalizador é contador acumulado, não produção do turno.** Produção = soma de deltas válidos; reset, rollover e zero-drift se tratam antes de somar. Ver `balanca-de-correia.md`.
- **Balança de correia é medida de processo; balança rodoviária é a referência de expedição.** Divergência é sinal para investigar zero, span, umidade e densidade, não para "corrigir" um lado no relatório.
- **Disponibilidade, utilização e OEE têm várias definições.** ISO 22400-2 define disponibilidade como tempo de produção real / tempo ocupado planejado; plantas de mineração costumam usar disponibilidade física (horas sem manutenção / horas calendário). Pergunte antes de comparar.
- **Parada sem motivo é o maior buraco de dado.** Um Pareto de paradas só vale com taxa de apontamento alta; informe a cobertura.
- **Tela por público:** operador vê o agora (estado, t/h contra o alvo, alarme), supervisor vê o turno (acumulado contra meta, paradas, tendência da hora), gestor vê desvio e tendência (dia/semana/mês), diretoria vê custo e resultado. Mais que isso vira ruído.

## Entrevista sobre um produto
Quando o orchestrator pede opinião sobre tela, relatório ou produto, responda em itens: **O que é útil**, **O que falta**, **O que confunde**, **Prioridades** (operador, supervisor, gestor), **Perguntas para a planta**. Marque cada item como Fato (com fonte), Prática de campo ou Opinião. Opinião não vira requisito: o `prd` decide.
