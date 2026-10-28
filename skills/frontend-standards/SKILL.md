---
name: frontend-standards
description: Padrões gerais de frontend da equipe, válidos para Vue, React e Astro — escolha de arquitetura (SPA Vite x Nuxt/Next x Astro), ferramental base (TypeScript 6.0 até a API do TS 7.1, Vite 8, ESLint 10 flat, Vitest 5, Playwright, MSW 3, pnpm com proteção de supply chain), cliente tipado do OpenAPI, estados de UI, tempo real (SSE, buffer + rAF, gráficos), datas no fuso da planta, performance (Core Web Vitals, bundle, cache, compressão sem quebrar SSE), acessibilidade WCAG 2.2 AA com axe, segurança (XSS, CSP, cookies, segredos no bundle), telemetria de erros (GlitchTip/Sentry, OTel web) e checklist de PR.
---

# Padrões de frontend

> As convenções que o projeto já tem têm prioridade. Estas regras valem quando o projeto não define.
> Carregue também a skill do framework: `frontend-vue`, `frontend-react` ou `frontend-astro`. Para visual, use `design-system` e `ui-ux` (e a `frontend-design` em telas de marketing ou de leitura). Para auditar a UI de um PR, use `ui-review`.

Versões verificadas em 15/10/2026 (npm, blogs oficiais). Contexto: dashboards (inclusive de dados industriais em tempo real) e SaaS B2B, consumindo API Fastify com OpenAPI e publicados em Docker Swarm atrás do Traefik (self-hosted).

## 1. Que arquitetura usar
| Caso | Padrão |
|---|---|
| **Dashboard ou app autenticado** (sem SEO, tempo real) | **SPA com Vite 8** (Vue Router ou TanStack Router), servida como estático (Caddy ou Nginx) atrás do Traefik, consumindo o Fastify |
| Site, marketing, docs, blog, landing | **Astro 7** |
| SEO **e** app no mesmo projeto, BFF ou SSR necessário | Nuxt 4 / Next 16, **com ADR** (é mais um servidor Node para operar e manter atualizado; o Next teve uma série de CVEs críticos em 2025–2026) |

**SPA estática:**
- fallback para `index.html`;
- `Cache-Control: public, max-age=31536000, immutable` em `/assets/*` (nome com hash);
- `no-cache` no `index.html`.

## 2. Ferramental base
| Ferramenta | Versão | Regra |
|---|---|---|
| **TypeScript** | **6.0.x** (`~6.0.3`) | O TS 7 (compilador nativo) ainda não tem API programática: `vue-tsc`, `typescript-eslint` e o language tools não funcionam com ele até o **TS 7.1**. O `tsgo` pode rodar em paralelo, só como checagem rápida |
| Vite | 8.x | Rolldown + Oxc. Opções em `build.rolldownOptions` |
| ESLint | 10.x | Só flat config (eslintrc foi removido). O ESLint 9 chegou ao EOL em 08/2026. `oxlint` pode rodar antes, como primeira passada rápida |
| Prettier | 3.x | Padrão. Biome 2 ou oxfmt só se o projeto já usa |
| Vitest | 5.x | Node 22+. `clearMocks` vem ligado; asserção async sem `await` reprova |
| Playwright | 1.64+ | E2E e browser mode do Vitest |
| MSW | 3.x | Só ESM; `worker.stop()` agora é async |
| pnpm | 11/12 | Ver supply chain |

- `tsconfig` preparado para o TS 7:
  - `moduleResolution: "bundler"`;
  - **sem `baseUrl`** (`paths` relativo à raiz);
  - `strict: true`;
  - `types` explícito (`["vite/client"]`);
  - sem `target: es5`.
- **No CI:** `typecheck`, `lint`, `test`, `build` e `e2e` (smoke). Typecheck sempre como etapa separada.

## 3. Supply chain (npm)
Houve ataques reais em 2025–2026 (chalk/debug, worm Shai-Hulud e variantes, ChainDrop). O mínimo:
- **Lockfile commitado** e `pnpm install --frozen-lockfile` no CI.
- **`minimumReleaseAge`** ≥ 1440 min (1 dia). É o padrão do pnpm 11+: não instale versão publicada há poucas horas.
- **Scripts de install bloqueados por padrão.** No pnpm 11+, libere por pacote com `allowBuilds` (substitui `onlyBuiltDependencies`, que foi removido). No npm, `ignore-scripts=true`.
- Renovate ou Dependabot **com cooldown**. Dependência nova precisa de justificativa (tamanho, manutenção, licença).
- **Nada de segredo no bundle.** Tudo em `VITE_*`, `NEXT_PUBLIC_*` e `runtimeConfig.public` é **público**.

## 4. API e dados
- **Cliente tipado gerado do OpenAPI do backend** (ver `backend-standards`):
  - **padrão:** `openapi-typescript` 7 + `openapi-fetch` (só tipos, cerca de 6 kB);
  - **Orval** 8 quando quiser hooks (TanStack Query) e mocks MSW gerados;
  - `@hey-api/openapi-ts` ainda é 0.x: só com versão exata.
- **Os tipos são gerados no CI.** Se o gerado divergir do commitado, o PR reprova.
- O `openapi-fetch` **não lança** em 4xx/5xx: confira `error` sempre. Os erros chegam em **Problem Details** (`application/problem+json`): a UI decide pelo `code`, mostra o erro por campo via `errors[].pointer` e exibe o `traceId` no erro inesperado.
- **Dado de servidor fica em cache de query** (TanStack Query, Pinia Colada), nunca copiado para a store global. A store guarda só o estado de UI e de sessão.
- Autenticação por **cookie de sessão `HttpOnly`** emitido pelo backend (`credentials: 'include'`). **Nunca** token em `localStorage`.

## 5. Estados de UI
Todo componente que mostra dados trata **os quatro estados**:
- **carregando:** skeleton com o **mesmo layout** do conteúdo, para não gerar CLS;
- **vazio:** mensagem e ação;
- **erro:** mensagem, botão de tentar de novo e `traceId`;
- **desatualizado ou desconectado:** selo "ao vivo" ou "offline", com o horário do último dado.

Use um Error Boundary (`onErrorCaptured` no Vue) por região do dashboard: um widget quebrado não derruba a tela.

## 6. Tempo real e gráficos
- **SSE** para fluxo servidor → cliente (telemetria, alarmes). Ele reconecta sozinho, tem `Last-Event-ID` e passa pelo Traefik.
  - O backend envia heartbeat a cada 15 a 30 s.
  - **Sem compressão no stream:** exclua `text/event-stream` do middleware `compress` do Traefik.
- **WebSocket** só quando o cliente também envia com frequência (comandos).
- **Reconexão:**
  - backoff exponencial com jitter (1 s → 30 s);
  - pausa com a aba oculta (`document.hidden`);
  - ao reconectar, **invalide as queries** para recuperar o que se perdeu.
- **Nunca atualize estado reativo por mensagem.** O padrão:
```ts
const buf: Point[] = []
source.onmessage = (e) => buf.push(JSON.parse(e.data))           // sem render
let raf = 0
const tick = () => { if (buf.length) chart.appendPoints(buf.splice(0)); raf = requestAnimationFrame(tick) }
raf = requestAnimationFrame(tick)                                 // no máximo 1 render por frame
```
- **Gráficos:**
  - **ECharts 6** é o padrão: canvas, `appendData`, `large`, `sampling: 'lttb'`, animação desligada no tempo real;
  - **uPlot** para séries densas (centenas de milhares de pontos);
  - bibliotecas SVG (Recharts, visx, Chart.js) só para gráficos de negócio;
  - a instância do gráfico fica **fora do estado reativo**, com janela deslizante de tamanho fixo;
  - tabela grande precisa de virtualização.
- Limpe assinaturas, sockets e gráficos ao desmontar o componente.

## 7. Datas, números e fuso
- A API manda **UTC em ISO 8601**. O front exibe no **fuso da planta ou do tenant, que vem da API**, não no fuso do navegador:
```ts
new Intl.DateTimeFormat('pt-BR', { timeZone: plant.tz, dateStyle: 'short', timeStyle: 'medium' }).format(new Date(ts))
```
- Números e unidades com `Intl.NumberFormat`. Eixos de gráfico no mesmo fuso da tabela. Cuidado com a mudança de horário de verão em outros países.
- Textos de interface em pt-BR por padrão, preparados para i18n (sem concatenar frases).

## 8. Performance
- **Core Web Vitals (p75):** LCP ≤ 2,5 s, **INP ≤ 200 ms** e CLS ≤ 0,1. Meça em campo com `web-vitals` 6 e envie para a telemetria.
- **Orçamento de bundle (meta da equipe):** ≤ 200 kB gzip de JS inicial por rota. Code splitting por rota, e lazy em editor, gráfico e biblioteca pesada. Confira com o analyzer no PR.
- **Imagens:** `width` e `height` sempre, AVIF ou WebP, `loading="lazy"` abaixo da dobra e `fetchpriority="high"` no LCP.
- **Fontes:** woff2 hospedado no próprio app, `font-display: swap` e preload só da principal.
- **Requisições em cascata (waterfalls) são o problema nº 1:** chamadas independentes saem em paralelo (`Promise.all`, várias queries ao mesmo tempo). O `await` fica no ramo que usa o dado. Faça o prefetch no loader da rota, e não no `onMounted`/`useEffect` do filho.
- **Imports:** evite barrel files grandes (`export *` em `index.ts` próprio). Bibliotecas de ícones e de componentes devem ser importadas por caminho, ou com `optimizePackageImports` no Next. Faça lazy por condição (o módulo só carrega quando o recurso é ativado) e preload por intenção (no `hover`/`focus` do botão que abre o editor pesado). Analytics e telemetria carregam depois da interação inicial.
- **Traefik:** middleware `compress` para HTML, JS e CSS (exceto SSE).

## 9. Acessibilidade (WCAG 2.2 AA)
- Meta **WCAG 2.2 AA** (a WCAG 3 ainda é rascunho). Critérios novos da 2.2 que pegam em dashboards:
  - foco não pode ficar escondido sob header ou toast fixo;
  - **alternativa a arrastar** (drag & drop, sliders);
  - **alvos de no mínimo 24×24 px**;
  - autenticação sem teste cognitivo, permitindo colar senha.
- **Teclado em tudo**, foco visível, `label` em todo campo, erro de formulário associado ao campo (`aria-describedby`) e contraste AA.
- **Gráficos:** a cor nunca é o único canal. Dê alternativa em tabela ou resumo textual. Alarmes em `aria-live="polite"` com throttle.
- **Automação:** `@axe-core/playwright` nos E2E, com tags `wcag2a`, `wcag2aa` e `wcag22aa`, sem violações. O axe pega 30 a 40% dos problemas: complete com teste de teclado.
- A base visual está na skill `ui-ux`.

## 10. Segurança
- **XSS:** nada de `v-html`, `dangerouslySetInnerHTML` ou `set:html` com dado externo. Se for inevitável, passe por `DOMPurify.sanitize`. URLs vindas de dado só com `https:` (bloqueie `javascript:`).
- **CSP:**
  - SPA: CSP estática por header no servidor estático, com `script-src 'self'` e sem `unsafe-inline`;
  - SSR: nonce por requisição;
  - `frame-ancestors 'none'`.
- **Cookies e CSRF:** sessão `HttpOnly; Secure; SameSite=Lax`. O backend confere `Origin` e usa token CSRF entre subdomínios.
- **Autorização é sempre do backend.** Esconder botão é UX, não segurança.
- Source maps vão **para a ferramenta de erros, não para o público**.

## 11. Telemetria do front
- Erros com o **SDK do Sentry**, enviando para **GlitchTip** (self-hosted e leve: Postgres + Redis/Valkey). O Sentry self-hosted pede 16 a 32 GB de RAM.
- Upload de source maps no CI, sem publicá-los.
- Scrub de PII (LGPD): sem e-mail ou CPF em breadcrumbs.
- Traces do front ao backend com OpenTelemetry web (`traceparent` nas chamadas à API). Opcional, ver `observability`.
- Feature flags: OpenFeature com provider self-hosted, quando houver.

## 12. Checklist de PR de frontend
- [ ] Typecheck, lint e testes verdes. Código gerado do OpenAPI sem diff.
- [ ] `ui-review` rodada nos arquivos de UI alterados, sem achados do tipo **bloqueia**.
- [ ] Visual coerente com o modo da tela (`ui-ux` §1) e com o design system. Captura de tela no PR quando o visual muda.
- [ ] Quatro estados de UI tratados. Skeleton sem CLS.
- [ ] Dado de servidor em cache de query, e não duplicado em store.
- [ ] Stream com buffer e rAF, sem render por mensagem. Assinaturas limpas ao desmontar.
- [ ] Acessibilidade: teclado, foco visível, labels, alvos ≥ 24 px, axe sem violações, gráfico com alternativa.
- [ ] Segurança: sem HTML cru externo, sem segredo em variável pública, autorização garantida pelo backend.
- [ ] Datas em UTC exibidas no fuso da planta. Números com `Intl`.
- [ ] Bundle dentro do orçamento. Lazy no que é pesado.
- [ ] Dependência nova justificada, com idade ≥ 1 dia e sem script de install não autorizado. Licença conferida.
