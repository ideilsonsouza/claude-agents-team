---
name: frontend-vue
description: "Padrões para frontend em Vue 3.5 (e Nuxt 4): script setup com TypeScript, reatividade, Pinia, Pinia Colada/TanStack Query, Vue Router, openapi-fetch, PrimeVue, ECharts, SSE, testes com Vitest e Nuxt. Usar ao criar ou alterar código Vue/Nuxt."
---

# Vue 3 (e Nuxt)

Versões verificadas em 15/10/2026:

| Pacote | Versão | Pacote | Versão |
|---|---|---|---|
| **vue** | **3.5.44** (3.6 em RC) | **nuxt** | **4.6.1** |
| vue-router | 5.4 | pinia | 4.1 |
| @pinia/colada | 1.4 | @tanstack/vue-query | 5.x |
| @vueuse/core | 15.0 | vite | 8.3 |
| @vitejs/plugin-vue | 6.0 | vue-tsc | 3.3 |
| eslint-plugin-vue | 10.11 | echarts / vue-echarts | 6.1 / 8.3 |

Padrões comuns (ferramental, supply chain, API, tempo real, a11y): `frontend-standards`.

## Componentes
- **Sempre `<script setup lang="ts">`** e Composition API. Nada de Options API em código novo.
- Recursos que viraram regra (3.4/3.5):
```vue
<script setup lang="ts">
const { size = 'md', items } = defineProps<{ size?: 'sm' | 'md'; items: Item[] }>()  // destructure reativo
const model = defineModel<string>({ required: true })                                // v-model
const emit = defineEmits<{ select: [id: string] }>()
const chartEl = useTemplateRef<HTMLDivElement>('chart')                              // no lugar de ref('chart')
const id = useId()                                                                   // id estável para label/aria
watch(() => size, () => {                                                            // prop desestruturada: use getter
  const ctrl = new AbortController()
  onWatcherCleanup(() => ctrl.abort())
})
</script>
```
- Componentes pequenos e com uma responsabilidade. A lógica reutilizável vai para **composables** `useXxx()`, que devolvem refs e fazem a própria limpeza.
- **Em feature não trivial, faça um mapa de componentes antes do código:** a responsabilidade de cada um numa frase, com props e emits. Use pastas por feature (`components/<feature>/`, `composables/use<Feature>.ts`).
- **Divida o componente quando qualquer uma destas for verdade** (critérios da `vuejs-ai/vue-best-practices`, MIT):
  - tem estado e orquestração **e** markup de várias seções;
  - tem 3 ou mais seções de UI independentes (filtros, lista, rodapé);
  - tem um bloco de template repetido.
  - Um CRUD vira, no mínimo: container, formulário, lista ou item e barra de filtros ou ações.
- **Views de rota e o `App.vue` são finos:** layout, providers e composição das features, sem a implementação delas.
- **Fluxo de dados:**
  - props descem e eventos sobem; props são só leitura;
  - `defineModel` só para contrato realmente bidirecional;
  - `provide/inject` com `InjectionKey<T>` tipada, só para contexto profundo (mais de ~3 níveis), e a mutação fica em ações expostas pelo provider;
  - `ref` de componente só para API imperativa.
- **`useAttrs()` não é reativo:** não use `watch` nele. Promova a prop o atributo que precisa ser observado.
- `v-for` sempre com `:key` estável, e **nunca `v-if` no mesmo elemento**.
- **Sem `v-html` com dado externo** (ver segurança em `frontend-standards`).

## Reatividade
- `ref` é o padrão. `reactive` só para objeto local de formulário. `computed` para tudo que é derivado (nunca `watch` + `ref` para derivar).
- **Dados grandes (séries de gráfico, listas enormes):**
  - `shallowRef`, trocando o valor inteiro (`data.value = novo`) ou chamando `triggerRef(data)`. Num `shallowRef`, `push` não dispara nada;
  - instância de terceiros (chart, map, socket, cliente) fica com `markRaw` ou fora do estado.
- **Performance vem depois do comportamento certo.** Para listas grandes:
  - virtualize;
  - **achate a hierarquia do item**: 100 linhas × 3 componentes aninhados dão 300 instâncias, então use elementos nativos onde o componente não acrescenta nada;
  - `v-memo` em linha que depende de poucas chaves;
  - `v-once` em conteúdo estático.
- **Vapor Mode** (Vue 3.6) está em RC: **não use em produção** até a 3.6 virar `latest`. Depois, só em tela isolada que precise de desempenho, sem misturar com VDOM aninhado.

## Estado e dados
- **Dados de servidor:**
  - **Pinia Colada** (1.x, leve, integra com os data loaders do Vue Router) em projeto novo;
  - **TanStack Vue Query 5** se o projeto já usa, ou se quiser hooks gerados pelo Orval.
  - Chaves por recurso e parâmetros (`['machines', plantId]`). Invalide depois de mutação e ao reconectar o stream.
- **Pinia 4** (só ESM; instale `@vue/devtools-api` v8 junto) **só para estado de UI e sessão.** Use setup stores e `storeToRefs` para desestruturar. **Não copie dado de servidor para a store.**
- **Cliente da API:**
```ts
import createClient from 'openapi-fetch'
import type { paths } from './api/schema'   // gerado por openapi-typescript no CI
export const api = createClient<paths>({ baseUrl: '/api', credentials: 'include' })
const { data, error } = await api.GET('/v1/machines/{id}', { params: { path: { id } } })
if (error) throw toUiError(error)            // Problem Details → mensagem por code
```

## Roteamento
- **Vue Router 5** já inclui o antigo `unplugin-vue-router`. Rotas por arquivo e tipadas com `import VueRouter from 'vue-router/vite'` (o plugin vem **antes** de `vue()` no `vite.config`). Quem usa a v4 sem rotas por arquivo atualiza sem mudar código.
- Rotas em lazy (`component: () => import(...)`), guard global `beforeEach` com `meta.requiresAuth`, filtros do dashboard na **query da URL** (compartilhável). Os data loaders ainda estão em `vue-router/experimental`: evite.

## UI e licenças
- **Nuxt UI 4** (MIT, gratuito, Tailwind 4, funciona também em Vue + Vite) ou **shadcn-vue + Reka UI** (componentes copiados para o projeto) são o padrão.
- **Vuetify 4** (MIT, Material 3) se o projeto já usa.
- **PrimeVue 5 tem licença comercial**, que exige chave. A Community é gratuita só para equipes muito pequenas e com faturamento baixo. **Não adote sem decisão de licença registrada.** A 4.5.x continua MIT.
- **Gráficos:** `vue-echarts` 8 + ECharts 6.
  - Importe só os módulos usados (`use([...])`).
  - A `option` vai em `shallowRef`, e a atualização é incremental (`setOption({ series: [{ data }] }, { lazyUpdate: true })` ou `appendData`).
  - No tempo real: `sampling: 'lttb'`, `large: true` e `animation: false`.
  - uPlot para séries densas.
  - O padrão de buffer + rAF está em `frontend-standards`.

## Tempo real (VueUse 15)
```ts
const { data, status } = useEventSource('/api/v1/stream', ['telemetry'], { autoReconnect: { retries: -1, delay: 2000 } })
const visible = useDocumentVisibility()      // pause/feche com a aba oculta
// data → buffer não reativo → flush por rAF (frontend-standards §6)
```
- VueUse 15:
  - `templateRef` foi removido (use `useTemplateRef`);
  - `useThrottleFn` agora usa `trailing: true` por padrão;
  - o `useWebSocket` ignora mensagens de um socket antigo.

## Testes
- Componentes com **Vitest 5 + `@vue/test-utils` 2.5** em `happy-dom`. Gráfico, canvas e interação real no **browser mode** (`@vitest/browser-playwright`). O `@testing-library/vue` está parado desde 2024: prefira test-utils ou os locators do Vitest.
- Mock de API com **MSW 3** (o mesmo handler serve no teste e no dev). E2E com **Playwright** e axe.
- Teste os composables isoladamente (são funções).

## Tooling
- **TypeScript ~6.0.3** + `vue-tsc --noEmit`. **O `vue-tsc` não funciona com o TS 7** até a API do 7.1.
- **ESLint 10** (flat) + `eslint-plugin-vue` 10 + `typescript-eslint`. No Nuxt, use `@nuxt/eslint`.
- O `oxlint` **não analisa o `<template>`**: use-o só como primeira passada (`eslint-plugin-oxlint`), mantendo o ESLint.
- Prettier 3 para formatar.

## Nuxt 4 (quando o projeto for Nuxt)
- **Use Nuxt** com páginas públicas com SEO, BFF/SSR ou equipe já habituada. Dashboard autenticado puro é **SPA Vite** (`frontend-standards`). No Nuxt, uma área logada pode ser `ssr: false` via `routeRules`.
- **Projeto novo:** Nuxt 4.6 com `future: { compatibilityVersion: 5 }` (o Nuxt 5 ainda não saiu; o Nuxt 3 chegou ao EOL em 07/2026).
- **Estrutura:** o código fica em `app/`, com um tsconfig por contexto (app, server, shared).
- **Dados:**
  - `useFetch`/`useAsyncData` com **chave explícita**. O dado é compartilhado entre componentes com a mesma chave e é shallow por padrão;
  - `dedupe: 'cancel'`;
  - `getCachedData(key, nuxtApp, ctx)` para reaproveitar o payload;
  - o handler recebe `{ signal }`: repasse ao fetch.
- **Segredos** em `runtimeConfig` (só no servidor). Tudo em `runtimeConfig.public` é **público**.
- **Sessão:** `useSession()` (4.6) com `NUXT_APP_SECRET` igual em todas as réplicas.
- **Deploy:** `nuxt build` gera `.output/server/index.mjs` em Node. Com várias réplicas, cache e sessão ficam compartilhados (Redis) e o build é feito uma vez só, com config em runtime por env (`NUXT_*`).

## Checklist (Vue)
- [ ] `<script setup lang="ts">`; prop desestruturada usada com getter no `watch`.
- [ ] Componentes divididos pelos critérios. Views de rota finas. `provide/inject` tipado.
- [ ] Dado grande em `shallowRef`/`markRaw`; render por rAF ou throttle; limpeza no unmount.
- [ ] Dado de servidor na Colada ou Query, não na Pinia.
- [ ] `error` do openapi-fetch sempre tratado.
- [ ] `typescript@~6.0`, `vue-tsc` e ESLint verdes.
- [ ] Licença da biblioteca de UI conferida.
- [ ] `:key` estável, sem `v-if` junto com `v-for`, sem `v-html` com dado externo.
