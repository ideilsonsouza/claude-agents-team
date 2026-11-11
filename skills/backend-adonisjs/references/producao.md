# AdonisJS 7: produção (Docker, Swarm, Traefik)

Detalhe de `../SKILL.md`. Fonte: docs.adonisjs.com v7, 2026-11-10.

- **Build:** `node ace build` gera `build/` standalone, sem `.env`. Dockerfile multi-stage:
  1. deps: `npm ci`;
  2. build: `node ace build`;
  3. runtime: `node:24-<variante>` fixado, `COPY --from=build /app/build ./`, `npm ci --omit=dev`, `USER node`, `CMD ["node", "bin/server.js"]` (forma JSON, para o SIGTERM chegar ao Node).
- **Env:** `HOST=0.0.0.0`, `PORT=3333`, `NODE_ENV=production` e **`APP_KEY` igual em todas as réplicas**, porque ele cifra cookies e dados. O `APP_KEY` vem do secret do Swarm, nunca da imagem.
- **Proxy:** em `config/app.ts`, `trustProxy: proxyAddr.compile(['loopback', 'uniquelocal'])` (a overlay do Swarm é rede privada). `keepAliveTimeout` **maior** que o idle timeout do Traefik.
- **Health:** `node ace configure health_checks` cria `/health/live` e `/health/ready`.
  - O `ready` usa `DbCheck`, `RedisCheck` e `DiskSpaceCheck`.
  - **O healthcheck do contêiner aponta para `live`.** O `ready` fica para o Traefik e o deploy; se o contêiner checasse `ready`, uma queda do banco reiniciaria tudo.
  - O relatório completo do `ready` expõe pid e versão: proteja com header secreto ou rede interna.
- **Shutdown:** o `bin/server.ts` já chama `app.terminate()` no SIGTERM. A limpeza fica no `shutdown()` dos providers. O `stop_grace_period` do Swarm deve ser maior que o tempo de drenagem (`cd-practices`).
- **Logs:** pino em JSON no stdout (`observability`).
- **Traces:** `node ace add @adonisjs/otel`, que cria `bin/otel.ts`, importado no topo do `server.ts`. Configure com as variáveis `OTEL_*`.
- **Filas:** **BullMQ direto** (`backend-bullmq`), com o worker em processo separado (comando ace ou entrypoint próprio, sem HTTP).
  - `@adonisjs/queue` (0.6, sobre `@boringnode/queue`) é **experimental**: só com ADR e versão exata.
  - O `@rlanz/bull-queue` não suporta a v7.

