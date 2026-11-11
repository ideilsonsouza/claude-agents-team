# Qualidade do dado e tempo/janelas

Seções 3 e 4 de `SKILL.md`, completas.

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
