---
name: backend-fastify
description: Padrões para backend em Fastify (Node.js/TypeScript) — plugins, schemas, hooks, erros, banco e testes.
---

# Backend em Fastify

## Estrutura
```
src/
  app.ts                 # cria a instância e registra plugins (exportada para testes)
  server.ts              # listen + graceful shutdown
  plugins/               # db, auth, config (com fastify-plugin quando precisam ser globais)
  modules/<dominio>/     # routes.ts, schemas.ts, service.ts, repository.ts
```
- TypeScript estrito. ESM.

## Idiomas
- **Tudo é plugin**: encapsulamento por módulo com `fastify.register`. Use `fastify-plugin` só para decorators que precisam vazar escopo.
- **Schemas JSON** em toda rota (`body`, `params`, `querystring`, `response`) — validam entrada e aceleram a serialização. Use TypeBox ou Zod com type provider para tipar a partir do schema.
- Hooks (`onRequest`, `preHandler`) para auth e contexto; não repita lógica nas rotas.
- Decorators para dependências compartilhadas (`fastify.decorate('db', ...)`).
- Erros: `setErrorHandler` central mapeando erros de domínio para o formato padrão; use `@fastify/sensible` para `httpErrors`.
- Logger nativo (pino); nada de `console.log`.

## Ecossistema comum
`@fastify/cors`, `@fastify/helmet`, `@fastify/rate-limit`, `@fastify/jwt`, `@fastify/swagger` (gera OpenAPI a partir dos schemas). ORM: siga o projeto (Prisma, Drizzle, Kysely).

## Testes
- `app.inject()` para testar rotas sem subir porta. Vitest ou `node:test`.
- Banco real de teste (container) para integração.
- Verificação: `npm run lint && npm run typecheck && npm test` (ajuste aos scripts do projeto).
