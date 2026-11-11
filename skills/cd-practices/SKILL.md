---
name: cd-practices
description: "Entrega contínua para serviços Node.js em contêiner (Swarm + Traefik, Coolify, Dokploy): build once/deploy many, rollback por imagem, healthcheck, graceful shutdown, expand/contract e checklist \"pronto para CD\". Usar ao desenhar ou revisar a esteira de deploy ou preparar um serviço para CD."
---

# Práticas de CD

Levantado em 2026-10-13 a partir de: docs do Docker/Swarm, código do Moby, Traefik e BullMQ, Node.js docs, 12factor, Google SRE workbook, Martin Fowler e dora.dev. Detalhes de plataforma ficam em `deploy-coolify` e `deploy-dokploy`; a esteira, em `cicd-github-actions`.

## 1. Artefato e versão
- **Build once, deploy many**: o CI gera a imagem uma vez e a mesma imagem (pelo **digest**) passa por staging e produção. Só a configuração muda por ambiente (12factor, build/release/run).
- Tags: `vX.Y.Z` (semver) e `sha-<commit>`. `latest` ou `main` nunca são versão de produção, porque tag é mutável e digest não.
- Changelog gerado dos Conventional Commits (release-please).
- **Rollback = redeploy da imagem anterior**, em segundos e sem CI. Reverter commit é a correção definitiva, depois.
- Rollback só é seguro com migration e contrato compatíveis para trás (§4). Ensaie o rollback antes de precisar.
- Retenção: guarde as tags semver e as últimas N imagens de release. `docker image prune` no servidor não pode apagar a imagem do rollback.

## 2. Healthcheck e zero downtime
- No Swarm e no Traefik, o healthcheck do Docker é **readiness**. Isso foi confirmado no código:
  - o Swarm só põe a tarefa no balanceamento depois de `healthy` e substitui a `unhealthy`;
  - o Traefik ignora container `starting` ou `unhealthy`;
  - **container sem HEALTHCHECK é roteado assim que fica `running`**.
- O healthcheck deve:
  - ser barato;
  - falhar até as dependências estarem prontas (ex.: Redis conectado);
  - **responder 503 durante o shutdown**.
- Em Docker puro, `unhealthy` não reinicia o container, só o tira do roteamento.
- Parâmetros: `start_period` cobrindo o boot, `start_interval` de 1 a 2 s (Engine 25 ou mais nova), `interval` de 10 a 30 s e `retries` igual a 3. Os defaults do Dockerfile são 30 s de interval, 30 s de timeout e 0 s de start-period.
- Rolling update:
  - `start-first` sobe o novo antes de parar o antigo. Precisa de healthcheck, e as duas versões coexistem por um tempo.
  - `stop-first` é o default do Swarm.
  - Rollback automático: `failure_action: rollback`, com `monitor` maior que `start_period + interval × retries`.
- O provider Swarm do Traefik faz polling (`refreshSeconds` 15 s por padrão). Drene com folga: health 503, espera, depois feche.
- Blue-green e canary não vêm prontos no Coolify/Dokploy. Exigem montagem manual (Traefik `weighted`) e só valem para serviço HTTP com tráfego. Para worker de fila são pouco úteis, porque todos consomem a mesma fila.

## 3. Graceful shutdown
- **PID 1**: o Node não é um bom PID 1. Use `dumb-init` ou `tini` (ou `init: true` no compose), com `CMD`/`ENTRYPOINT` em forma exec. **Nunca `npm start`** no container, porque o npm engole o SIGTERM. Script de entrypoint termina com `exec node ...`.
- O `docker stop` manda SIGTERM e, após o prazo, SIGKILL. **O padrão é 10 s** (Docker, Compose e Swarm); no Coolify é 30 s. Ajuste `stop_grace_period`/`StopGracePeriod` para ser **maior que o job mais longo mais a drenagem mais uma margem**.
- Ordem no SIGTERM:
  1. health 503;
  2. esperar alguns segundos (o proxy percebe);
  3. `server.close()`;
  4. `await worker.close()`, com **timeout próprio**;
  5. no limite, `worker.close(true)` e `server.closeAllConnections()`;
  6. `redis.quit()`;
  7. `exit`.
- **BullMQ**:
  - `worker.close()` para de pegar jobs e espera os atuais, mas **não tem timeout**.
  - Se o processo morrer, o job vira *stalled* e volta para `wait` em cerca de 30 s (`lockDuration` e `stalledInterval` de 30000). Com `maxStalledCount` 1, o segundo stall leva o job para `failed`.
  - Código síncrono pesado no event loop impede a renovação do lock e causa stall falso.
  - **Jobs precisam ser idempotentes ou reentrantes**: stall e retry executam de novo.
- Timeout do sandbox ou do job menor que o stop grace period. Senão, o SIGKILL corta no meio.

## 4. Compatibilidade entre versões e serviços
- **Expand/contract**:
  1. expandir: aceitar o velho e o novo;
  2. migrar os produtores e consumidores;
  3. contrair: remover o velho.
  Vale para schema de banco, payload de job e API. **Nunca contraia no mesmo release em que expande.**
- **Ordem com contrato produtor → fila → consumidor** (ex.: core → BullMQ → worker):
  1. primeiro, o **consumidor tolerante** (aceita v1 e v2, campos novos opcionais);
  2. depois, o produtor passa a enviar v2;
  3. espere a fila e os jobs agendados ou com retry em v1 se esgotarem;
  4. só então contraia.
- Durante rolling update ou com várias réplicas, **versão velha e nova consomem a mesma fila ao mesmo tempo**. Qualquer job cai em qualquer versão.
- Versione o payload (`schemaVersion`). Versão desconhecida deve virar erro não-retentável (`UnrecoverableError`) com log claro.
- Banco: a migration roda antes do deploy, é compatível com N e N+1 e nunca é destrutiva no mesmo release.
- Feature flags desacoplam deploy de release. Todo flag nasce com data e tarefa de remoção.

## 5. Ambientes e segredos
- Staging com a mesma imagem, topologia e versões (Redis, proxy) que produção, e com dados sintéticos.
- Preview de PR para worker de fila exige **Redis/fila isolados** (DB ou prefixo próprio), senão consome jobs de outro ambiente.
- Segredos só em runtime, diferentes por ambiente. Nunca em `ARG`/`ENV` de build, que ficam na imagem e na proveniência. Para segredo de build, use `RUN --mount=type=secret`.

## 6. Verificação pós-deploy
1. A plataforma chegou ao estado final (polling da API).
2. Smoke test pelo caminho real (proxy): `/health` com retry, **conferindo a versão nova**. Expor versão ou SHA no health facilita.
3. Alguns minutos de métricas: taxa de erro, jobs `failed` e stalled, tamanho da fila, latência e callbacks.

- Critério de rollback: health falhando após a estabilização, erro acima do patamar anterior ou fluxo crítico quebrado.
- Critérios além do health exigem script ou alerta, porque não são nativos das plataformas.
- **DORA** (5 métricas atuais): deployment frequency, change lead time, failed deployment recovery time, change fail rate e deployment rework rate. Meça a partir dos timestamps do CI e marque os deploys revertidos.

## 7. Cadeia de suprimentos
- Imagem base fixada por digest (`FROM node:24-alpine@sha256:...`), atualizada por Renovate (`pinDigests`) ou Dependabot (`docker`).
- Multi-stage, sem toolchain na imagem final, com `USER node`.
- Scan (Trivy ou Grype) com gate em CRITICAL/HIGH. SBOM e proveniência pelo BuildKit.
- `cosign` (keyless) é opcional. Coolify e Dokploy não verificam assinatura no pull.

## 8. Checklist "pronto para CD"
- [ ] Dockerfile multi-stage, base por digest, não-root, PID 1 com init, `exec node` em forma exec.
- [ ] HEALTHCHECK de readiness (dependências prontas, 503 no shutdown) com `start_period` calibrado.
- [ ] SIGTERM tratado na ordem do §3, com timeout próprio. Stop grace period maior que job + drenagem.
- [ ] Jobs idempotentes; lock e stall revistos para a duração real.
- [ ] Contrato versionado, consumidor tolerante a N-1 e N+1, ordem de deploy entre serviços documentada.
- [ ] Imagem única do CI, tag imutável, deploy por tag ou digest; rollback por imagem documentado e ensaiado.
- [ ] Deploy acompanhado até o fim + smoke test que confirma a versão + alerta de falha.
- [ ] Segredos só em runtime e por ambiente.
- [ ] Renovate ou Dependabot ativos e scan de imagem no CI.
- [ ] Plataforma configurada para rolling sem porta publicada no host (Coolify) ou com Swarm settings e healthcheck (Dokploy).
