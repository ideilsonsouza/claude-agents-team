# Balança de correia (belt weigher / belt scale)

## O que é
Instrumento que pesa material a granel sobre a correia em movimento, sem dividir a massa em lotes nem parar a correia. Integra carga por metro (kg/m) x velocidade da correia e acumula no **totalizador**. A norma de referência internacional é a OIML R 50 (parte 1 requisitos, parte 2 ensaios, parte 3 relatório); a de 2014 trata classes de exatidão, erro máximo permitido, carga mínima totalizada e vazão mínima. Os valores das classes não foram verificados aqui: consultar o PDF oficial. [fonte: OIML R 50-1; classes e limites não verificados]

## Rotina de verificação [fonte parcial, a maioria prática de fabricante]
| Ensaio | O que faz | Observações |
|---|---|---|
| **Zero** | Correia vazia, em movimento, por voltas inteiras; ajusta o ponto zero | Fabricantes citam periodicidade diária (Rice Lake), semanal ou após parada (blog OxMaint), antes de cada teste de material (Cardinal). Zero check não é calibração. [campo] |
| **Span** | Carga conhecida (pesos de teste ou corrente) após o zero estável | Tolerância de 0,25% e frequência mensal aparecem em blog de fornecedor: não é norma. [campo] |
| **Teste de material** | Passa uma quantidade conhecida de produto e compara o totalizador com a balança de referência (ex.: rodoviária certificada); ajusta o fator (trim) | É a referência de exatidão em operação. Registrar leituras antes/depois. [campo, fabricantes] |

Exatidão é melhor no meio e na parte alta da faixa, pior fora dela. [campo]

## Causas de deriva e erro
Acúmulo de material em estruturas fora do pivô (amplifica deriva de zero em desenhos de quadro articulado), esticamento e desgaste da correia, roletes desgastados, mudança de densidade, desalinhamento da correia, chuva/umidade no material, vibração. [campo: fabricantes Thermo, Tru-Trac, Siemens]

## Qualidade do dado a olhar (para o analista)
- **Zero em operação:** vazão diferente de zero com a correia vazia (sensor de rotação ou corrente do motor indicam vazio) = deriva de zero.
- **Totalizador:** só cresce; **queda** = reset ou troca de equipamento; **salto** impossível (maior que vazão máxima x intervalo) = descarte; **rollover** perto do fundo de escala. Soma de deltas positivos, não último menos primeiro. Ver `industrial-timeseries-etl`.
- **Totalizador parado com correia rodando**: falha de comunicação ou da balança, não "zero produção".
- **Dado atrasado ou repetido** (heartbeat sem mudança) é diferente de dado ausente.
- **Ruído de vazão:** oscilação alta com carga constante aponta roletes ou correia.

## Reconciliação [campo, sem norma]
Balança de correia x balança rodoviária x inventário (levantamento). Tolerâncias de 1% a 2% entre levantamento e livro aparecem em relato de praticante (fórum, 2009): usar só como pergunta à planta, não como regra. Fluxo recomendado: (1) mesmo período e fronteira (do mesmo ponto da correia ao mesmo ponto de expedição); (2) corrigir umidade se um lado é seco e o outro úmido; (3) comparar diferença percentual por período e por balança; (4) se a diferença anda sempre no mesmo sentido, suspeitar de span; se oscila, de zero.
