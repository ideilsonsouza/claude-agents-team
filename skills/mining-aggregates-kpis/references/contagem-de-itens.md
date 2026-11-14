# Contagem de itens e pesagem em esteira (ensacamento, paletização, peças)

Fontes aqui são de fornecedor e blog técnico: tratar como [campo]; nenhum limite abaixo é norma.

- **Contagem por borda:** contar só a transição desligado->ligado do sensor, com intervalo mínimo entre contagens (lockout) quando os itens estão colados. Debounce de 250 a 350 ms aparece para itens espaçados 0,5 s ou mais; validar na linha. [campo]
- **Dupla contagem:** formato do item cria segunda superfície de detecção (ex.: ponta/aba do saco); cortina de luz adicional detecta item rasgado ou colapsado. [campo]
- **Sensor:** resposta de cerca de 1 ms é padrão para contagem em esteira; poeira na lente e luz ambiente reduzem a confiabilidade; inclinar 10 a 15 graus evita reflexo. Em britagem e ensacamento de calcário a poeira é regra, não exceção. [campo]
- **Aceite:** um blog sugere 99% de exatidão de contagem contra contagem manual de 100 itens e teste na velocidade máxima da linha; é referência, não padrão. Perguntar à planta o critério dela. [campo]
- **Checkweigher** (pesadora dinâmica de itens): pesa cada item, conta e rejeita fora da faixa; produz **refugo/rejeição**, base de qualidade do OEE. [campo, Thermo Fisher]
- **Peso por contagem:** sacos x peso nominal x tolerância de embalagem, comparado com a balança de correia ou rodoviária, é outra reconciliação. Peso nominal e tolerância legal: [não verificado]; perguntar ao metrologia/qualidade da planta.
- **No OEE:** contador errado distorce desempenho (itens produzidos) e qualidade (boas/produzidas). Como o erro de contador entra nas perdas não foi encontrado em fonte: [não verificado]. Registre o erro de contagem como incerteza, não como perda.
