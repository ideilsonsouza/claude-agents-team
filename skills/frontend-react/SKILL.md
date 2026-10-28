---
name: frontend-react
description: Padrões para frontend em React 19.3 (e Next.js 16) — componentes e hooks, React Compiler 1.0 (sem memo manual), Actions/useActionState/useOptimistic, quando usar Server Components, SPA com Vite 8 + TanStack Router/React Router 8 como padrão para dashboard, TanStack Query 5 e Zustand, formulários com React Hook Form + Zod 4, cliente openapi-fetch, shadcn/ui (Base UI) e Tailwind 4, gráficos em tempo real fora do ciclo de render (useSyncExternalStore), testes com Vitest 5/Testing Library/Playwright/MSW 3, e Next 16 self-hosted em Docker (standalone, várias réplicas, cache compartilhado) com a lista de CVEs e versões mínimas.
---

# React (e Next.js)

Versões verificadas em 15/10/2026:

| Pacote | Versão | Pacote | Versão |
|---|---|---|---|
| **react** | **19.3.1** | **next** | **16.4.1** |
| @vitejs/plugin-react | 6.1 | vite | 8.3 |
| @tanstack/react-router | 1.170 | react-router | 8.4 |
| @tanstack/react-query | 5.104 | zustand | 5.0 |
| react-hook-form | 7.90 | zod | 4.6 |
| shadcn (CLI) | 4.x | tailwindcss | 4.3 |
| babel-plugin-react-compiler | 1.0 | eslint-plugin-react-hooks | 7.1 |

Padrões comuns: `frontend-standards`.

## Segurança: versões mínimas (obrigatório)
- **`react` / `react-dom` / `react-server-dom-*` ≥ 19.3.1**, ou o patch mais recente da linha: 19.2.9, 19.1.10 ou 19.0.9.
- **`next` ≥ 16.4.1** (ou 15.5.28). O Next teve **RCEs e bypasses de autorização** em sequência em 2025–2026:
  - "React2Shell" (CVE-2025-55182) no protocolo RSC;
  - bypass de middleware (CVE-2025-29927 e a série de 05/2026);
  - SSRF e RCE no Image Optimization;
  - cache poisoning em ISR self-hosted;
  - RCE no `use cache` (14/10/2026).
- **Regras que decorrem disso:**
  - **atualize o Next no mesmo dia** dos advisories (`gh api repos/vercel/next.js/security-advisories`);
  - **autorização nunca só no `proxy.ts`/middleware**: confira na camada de dados e na API Fastify;
  - se não usar o otimizador de imagens, desligue (`images.unoptimized: true`); se usar, restrinja `remotePatterns`.

## Que arquitetura usar
- **Dashboard ou app autenticado:** **SPA com Vite 8 + TanStack Router** (search params e loaders tipados, bom para dashboard com muitos filtros na URL) ou **React Router 8** (só ESM, Node 22+). É servida como estático e consome o Fastify. Assim não há servidor Node para manter atualizado.
- **Next 16** só com páginas públicas com SEO junto do app, ou com SSR ou streaming realmente necessário. A escolha vai num ADR.
- **Server Components** valem num app Next com páginas de leitura pesadas e pouca interação. Num dashboard em tempo real quase tudo é cliente, e o RSC só acrescenta superfície de ataque.

## Componentes e hooks
- Componentes funcionais, pequenos, com props tipadas. **Sem `useEffect` para derivar estado** (calcule durante o render) **nem para buscar dados** (use TanStack Query).
- **React Compiler 1.0 é o padrão em projeto novo:**
  - em código novo **não escreva `useMemo`/`useCallback`/`memo` "por precaução"**. Use o hook manual só como saída de emergência (por exemplo, valor que é dependência de Effect);
  - em código existente, **não remova memoização em massa**: isso muda a saída do compilador;
  - instale com **versão exata** (`--save-exact`), porque atualizar o compilador pode mudar quando os Effects disparam;
  - Vite 8 + plugin-react 6: `react()` + `@rolldown/plugin-babel` com `reactCompilerPreset()`. No Next: `reactCompiler: true`.
- Lint com `eslint-plugin-react-hooks` 7 (`configs.flat.recommended`), que já traz as regras do compilador. Remova o `eslint-plugin-react-compiler`.
- **React 19.x:**
  - `use()`, `useActionState`, `useFormStatus` e `useOptimistic`;
  - `<Activity mode="hidden">` mantém o estado de abas ocultas;
  - `useEffectEvent` para handler usado dentro de Effect;
  - `<ViewTransition>` e Fragment refs estáveis na 19.3.
  - Não misture `useOptimistic` com o optimistic update do TanStack Query na mesma mutação.

## Composição de componentes
Adaptado de `vercel-composition-patterns` (vercel-labs/agent-skills, MIT):
- **Sem proliferação de props booleanas** (`isEditing`, `showHeader`, `compact`…). Cada booleano dobra os estados possíveis. Prefira **variantes explícitas** (`<Composer.Edit>` / `<Composer.Thread>`, ou `variant="edit"`) e **compound components** (`<Card><Card.Header/><Card.Body/></Card>`) que compartilham estado por context.
- **`children` em vez de render props**, a não ser que o pai precise de dados do filho para renderizar.
- **Context com interface genérica** (`state`, `actions`, `meta`): o provider esconde a implementação (useState, Zustand, servidor), e a UI consome só a interface. Suba o estado para o provider quando irmãos precisarem dele.
- **React 19:** `ref` é prop comum (sem `forwardRef`) e `use(Context)` no lugar de `useContext`.

## Dados sem cascata
Adaptado de `vercel-react-best-practices` (MIT). Regras que valem para a nossa stack:
- **Chamadas independentes em paralelo:** `Promise.all`, ou várias `useQuery`/`useSuspenseQueries` no mesmo nível. Nunca componente pai buscando e filho só buscando depois do pai renderizar.
- **Dependência parcial:** crie as promises primeiro e junte no fim (`const u = getUser(); const p = u.then(x => getProfile(x.id))`).
- **Prefetch no loader da rota** (TanStack Router `loader` + `ensureQueryData`, ou o loader do React Router), e não no `useEffect` do componente.
- **Suspense por região:** o layout aparece logo e só o widget espera. Não use um `await` que bloqueia a página inteira.
- **Bundle:**
  - nada de barrel próprio grande;
  - `lucide-react` e afins importados direto ou com `optimizePackageImports` (Next);
  - `lazy()` + `Suspense` para editor, gráfico e mapa;
  - `void import('./Editor')` no `onMouseEnter`/`onFocus` do botão que abre;
  - analytics só depois da interação inicial.
- **Ignore desse pacote:** as regras de `memo`/`useMemo` manual (usamos o React Compiler) e as de SWR (usamos TanStack Query).

## Estado e dados
- **Dados de servidor: TanStack Query 5**, com `queryOptions()` como fábrica por recurso. Em tempo real, use `setQueryData` a partir do stream ou `invalidateQueries` com throttle.
- **Estado de cliente compartilhado: Zustand 5**, com seletores e `useShallow`. Jotai 3 só se o projeto já usa. Não use os dois juntos.
- **Formulários:** **React Hook Form 7** + `@hookform/resolvers` + **Zod 4**. Os erros do backend (Problem Details, `errors[].pointer`) são mapeados com `setError` campo a campo.
- **Cliente da API:** `openapi-typescript` + `openapi-fetch` (padrão da equipe), com `openapi-react-query` ou `queryOptions` próprios. **Orval** 8 quando quiser hooks e mocks gerados.

## UI
- **shadcn/ui:** desde 07/2026 o `init` usa **Base UI** por padrão. Projeto novo fica em Base UI; projeto existente continua em Radix (há suporte total). Em CI, fixe a base (`-b`) para o `init` não trocá-la por conta própria.
- **Tailwind 4:**
  - config no CSS (`@import "tailwindcss"; @theme { ... }`), sem `tailwind.config.js`;
  - plugin `@tailwindcss/vite`;
  - `@utility` e `@custom-variant`;
  - escalas renomeadas (`shadow-sm` virou `shadow-xs`, `rounded` virou `rounded-sm`);
  - borda padrão em `currentColor`.
- **Gráficos em tempo real:** ECharts 6 (ou uPlot para séries densas), **imperativo via ref e fora do ciclo de render**. Recharts e visx (SVG) só para gráficos de negócio. Tabelas grandes com TanStack Virtual.
- **Store externa de streaming** com `useSyncExternalStore`:
```ts
const value = useSyncExternalStore(store.subscribe, () => store.getSnapshot(tagId))
// getSnapshot devolve referência ESTÁVEL (objeto novo a cada chamada = loop infinito);
// a store notifica no máximo 1x por frame (buffer + rAF, ver frontend-standards)
```
- **`setState` por mensagem do stream gera centenas de renders por segundo e estoura o INP.**

## Testes
- **Vitest 5** + **Testing Library** (`@testing-library/react` 16 + user-event) para componentes. Interação real e gráficos no **browser mode**.
- **MSW 3** para a API. **Playwright** para E2E, com `@axe-core/playwright`.
- Teste o comportamento (o que o usuário vê e faz), não detalhes de implementação.

## Tooling
- **TypeScript ~6.0** (o `typescript-eslint` não suporta o 7). O `tsgo` (TS 7) é opcional, só para typecheck rápido, via alias `"@typescript/native": "npm:typescript@^7"`.
- ESLint 10 flat + `typescript-eslint` + `react-hooks`. Prettier 3. O Biome 2 é aceitável se o projeto já usa, mantendo o ESLint para `react-hooks`.

## Next.js 16 self-hosted (quando for Next)
- **Mudanças em relação à 15:**
  - Turbopack é o padrão;
  - **`middleware.ts` virou `proxy.ts`** (função `proxy`, runtime Node);
  - `params`, `searchParams`, `cookies()` e `headers()` são **async**;
  - `next lint` foi removido (rode o ESLint direto);
  - `revalidateTag(tag, perfil)`, `updateTag()` e `refresh()`;
  - `cacheComponents` (antigo `dynamicIO`), recomendado na 16.4 e padrão no Next 17.
- **Docker e Swarm com várias réplicas:**
  1. `output: 'standalone'`. Rode `node server.js` como usuário não root.
  2. **Faça o build uma vez** e promova a mesma imagem entre ambientes. O `NEXT_PUBLIC_*` é **inlined no build**: configuração que muda por ambiente é lida no servidor em runtime (ou num endpoint `/config`).
  3. `deploymentId` com a versão (evita version skew no rolling update) e **`NEXT_SERVER_ACTIONS_ENCRYPTION_KEY` fixa** (sem ela aparece "Failed to find Server Action" entre réplicas).
  4. **Cache compartilhado** (Redis): `cacheHandler` com `cacheMaxMemorySize: 0` para ISR, e `cacheHandlers` para `'use cache'`, implementando `refreshTags()`. Sem isso cada réplica tem um cache diferente.
  5. Shutdown com SIGTERM e `stop_grace_period` de 30 s. O streaming passa pelo Traefik sem middleware de buffer.
- **CSP com nonce** gerada no `proxy.ts` (as páginas viram dinâmicas). Use a versão corrigida da CVE-2026-44581.

## Checklist (React)
- [ ] `react` ≥ 19.3.1 e `next` ≥ 16.4.1 (se houver Next) no lockfile.
- [ ] Sem `useEffect` para derivar ou buscar dado. Sem memo manual sem motivo.
- [ ] Sem cascata de requisições: o que é independente sai em paralelo, com prefetch no loader da rota.
- [ ] Componentes compostos (compound/variantes) em vez de pilha de props booleanas.
- [ ] Dado de servidor no TanStack Query. Store só para estado de cliente.
- [ ] Stream fora do render (store externa + rAF), com referência estável no snapshot.
- [ ] Erros de formulário mapeados do Problem Details.
- [ ] Autorização conferida no backend, não só no proxy.
- [ ] Next: chave de Server Actions, `deploymentId` e cache handler compartilhado com mais de 1 réplica.
