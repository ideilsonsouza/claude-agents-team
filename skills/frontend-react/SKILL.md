---
name: frontend-react
description: Padrões para frontend em React (e Next.js) — componentes funcionais, hooks, estado, dados, Server Components e testes.
---

# Frontend em React

## Idiomas
- Componentes funcionais com TypeScript. Sem classes em código novo.
- **Hooks**: respeite as regras (eslint `react-hooks`). Lógica reutilizável em hooks customizados (`useAlgo`).
- Não use `useEffect` para derivar estado ou buscar dados que um cache resolve. Derivado → calcule no render (ou `useMemo` se for caro).
- Dados de servidor com **TanStack Query** (ou o mecanismo do framework). Estado global leve com Zustand ou Context (só para coisas que mudam pouco).
- Formulários com React Hook Form + Zod.
- `key` estável em listas; nunca índice se a lista muda.
- Memoização (`memo`, `useCallback`) só com problema medido.

## Next.js (se for o caso)
- App Router: **Server Components por padrão**; `"use client"` só onde há interatividade. Busque dados no servidor.
- Server Actions para mutações; `next/image`, `next/font`; variáveis públicas só com `NEXT_PUBLIC_`.

## Estrutura
Por feature: `src/features/<feature>/{components,hooks,api}`; compartilhados em `src/components/ui`.

## Testes
- Vitest + React Testing Library + `user-event`. E2E com Playwright.
