---
name: backend-adonisjs
description: Padrões para backend em AdonisJS (v6) — estrutura, controllers, validação com VineJS, Lucid ORM, auth, IoC e testes com Japa.
---

# Backend em AdonisJS

> Referência: AdonisJS v6 (TypeScript, ESM). Se o projeto for v5, siga as convenções da v5 já existentes.

## Estrutura (convenção do framework — respeite)
```
app/controllers/   app/models/   app/validators/   app/services/
app/middleware/    app/exceptions/   start/routes.ts   start/kernel.ts
database/migrations/   database/seeders/   tests/
```
- Gere arquivos com `node ace make:<tipo>` para manter o padrão.

## Idiomas
- **Controllers finos**: recebem, validam, chamam um service, respondem. Regra de negócio em `app/services`.
- **Validação com VineJS** em `app/validators`, usando `request.validateUsing(validator)`.
- **Lucid ORM**: models com relacionamentos declarados; evite N+1 com `preload`; transações com `db.transaction`.
- **Injeção de dependência** via container (`@inject()`) para services.
- **Auth** com `@adonisjs/auth` (guards de sessão ou access tokens) e **autorização** com `@adonisjs/bouncer` (policies).
- Erros: exceções próprias em `app/exceptions` e o handler global para o formato padrão.
- Imports com os aliases de subpath (`#controllers/...`, `#models/...`).
- Variáveis de ambiente validadas em `start/env.ts`.

## Testes
- **Japa** (`node ace test`) com plugin de API client para rotas; banco de teste com transação global por teste.
- Verificação: `node ace test` + `npm run lint` + `npm run typecheck`.
