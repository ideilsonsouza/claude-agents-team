---
name: security-rust
description: "Segurança de Rust (axum, tokio, SQLite, gateway em Raspberry Pi): senha com Argon2id e migração de hash antigo, comparação em tempo constante (subtle), limite de tentativas por IP com ConnectInfo e mapa limitado, token com expiração, SSE sem token na URL, segredo mascarado na API de configuração, https obrigatório, instalador com manifesto SHA-256 e minisign-verify, cargo-deny/cargo-audit e systemd com usuário dedicado. Usar ao blindar, auditar ou revisar código Rust, install.sh ou a unit do serviço, mesmo que o pedido diga só 'segurança do gateway' ou 'login da UI local'."
---

# Blindagem em Rust

Referência verificada em **12/11/2026**: fonte das crates em `~/.cargo/registry/src` (argon2 0.6.0, password-hash 0.6.1, subtle 2.6.1, minisign-verify 0.3.0, axum 0.8.9, reqwest 0.12.28), crates.io, docs.rs, doc oficial do cargo-deny, cargo-audit e systemd. O que não foi verificado está marcado.
Base: `security-hardening` (OWASP, ASVS, segredos, runbook). Padrões da linguagem: `rust-standards`. Gateway (UI local, OTA, systemd): `edge-gateway` §6 e §8. Dependências e CI: `security-supply-chain`. Não repita o que essas skills já dizem; aqui está o que é específico de Rust.

## 1. Versões (crates.io, 12/11/2026)
| Crate | Versão | Nota |
|---|---|---|
| `argon2` / `password-hash` | 0.6.0 / 0.6.1 | `PasswordHash` agora é `password_hash::phc::PasswordHash`; o alias antigo está deprecated |
| `subtle` | 2.6.1 | `ConstantTimeEq`; estável, sem release desde 06/2024 |
| `minisign-verify` | 0.3.0 | sem dependências; verifica, não assina |
| `governor` / `tower_governor` | 0.10.4 / 0.8.0 | `tower_governor` 0.8.0 declara `axum ^0.8` (opcional) |
| `zeroize` / `secrecy` | 1.9.1 / 0.10.3 | `secrecy` sem release desde 10/2024 |
| `cargo-deny` / `cargo-audit` | 0.20.2 / 0.23.0 | |
`sha2` 0.11 existe; o código em campo pode estar em 0.10. A diferença de API entre as duas: não verificado, confira antes de subir.

## 2. Senha: Argon2id e migração do hash antigo
- `Argon2::default()` é Argon2id v19 com **m = 19456 KiB, t = 2, p = 1** (constantes `DEFAULT_*` em `params.rs`): o mínimo OWASP (`security-hardening` §5). `hash_password` gera o salt sozinho com a feature `getrandom` (padrão). O hash sai em PHC (`$argon2id$v=19$m=19456,t=2,p=1$...`).
- `verify_password` usa os parâmetros **do hash**, não os do `Argon2` configurado. Por isso o rehash é uma decisão sua: compare `Params::try_from(&parsed)` com os parâmetros atuais.
```rust
use argon2::{Argon2, Params, password_hash::{PasswordHasher, PasswordVerifier, phc::PasswordHash}};

fn verificar(senha: &[u8], guardado: &str) -> Result<(bool /*ok*/, bool /*rehash*/), Erro> {
    if guardado.starts_with("$argon2id$") {
        let ph = PasswordHash::new(guardado)?;
        let ok = Argon2::default().verify_password(senha, &ph).is_ok();
        let rehash = ok && Params::try_from(&ph).map(|p| p != Params::DEFAULT).unwrap_or(true);
        return Ok((ok, rehash));
    }
    // formato legado: compare em tempo constante (§3) e peça rehash se acertou
    let ok = legado_confere(senha, guardado);
    Ok((ok, ok))
}
```
- **Migração transparente** (ninguém é obrigado a trocar a senha, e o formato velho continua entrando): no login, o formato do valor guardado decide o caminho (`$argon2id$` = novo; qualquer outro = legado). Acertou no legado ⇒ calcule o Argon2id **da senha que acabou de ser digitada** e grave na mesma operação que cria a sessão. Nunca grave um hash legado para senha nova. Mantenha o caminho legado até que nenhuma linha use o formato antigo; só então remova, num PR próprio. Teste: banco com hash legado entra, é regravado em Argon2id e entra de novo.
- **Usuário inexistente gasta o mesmo tempo**: verifique contra um hash fixo gerado no boot. Sem isso, o tempo de resposta revela quais usuários existem.
- Argon2 usa ~19 MiB e CPU por tentativa. Rode em `spawn_blocking` e limite a concorrência com `tokio::sync::Semaphore` (poucos permits num Raspberry Pi): senão, N logins simultâneos esgotam a memória do dispositivo. O limite de tentativas (§4) vem **antes** do hash.
- Sem senha padrão e sem senha em argumento de linha de comando, log ou erro. Parâmetro de custo em constante nomeada; suba em PR próprio e o rehash no login faz o resto.

## 3. Comparação em tempo constante
- `subtle::ConstantTimeEq`: `bool::from(a.ct_eq(b))`. `==` em segredo, token, HMAC ou hash é defeito.
- **`ct_eq` em slices retorna na hora se os tamanhos diferem** (conferido em `subtle-2.6.1/src/lib.rs`). Para token, compare os **digests** (SHA-256 dos dois lados, 32 bytes fixos) ou garanta tamanho fixo. Guarde no banco o hash do token, nunca o token (então a comparação é de hash com hash).
- Senha não se compara com `ct_eq`: use `verify_password` (§2). HMAC: use `verify_slice` do `hmac` (já é constante).
- Teste de tempo estatístico em CI é frágil; revise o código e proíba `==` por lint de revisão (`rg '== .*(token|secret|hash|mac)'` no PR).

## 4. Limite de tentativas por IP (axum + ConnectInfo)
- IP do cliente = `ConnectInfo<SocketAddr>`, e só funciona se o servidor for criado com `app.into_make_service_with_connect_info::<SocketAddr>()` passado a `axum::serve` (fonte: `axum-0.8.9/src/routing/mod.rs:537`). Sem isso o extractor falha em tempo de execução, com 500.
- **Atrás de proxy** o IP do socket é o do proxy: todos os clientes viram um só e um atacante bloqueia todo mundo. Confie em `X-Forwarded-For` **só** se o IP do socket estiver numa lista de proxies confiáveis, e use o IP à direita da lista, não o primeiro. Gateway exposto direto na LAN: use o IP do socket.
- IPv6: chave pelo prefixo **/64**, senão um atacante gira endereços sem custo.
- **Mapa limitado** (o ponto fraco clássico: `HashMap<IpAddr, _>` sem teto é um vazamento de memória controlado pelo atacante):
```rust
struct Tentativas { falhas: u32, janela_ini: Instant, bloqueado_ate: Option<Instant> }
struct Limitador { mapa: Mutex<HashMap<IpAddr, Tentativas>>, max_chaves: usize /* ex.: 4096 */ }
// Na entrada: 1) remova expiradas se len >= max_chaves; 2) ainda cheio -> remova a mais antiga;
// 3) bloqueado_ate no futuro -> 429 com Retry-After. Falha de login -> falhas += 1; ao passar o limite,
// bloqueio com backoff exponencial e teto (ex.: 1 min -> 15 min). Sucesso -> remove a chave.
```
  - `std::sync::Mutex` basta (seção curta, sem `.await` com o lock preso); varredura de expiradas num `tokio::time::interval`, numa task com dono e token de cancelamento.
  - Conte **falhas**, não requisições, e bloqueie por IP, não só por conta: bloqueio só por conta deixa qualquer um travar o administrador.
  - Resposta: **429 + `Retry-After`**, mesma mensagem para usuário inexistente e senha errada.
- Alternativa pronta: `tower_governor` 0.8 (`PeerIpKeyExtractor` usa o IP do socket) sobre `governor`. O armazenamento por chave cresce: chame `retain_recent()` e `shrink_to_fit()` periodicamente (doc do `RateLimiter`, seção "Housekeeping"). Serve para limite de taxa geral; o bloqueio progressivo por falha de login continua sendo seu.

## 5. Token com expiração e SSE
- Token de sessão: 32 bytes do CSPRNG do SO (`getrandom` ou `OsRng`), em hex/base64url. Guarde **SHA-256 do token**, `criado_em`, `expira_em` (absoluto) e `ultimo_uso` (ocioso). Valide no servidor a cada requisição; logout e troca de senha revogam; varra os expirados. TTL curto para token de UI (horas, não meses).
- `EventSource` do navegador só aceita `withCredentials` (MDN), **não aceita cabeçalho**, e por isso muita UI põe o token na query string. Isso vaza em log de proxy, `journald`, histórico e `Referer` (CWE-598). Alternativas, da preferida para a de reserva:
  1. cookie `HttpOnly; Secure; SameSite=Strict` + `new EventSource(url, { withCredentials: true })`. O SSE é GET só de leitura; as rotas que alteram estado exigem checagem de `Origin`/token anti-CSRF;
  2. `fetch()` com `Authorization: Bearer` e leitura do `ReadableStream` (biblioteca de SSE sobre fetch ou código próprio);
  3. **ticket** de uso único (opaco, ≤ 30 s, amarrado à sessão e ao IP) obtido por `POST` autenticado e passado na query. Nunca o token de sessão.
- Em campo pode haver UI antiga falando o formato velho: aceite o antigo por prazo e atrás de flag, registre o uso e remova num PR depois (contrato só aditivo).
- `tower_http::trace::TraceLayer` registra a URI: redija a query (`make_span_with` próprio) ou não habilite o campo; nenhum token em `tracing`.

## 6. Segredo na API de configuração
- Tipo próprio para segredo (ou `secrecy::SecretString`): `Debug` imprime `***`, sem `Display`, e `Serialize` emite máscara fixa. O `GET` devolve a máscara (ou `{"definido": true}`); **nunca** o valor, nem a parte final.
- No `PUT`, máscara ou campo ausente = **manter o valor atual**; só valor novo troca. Sem isso, a UI que reenvia a configuração apaga o segredo.
- O segredo em disco: arquivo `0600` do usuário do serviço (ou `LoadCredential=` do systemd); nunca em argumento de linha de comando (aparece em `ps`) nem em variável que o processo filho herda sem necessidade. `zeroize` no que viver em memória.
- Teste: snapshot (`insta`) do JSON de `GET /config` não contém o segredo; `format!("{:?}", cfg)` também não.

## 7. https obrigatório, com exceção explícita
- Valide no boot a URL do servidor: esquema `https` ou **recuse**. Exceção só por chave de configuração com nome inequívoco (ex.: `permitir_http_inseguro = true`), registrada em `warn` a cada boot e exibida na UI. Loopback pode ficar isento, e isso deve estar escrito.
- `reqwest::ClientBuilder::https_only(true)` recusa `http` (inclusive após redirect). TLS com `rustls`; proibido `danger_accept_invalid_certs`/`danger_accept_invalid_hostnames`, nem em debug. Redirecionamento: limite e nunca para outro esquema.
- Mudar o padrão derruba quem hoje usa `http`: faça o aviso primeiro e imponha o padrão com migração (decisão do dono).

## 8. Instalador: manifesto SHA-256 assinado com minisign
- Fluxo: baixar → **verificar a assinatura do manifesto** → conferir o SHA-256 de cada arquivo contra o manifesto → só então instalar (`install -m`, troca atômica por `rename`). Assinatura ausente ou inválida = aborta, sem `--insecure`.
- `minisign-verify` 0.3 (conferido na fonte):
```rust
let pk = PublicKey::from_base64(CHAVE_PUBLICA)?;               // constante embutida no binário ou no installer
let sig = Signature::decode(&std::fs::read_to_string("manifest.json.minisig")?)?;
pk.verify(&manifest_bytes, &sig, false)?;                      // false = só aceita o modo prehashed
let trusted = sig.trusted_comment();                           // assinado: confira versão e alvo
```
  - `allow_legacy = false` rejeita assinatura legada (`UnexpectedAlgorithm`) e o `minisign` 0.12 assina em prehashed por padrão (`-l` é o legado). `key_id` diferente = `UnexpectedKeyId`. Arquivo grande: `verify_stream` (só prehashed).
  - O `untrusted comment` não é assinado: não decida nada com ele.
- No shell (`install.sh`): `minisign -V -H -P "<chave pública>" -m manifest.json` e `sha256sum -c`. A chave pública vai **embutida no script**, e o script chega por canal que o dono controla. `curl | sh` do mesmo servidor do pacote não protege contra quem invade o servidor: documente a limitação e publique a chave por outro canal.
- Manifesto traz versão, alvo (`aarch64`), tamanho e SHA-256; rejeite versão menor que a instalada (anti-downgrade). A chave privada de assinatura nunca vai ao repositório nem ao CI sem proteção (`security-supply-chain`, runbook de chave em `security-hardening`).
- `install.sh`: `set -euo pipefail`; `umask 077` ao criar segredo; `trap` para limpar o diretório temporário; nenhum segredo em argumento nem em `echo`.

## 9. Cadeia de suprimentos em Rust
- `Cargo.lock` versionado, `--locked` em CI e no instalador de dev. Atualize com `cargo update -p <crate>` e diff do lock revisado.
- `cargo deny check` com `deny.toml` (chaves conferidas na doc oficial):
```toml
[advisories]
yanked = "deny"                  # padrão é warn
[sources]
unknown-registry = "deny"        # padrão é warn
unknown-git = "deny"
allow-registry = ["https://github.com/rust-lang/crates.io-index"]
[licenses]
allow = ["MIT", "Apache-2.0", "BSD-3-Clause", "ISC", "Unicode-3.0"]   # ajuste à política
[bans]
multiple-versions = "warn"
```
  Em advisories, `vulnerability`, `notice` e `severity-threshold` foram removidos (dão erro): não copie `deny.toml` antigo. Toda exceção em `ignore` leva `reason` e, de preferência, `expiry`.
- `cargo audit` olha só RustSec: `cargo audit --file Cargo.lock`, e `cargo audit bin <binário>` (exato só se o binário foi feito com `cargo auditable`). Se `cargo-deny` já roda, `audit` é redundante; agende os dois **semanalmente**, porque advisory novo sai em código que não mudou. Flag para falhar em warning no `cargo audit`: não verificado.
- Crate nova: confira mantenedor, downloads, licença e `build.rs`/proc-macro (executam na sua máquina). Prefira o que já está na árvore.

## 10. systemd, usuário de serviço e permissões
- Usuário de sistema dedicado: `useradd --system --no-create-home --shell /usr/sbin/nologin <app>`. O serviço nunca roda como root nem como o usuário `pi`.
- Unit: `User=`/`Group=`, `StateDirectory=<app>` (cria `/var/lib/<app>` do usuário), `ConfigurationDirectory=<app>` (`/etc/<app>`, **não** é chown ao usuário: ajuste dono e modo no instalador), `UMask=0077`, `ProtectSystem=strict`, `ProtectHome=yes`, `PrivateTmp=yes`, `NoNewPrivileges=yes`, `CapabilityBoundingSet=` vazio, `RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX`, `SystemCallFilter=@system-service`, `MemoryMax=`, `Restart=always`. Porta abaixo de 1024: `AmbientCapabilities=CAP_NET_BIND_SERVICE` ou porta alta. Meça com `systemd-analyze security <unit>`.
- Permissões: diretórios `750`, arquivos de configuração com segredo e a chave `600`, banco SQLite `600` (o `-wal` e o `-shm` herdam o modo do diretório/umask: confira), dono = usuário do serviço; binário `755` de **root** (o serviço não pode sobrescrever o próprio executável).
- **`NoNewPrivileges=yes` e `sudo`:** com a opção, o serviço e seus filhos não ganham privilégio por `execve()` (setuid/setgid, capabilities de arquivo), segundo `systemd.exec(5)`. Logo `sudo`, `su` e helper setuid chamados **pelo serviço** deixam de funcionar. Se o gateway reinicia a si mesmo ou aplica atualização via `sudo systemctl ...`, isso quebra em campo na hora do OTA. Saídas, da melhor para a pior: (1) o serviço só grava o pedido e uma unit própria (`.path`/`.timer`, como root, mínima) aplica a atualização; (2) regra polkit estreita para `systemctl restart <app>`; (3) abrir mão de `NoNewPrivileges` com sudoers de **um** comando, sem curinga, e registrar a troca. Teste o fluxo de atualização com a unit endurecida antes de entregar.
- Teste de aceite: `systemd-analyze verify`, serviço sobe, `ls -l` e `stat -c '%a %U'` dos arquivos, e atualização/reinício de ponta a ponta.

## 11. Testes negativos que provam a blindagem
- Login: hash legado entra e é regravado; usuário inexistente leva o mesmo tempo de ordem de grandeza; N falhas do mesmo IP geram 429 com `Retry-After`; **mapa não passa de `max_chaves`** depois de milhares de IPs; IP diferente não é afetado; sucesso zera.
- Token expirado, revogado e de outro usuário: 401. SSE sem credencial: 401; URL com token antigo segue a política do §5. Log da requisição não contém token.
- `GET /config` sem segredo; `PUT` com máscara preserva; `http://` recusado no boot; flag de exceção emite o aviso.
- Instalador: manifesto adulterado, assinatura de outra chave, arquivo com SHA diferente e versão menor abortam sem instalar nada.
- Mutante: remova a guarda (limite, expiração, máscara) e confirme que o teste falha pela asserção esperada (`backend-pitfalls`).

## Checklist de PR (segurança Rust)
- [ ] Argon2id com PHC, rehash no login, hash legado aceito só para entrar; Argon2 fora do runtime (`spawn_blocking`) com limite de concorrência.
- [ ] Nenhum `==` em segredo/token/hash; digest de tamanho fixo no `ct_eq`.
- [ ] `into_make_service_with_connect_info` presente; mapa de tentativas com teto e varredura; política de proxy confiável escrita.
- [ ] Token: CSPRNG, hash no banco, expiração absoluta e ociosa, revogação. Nenhum token em URL, log ou `Debug`.
- [ ] Segredo mascarado no `GET` e preservado no `PUT`; arquivo `600`.
- [ ] `https_only`, sem `danger_accept_*`; exceção explícita e visível.
- [ ] Instalador: assinatura do manifesto antes de qualquer cópia, SHA-256 por arquivo, anti-downgrade, chave pública embutida.
- [ ] `Cargo.lock` no git, `cargo deny check` verde, `--locked`.
- [ ] Unit endurecida, usuário dedicado, permissões conferidas; fluxo de atualização testado com `NoNewPrivileges`.

## Fontes
- OWASP Password Storage Cheat Sheet (Argon2id 19 MiB/t=2/p=1) e RFC 9106: https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
- argon2 0.6.0 (docs e fonte): https://docs.rs/argon2/0.6.0/argon2/ ; password-hash 0.6.1: https://docs.rs/password-hash/0.6.1/
- subtle 2.6.1: https://docs.rs/subtle/2.6.1/subtle/
- axum 0.8 `ConnectInfo`: https://docs.rs/axum/0.8.9/axum/extract/struct.ConnectInfo.html
- governor (housekeeping do estado por chave): https://docs.rs/governor/0.10.4/governor/struct.RateLimiter.html ; tower_governor: https://docs.rs/tower_governor/0.8.0/
- MDN `EventSource` (só `withCredentials`): https://developer.mozilla.org/en-US/docs/Web/API/EventSource/EventSource ; CWE-598: https://cwe.mitre.org/data/definitions/598.html
- minisign-verify 0.3.0: https://docs.rs/minisign-verify/0.3.0/minisign_verify/ ; minisign: https://jedisct1.github.io/minisign/
- cargo-deny: https://embarkstudios.github.io/cargo-deny/checks/sources/cfg.html e .../advisories/cfg.html ; cargo-audit: https://github.com/rustsec/rustsec/tree/main/cargo-audit
- systemd.exec(5) (`NoNewPrivileges=`, `ProtectSystem=`, `StateDirectory=`, `ConfigurationDirectory=`): https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html
- Prática de campo (não oficial): bloqueio por IP /64 em IPv6, ticket de SSE de uso único e `X-Forwarded-For` pela direita são práticas consagradas de mercado, sem norma única; valide contra o proxy usado.
