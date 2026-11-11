---
name: rust-standards
description: Padrões para Rust 1.99 com edição 2024 — toolchain e MSRV (rust-toolchain.toml, rust-version, resolver 3), estrutura de crate e workspace com lints herdados, erros (thiserror em biblioteca, anyhow em binário), async com tokio (cancelamento e cancel safety, JoinSet, TaskTracker e CancellationToken, shutdown ordenado com SIGTERM, backpressure com canal limitado, spawn_blocking), axum 0.8, serde tolerante para contrato aditivo, configuração, SQLite com rusqlite ou sqlx (WAL, synchronous, migrations, durabilidade em queda de energia), tracing, testes (unitários, integração, proptest, insta, nextest, tempo pausado), clippy pedante seletivo, rustfmt, cargo-deny e cargo-audit, cross-compile para Raspberry Pi (cargo-zigbuild ou cross, gnu x musl, binário estático), perfil de release (lto, strip, panic=abort), unsafe e FFI com C/C++ (cxx, bindgen, cbindgen) e checklist de PR. Usar ao criar ou alterar código em projetos com Cargo.toml.
---

# Rust

Referência: **Rust 1.99.1** (estável, 15/10/2026) com **edição 2024** (estável desde a 1.85.0, 20/02/2025). O ciclo é de 6 semanas; a 1.100.0 deve sair por volta de 12/11/2026 (previsão pela cadência, não verificado). Fontes: blog.rust-lang.org/releases, posts da 1.85.0, 1.92.0, 1.98.0 e 1.99.0, doc.rust-lang.org/cargo e API do crates.io, verificados em 08/11/2026.
- Arquitetura do gateway de borda (fila local, uplink, atualização): `edge-gateway`. Tópicos e payload MQTT: `mqtt-contract`. Dependências e publicação: `security-supply-chain`.

## Versões de referência (crates.io, 08/11/2026)
| Área | Crate | Versão |
|---|---|---|
| Async | `tokio` / `tokio-util` / `bytes` | 1.54.1 / 0.7.20 / 1.12.1 |
| HTTP | `axum` / `tower-http` / `reqwest` | 0.8.9 / 0.7.1 / 0.13.5 |
| Serialização e config | `serde` / `config` | 1.0.229 / 0.15.27 (`figment` 0.10.19 está sem release desde 05/2024) |
| Erros | `thiserror` / `anyhow` | 2.0.21 / 1.0.104 |
| Logs | `tracing` / `tracing-subscriber` / `tracing-appender` | 0.1.44 / 0.3.23 / 0.2.5 |
| SQLite | `rusqlite` / `libsqlite3-sys` / `rusqlite_migration` / `sqlx` / `refinery` | 0.41.1 / 0.39.1 / 2.6.0 / 0.9.0 / 0.10.0 |
| Testes | `proptest` / `insta` / `mockall` / `cargo-nextest` | 1.12.0 / 1.49.0 / 0.15.0 / 0.9.151 |
| Qualidade | `cargo-deny` / `cargo-audit` / `cargo-machete` | 0.20.2 / 0.22.2 / 0.9.2 |
| Cross | `cargo-zigbuild` / `cross` | 0.24.1 / 0.2.5 no crates.io (de 02/2023; instale do git) |
| FFI | `cxx` / `autocxx` / `bindgen` / `cbindgen` | 1.0.205 / 0.30.0 / 0.73.2 / 0.29.4 |
| Industrial | `tokio-modbus` / `tokio-serial` / `serialport` / `async-opcua` | 0.17.0 / 5.5.0 / 4.10.1 / 0.19.0 (`opcua` 0.12 está parado desde 01/2024) |
| MQTT e desktop | `rumqttc` / `tauri` | 0.25.1 / 2.12.5 |
| Tempo | `jiff` | 0.2.40 |

Crate 0.x quebra API em toda minor: fixe a minor no `Cargo.toml` e leia o changelog antes de subir. Compatibilidade entre `tower-http` 0.7 e o `tower` usado pelo `axum` 0.8.9: não verificado, confira no `Cargo.lock` (duas versões de `tower` na árvore = incompatível).

## Toolchain, edição e MSRV
```toml
# rust-toolchain.toml (na raiz; o rustup instala sozinho)
[toolchain]
channel = "1.99.1"
components = ["rustfmt", "clippy"]
targets = ["aarch64-unknown-linux-gnu", "aarch64-unknown-linux-musl", "armv7-unknown-linux-gnueabihf"]
```
- Fixe a versão exata no binário (build reproduzível); suba de propósito, num PR próprio.
- **`rust-version`** no `[workspace.package]` declara o MSRV. Política padrão: **acompanhar a estável** em binário; em biblioteca publicada, "N-2" e escrita no README. Abaixo do MSRV o Cargo falha com erro claro; o lint `clippy::incompatible_msrv` acusa API nova demais.
- **Edição 2024** traz o resolver sensível ao `rust-version` (resolver 3 é o padrão nela; declare `resolver = "3"` no workspace). Mudanças que afetam o código:
  - `unsafe extern "C" { ... }` e atributos inseguros (`#[unsafe(no_mangle)]`, `#[unsafe(export_name = "...")]`);
  - `std::env::set_var` e `remove_var` passam a ser `unsafe` (configure tudo antes de criar threads ou o runtime);
  - `unsafe_op_in_unsafe_fn` avisa; referência a `static mut` é negada;
  - escopo de temporários em `if let` e em expressão final mudou (locks soltos antes);
  - captura de lifetime em `impl Trait` de retorno; `gen` virou palavra reservada;
  - closures assíncronas (`async || {}`, traits `AsyncFn*` no prelude).
- Migração de edição: `cargo fix --edition`, depois troque `edition = "2024"` e rode testes. As correções automáticas são conservadoras; revise o diff.
- Novidades recentes úteis: 1.92 emite unwind tables mesmo com `panic=abort` (backtrace funciona); 1.98 traz `format_into` em inteiros e `str::strip_circumfix`; 1.99 permite **definir** funções variádicas C em Rust (`VaList`) e estabiliza `Vec::into_parts`/`from_parts` e `fs::set_times`.

## Estrutura de workspace
```
Cargo.toml              # [workspace], resolver = "3", [workspace.package|dependencies|lints]
rust-toolchain.toml  deny.toml  .cargo/config.toml
crates/
  app/                  # binário fino: main, config, wiring, anyhow
  core/                 # domínio puro, sem I/O (fácil de testar)
  store/                # SQLite local (fila, estado)
  driver-modbus/        # um crate por protocolo, atrás de um trait do core
  uplink/               # envio ao servidor (HTTP/MQTT)
  ffi/                  # único lugar com unsafe e bindings C/C++
```
```toml
[workspace.dependencies]
tokio = { version = "1.54", features = ["rt-multi-thread", "macros", "signal", "time", "sync"] }
[workspace.lints.rust]
unsafe_code = "forbid"          # o crate ffi sobrescreve para "deny" com allow local
[workspace.lints.clippy]
pedantic = { level = "warn", priority = -1 }
module_name_repetitions = "allow"
missing_errors_doc = "allow"
must_use_candidate = "allow"
unwrap_used = "warn"
undocumented_unsafe_blocks = "deny"
```
- Cada membro: `[lints] workspace = true` e dependências com `{ workspace = true }`.
- Crates pequenos por fronteira (protocolo, armazenamento, uplink), não por camada técnica. `main.rs` mínimo; lógica em `lib.rs` para ser testável.
- Features aditivas; nunca uma feature que remove comportamento.

## Erros
- **Biblioteca: `thiserror` 2** com enum por fronteira; o chamador consegue fazer `match`.
```rust
#[derive(Debug, thiserror::Error)]
pub enum ReadError {
    #[error("timeout lendo {addr} após {after:?}")]
    Timeout { addr: u16, after: std::time::Duration },
    #[error("exceção Modbus {0:?}")]
    Exception(tokio_modbus::ExceptionCode),
    #[error(transparent)]
    Io(#[from] std::io::Error),
}
```
- **Binário: `anyhow`** com `.context("abrir fila local")?` em cada borda de I/O; `main` devolve `anyhow::Result<()>`.
- Nada de `unwrap`/`expect` em caminho de produção. `expect("invariante: ...")` só no boot ou quando a invariante é provada no código.
- Erro transitório (timeout, conexão) x permanente (payload inválido): o retry trata só o transitório. Leitura inválida vai para quarentena com motivo, não derruba o laço.

## Async com tokio
- **Runtime:** `#[tokio::main]` multi-thread no serviço; `flavor = "current_thread"` em dispositivo com 1 a 2 núcleos ou memória curta. Nunca bloqueie o runtime: I/O síncrono (rusqlite, serial síncrono, CPU pesada) vai em `tokio::task::spawn_blocking` ou numa thread dedicada com canal.
- **Toda task tem dono e saída.** Use `JoinSet` para tasks irmãs (`join_next` propaga panic e erro; ao dropar, aborta todas) ou `TaskTracker` + `CancellationToken` (`tokio-util`) para serviços longos.
- **Cancelamento = drop do future no `.await`.** Em `tokio::select!`, só use ramos *cancel safe* (`mpsc::Receiver::recv`, `CancellationToken::cancelled`, `sleep`). `read_exact`, `write_all` e escrita em lote no SQLite não são: rode-os numa task própria ou mantenha o future fora do laço (`tokio::pin!`).
- **Backpressure:** `tokio::sync::mpsc::channel(N)` limitado entre leitor de equipamento → gravador da fila → uplink. `send().await` espera quando enche. `unbounded_channel` é proibido em caminho de dados. `try_send` com descarte só para dado não crítico, com contador de descarte em métrica.
- **Timeout em todo I/O externo:** `tokio::time::timeout(dur, fut)`; retry com backoff exponencial e jitter, numa camada só.
- **Shutdown ordenado com SIGTERM:**
```rust
#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let cfg = config::load().context("config")?;
    let token = CancellationToken::new();
    let tracker = TaskTracker::new();
    let (tx, rx) = tokio::sync::mpsc::channel(1024);
    tracker.spawn(reader::run(cfg.reader, tx, token.child_token()));   // para de ler
    tracker.spawn(store::writer(rx, cfg.db));                          // termina quando o canal fecha
    tracker.spawn(uplink::run(cfg.uplink, token.child_token()));
    tracker.close();

    let mut term = signal(SignalKind::terminate())?;
    tokio::select! { _ = term.recv() => {}, _ = tokio::signal::ctrl_c() => {} }
    token.cancel();                                                     // 1. leitores e uplink param
    if tokio::time::timeout(Duration::from_secs(15), tracker.wait()).await.is_err() {
        tracing::warn!("shutdown excedeu 15 s");                        // 2. gravador drena e faz commit
    }
    Ok(())
}
```
  - O gravador não recebe o token: ele termina quando todos os `Sender` são dropados, depois de gravar o que estava no canal.
  - O tempo total cabe no `TimeoutStopSec` do systemd (ou no `stop_grace_period` do contêiner).

## axum, serde e configuração
- **axum 0.8:** rotas com `/{id}` (a sintaxe `/:id` é da 0.7), `axum::serve(listener, app).with_graceful_shutdown(token.cancelled_owned())`. Limite de corpo (`DefaultBodyLimit`), timeout por camada (`tower-http`) e `State` com `Arc` de dependências. Porta de diagnóstico do gateway só em `127.0.0.1` ou rede de gestão.
- **serde e contrato aditivo** (o servidor e o dispositivo evoluem em tempos diferentes):
  - campo novo: `Option<T>` com `#[serde(default, skip_serializing_if = "Option::is_none")]`;
  - **não** use `deny_unknown_fields` em mensagem que vem do servidor (leitor tolerante); use só em arquivo de configuração local, para pegar erro de digitação;
  - enum recebido tem variante `#[serde(other)] Unknown`;
  - teste de snapshot (`insta`) do JSON enviado trava o formato.
- **Configuração:** `struct Config` com `Deserialize`, carregada de TOML (`/etc/<app>/config.toml`) + env com prefixo, via `config` 0.15 ou `toml` + `serde` direto. Valide no boot e falhe cedo. Segredo em arquivo `0600` ou `LoadCredential=` do systemd, nunca em argumento de linha de comando.
- Tempo: `ts` de origem em UTC (`jiff::Timestamp` ou `SystemTime`); intervalos e timeouts com `Instant` (monotônico; o relógio do dispositivo pode pular no NTP).

## SQLite local (fila e estado)
- **rusqlite** (síncrono, feature `bundled`: compila o SQLite junto, sem depender da versão do alvo; facilita o cross) é o padrão no dispositivo. Uma conexão de escrita numa thread dedicada ou via `spawn_blocking`. **sqlx 0.9** quando o serviço já é todo async e quer queries checadas em compilação (`sqlx::migrate!`); o modo offline (`.sqlx/`) precisa estar no repositório para o cross-build.
- **PRAGMAs na abertura de toda conexão** (o SQLite não guarda a maioria):
```sql
PRAGMA journal_mode = WAL;        -- persiste no arquivo
PRAGMA synchronous = FULL;        -- fila de leituras: commit sobrevive a queda de energia
PRAGMA busy_timeout = 5000;
PRAGMA foreign_keys = ON;         -- padrão é OFF
PRAGMA journal_size_limit = 67108864;
```
  - Pela doc do SQLite, WAL + `NORMAL` **não corrompe**, mas o último commit **pode voltar atrás** após queda de energia; WAL + `FULL` é durável. Use `NORMAL` só para dado que pode ser relido do equipamento.
- **Lote em transação:** grave N leituras por `BEGIN IMMEDIATE ... COMMIT` (ex.: a cada 1 s ou 500 linhas). Commit por leitura gasta o cartão SD e derruba o throughput.
- **Fila durável:** linha com `id` crescente, `device_id`, `seq`, `ts`, `payload`, `attempts`. Sai da fila **só depois do ack** do servidor (`DELETE ... WHERE id <= ?` na mesma transação que marca o envio). O servidor deduplica por `(device_id, seq)`.
- **Disco cheio e retenção:** limite de linhas ou de bytes, política escrita (descartar a mais antiga com contador e log), `PRAGMA wal_checkpoint(TRUNCATE)` periódico. `SQLITE_FULL` não derruba o processo.
- **Migrations:** `rusqlite_migration` (versiona por `user_version`) ou `refinery`. Só aditivas (`ADD COLUMN` com default, tabela nova), testadas sobre um arquivo criado pela versão anterior (fixture em `tests/fixtures/`). Firmware antigo pode voltar no rollback: a versão antiga precisa abrir o banco migrado.
- Corrupção: `PRAGMA quick_check` no boot; se falhar, renomeie o arquivo para `*.corrupt-<ts>`, recrie e alerte. Nunca apague silenciosamente.

## Logs com tracing
- `tracing-subscriber` com `EnvFilter` (`RUST_LOG`) e formato JSON em serviço; `#[tracing::instrument(skip(conn), fields(device_id))]` nas bordas.
- No dispositivo, escreva em **stdout/journald** (limite de tamanho no `journald.conf`) em vez de arquivo no SD. Se precisar de arquivo: `tracing-appender` com rotação e `non_blocking`, guardando o `WorkerGuard` até o fim do `main` (senão perde as últimas linhas).
- Sem segredo, token ou dado pessoal em log. Leitura com erro em `warn` com amostragem; não registre cada leitura em `info`.

## Testes
- **Unitários** no próprio módulo (`#[cfg(test)]`); **integração** em `tests/` usando a API pública do crate.
- **Tempo:** `#[tokio::test(start_paused = true)]` (feature `test-util`) para timeout, retry e lote sem `sleep` real.
- **`proptest`** em decodificação de registradores, parsers de protocolo e roundtrip `serialize → deserialize`. Fuzz (`cargo fuzz`, nightly) em parser de bytes vindos da rede ou da serial.
- **`insta`** (`assert_json_snapshot!`, `cargo insta review`) trava o payload enviado ao servidor: snapshot mudou = contrato mudou.
- **Hardware simulado:** servidor Modbus de teste do `tokio-modbus` na mesma task de teste; serial com par de pseudo-terminais (`socat -d -d pty,raw,echo=0 pty,raw,echo=0`, PID guardado). Teste de queda: mate o processo no meio de um lote e confira que nada se perdeu nem duplicou.
- `cargo nextest run` no CI (isola cada teste em processo); `cargo test --doc` à parte, porque o nextest não roda doctests.
- Banco de teste em `tempfile::TempDir`, apagado no fim. Serviços externos seguem a regra de serviços locais do `CLAUDE.md`.

## Qualidade e segurança
- `cargo fmt --check` com `rustfmt.toml` mínimo (`style_edition = "2024"`); `cargo clippy --all-targets --all-features -- -D warnings` com o pedante seletivo do workspace.
- **`cargo deny check`** no CI (advisories RustSec, licenças permitidas, crates banidos, duplicatas, fontes só do crates.io). `cargo audit` cobre só advisories: use-o se não houver `cargo-deny`. `cargo machete` aponta dependência sem uso.
- `Cargo.lock` versionado (binário e biblioteca). Builds no CI com `--locked`.
- TLS com `rustls` (evita OpenSSL no cross e no musl); confira o nome da feature de TLS na versão do `reqwest` em uso.

## Cross-compile para Raspberry Pi
| Placa / SO | Target | Observação |
|---|---|---|
| Pi 3/4/5, Zero 2 W com SO 64 bits | `aarch64-unknown-linux-gnu` ou `-musl` | Padrão |
| Pi 2/3/4 com SO 32 bits (armhf) | `armv7-unknown-linux-gnueabihf` | Use `cross` |
| Pi 1 e Zero (ARMv6) | `arm-unknown-linux-gnueabihf` | Legado |

- **`cargo-zigbuild`** (sem contêiner) é o padrão para `aarch64`: `cargo zigbuild --release --target aarch64-unknown-linux-gnu.2.31`. O sufixo fixa a **glibc mínima**; use a do SO mais antigo em campo (`ldd --version` no alvo). Ele não reconhece `armv7-unknown-linux-gnueabihf` e não faz glibc estática.
- **`cross`** para `armv7`, testes sob QEMU (`cross test`) e dependências C com sysroot: `cargo install cross --git https://github.com/cross-rs/cross` (a release do crates.io é de 2023). Exige Docker ≥ 20.10 e sobe contêiner de build efêmero: confirme que o ambiente permite. Configuração em `Cross.toml`.
- **Binário estático:** target `*-musl` (com `rusqlite` `bundled` e `rustls`, sai sem dependência dinâmica; confira com `file` e `ldd`). O alocador do musl é lento com muitas threads: meça e, se pesar, use outro alocador global.
- `-C target-cpu` só se todo dispositivo em campo tiver a CPU; senão gera `Illegal instruction`.

## Perfil de release
```toml
[profile.release]
lto = "fat"            # "thin" se o build ficar lento demais
codegen-units = 1
panic = "abort"        # menor e sem unwind; panic em qualquer task derruba o processo
strip = "symbols"
opt-level = 3          # "s" ou "z" se o tamanho importar mais que a CPU
```
- Com `panic = "abort"`, o supervisor (systemd `Restart=always`, contêiner com restart) reinicia o processo, e a fila precisa estar consistente (WAL + `FULL`). Não use `catch_unwind` como controle de fluxo.
- Guarde no CI o binário com símbolos (ou `split-debuginfo`) da mesma build para analisar crash; no dispositivo vai o stripado.
- Meça o tamanho com `cargo bloat` (não verificado na versão) antes de trocar `opt-level`.

## unsafe e FFI com C/C++
- `unsafe` só no crate `ffi`, cada bloco com `// SAFETY:` explicando a invariante (`clippy::undocumented_unsafe_blocks`). Teste o crate com Miri (`cargo +nightly miri test`) quando possível.
- **C++ → `cxx`** (bridge segura com `#[cxx::bridge]` e `cxx-build` no `build.rs`): `String`, `Vec`, `UniquePtr` e exceções mapeadas para `Result`. `autocxx` 0.30 ainda é pré-1.0.
- **Cabeçalho C → `bindgen`** (exige libclang; no cross, aponte o sysroot do alvo). Gere no `build.rs` ou versione o binding gerado por target. **Rust → C:** `cbindgen` com `extern "C"` e `#[unsafe(no_mangle)]`.
- Regras de fronteira: nenhum panic atravessa FFI (use `extern "C-unwind"` só se o outro lado espera unwind); posse explícita (quem aloca libera); ponteiro nulo checado; tipos `#[repr(C)]`.

## Checklist de PR (Rust)
- [ ] `fmt`, `clippy -D warnings`, testes e `cargo deny check` verdes; `Cargo.lock` atualizado de propósito.
- [ ] Cross-build do alvo em release verde; tamanho do binário conferido.
- [ ] Sem `unwrap`/`expect` em caminho de produção; erros com contexto; tipos de erro em biblioteca.
- [ ] Toda task com dono e saída; canais limitados; I/O bloqueante fora do runtime; timeout em todo I/O externo.
- [ ] `select!` só com ramos cancel safe; SIGTERM testado com lote em andamento sem perda nem duplicata.
- [ ] Contrato com o servidor só aditivo; snapshot do payload revisado; leitor tolerante a campo novo.
- [ ] Migration do SQLite local aditiva e testada sobre banco da versão anterior; PRAGMAs aplicados na abertura.
- [ ] `unsafe` só no crate FFI, com `// SAFETY:` e teste.
- [ ] Logs sem segredo nem dado pessoal; sem log por leitura em `info`.
- [ ] Nenhum binário rodado em hardware real sem pedido; o que foi simulado está no relatório.
