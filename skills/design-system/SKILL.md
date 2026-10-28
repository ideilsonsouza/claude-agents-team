---
name: design-system
description: Como construir e aplicar um design system — design tokens em 3 níveis (Tailwind 4 @theme ou variáveis CSS), plano de tokens antes do código, escalas de espaço, tipografia, raio e sombra por hierarquia, cores semânticas e paleta de gráficos, tema claro/escuro (color-scheme, theme-color), componentes headless por framework, estados e variantes, documentação no Storybook e regras para não cair no "kit de cards" genérico.
---

# Design system

> Se o projeto já tem design system (tokens, biblioteca de componentes, `@theme` do Tailwind, Figma), **use-o**: ele vence esta skill, a `ui-ux` e a `frontend-design`. Estas regras servem para criar ou evoluir um.

## 1. Plano de tokens (antes do código)
Ao criar um sistema ou tema novo, escreva primeiro um plano curto e revise-o com a pergunta "isto é o padrão de qualquer SaaS?" (o processo está em `ui-ux` §2):
- **Cor:** 4 a 6 cores-base nomeadas em hex, ligadas ao assunto do produto (indústria, materiais, vocabulário), e não à paleta que se usaria em qualquer projeto.
- **Tipo:** uma ou duas famílias escolhidas de propósito. Se forem duas, que sejam claramente diferentes. Diga o papel de cada uma.
- **Forma:** a escala de raio e de sombra, e onde cada uma se aplica.
- **Princípios:** 2 ou 3 frases sobre o que distingue este sistema.

## 2. Tokens (fonte única da verdade)
São três níveis:
1. **Primitivos:** a paleta bruta (`--blue-500`), a escala de espaço e as fontes.
2. **Semânticos:** a intenção (`--color-bg`, `--color-surface`, `--color-text`, `--color-text-muted`, `--color-primary`, `--color-danger`, `--color-warning`, `--color-success`, `--color-border`, `--color-focus`). **Os componentes usam só estes.**
3. **De componente** (opcional): `--button-bg`.

**Tailwind 4:** os tokens ficam no CSS, sem `tailwind.config.js`:
```css
@import "tailwindcss";
@theme {
  --color-primary: oklch(0.55 0.15 250);
  --font-sans: "Inter Variable", system-ui, sans-serif;
  --radius-control: 0.375rem;   /* botão, input */
  --radius-surface: 0.75rem;    /* card, painel */
}
```

**Escalas:**
- **Espaçamento:** base de 4 px (4, 8, 12, 16, 24, 32, 48, 64).
- **Tipografia:** escala modular (12, 14, 16, 20, 24, 32, 40), no máximo 2 famílias, e line-height de 1,4 a 1,6 no texto (mais apertado em título). Defina pesos e larguras de propósito. `tabular-nums` é um utilitário do sistema.
- **Raio e sombra por hierarquia**, e não um valor único para tudo: controle < superfície < overlay. Use sombra para elevação real (menu, modal). Para separar regiões, prefira borda ou fundo.
- **z-index e duração de animação:** escalas pequenas e nomeadas (`--duration-fast: 150ms`, `--duration-base: 250ms`).

**Cor:**
- Use OKLCH para gerar escalas com luminosidade uniforme. Confira o contraste de cada par texto/fundo semântico (4,5:1 e 3:1).
- **Estado e dado são separados:** os tokens `danger/warning/success` são só para estado. Os gráficos têm uma paleta categórica própria (`--chart-1`…`--chart-8`), segura para daltônicos, e uma sequencial para mapas de calor.

**Tema escuro:**
- Redefina os tokens semânticos (`[data-theme="dark"]` e `prefers-color-scheme`), e nunca as cores dentro dos componentes.
- `color-scheme: dark` no `<html>` (corrige scrollbar e inputs nativos) e `<meta name="theme-color">` igual ao fundo.
- No escuro, a superfície mais elevada fica mais clara. Não basta inverter a paleta.

## 3. Componentes
- **Primitivos acessíveis primeiro:** Button, Input, Select, Checkbox, Dialog, Toast, Tooltip, Tabs, Card, Table.
- **Bases headless** (acessibilidade pronta, ver as skills de framework):
  - React: **shadcn/ui com Base UI** (projeto novo) ou Radix (projeto existente);
  - Vue: **Reka UI** (shadcn-vue) ou Nuxt UI 4.
- **Em cada componente:**
  - variantes: `primary`, `secondary`, `ghost`, `danger`;
  - tamanhos: `sm`, `md`, `lg`;
  - estados: hover, focus-visible, active, disabled, loading;
  - hover, active e focus são **mais visíveis** que o repouso.
- **API consistente:** o mesmo nome de prop para a mesma ideia. Prefira variantes explícitas e composição (slots, compound components) a uma pilha de props booleanas (`isPrimary`, `isCompact`, `hasIcon`…).
- **Foco:** `:focus-visible` com o token `--color-focus`. Nunca `outline: none` sem substituto.
- **Card não é o padrão de layout.** Use-o para itens que se manipulam como unidade. Seções de página e grupos de campos não precisam virar cards.

## 4. Documentação
- Storybook (ou Histoire, para Vue) com cada variante e estado, e notas de uso (quando usar e quando não usar).
- Uma página de tokens com amostras de cor e contraste, a escala tipográfica e os exemplos de raio e sombra.

## 5. Regras
- Nenhum valor mágico no componente (`#3b82f6`, `13px`): use token.
- Mudou um token, mudou o sistema todo. Componente novo só se nenhum existente resolver.
- Mudança de token ou componente-base é revisada com captura de tela, nos temas claro e escuro.
