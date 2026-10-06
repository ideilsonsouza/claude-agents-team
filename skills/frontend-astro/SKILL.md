---
name: frontend-astro
description: Padrões para Astro — arquitetura de ilhas, componentes .astro, content collections, integrações com Vue/React, SSG/SSR e desempenho.
---

# Frontend em Astro

## Idiomas
- **Zero JS por padrão**: componentes `.astro` renderizam no servidor/build. Só adicione interatividade onde precisa.
- **Ilhas**: componentes Vue/React com diretiva de hidratação explícita — prefira `client:visible` ou `client:idle`; `client:load` só para o que é crítico acima da dobra. Sem diretiva = HTML estático.
- **Content Collections** com schema Zod (`src/content.config.ts`) para conteúdo em Markdown/MDX; tipagem gerada.
- Roteamento por arquivos em `src/pages`; layouts em `src/layouts`.
- Estado compartilhado entre ilhas com **nanostores** (funciona em Vue e React).
- Imagens com `astro:assets` (`<Image />`) para otimização automática.
- Saída: estática (SSG) por padrão; SSR/híbrido com adapter só quando há conteúdo dinâmico real.
- Variáveis de ambiente com `astro:env` (schema) — cliente vs servidor explícitos.

## Estrutura
`src/pages`, `src/layouts`, `src/components` (`.astro` e ilhas), `src/content`, `public/`.

## Verificação
- `astro check` (tipos) + build + Lighthouse nas páginas principais (meta: 95+ em performance).
