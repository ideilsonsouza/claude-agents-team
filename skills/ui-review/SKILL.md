---
name: ui-review
description: "Auditoria de código de interface (Vue, React, Astro) contra checklist de acessibilidade, foco, formulários, animação, performance, tema escuro, i18n e copy pt-BR, com achados em arquivo:linha. Usar em \"revisar a UI\", \"auditar acessibilidade\", \"revisar UX\" ou revisão de PR de frontend."
argument-hint: <arquivo-ou-padrão>
---

# Revisão de UI

Adaptada das Web Interface Guidelines da Vercel (`vercel-labs/web-interface-guidelines`, MIT, `command.md` no commit `434b7f91`). **É uma cópia fixa**: não busque a versão remota. Diferenças em relação ao original: Vue e Astro, copy em pt-BR (sem Title Case) e regras da equipe (`ui-ux`, `frontend-standards`).

## Como usar
1. Leia os arquivos pedidos. Se nenhum foi indicado, use os do diff da branch (`git diff --name-only main...`) ou pergunte.
2. Compare cada um com as regras abaixo. **O design system e as convenções do projeto vencem** o checklist.
3. Entregue no formato da última seção. Sem preâmbulo e sem explicação, a não ser que a correção não seja óbvia.

## Regras

### Acessibilidade
- Botão só com ícone tem `aria-label`. Ícone decorativo tem `aria-hidden="true"`.
- Controle de formulário tem `<label>` ou `aria-label`.
- `<button>` para ação, `<a>`/`<RouterLink>`/`<Link>` para navegação. Nunca `<div @click>`/`<div onClick>`.
- Imagem tem `alt` (ou `alt=""`, se decorativa).
- Atualização assíncrona (toast, validação, alarme) em `aria-live="polite"`.
- HTML semântico antes de ARIA. Títulos `h1`–`h6` em ordem, e skip link para o conteúdo.
- `scroll-margin-top` em âncora de título.
- Gráfico tem alternativa em tabela ou texto. A cor nunca é o único canal.

### Foco
- Elemento interativo tem foco visível (`:focus-visible`, `focus-visible:ring-*`).
- Nunca `outline: none`/`outline-none` sem substituto.
- `:focus-within` em controle composto.
- Header, footer ou overlay fixo não cobre o elemento focado.

### Formulários
- Input tem `autocomplete` e `name` com significado. Use o `type` e o `inputmode` certos.
- **Nunca bloqueie colar.**
- Label clicável (`for`/`htmlFor`, ou envolvendo o controle). Checkbox e radio dividem a mesma área de clique com o label.
- `spellcheck="false"` em e-mail, código e usuário.
- Envio: o botão fica habilitado até a requisição começar, e mostra o carregamento durante ela.
- O erro aparece junto do campo, e **o foco vai ao primeiro erro** no envio.
- O placeholder mostra um exemplo e termina com `…`.
- Aviso ao sair com alterações não salvas (guard do router ou `beforeunload`).

### Animação
- `prefers-reduced-motion` respeitado.
- Só `transform`/`opacity`. **Nunca `transition: all`**: liste as propriedades.
- `transform-origin` correto. Em SVG, `transform-box: fill-box` no `<g>`.
- A animação é interrompível. Movimento automático de mais de 5 s tem controle de pausar.
- Nenhuma animação na atualização de dados em tempo real.

### Tipografia
- `…` em vez de `...`. Aspas curvas (“ ”).
- Espaço não separável: `10&nbsp;kW`, `⌘&nbsp;K`.
- Estado de carregamento termina com `…`: "Carregando…", "Salvando…".
- `tabular-nums` em colunas numéricas, KPIs e comparações.
- `text-wrap: balance` ou `pretty` em títulos.

### Conteúdo
- Contêiner de texto aguenta conteúdo longo (`truncate`, `line-clamp-*`, `break-words`). Filho de flex tem `min-w-0`.
- Estado vazio tratado: nada de UI quebrada com string ou array vazio. Os 4 estados estão em `frontend-standards` §5.
- Conteúdo do usuário: pense no curto, no médio e no muito longo.

### Imagens
- `<img>` com `width` e `height`. `loading="lazy"` abaixo da dobra e `fetchpriority="high"` na imagem de LCP.

### Performance
- Lista com mais de 50 itens tem virtualização (TanStack Virtual, `vue-virtual-scroller`, `content-visibility: auto`).
- Nenhuma leitura de layout no render (`getBoundingClientRect`, `offsetHeight`, `scrollTop`). Leituras e escritas de DOM em lote.
- Input controlado é barato a cada tecla.
- `preconnect` para domínios de assets. A fonte crítica tem `preload` e `font-display: swap`.
- Stream sem render por mensagem (buffer + rAF, `frontend-standards` §6).

### Navegação e estado
- A URL reflete o estado: filtros, abas, paginação e painéis expandidos na query.
- Links são `<a>` de verdade, com suporte a Ctrl+clique e clique do meio.
- Ação destrutiva tem confirmação ou desfazer, e nunca é imediata.

### Toque e interação
- `touch-action: manipulation`. `overscroll-behavior: contain` em modal, drawer e sheet.
- Gesto (arrastar, deslizar, pinçar) tem alternativa por clique e teclado. Alvos de pelo menos 24×24 px.
- `autofocus` com moderação: só no desktop e só no input principal.

### Layout
- `env(safe-area-inset-*)` em layout de borda a borda. Sem scrollbar indesejada nem rolagem horizontal.
- Layout com flex e grid, não com medição em JS.

### Tema escuro
- `color-scheme: dark` no `<html>`. `<meta name="theme-color">` igual ao fundo.
- `<select>` nativo com `background-color` e `color` explícitos.
- Cores via tokens semânticos, nunca fixas no componente (`design-system`).

### Locale e i18n
- Datas com `Intl.DateTimeFormat` **no fuso da planta ou do tenant**. Números com `Intl.NumberFormat`.
- Nome de marca, código e identificador com `translate="no"`.
- Frases sem concatenação (prontas para i18n).

### Hidratação (Nuxt, Next, Astro com ilhas)
- Input com `value` tem `onChange` (ou `defaultValue`).
- Data e hora protegidas contra divergência entre servidor e cliente. `suppressHydrationWarning` só onde for inevitável.

### Hover e estados
- Botão e link têm estado de hover. Hover, active e focus têm **mais** contraste que o repouso.

### Copy (pt-BR, ver `ui-ux` §10)
- Voz ativa. Botão específico ("Salvar chave da API", não "Continuar").
- **Só a primeira letra maiúscula** em título e botão.
- A mesma ação tem o mesmo nome no fluxo inteiro ("Publicar" gera "Publicado").
- A mensagem de erro diz o próximo passo. Algarismos em contagens.

### Antipadrões (aponte sempre)
- `user-scalable=no` ou `maximum-scale=1`.
- `onPaste`/`@paste` com `preventDefault`.
- `transition: all`.
- `outline-none` sem substituto de `focus-visible`.
- Navegação por `onClick` sem `<a>`. `<div>`/`<span>` com handler de clique.
- Imagem sem dimensões.
- `.map()`/`v-for` grande sem virtualização.
- Input sem label. Botão de ícone sem `aria-label`.
- Formato de data ou número fixo no código.
- `autofocus` sem justificativa. GIF animado onde caberia vídeo.
- Gesto sem alternativa.
- `v-html`/`dangerouslySetInnerHTML`/`set:html` com dado externo.
- Valor mágico de cor ou espaço no lugar de token.
- Sinais de "visual de IA" (`ui-ux` §2) usados sem motivo no brief.

## Formato de saída
Agrupe por arquivo, com `arquivo:linha` clicável:

```text
## src/components/MachineCard.vue

src/components/MachineCard.vue:42 - botão de ícone sem aria-label
src/components/MachineCard.vue:55 - animação sem prefers-reduced-motion
src/components/MachineCard.vue:67 - transition: all → listar propriedades

## src/components/AlarmList.vue

src/components/AlarmList.vue:12 - 800 itens sem virtualização
src/components/AlarmList.vue:34 - "..." → "…"

## src/components/Header.vue

✓ ok
```

No fim, uma linha com o total por gravidade:
- **bloqueia:** a11y, segurança, perda de dado;
- **corrigir:** UX e performance;
- **sugestão:** polimento.
