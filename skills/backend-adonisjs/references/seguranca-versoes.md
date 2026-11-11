# AdonisJS 7: versões mínimas seguras

Detalhe de `../SKILL.md`. Fonte: GitHub Security Advisories, verificado em 15/10/2026; reconfira o lockfile a cada release.

- **`@adonisjs/core` ≥ 7.5.2.** É a primeira que puxa `@adonisjs/http-server` ^9.3.1 e `@adonisjs/bodyparser` ^11.0.4, cobrindo:
  - path traversal, prototype pollution e DoS no bodyparser/multipart;
  - XSS refletido no exception handler;
  - ReDoS;
  - open redirect.
- `@adonisjs/lucid` ≥ 22.0 (mass assignment), `@adonisjs/ally` ≥ 6.3.1 (bypass do `state` OAuth), `@adonisjs/inertia` ≥ 5.0.4.
- Confira o lockfile, e não só o `package.json`: `npm ls @adonisjs/http-server @adonisjs/bodyparser`.

