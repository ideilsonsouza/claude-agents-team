---
name: design-system
description: Como construir e aplicar um design system — design tokens, escala de espaçamento e tipografia, cores com tema claro/escuro, biblioteca de componentes e documentação.
---

# Design system

> Se o projeto já tem design system (tokens, biblioteca de componentes, Tailwind config, Figma), **use-o**. Estas regras servem para criar ou evoluir um.

## Tokens (fonte única da verdade)
Defina como variáveis CSS (ou tema do Tailwind) em três níveis:
1. **Primitivos**: paleta bruta (`--blue-500`), escala de espaço, fontes.
2. **Semânticos**: intenção (`--color-bg`, `--color-text`, `--color-primary`, `--color-danger`, `--color-border`). Componentes usam **só** estes.
3. **De componente** (opcional): `--button-bg`.

- **Espaçamento**: escala de 4 px (4, 8, 12, 16, 24, 32, 48, 64).
- **Tipografia**: escala modular (12, 14, 16, 20, 24, 32, 40), no máximo 2 famílias, line-height 1.4–1.6 para texto.
- **Raio, sombra, z-index, duração de animação**: escalas pequenas e nomeadas.
- **Tema escuro**: redefina os tokens semânticos (`[data-theme="dark"]` e `prefers-color-scheme`), nunca as cores dentro dos componentes.

## Componentes
- Primitivos acessíveis primeiro: Button, Input, Select, Checkbox, Dialog, Toast, Tooltip, Tabs, Card.
- Cada componente: variantes (`primary`, `secondary`, `ghost`, `danger`), tamanhos (`sm`, `md`, `lg`) e estados (hover, focus-visible, active, disabled, loading).
- API consistente entre componentes (mesmos nomes de prop para a mesma ideia).
- Para acessibilidade pronta, prefira bases headless: Radix/shadcn (React), Reka UI/Radix Vue (Vue).

## Documentação
- Storybook (ou Histoire para Vue) com cada variante e estado, e notas de uso (quando usar / quando não usar).

## Regras
- Nenhum valor mágico no componente (`#3b82f6`, `13px`): use token.
- Mudou token → mudou o sistema todo. Componente novo só se nenhum existente resolver.
