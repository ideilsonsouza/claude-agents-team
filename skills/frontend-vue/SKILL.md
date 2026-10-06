---
name: frontend-vue
description: Padrões para frontend em Vue 3 (e Nuxt) — Composition API, script setup, composables, Pinia, Vue Router e testes.
---

# Frontend em Vue 3

## Idiomas
- **Composition API com `<script setup lang="ts">`**. Sem Options API em código novo (a menos que o projeto use).
- `defineProps`/`defineEmits` tipados; `defineModel` para v-model em componentes.
- `ref` para primitivos, `reactive` com parcimônia; `computed` para derivados (nunca duplique estado). `watch` só para efeitos colaterais.
- Lógica reutilizável em **composables** (`useAlgo()` em `src/composables`).
- Estado global com **Pinia** (setup stores). Dados de servidor com TanStack Vue Query.
- Vue Router com lazy loading (`component: () => import(...)`) e guards para auth.
- `v-for` sempre com `:key` estável; nunca `v-if` junto com `v-for` no mesmo elemento.

## Nuxt (se for o caso)
- `useFetch`/`useAsyncData` para dados SSR, `server/api` para rotas, auto-imports do framework, `runtimeConfig` para variáveis.

## Estrutura
`src/components` (UI), `src/views` ou `pages`, `src/composables`, `src/stores`, `src/services` (cliente de API).

## Testes
- Vitest + `@vue/test-utils` / Testing Library Vue. Lint com `eslint-plugin-vue`. Typecheck com `vue-tsc`.
