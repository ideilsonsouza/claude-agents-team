---
name: test-strategy
description: Estratégia de testes da equipe para Go, Node/TypeScript (Fastify, AdonisJS, BullMQ, MQTT) e frontend (Vue, React, Astro) — nível certo de teste por tipo de mudança, testes de aceite escritos antes da implementação a partir dos critérios EARS, suíte negativa obrigatória (autorização, tenant cruzado, entrada inválida, duplicata, SSRF, webhook), dependências reais (serviços locais; no CI, da esteira), dados e fixtures determinísticos, testes instáveis e checklist de qualidade de teste. Usar ao planejar testes, escrever testes de aceite, validar entrega ou revisar se os testes provam o comportamento.
---

# Estratégia de testes

Objetivo: **provar o comportamento pedido** com o menor conjunto de testes rápidos e confiáveis. A cobertura indica onde olhar, mas não prova nada.

## 1. Nível certo por tipo de mudança

| Mudança | Teste principal | Complemento |
|---|---|---|
| Regra de negócio pura (cálculo, validação, máquina de estado) | Unitário, tabela de casos | Property/fuzz se a entrada é grande (Go: `testing.F`; TS: fast-check) |
| Endpoint HTTP | Integração no nível HTTP com banco real: Fastify `app.inject`, Adonis `client` do Japa, Go `httptest` + handler real | Contrato OpenAPI no CI |
| Query, migration, transação | Integração com Postgres real (serviço local em banco `test_<projeto>_<id>`; no CI, serviço da esteira), migrations aplicadas | Teste da migration sobre dados que já existem |
| Fila/worker (BullMQ, River) | Integração com Redis/Postgres real: enfileira → processa → efeito persistido | Retry, idempotência, shutdown no meio |
| Consumidor/publicador MQTT | Integração com broker real (Mosquitto em container) | Duplicata, reentrega sem ack, payload inválido em quarentena |
| Integração externa (HTTP de terceiro) | Integração com servidor falso (MSW, `httptest.Server`) | Timeout, 5xx, 429, resposta malformada |
| Componente de UI | Testing Library (comportamento visível, papéis ARIA) | Estados: carregando, vazio, erro, sem permissão |
| Jornada crítica (login, checkout, fluxo principal) | E2E Playwright, poucos e estáveis | axe-core na mesma jornada |
| Bug | **Teste de regressão que reproduz o bug primeiro** (falha antes, passa depois) | — |

Regra: desça o teste ao nível mais baixo que ainda prova o critério. Não use E2E para regra de negócio nem mock de banco para testar query.

## 2. Testes de aceite antes da implementação (só G; em M, o `qa` valida no fim)

1. Para cada critério EARS (`QUANDO <evento> O sistema DEVE <resposta>`), escreva **um teste nomeado pelo critério**: `CA2: quando o token expira, retorna 401 com problem+json`.
2. Escreva contra a **interface pública** do `design.md` (rota, status, payload, função exportada), nunca contra detalhe interno que ainda não existe.
3. Rode e confirme que **falha pelo motivo certo**: asserção de status ou de corpo, ou rota inexistente (404). Erro de compilação, de import ou de fixture **não** conta como falha válida. Nesses casos crie o mínimo (stub da rota que retorna 501, tipo exportado) ou marque BLOQUEADO.
4. Depois da implementação, o teste de aceite **não pode ser editado** pelo autor. Se o teste estiver errado, quem corrige é o `qa`, com motivo registrado.

## 3. Suíte negativa (aplicar o que couber)

| Risco | Caso mínimo |
|---|---|
| Autorização por objeto (BOLA/IDOR) | Usuário A acessa recurso de B pelo ID → 404 (ou 403, conforme o contrato) |
| Tenant cruzado | Mesmo ID com token do tenant X sobre dado do tenant Y → não encontra; listagem não vaza |
| Escalada | Papel comum chama rota de admin → 403 |
| Sessão | Token expirado, revogado ou com assinatura errada → 401 |
| Mass assignment | Corpo com `role`, `tenantId` ou `id` extras → ignorados ou rejeitados |
| Entrada | Campo faltando, tipo errado, tamanho acima do limite, Unicode estranho → 400/422 problem+json |
| Injeção | `' OR 1=1 --` ou `../../etc/passwd` tratados como dado |
| SSRF (se busca URL) | `http://169.254.169.254`, `localhost`, IPv6 `[::1]` e redirect para interno → recusado |
| Webhook | Assinatura inválida, timestamp antigo, mesmo evento 2× → rejeita ou processa uma vez |
| Idempotência | Mesmo `Idempotency-Key` 2× → um efeito, mesma resposta |
| Concorrência | Duas atualizações simultâneas → uma vence (ETag/If-Match ou lock) e a outra recebe 409/412 |
| Limites | Página acima do máximo, upload grande, rate limit → resposta definida (429 com `Retry-After`) |
| Logs | Nenhum token, senha ou segredo no log do caso de erro |

Todo endpoint novo com autenticação tem **pelo menos** os casos de BOLA e de tenant cruzado.

## 4. Dependências reais e isolamento

- Banco, Redis e broker reais: localmente, use os serviços locais da máquina (ver `~/.claude/CLAUDE.md`, seção Serviços locais); no CI, serviços da própria esteira. Não crie containers de teste (Testcontainers, `docker run`, compose próprio). Use um banco por execução (`test_<projeto>_<id>`, apagado ao terminar) e isole por transação ou por schema por arquivo. Broker que não existe nos serviços locais da máquina (ver `~/.claude/CLAUDE.md`, seção Serviços locais): pergunte ao dono.
- Mock apenas o que está **fora** do sistema (API de terceiro, relógio, aleatoriedade). Não mocke o próprio código para fazer o teste passar.
- Relógio: injete (`clock`/`time.Now` como dependência; Vitest `vi.useFakeTimers`; Go 1.25+ `testing/synctest` para concorrência com tempo).
- Rede externa bloqueada nos testes (MSW `onUnhandledRequest: 'error'`).

## 5. Dados e fixtures

- Use factories com padrões mínimos e sobrescreva só o que o teste precisa. Nada de fixture global que todos os testes alteram.
- IDs, datas e e-mails gerados, únicos por teste. Nunca dependa da ordem dos testes.
- Use dados sintéticos e nunca uma cópia de produção.

## 6. Testes instáveis (flaky)

- Teste que falha sem mudança de código é defeito do teste. Investigue antes de re-rodar.
- Causas comuns: `sleep` em vez de esperar uma condição, ordem entre testes, porta fixa, fuso, dependência de rede, timer real.
- Não marque `.skip` nem retry automático para "resolver". Se precisar isolar, abra um item no `backlog.md` com o dono.

## 7. Comandos por stack (confirmar no `tech.md` / `package.json`)

| Stack | Rodar módulo | Notas |
|---|---|---|
| Go | `go test ./internal/orders/... -race -count=1` | `-count=1` evita cache; `-run 'CA2'` para filtrar |
| Vitest | `pnpm vitest run src/orders` | `--reporter=dot` reduz saída |
| AdonisJS (Japa) | `node ace test --files tests/functional/orders` | |
| Playwright | `pnpm playwright test e2e/checkout.spec.ts` | Trace só em falha |

## 8. Checklist de qualidade do teste (para `qa` e `reviewer`)

- [ ] O nome diz o comportamento e o critério (CA#).
- [ ] A asserção é sobre o resultado observável (status, corpo, linha no banco, mensagem publicada), não só "não lançou".
- [ ] Falharia se a implementação estivesse errada (mude mentalmente a regra: o teste pega?).
- [ ] Casos negativos aplicáveis da seção 3 estão presentes.
- [ ] Sem `sleep`, sem ordem implícita, sem rede externa, sem dado de produção.
- [ ] Nenhum teste existente foi pulado, afrouxado ou apagado sem justificativa no relatório.
