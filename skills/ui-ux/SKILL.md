---
name: ui-ux
description: Princípios de UI/UX da equipe — modo da tela (Operar, Persuadir, Ler) e quanto de expressão visual cabe em cada um, direção visual sem "cara de IA" (sinais a evitar, plano em 2 passes, uma ousadia só), hierarquia e layout, estados de interface, formulários, feedback e motion, densidade de dados em dashboard, responsividade, acessibilidade WCAG 2.2 AA e escrita de interface em pt-BR.
---

# UI/UX

> Ordem de prioridade: **pedido do usuário ou brief > design system do projeto > esta skill > `frontend-design`**.
> Para tokens e componentes, use `design-system`. Para auditar código pronto, use `ui-review`.

## 1. Modo da tela (decida antes de desenhar)
| Modo | Exemplos | O que vence | Expressão visual |
|---|---|---|---|
| **Operar** | dashboard, monitoramento da planta, CRUD, configurações | consistência, leitura rápida, densidade, previsibilidade | **baixa**: o design system manda; a ousadia fica num ponto só (ex.: o KPI principal ou o estado de alarme) |
| **Persuadir** | landing, marketing, onboarding, página de preço | identidade, memória, conversão | **alta**: use a `frontend-design` para a direção de arte |
| **Ler** | docs, blog, relatório, ajuda | tipografia, ritmo, navegação | **média**: a tipografia carrega a personalidade |

Uma mesma aplicação pode ter telas em modos diferentes. Na dúvida, um produto B2B fica em **Operar**.

## 2. Direção visual sem "cara de IA"
Hoje os layouts gerados por IA se repetem em poucos padrões. Eles não são proibidos, mas só valem como **escolha** feita para o brief, e não como padrão automático:
1. fundo creme (≈`#F4F1EA`) com serifa de alto contraste e destaque terracota (≈`#D97757`);
2. fundo quase preto com um único destaque verde-ácido ou vermelhão;
3. layout de jornal: fios finos, raio zero, colunas densas;
4. **kit de cards de SaaS**: tudo em cards idênticos, o mesmo raio em tudo, a mesma sombra cinza (`rgba(0,0,0,.1)`) e degradê como enfeite;
5. adornos de template: eyebrow em CAIXA ALTA acima de cada título, metadados separados com " · ", rótulos "PALAVRA — fragmento", `#0B0B0B` no lugar de preto, monoespaçada em rótulo pequeno, "→" colado no texto de botão e link.

Na tipografia, evite também:
- destacar uma única palavra do título com itálico, negrito ou outra cor;
- rótulo extra acima de conteúdo que já se explica;
- numeração "01 / 02 / 03" em algo que não é sequência;
- o hero padrão (número grande, rótulo pequeno, stats e destaque em degradê) quando ele não é a melhor opção.

**Processo em 2 passes** (tela nova ou redesenho, nos modos Persuadir e Ler; em Operar, só quando não houver design system):
1. **Plano:** 4 a 6 cores nomeadas em hex, as fontes e seus papéis, o layout em uma frase + wireframe ASCII com o alinhamento, e 2 ou 3 princípios desta tela.
2. **Revisão:** "isto sairia igual para qualquer produto parecido?" Se sim, troque essa parte e diga o que mudou e por quê. Só depois escreva o código.

**Contenção:** uma ousadia só. Um elemento memorável, e o resto quieto e disciplinado. Antes de terminar, tire um enfeite.

## 3. Hierarquia e layout
- Uma ação principal por tela, visualmente dominante. As secundárias têm menos peso.
- Agrupe por proximidade e alinhe em grade. Espaço em branco é estrutura, não desperdício.
- **A estrutura visual informa:** borda, divisor, numeração e rótulo existem porque dizem algo sobre o conteúdo, não para decorar.
- **O raio e a sombra seguem a hierarquia:** um contêiner de página, um card e um botão não precisam ter o mesmo raio.
- Linhas de texto com 60 a 80 caracteres (serifa aceita um pouco mais, com entrelinha maior). Títulos com contraste de tamanho e peso.

## 4. Dashboards e dados (modo Operar)
- **Números:** `font-variant-numeric: tabular-nums` em tabelas, KPIs e eixos; alinhe à direita; unidade sempre visível; casas decimais consistentes por grandeza.
- **Cor semântica é reservada:** vermelho, âmbar e verde só para estado (alarme, atenção, ok). Séries de gráfico usam uma paleta categórica separada e segura para daltônicos.
- **Densidade:** um modo compacto para operador experiente, sem baixar os alvos de 24 px nem o contraste.
- **O dado mais recente sempre visível:** selo "ao vivo"/"offline" com o horário do último dado (os 4 estados estão em `frontend-standards`).
- **Hierarquia do painel:** primeiro o que exige ação (alarmes), depois os KPIs, depois as tendências, e por último o detalhe.
- Filtros, abas e paginação ficam na URL.

## 5. Estados (toda tela e componente que depende de dados)
- **Carregando:** skeleton no formato do conteúdo. Spinner só para ação curta. Texto com reticências: "Salvando…".
- **Vazio:** um convite para agir. Explica o que vai aparecer ali e oferece a primeira ação.
- **Erro:** diz o que aconteceu e como resolver, sem pedir desculpas e sem ser vago. Oferece tentar de novo.
- **Sucesso:** confirmação discreta (toast), sem bloquear o fluxo.

## 6. Formulários
- Label visível sempre (placeholder não é label). O placeholder mostra um exemplo e termina com "…".
- Validação ao sair do campo e no envio. A mensagem fica junto do campo e é específica ("CPF deve ter 11 dígitos"). **No envio com erro, leve o foco ao primeiro campo errado.**
- O botão de envio fica habilitado até a requisição começar. Depois mostra o carregamento e bloqueia o duplo clique. Os dados digitados são preservados em caso de erro.
- Use o tipo certo (`email`, `tel`, `inputmode="numeric"`) e o `autocomplete`. **Nunca bloqueie colar.**
- Avise ao sair com alterações não salvas.

## 7. Feedback, interação e motion
- Toda ação responde em até 100 ms, nem que seja só com um estado visual.
- Ações destrutivas pedem confirmação ou oferecem desfazer. Nunca são imediatas.
- **Motion que responde a uma ação** (abrir, expandir, confirmar) é bem-vinda quando mostra o que mudou: de 150 a 300 ms, só `transform`/`opacity`, interrompível.
- **Motion que ninguém pediu** fica num único momento orquestrado, se houver. Fade + slide-up em cada seção e hover animado em todo card são o padrão genérico.
- Respeite `prefers-reduced-motion`. **Em dashboard de tempo real, nada de animação na atualização de dados.**

## 8. Responsividade
- Mobile first. Alvos de toque de 44×44 px (o mínimo WCAG é 24×24). Sem rolagem horizontal.
- Teste em 360, 768 e 1280 px. Dashboard também em 1920 px e em telão da planta, se for o caso.

## 9. Acessibilidade (WCAG 2.2 AA, obrigatória)
- HTML semântico: `button` para ação, `a` para navegação, landmarks, um `h1` por página, títulos em ordem e skip link.
- Tudo operável por teclado, com **foco visível** e ordem lógica. O foco não pode ficar escondido sob header fixo. Modais prendem e devolvem o foco.
- Contraste de 4,5:1 em texto normal, e de 3:1 em texto grande e em elementos de interface.
- Imagens com `alt` significativo (ou vazio, se forem decorativas). Botão só com ícone tem `aria-label`.
- A cor nunca é o único indicador: um erro tem cor, ícone e texto.
- Erros de formulário são anunciados (`aria-live` / `aria-describedby`).

## 10. Escrita na interface (pt-BR)
- **As palavras existem para facilitar o uso, não para enfeitar.** Cada texto tem um único trabalho.
- **Use a linguagem do usuário, não a do sistema:** "Notificações", não "Configuração de webhook".
- **O botão diz o que acontece:** "Salvar alterações", não "OK" ou "Enviar". **A ação mantém o nome no fluxo inteiro:** o botão "Publicar" gera o toast "Publicado".
- Prefira a voz ativa e verbos simples. **Só a primeira letra maiúscula** em título e botão (o padrão do pt-BR; o Title Case é inglês).
- Erros explicam o que houve e o próximo passo, na voz da interface: "Não foi possível salvar. Verifique a conexão e tente de novo."
- Use algarismos para contagens ("8 máquinas") e `…` em vez de "...". Use espaço não separável entre número e unidade (`10&nbsp;kW`).
- Mantenha os termos consistentes e use um glossário do produto quando houver.
