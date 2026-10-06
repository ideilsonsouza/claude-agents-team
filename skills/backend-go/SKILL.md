---
name: backend-go
description: Padrões para backend em Go — estrutura de projeto, HTTP, erros, contexto, concorrência, banco e testes.
---

# Backend em Go

## Estrutura
```
cmd/<app>/main.go        # wiring e inicialização
internal/<dominio>/      # handler.go, service.go, repository.go, model.go
internal/platform/       # db, config, logger, http server
migrations/
```
- `internal/` para tudo que não é API pública do módulo. Pacotes por domínio, não por camada técnica.

## Idiomas
- Erros: retorne `error`, envolva com contexto `fmt.Errorf("buscar usuário %d: %w", id, err)`, compare com `errors.Is/As`. Erros de domínio como variáveis sentinela (`ErrNotFound`).
- `context.Context` como primeiro parâmetro em tudo que faz I/O; respeite cancelamento e timeouts.
- Interfaces pequenas, definidas **por quem consome**.
- Concorrência: toda goroutine tem dono e forma de terminar (`errgroup`, `context`). Rode testes com `-race`.
- Sem `panic` para fluxo normal.

## HTTP
- `net/http` com o roteador da stdlib (Go 1.22+) ou chi; siga o que o projeto usa.
- Timeouts no `http.Server` (`ReadHeaderTimeout`, `ReadTimeout`, `WriteTimeout`) e graceful shutdown.
- Logs com `log/slog` (JSON).

## Banco
- `database/sql`/`pgx` com `sqlc`, ou o que o projeto já usa. Migrations com `golang-migrate` ou `goose`.

## Qualidade
- `gofmt`/`goimports`, `go vet`, `golangci-lint`.
- Testes table-driven com `t.Run`; `httptest` para handlers; `testcontainers-go` para integração.
- Comando de verificação: `go test -race ./... && go vet ./...`
