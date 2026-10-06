---
name: padroes-frontend
description: Padrões gerais de frontend da equipe, válidos para Vue, React e Astro — componentes, estado, dados, desempenho, acessibilidade e testes.
---

# Padrões de frontend

> As convenções do projeto têm prioridade. Carregue também a skill da stack: `frontend-vue`, `frontend-react` ou `frontend-astro`.

## Componentes
- Pequenos e com uma responsabilidade. Separe componentes de apresentação (props in, eventos out) dos que buscam dados.
- TypeScript estrito; props tipadas.
- Use os componentes e tokens do design system; não crie variações locais de botão, input etc.

## Estado e dados
- Estado o mais local possível; global só para o que é realmente compartilhado.
- Estado de servidor (dados da API) em ferramenta de cache (TanStack Query / Vue Query / equivalente), não em store global manual.
- Cliente de API tipado a partir do contrato. Trate os quatro estados: **carregando, vazio, erro, sucesso**.

## Desempenho
- Code splitting por rota, lazy de componentes pesados, imagens otimizadas com dimensões definidas.
- Evite re-renderizações desnecessárias; meça antes de otimizar.
- Metas: LCP < 2,5 s, INP < 200 ms, CLS < 0,1.

## Acessibilidade
Siga a skill `ui-ux`. Mínimo: HTML semântico, navegação por teclado, foco visível, labels em inputs, contraste AA.

## Segurança
- Nunca injete HTML não sanitizado (`v-html`, `dangerouslySetInnerHTML`, `set:html`) com dados do usuário.
- Nada de segredos no bundle: variável de ambiente exposta ao cliente é pública.

## Testes
- Vitest + Testing Library (testar comportamento, não implementação). E2E dos fluxos críticos com Playwright.
