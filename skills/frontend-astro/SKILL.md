---
name: frontend-astro
description: Padrões para Astro 7 — quando usar (site, marketing, docs, blog x app), arquitetura de ilhas e diretivas client:* e server:defer, componentes .astro, content collections com Content Layer, integrações Vue/React, estático por padrão com SSR por rota, adapter Node standalone em Docker com várias réplicas (sessão em Redis), astro:env, imagens, i18n, CSP, e breaking changes das versões 6 e 7 (compilador em Rust, Markdown, compressHTML).
---

# Astro

Versão: **astro 7.4** (7.0 de 22/06/2026; 6.0 de 10/03/2026), `@astrojs/node` 11, `@astrojs/vue` 7. Verificado em 15/10/2026. Requer Node 22.12+ e usa Vite 8. Padrões comuns: `frontend-standards`.

## Quando usar
- **Astro** para site institucional, marketing, docs, blog e landing de SaaS: conteúdo primeiro, zero JS por padrão.
- **Não use** para dashboard ou app autenticado com roteamento rico e tempo real: isso é SPA Vite + Vue ou React (`frontend-standards`). Uma área logada pequena pode ser uma ilha `client:only`.

## Ilhas
- **Sem diretiva, o componente vira HTML estático** (zero JS). A interatividade é opt-in, por ilha:

| Diretiva | Quando |
|---|---|
| `client:visible` / `client:idle` | **padrão** para widgets |
| `client:load` | só o que está acima da dobra e precisa responder já |
| `client:only="vue"` | widget que depende do browser (gráfico, mapa) |
| `server:defer` | **Server Island**: trecho personalizado (usuário, preço) dentro de uma página estática |

- **Props de ilha precisam ser serializáveis.** Duas ilhas Vue **não dividem** a mesma app nem a mesma Pinia: o estado entre ilhas vai em **nanostores**.
- `.astro` para layout e conteúdo. Componentes Vue ou React só onde houver interação.

## Conteúdo
- **Content Layer:** coleções em `src/content.config.ts`, com loaders (`glob`, `file` ou próprio) e schema **Zod 4** (import de `astro/zod`). As **coleções legadas foram removidas** na 6. Live collections servem para dados buscados em runtime.
- `import.meta.glob()` em vez de `Astro.glob()` (removido). Imagens com `<Image />`/`<Picture />` do `astro:assets`: a imagem Docker precisa de `sharp`, e o serviço de imagem corta por padrão e nunca amplia.
- **Markdown (7):** processador novo (Sätteri). Para plugins remark/rehype, use `markdown.processor: unified()` com `@astrojs/markdown-remark`.

## Renderização e deploy
- **Estático por padrão.** SSR por rota com `export const prerender = false`. O modo `hybrid` não existe mais.
- **Adapter Node para Docker:**
```js
// astro.config.mjs
import node from '@astrojs/node'
export default defineConfig({
  adapter: node({ mode: 'standalone', staticHeaders: true }),   // staticHeaders: CSP como header
  security: { csp: true },
  session: { driver: 'redis' },                                // padrão é filesystem: quebra com >1 réplica
})
```
  - Rode com `node dist/server/entry.mjs`, `HOST=0.0.0.0` e `PORT` em runtime.
  - Site 100% estático dispensa o adapter: os arquivos de `dist/` vão para o Caddy ou Nginx.
- **Variáveis:** `astro:env` com schema e `access: 'secret'` para o que é só do servidor. `import.meta.env` é **sempre inlined no build**.
- **i18n:** `i18n.locales` com `prefixDefaultLocale`. Na 6, `redirectToDefaultLocale` passou a `false` por padrão.

## O que muda ao atualizar
- **6:**
  - Node 22.12+ e Zod 4;
  - coleções legadas removidas;
  - `<ViewTransitions />` virou `<ClientRouter />`;
  - `Astro.glob()` removido;
  - CSP, Fonts e live collections estáveis;
  - sessões configuradas em `sessionDrivers`.
- **7:**
  - **compilador em Rust e mais estrito**: tag sem fechamento e HTML aninhado de forma inválida passam a dar **erro**;
  - Vite 8;
  - `compressHTML: 'jsx'` pode remover espaço entre elementos inline (revise o texto);
  - `src/fetch.ts` virou arquivo reservado;
  - `cache`/`routeRules` estáveis;
  - `@astrojs/db` removido.
- Siga os guias `docs.astro.build/en/guides/upgrade-to/v6` e `/v7`, uma versão major por vez.

## Checklist (Astro)
- [ ] Interatividade só onde precisa, com `client:visible`/`idle` por padrão.
- [ ] Props de ilha serializáveis. Estado entre ilhas em nanostores.
- [ ] Coleções com schema Zod. Imagens via `astro:assets`.
- [ ] Sessão em Redis quando houver mais de uma réplica com SSR.
- [ ] CSP ligada. Segredos só via `astro:env` com `access: 'secret'`.
- [ ] `astro check` (TS 6), build e Lighthouse ≥ 95 nas páginas principais.
