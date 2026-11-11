---
name: security-go
description: "Segurança de Go 1.26/1.27: govulncheck, gosec, -race, fuzzing, net/http com timeouts, os.Root, injeção, criptografia/TLS, build endurecido e distroless. Usar ao blindar, auditar ou revisar código Go ou seus portões de CI."
---

# Blindagem em Go

Fontes verificadas em **23/10/2026**: go.dev/doc/security/best-practices, go.dev/doc/go1.24–1.27,
golangci-lint.run, pkg.go.dev (`golang.org/x/crypto/argon2`, `crypto/subtle`).
Base: `security-hardening`. Dependência e CI: `security-supply-chain`.
Padrões de API, authz, JWT e senha: `backend-standards`. Estrutura e stack: `backend-go`.

## 1. Versão e atualização
- Suportadas: **1.27.x** e **1.26.x**. Correção de segurança sai no **último patch de cada linha** —
  rodar 1.27.0 quando existe 1.27.2 é dívida.
- Assine `golang-announce`: release de segurança é pré-anunciado lá.
- Fixe `toolchain go1.27.2` no `go.mod` e a mesma tag no `FROM` do Dockerfile. Não deixe o CI
  resolver toolchain sozinho.

## 2. Ferramentas (portões de CI)
```bash
go vet ./...
go test -race ./...                 # corrida só aparece no caminho executado
govulncheck ./...                   # vulnerabilidade ALCANÇÁVEL por caminho de chamada
golangci-lint run                   # inclui gosec; config v2
go mod verify && go mod tidy -diff  # integridade e sincronia do go.sum
osv-scanner scan source -r .
```
`govulncheck` é o diferencial do Go: ele diz se **o seu código chega** na função vulnerável.
Achado dele é prioridade real; achado de scanner genérico pode ser presença sem alcance — mas
registre a análise, não ignore em silêncio.

`.golangci.yml` (v2) com o mínimo de segurança:
```yaml
version: "2"
linters:
  enable:
    - gosec          # padrões de segurança
    - bodyclose      # resp.Body não fechado = vazamento de conexão
    - noctx          # requisição HTTP sem context
    - errcheck       # erro ignorado
    - errorlint      # errors.Is/As em vez de comparação
    - rowserrcheck   # rows.Err() não verificado
    - sqlclosecheck
    - contextcheck
```
Supressão de gosec é **por linha, com motivo** (`//nolint:gosec // math/rand só para jitter`).
Arquivo inteiro suprimido esconde o próximo bug de verdade.

## 3. Integridade de módulo
Default já é forte: module proxy + checksum DB (`sum.golang.org`) detectam troca de conteúdo, e
**não existe install script** em Go. Onde ainda dá errado:
- `GOPRIVATE`/`GONOSUMDB` **desligam a verificação** para os padrões listados — liste o mínimo
  (`github.com/minha-org/*`), nunca `*`.
- `replace` para fork ou caminho local **não passa pelo sumdb**: revise todo `replace` no PR;
  nenhum `replace` local chega na `main`.
- `GOFLAGS=-mod=readonly` no CI, para o build não alterar `go.mod` silenciosamente.

## 4. Servidor HTTP
Zero value de timeout é **sem limite** — é o furo mais comum em Go.
```go
srv := &http.Server{
    Addr:              ":8080",
    Handler:           mux,
    ReadHeaderTimeout: 10 * time.Second, // Slowloris
    ReadTimeout:       30 * time.Second,
    WriteTimeout:      30 * time.Second,
    IdleTimeout:       120 * time.Second, // > idle do Traefik
    MaxHeaderBytes:    1 << 14,           // 16 KiB
    ErrorLog:          slogErrorLog,
}
```
- Body: `r.Body = http.MaxBytesReader(w, r.Body, 1<<20)` em **toda** rota que lê body, e
  `json.Decoder` com `DisallowUnknownFields()` (allowlist de entrada).
- `recover()` em middleware no topo do handler: panic em handler mata a conexão, e em **goroutine
  sem recover mata o processo**. Toda goroutine disparada por request precisa de recover próprio.
- Não use `http.DefaultServeMux` nem `http.DefaultClient` (sem timeout) em código de serviço.
- `http.ServeMux` da 1.22+ faz roteamento por método e padrão — prefira a stdlib ou `chi` com
  middleware explícito de authz.
- Propague `r.Context()` para banco, broker e chamada externa: cliente desconectado deve cancelar
  trabalho (é limite de recurso, não só performance).

## 5. Cliente HTTP e SSRF
```go
client := &http.Client{
    Timeout: 5 * time.Second,
    CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse },
    Transport: &http.Transport{
        MaxIdleConns: 100, MaxConnsPerHost: 20,
        TLSClientConfig: &tls.Config{MinVersion: tls.VersionTLS12},
        DialContext: (&net.Dialer{Timeout: 3 * time.Second, Control: blockPrivateIP}).DialContext,
    },
}
```
Com URL vinda do usuário: allowlist de esquema/host, **bloqueio de IP privado/loopback/link-local no
`Control` do Dialer** (depois da resolução de DNS, o que fecha o DNS rebinding), sem seguir redirect.
Nunca `InsecureSkipVerify: true` — se o certificado é privado, carregue a CA em `RootCAs`.

## 6. Arquivo e caminho
```go
root, err := os.OpenRoot("/app/uploads")   // Go 1.24+: I/O confinado ao diretório
defer root.Close()
f, err := root.Open(userName)              // "../" e symlink para fora falham aqui
```
`filepath.Clean`/`Join` **não** confinam. Sem `os.Root` (1.23-), resolva e compare prefixo com
`filepath.Abs` + `strings.HasPrefix(p, base+string(os.PathSeparator))`.
Nome de arquivo salvo é gerado pelo servidor; `archive/zip` e `tar` exigem checar cada entrada
(zip-slip) e limitar tamanho descomprimido.

## 7. Injeção
- SQL: sempre placeholder (`$1`), nunca `fmt.Sprintf`. Identificador dinâmico por allowlist +
  `pgx.Identifier{}.Sanitize()`. Ver `sql-standards`.
- Comando: `exec.CommandContext(ctx, "/usr/bin/ffmpeg", args...)` — sem `sh -c`, caminho absoluto,
  env mínimo (`cmd.Env = []string{...}`).
- HTML: **`html/template`** (escapa por contexto). `text/template` para HTML é XSS garantido.
  Nunca `template.HTML(entradaDoUsuário)`.
- Log: não concatene entrada do usuário em mensagem de log sem escapar quebra de linha (log injection).

## 8. Criptografia
- Senha: `golang.org/x/crypto/argon2` — `argon2.IDKey(pw, salt, 2, 19*1024, 1, 32)`
  (t=2, m=19 MiB, p=1), salt de 16 B do `crypto/rand`, guardado em formato PHC.
- Comparação: `subtle.ConstantTimeCompare` (ou `hmac.Equal` para MAC). Nunca `==` em segredo.
- Aleatório: **`crypto/rand`**. `math/rand`/`math/rand/v2` só para jitter e amostragem — e com
  comentário dizendo isso (gosec G404).
- TLS do servidor: `MinVersion: tls.VersionTLS12`. A troca híbrida pós-quântica
  (`X25519MLKEM768`) é default desde a 1.24 — deixe o default, não force `CurvePreferences`.
- JWT: `golang-jwt/jwt/v5` com `jwt.WithValidMethods([]string{"ES256"})` e validação de
  `iss`/`aud`/`exp`. Nunca aceitar `alg` do token.
- FIPS 140-3 (quando o cliente exigir): `GOFIPS140=latest` no build e/ou `GODEBUG=fips140=on`;
  `fips140=only` faz panic em algoritmo não aprovado. Validação cobre o módulo, não o seu produto.
- Dado em repouso: AEAD (`crypto/cipher` GCM ou `chacha20poly1305`) com nonce único por mensagem.

## 9. Erro, panic e recurso (A10)
- Nunca descarte erro (`_ =`) fora de `defer Close()` em leitura. `errcheck` cobra.
- `errors.Is`/`errors.As` (1.27: `errors.AsType`); erro sentinela tipado na borda, mensagem genérica
  para o cliente, detalhe no log com `requestId` — sem vazar SQL nem caminho de arquivo.
- `defer resp.Body.Close()` **e** `io.Copy(io.Discard, resp.Body)` quando descarta corpo, senão a
  conexão não volta ao pool.
- `rows.Err()` depois do loop; `tx.Rollback()` em `defer` com commit explícito.
- Transação multi-etapa: rollback completo, nunca compensação parcial.
- Goroutine: sempre com dono e cancelamento (`errgroup.WithContext`), limite de concorrência
  (`g.SetLimit`), e **recover**. Vazamento de goroutine é DoS lento.
- Conversão de inteiro: `int` → `int32`/`uint` com entrada do usuário trunca/inverte sinal
  (gosec G115) — valide faixa antes com `strconv.ParseInt(s, 10, 32)`.
- `unsafe` e `cgo` saem do modelo de memória seguro: justifique no PR ou não use.
  `CGO_ENABLED=0` por default.

## 10. Build e imagem
```dockerfile
FROM golang:1.27.2 AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download && go mod verify
COPY . .
RUN CGO_ENABLED=0 go build -trimpath -buildvcs=true -ldflags="-s -w" -o /out/api ./cmd/api

FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=build /out/api /api
USER 65532:65532
ENTRYPOINT ["/api"]
```
`-trimpath` tira caminho do build do binário; `-buildvcs=true` grava commit (rastreabilidade);
`distroless/static` + `CGO_ENABLED=0` dá imagem sem shell nem libc.
Runtime: read-only rootfs, `cap_drop: ALL`, `no-new-privileges`, limites de memória
(o GOMAXPROCS respeita cgroup desde a 1.25).

## 11. Testes de segurança
- `go test -race ./...` no CI, sempre.
- **Fuzzing** (`func FuzzX(f *testing.F)`) em todo parser de entrada não confiável: payload MQTT,
  JSON de dispositivo, importador de CSV, decoder binário. É o jeito mais baixo custo de achar
  pânico explorável e DoS.
- Teste de authz cruzado (tenant A → recurso de B = 404) por recurso.
- Teste de caminho de falha: banco/broker fora → nega, sem panic, sem vazar detalhe.
- `synctest` (1.25+) para testar timeout e cancelamento sem flake.
