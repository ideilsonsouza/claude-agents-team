# KPIs, variantes e públicos

## Definições (sempre cite a variante)
| KPI | Definição | Variantes e cuidados |
|---|---|---|
| Produção (t) | Soma de deltas válidos do totalizador da balança de correia do ponto de produção | Ponto de medição importa (saída do britador x entrada do silo). Ver `balanca-de-correia.md`. |
| Taxa horária (t/h) | t produzidas / horas **operando** | Por calendário dá "t/h médio do turno"; chame de outro nome. Precisa de pelo menos uma balança de correia. [fonte: Maintworld] |
| Disponibilidade (ISO 22400-2) | Tempo de produção real / tempo ocupado planejado | Fonte secundária; a norma é paga. [fonte secundária: iteh, fabrico, teeptrak] |
| Disponibilidade física (mineração) | (horas calendário - horas de manutenção) / horas calendário | Convenção de campo; confirmar com a planta. [campo] |
| Utilização | Horas operando / horas disponíveis (ou duração do turno) | Exemplo de produtor de agregados: 12 h de operação em turno de 16 h. [fonte: Maintworld] |
| Tempo efetivo de britagem | Fração do tempo ligado em que há material passando | Maintworld usa "tempo de britagem eficiente / tempo ligado" (0 a 100%). Distingue ligado vazio de produzindo. [fonte] |
| OEE | Disponibilidade x desempenho x qualidade (ISO 22400-2: efetividade = tempo planejado por item x quantidade / tempo de produção real) | Em fluxo contínuo, "ciclo ideal" vira taxa nominal (t/h de projeto). Qualidade em calcário: fração dentro da especificação/PRNT. [fonte secundária + campo] |
| Consumo específico (kWh/t) | kWh da planta / t produzidas | Metso Benchmark Quarry Index usa kWh/t total da planta, junto com t/h e dificuldade da rocha. [fonte] |
| Combustível por tonelada | L diesel / t produzidas | Exige balança de correia. [fonte: Maintworld] |
| MTBF / MTTR | Tempo médio entre falhas / tempo médio de reparo | Defina o que conta como falha e a origem do tempo de reparo. |
| Parada por motivo | Tempo parado por categoria (planejada, não planejada, operacional, falta de material, manutenção) | Registre a **cobertura** (% do tempo parado com motivo). |
| Custo por tonelada | Custo operacional / t | Depende de dado financeiro; fora do alcance do chão sem integração. [campo] |
| Estoque em pilha / expedição | t em pilha (levantamento + livro), t expedidas | Reconciliar com a balança rodoviária. |
| Share de produto planejado | t do produto planejado / t totais | Presente no Benchmark Quarry Index da Metso. [fonte] |

## O que cada público precisa (opinião fundamentada; validar com a planta)
- **Operador (HMI, andon):** estado de cada equipamento (rodando, parado, alarme), t/h contra o alvo, alarme com ação, motivo de parada em poucos toques, produção do turno até agora. ISA-101/HMI de alto desempenho: fundo neutro, cor reservada a condição anormal, contraste mínimo 3:1, validar com operadores reais. [fonte: ISA/ASM, valores de cinza divergem entre fontes]
- **Supervisor:** acumulado do turno contra meta e curva de ritmo por hora, paradas por motivo (Pareto do turno), equipamento limitante, passagem de turno com pendências. Controle de intervalo curto (short interval control): ver o desvio enquanto há tempo de recuperar. [fonte: artigos de mineração; vendor]
- **Gestor:** resumo diário/semanal/mensal, tendência e desvio contra meta, disponibilidade e utilização, causas principais de perda, estoque e expedição, qualidade do dado (cobertura, balança fora de calibração).
- **Diretoria:** produção, custo/t, resultado, risco; poucos números, com rastro até a origem.
- **Adoção do produto (analista):** usuários ativos por papel e turno, % de paradas com motivo apontado, tempo até apontar, telas mais vistas, uso na passagem de turno, divergência balança x relatório manual.

## Painéis e análises úteis
Curva de ritmo (acumulado por hora x meta), Pareto de paradas por tempo e por frequência, tendência de zero da balança, t/h por hora do dia, comparação entre turnos e equipes (com cuidado: turnos pegam rocha e equipamento diferentes).
