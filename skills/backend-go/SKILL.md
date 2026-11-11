---
name: backend-go
description: "Padrões para backend em Go 1.26/1.27: go.mod, estrutura cmd/internal, HTTP, OpenAPI, erros, concorrência, pgx + sqlc + goose, MQTT, River, slog/OTel, testes, golangci-lint e Dockerfile distroless. Usar ao criar ou alterar código em projetos com go.mod."
---

# Go

Referência: **Go 1.27** (1.27.2) e **1.26** (1.26.9), que são as duas versões suportadas. A 1.25 já não recebe correções. Fontes: go.dev/doc/go1.23 a go1.27, go.dev/dl, e GitHub releases das bibliotecas, verificados em 15/10/2026.
- Padrões gerais de API: `backend-standards`. Banco: `sql-standards` e `postgres-scaling`. MQTT: `mqtt-contract`. Telemetria: `observability`.

## Versão e go.mod
- `go 1.26.0` (piso compatível com as duas suportadas) e `toolchain go1.27.2`. Suba o piso para `go 1.27.0` quando quiser usar `encoding/json/v2` e `uuid` da stdlib.
- **Nenhum símbolo da stdlib mais novo que a diretiva `go`.** O `go test` da 1.27 roda o `stdversion` e acusa.
- **Ferramentas como dependência** (1.24+): `go get -tool github.com/sqlc-dev/sqlc/cmd/sqlc` e `go tool sqlc generate`. O mesmo vale para govulncheck, goose e golangci-lint, se quiser fixar a versão no go.mod.
- **O que mudou e afeta o código:**

| Versão | Mudança |
|---|---|
| 1.23 | Iteradores (`iter.Seq`, `slices.Collect`, `maps.Keys`); timers sem `Stop` passam a ser coletados |
| 1.24 | Generic type aliases; `os.Root` (I/O confinado a um diretório, use em upload e arquivos); `testing.B.Loop`; `t.Context()`; tag JSON `omitzero`; FIPS 140-3 |
| 1.25 | **GOMAXPROCS respeita o limite de CPU do contêiner**; `sync.WaitGroup.Go`; `testing/synctest`; `http.CrossOriginProtection`; usar o resultado antes de checar `err` agora dá panic (era bug do compilador) |
| 1.26 | Green Tea GC por padrão; `new(expr)`; **`errors.AsType[T]`**; `slog.NewMultiHandler`; `go fix` como modernizer; TLS pós-quântico híbrido por padrão |
| 1.27 | **Métodos genéricos**; **`encoding/json/v2` estável** (o v1 usa a implementação v2: mesmo comportamento, mensagens de erro diferentes); **pacote `uuid`**; perfil `goroutineleak`; `asynctimerchan` removido |

## Estrutura
```
cmd/{api,ingest,worker}/main.go     # um binário por papel (ver architecture-scalability)
internal/<dominio>/                 # handler, service, repo, tipos do domínio
internal/platform/{config,db,httpserver,mqtt,otel}/
db/{migrations,queries}/            # goose + sqlc
```
- Sem `pkg/` por padrão. Pacote por domínio, não por camada técnica. **DI manual** no `run`, sem wire nem fx.
- **Config:** `caarlos0/env` v11 (`env.ParseAs[Config]()` com `required`/`notEmpty`). Use `koanf` v2 só se houver arquivo de configuração. O `envconfig` está parado.
- **`main` mínimo, `run(ctx) error` testável e shutdown em ordem:**
```go
func main() {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	if err := run(ctx); err != nil {
		slog.Error("fatal", "err", err)
		os.Exit(1)
	}
}

func run(ctx context.Context) error {
	cfg, err := env.ParseAs[config.Config]()
	if err != nil { return fmt.Errorf("config: %w", err) }
	// otel → pool → mqtt → http, cada um com o seu Close
	<-ctx.Done()
	sctx, cancel := context.WithTimeout(context.Background(), 20*time.Second) // ctx principal já foi cancelado
	defer cancel()
	ready.Store(false)        // 1. readiness 503
	_ = srv.Shutdown(sctx)    // 2. drena o HTTP
	mqttConn.Disconnect(sctx) // 3. para de receber
	ingestor.Flush(sctx)      // 4. grava o lote pendente e dá ack
	pool.Close()              // 5. banco
	return otelShutdown(sctx) // 6. flush da telemetria
}
```
  - `os.Exit` e `log.Fatal` fora do `main` pulam os `defer`.
  - O tempo total de shutdown precisa caber no `stop_grace_period` do Swarm.

## HTTP
- **`net/http.ServeMux`** com método e wildcard é o padrão (`mux.HandleFunc("POST /v1/devices/{id}/commands", h)`, `r.PathValue("id")`). Use **chi v5** quando precisar de grupos e subrouters com middleware. Evite gin, echo e fiber; o fiber nem usa `net/http`, e perde `otelhttp` e `httptest`.
- **Timeouts obrigatórios:**
```go
srv := &http.Server{
	Addr: ":8080", Handler: h,
	ReadHeaderTimeout: 5 * time.Second, ReadTimeout: 30 * time.Second,
	WriteTimeout: 30 * time.Second, IdleTimeout: 120 * time.Second, // > idle timeout do Traefik
}
r.Body = http.MaxBytesReader(w, r.Body, 1<<20) // limite de corpo por rota
```
  - Sem `ReadHeaderTimeout`, o servidor fica exposto a Slowloris.
  - O `WriteTimeout` corta SSE e streaming: desligue-o por rota com `http.NewResponseController(w).SetWriteDeadline`.
- **Cliente HTTP** sempre com `Timeout` (nunca `http.DefaultClient`) e `ctx` na requisição.
- **OpenAPI:**
  - **huma v2** quando o código é a fonte da verdade (gera OpenAPI 3.1 e erros RFC 9457 nativos);
  - **oapi-codegen ≥ v2.8.0** quando o contrato vem primeiro (a v2.7.1 e a v2.7.2 corrigiram injeção de código no gerador).
- **Validação:** `go-playground/validator` v10, com DTO de entrada explícito.
- **Erros** em `application/problem+json` (`backend-standards`), mapeados num único ponto.
- **CSRF** (API com cookie): `http.CrossOriginProtection` (1.25). CORS no middleware ou no Traefik.
- Atrás do Traefik, o IP real vem do `X-Forwarded-For` **só se** a conexão vier do proxy.

## Erros e contexto
- Envolva com `fmt.Errorf("criar pedido: %w", err)`. Compare com `errors.Is` e extraia com **`errors.AsType`** (1.26+):
```go
if pgErr, ok := errors.AsType[*pgconn.PgError](err); ok && pgErr.Code == "23505" {
	return ErrDuplicate
}
```
- Use sentinela (`ErrNotFound`) para caso de domínio e tipo de erro quando houver dados. Nunca compare `err.Error()`.
- **`ctx` é o primeiro parâmetro de todo I/O.** Não guarde `ctx` em struct.
  - `context.WithoutCancel` para trabalho que precisa terminar depois da resposta.
  - `context.AfterFunc` para fechar um recurso no cancelamento.
  - `context.Cause` para saber o motivo do cancelamento.

## Concorrência
- **`errgroup`** (`golang.org/x/sync`) com `SetLimit(n)` para paralelismo limitado e com erro. `wg.Go(func(){...})` (1.25) quando não há erro a propagar. `sync.OnceValue` para inicialização preguiçosa.
```go
g, ctx := errgroup.WithContext(ctx)
g.SetLimit(8)
for _, b := range batches {
	g.Go(func() error { return store.Insert(ctx, b) })
}
return g.Wait()
```
- Channel para passar posse ou montar pipeline; mutex para proteger estado.
- **Backpressure:** use channel **com buffer limitado** entre o consumidor (MQTT) e o gravador em lote. Quando enche, **bloqueia** em vez de descartar.
- **Toda goroutine tem dono e condição de saída** (`ctx.Done()`).
- `go test -race` no CI, `goleak` no `TestMain` e o perfil `goroutineleak` (1.27) em produção.
- Armadilhas:
  - `time.After` em loop quente;
  - channel sem buffer com retorno antecipado (vaza goroutine);
  - map compartilhado sem lock.

## Banco (PostgreSQL/TimescaleDB)
- **pgx v5.11 + `pgxpool`** é o padrão. Configure `MaxConns` pelo orçamento de conexões (réplicas × MaxConns, ver `postgres-scaling`), `MaxConnIdleTime` e `HealthCheckPeriod`. O readiness faz `pool.Ping(ctx)`.
- **sqlc v1.31** (`sql_package: pgx/v5`) é o padrão para queries: SQL escrito à mão, tipos gerados. GORM, não; ent ou bun só se o projeto já usa.
- **Migrations com goose v3** (SQL puro): rodam como etapa do deploy, nunca no boot das réplicas. As regras de migration estão em `sql-standards`.
- **Transação:**
```go
err := pgx.BeginFunc(ctx, pool, func(tx pgx.Tx) error {
	q := queries.New(tx)
	// ... operações + outbox na mesma tx
	return nil
}) // commit, ou rollback se a função devolver erro
```
- **Ingestão em lote** (telemetria):
  - `INSERT ... SELECT * FROM unnest($1::timestamptz[], $2::int[], ...) ON CONFLICT DO NOTHING` (idempotente);
  - ou `pool.CopyFrom` numa tabela de staging + `INSERT ... SELECT ... ON CONFLICT`, já que o COPY não aceita `ON CONFLICT`;
  - numa hypertable, a unique inclui a coluna de tempo.
- **PgBouncer** em transaction mode: configure `DefaultQueryExecMode` para `QueryExecModeCacheDescribe` ou `QueryExecModeExec`, sem prepared statements nomeados por conexão. Valide com carga.
- Sempre `defer rows.Close()` e confira `rows.Err()`. Mapeie `pgx.ErrNoRows` para `ErrNotFound`.

## MQTT
- **`github.com/eclipse/paho.golang`** (MQTT 5, `autopaho`) é o padrão; ainda é pré-1.0, então fixe a versão. O `paho.mqtt.golang` (só MQTT 3.1.1) fica para broker legado.
- **Ack só depois de persistir** (mesma regra de `backend-fastify-mqtt`):
  - `ClientConfig.EnableManualAcknowledgment = true`;
  - o handler enfileira no buffer limitado;
  - o gravador, **depois do commit do lote**, chama `client.Ack(pkt)` para cada mensagem, **na ordem de chegada**.
- **Sessão persistente:** `CleanStartOnInitialConnection = false`, `SessionExpiryInterval` > 0 (ex.: 3600) e **`ClientID` estável por réplica** (slot do Swarm). `$share/<grupo>/<filtro>` para dividir carga.
- O `receiveMaximum` (50 a 200) limita quantas mensagens ficam em voo sem ack.
- Não publique QoS 1 de dentro do callback de recepção esperando o PUBACK: há risco de deadlock. Mande para uma goroutine ou channel.
- **Payload inválido vai para a quarentena** e recebe ack. O contrato está em `mqtt-contract`.
- Faça **fuzz** do parser de payload (`FuzzParseTelemetry`).

## Redis e filas
- Redis: `go-redis` v9.
- **Filas: River** (v0.49, Postgres + pgx) é o padrão em Go. O job é **enfileirado na mesma transação** do dado, o que dispensa outbox. Fixe a versão, porque é pré-1.0; na v0.49 o chamador faz rollback em caso de erro nos helpers de transação.
- `asynq` só se o projeto já for centrado em Redis (v0.x, desenvolvimento moderado).

## Logs, métricas e traces
- **`log/slog`** com `slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: levelVar})`.
  - Para ocultar dados sensíveis, implemente `LogValuer` nos tipos sensíveis ou use `ReplaceAttr`.
  - `slog.NewMultiHandler` (1.26) envia para stdout e para a ponte OTel (`otelslog`).
- **OpenTelemetry Go** SDK 1.47: `otelhttp` no handler e no client, e `exaring/otelpgx` no pool.
- **Prometheus** `client_golang` v1.25 (exige Go ≥ 1.26), ou métricas via OTel. **Nunca** use id de device ou usuário em label.
- **pprof** só em **porta interna** (`:6060`, fora do Traefik): `net/http/pprof` e, na 1.27, `/debug/pprof/goroutineleak`.

## Testes
- Table-driven com `t.Run`, `t.Context()` e `go-cmp` (testify só se o projeto já usa).
- **Integração com serviços reais**: localmente, os serviços locais da máquina (ver `~/.claude/CLAUDE.md`, seção Serviços locais); no CI, serviços da própria esteira. Não use testcontainers-go nem crie containers. No `TestMain`, crie **uma vez por pacote** o banco `test_<projeto>_<id>` e apague-o ao terminar, mesmo com falha. Broker MQTT não existe nos serviços locais da máquina (ver `~/.claude/CLAUDE.md`, seção Serviços locais): pergunte ao dono.
- **Tempo:** `testing/synctest` para timeouts, retries e batching sem `sleep` real. `httptest.NewTestServer` e `synctest.Sleep` são da 1.27.
- Golden files em `testdata/` com `-update`. Fuzz em parsers. Benchmarks com `for b.Loop() {}`.
- No CI: `go test -race -coverprofile=cover.out ./...`.

## Qualidade, segurança e imagem
- **golangci-lint v2** (`version: "2"`, `linters.default: standard`, formatadores na seção `formatters`: gofumpt, goimports). Habilite `errcheck`, `govet`, `staticcheck`, `unused`, `bodyclose`, `contextcheck`, `errorlint`, `gosec`, `noctx`, `rowserrcheck`, `sqlclosecheck`, `nilerr` e `exhaustive`.
- No CI: `go mod tidy && git diff --exit-code`, `go vet`, **`govulncheck ./...`** e `go fix -diff` (1.26+).
```dockerfile
FROM golang:1.27.2-trixie AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/app ./cmd/api

FROM gcr.io/distroless/static-debian13:nonroot
COPY --from=build /out/app /app
USER nonroot
ENTRYPOINT ["/app"]
```
- **`GOMEMLIMIT`** em cerca de 80 a 90% do limite de memória do contêiner (via env no stack). **Não fixe `GOMAXPROCS`**: isso desliga o ajuste automático ao cgroup da 1.25.
- A distroless não tem shell, então o healthcheck do Swarm chama um subcomando do próprio binário (`/app healthcheck`, que faz GET no `/health/live`). Com `scratch`, copie os certificados de CA e o tzdata.

## Checklist de PR (Go)
- [ ] `ctx` em todo I/O. Erros envolvidos com `%w` e mapeados num ponto só.
- [ ] Toda goroutine com dono e saída. Buffers limitados. `-race` verde.
- [ ] Timeouts no `http.Server` e nos clients. Limite de corpo e de lote.
- [ ] Queries via sqlc. Migration conforme `sql-standards`. Ingestão idempotente.
- [ ] MQTT com ack só depois do commit.
- [ ] Logs sem segredo nem PII. Métricas sem label de alta cardinalidade.
- [ ] Testes de integração com serviços reais (locais ou da esteira), incluindo autorização (BOLA).
- [ ] golangci-lint, govulncheck e `go mod tidy` limpos. Nenhum símbolo mais novo que a diretiva `go`.
- [ ] Shutdown testado (SIGTERM com lote em andamento não perde dados).
