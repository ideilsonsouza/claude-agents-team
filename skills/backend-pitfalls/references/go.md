# Armadilhas específicas de Go

Confirme sempre na versão instalada (`go doc pacote.Simbolo` ou fonte em `$(go env GOMODCACHE)`).

## pgx
- **`PgConn.CopyFrom` com `io.Reader` próprio:** o reader é lido numa goroutine; em retornos antecipados por erro o CopyFrom pode sair sem esperá-la. Estado do reader lido depois (flag de "excedeu") vira data race, e o reader pode ser lido após o `defer Close`. Flag compartilhada → `atomic.Bool`; teste com cancelamento durante o COPY sob `-race`.
- O CopyFrom troca o erro do reader por cancelamento (SQLSTATE 57014): não dependa da mensagem original.
- Arquivo de migration executado sem argumentos vai em protocolo simples = transação implícita; aplicar e registrar em dois comandos deixa janela de estado inconsistente se o processo morrer entre eles.

## River (fila sobre Postgres)
- `RescueStuckJobsAfter` (padrão 1 h) é comparado com o `JobTimeout` do client; o `Timeout()` por worker pode não entrar no cálculo. Worker com timeout maior que o resgate é reexecutado enquanto ainda roda.
- "Rollback não deixa job na fila": conte `river_job` direto, não por JOIN com a tabela de histórico (o JOIN zera junto).

## HTTP
- `chi/middleware.RealIP` (deprecado) prioriza `True-Client-IP`, que proxies comuns não removem: limite por IP contornável. Use extração do cabeçalho que o proxy reescreve ou XFF com proxies confiáveis. Teste com cabeçalho forjado.
- Upload grande: estender `ReadTimeout`/deadline de leitura sem ajustar `http.Server.WriteTimeout` corta a resposta.
- `netip.Addr.IsPrivate` inclui `fc00::/7` (onde fica o IMDS IPv6 de nuvem). Negue metadados antes; teste IPv6 e IPv4-mapeado (`Unmap`).

## Segredos e logs
- `fmt` só chama `String`/`Format` de campo se `CanInterface()`: campo não exportado de outra struct sai cru com `%+v`, e o `slog.TextHandler` usa `%+v`. Guarde o valor atrás de ponteiro e teste imprimindo a struct externa.
- Assinatura (SigV4, HMAC) refeita à mão para injetar relógio: use o assinador da biblioteca com relógio injetável.

## Configuração
- `caarlos0/env` v11: variável vazia com `envDefault` vira o default. `VAR=""` não desliga nada.
- `os.Hostname()` com erro ignorado como identidade de réplica: vazio ou repetido (`network_mode: host`).

## Testes
- Sinalização por canal: feche com `sync.OnceFunc` + `defer`, também no erro; rode com `go test -timeout` curto.
- Nada de `t.Fatal` (nem helper que o chame) dentro de callback de transação: o `Goexit` impede commit/rollback e o `pool.Close` do cleanup pendura a suíte inteira.
- `-run` casa por regex de nome e por pacote: confira na saída `-v` que o teste rodou (`RUN`/`PASS` por nome) e que todos os pacotes da prova estão no comando.
- Guarda AST que casa `x.Name == "pkg"` não vê alias de import e só varre o diretório passado.
