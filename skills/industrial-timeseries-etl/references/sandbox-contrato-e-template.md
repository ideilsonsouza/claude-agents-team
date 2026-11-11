# Lógica em sandbox: contrato típico, template e teste local

Seção 11 de `SKILL.md`, completa. Template: `template-logica.js`.

## 11. Lógica em sandbox: contrato típico, template e teste local

Plataformas de curadoria impõem um desenho parecido; o contrato exato (nomes, limites, validação) vem do projeto (arquivo de base `team-state/<slug>/curadoria.md` ou skill de projeto) e **manda no formato**. Template comentado e genérico: `references/template-logica.js` (ajuste o bloco "AJUSTE AQUI" e confira a forma do `ctx` com o contrato).

**Forma do módulo e do `ctx`**
- Módulo ES com `export default function (ctx)`, **síncrono** (Promise/`async` falha), sem `import`, `require`, `process`, `fetch` nem timers. `Date.now()` e `Math.random()` existem, mas não use (seção 7): derive tempo só de `ctx.window` e dos `ts` dos itens.
- `ctx` típico: `window {start, end}` ISO UTC (`[start, end)`, 1 hora); `items` da janela, ordenados; `prior` (último item de cada série antes da janela, até um prazo): **só ponto de partida**, nunca vira fato; `params` (JSON da versão); fuso e equipamentos do tenant; versão da lógica.
- `ctx` costuma chegar **congelado em profundidade**: `ctx.items.sort()` lança erro. Copie antes de ordenar. Série do `prior` pode vir duplicada (troca de credencial/chave): fique com a de maior `ts`.
- Cada execução usa um Isolate novo: nada persiste entre janelas, nem variável global.

**Saída**
- `{ facts: [{ entity, metric, periodStart, periodEnd, value, attributes }] }`. O host valida e **um único fato inválido derruba a janela inteira**: `metric` em snake_case (`^[a-z][a-z0-9_.]*$`), `value` finito (`NaN`/`Infinity` viram `null` no JSON), período ISO UTC com `Z` e **dentro da janela**, `attributes` objeto (`unit` sempre). Campo extra é descartado; o tenant é sempre o do job.
- Não há chave única de fato: emita **um fato por (entity, metric, período)**. Período da janela inteira para agregados horários; subperíodo só para intervalo real (uma parada).
- Pergunte ao contrato os **limites**: tamanho do código, da entrada e da saída com logs, nº de fatos, memória, tempo total, nº e tamanho de linhas de log (o excedente costuma ser ignorado em silêncio). Em produção o log pode nem ser gravado: só a simulação o mostra.

**Estrutura do template (mantenha)**: agrupar `ctx.items` por entidade (filtrando `kind`) → colar o `prior` mais recente **só se estiver colado** na 1ª amostra (distância ≤ teto + folga) → filtrar qualidade **por chave**, com uma função única → totalizador por soma de deltas positivos (queda = reset: não soma, é contada) → estado com teto (`intervalo × fatorBuraco`) e recorte na janela → fatos só quando há dado, `attributes.unit` sempre, percentual junto de numerador e denominador → **uma linha de log por janela** com contadores.

**Teste local**: rode no **sandbox real** da plataforma (mesmo `isolated-vm`, mesmos limites), não só em Node puro: Node não acusa `import`, `async`, `ctx` congelado nem período fora da janela. O teste é descartável e nunca vai para o repositório do produto. Casos obrigatórios, com número esperado calculado à mão:
1. caminho feliz com `prior` colado; 2. janela vazia (e só `prior`): nenhum fato; 3. sem `prior` ou `prior` longe demais: não inventar o delta da fronteira; 4. reset/rollover: não soma, é contado; 5. buraco: o teto limita o tempo do estado; 6. qualidade: código ruim descartado, congelado aceito só onde a spec permite; 7. recorte: nenhum período fora da janela; 8. **reconciliação entre horas**: soma dos deltas de duas horas seguidas = último total − primeiro; 9. entradas hostis: item sem `values`, `kind` inesperado, `params` ausentes; 10. contrato: `async`, `import` e período fora da janela falham; 11. `Intl` com o fuso do tenant, se usa dia civil; 12. linha final gravada (`unit` em `attributes`).

**Reconciliar antes de ativar**, contra fonte independente do mesmo período: (a) delta do totalizador = soma das toneladas das horas; (b) `min_rodando + min_parado` ≤ minutos com dado (nunca > 60 por hora e entidade); (c) disponibilidade = `rodando / (rodando + parado)`; (d) totais batem com relatório do equipamento ou do cliente. Divergência pequena e explicável (buraco, reset) vai nos `attributes`.

**Ciclo de vida**: versão imutável e numerada (mudar = versão nova, `params` incluídos); escopo piloto (um cliente) antes do global; **simular com dado real** de 1 a 7 dias com buracos e paradas (período sem itens "passa" sem provar nada); ativar não recalcula (janelas antigas ficam na versão anterior até o recálculo explícito, e o painel mostra versões misturadas); falha de lógica deixa a janela falhada até versão nova ou recálculo; reversão por rollback para a versão anterior.
