---
name: security-python
description: Segurança de Python (FastAPI, Django, Flask, workers) — versões suportadas, uv com hashes, pip-audit, ruff/bandit/semgrep, desserialização insegura, injeção e SSTI, path traversal e tarfile, SSRF, criptografia e JWT, produção no FastAPI/Django, runtime e imagem non-root. Usar ao blindar, auditar ou revisar código Python.
---

# Blindagem em Python

Fontes verificadas em **23/10/2026**: docs.python.org (tarfile, pickle, subprocess, secrets, ssl),
PEP 578/706/740/751, docs.astral.sh/uv, pypa/pip-audit, OWASP Cheat Sheets, endoflife.date/python.
Base: `security-hardening`. Dependência e CI: `security-supply-chain`.
Padrões de API, authz e senha: `backend-standards`. Ferramental do uv: `uv`.

## 1. Versão
| Linha | Atual | Situação |
|---|---|---|
| 3.15 | 3.15.1 | mais nova |
| **3.14** | **3.14.9** | padrão seguro para produção |
| 3.13 / 3.12 / 3.11 | 3.13.17 / 3.12.15 / 3.11.17 | suportadas |
| **3.10** | 3.10.22 | **fim de vida em 01/10/2026 — sem correção de segurança** |

Se algum serviço ainda roda 3.10 ou anterior, **isso é o item nº 1 da blindagem**: não há patch.
Fixe a versão em `.python-version`, `requires-python` e no `FROM` do Dockerfile, no mesmo valor.

## 2. Dependência (o elo mais frágil do ecossistema)
`pip`/`uv` **não têm `--ignore-scripts`**: instalar **sdist** executa `setup.py` na sua máquina.
```bash
uv sync --frozen                       # instala exatamente o uv.lock (CI e imagem)
uv add --frozen <pacote>               # avalie antes: mantenedores, último release, transitivas
uv export --format requirements-txt --no-emit-project > requirements.lock
pip install --require-hashes --no-deps --only-binary :all: -r requirements.lock
pip-audit -r requirements.lock         # ou pip-audit (lê pylock.toml/pyproject)
osv-scanner scan source -r .
```
- **Só wheel** (`--only-binary :all:`) onde der; quando precisar de sdist, saiba qual pacote e por quê.
- `--require-hashes` exige grafo completo pinado com `==` — lock incompleto falhar é o comportamento
  correto.
- **PEP 740**: atestação diz *qual workflow publicou*, não que é seguro — e **nem pip nem uv
  verificam isso na instalação**. Use como sinal ao revisar o diff do lock.
- Reprodutibilidade/cooldown: `uv lock --exclude-newer 2026-10-16` resolve "como estava na data".
  Não existe `minimumReleaseAge` no PyPI — revise release muito recente no PR.
- Índice privado: mantenha o default `first-index` do uv. Fallback para o PyPI público abre
  **dependency confusion**.

## 3. Ferramentas e portões de CI
```bash
ruff check .                                    # inclua as regras S (flake8-bandit)
bandit -r src/ -ll                              # severidade média+
semgrep --config p/python --config p/secrets --error --metrics=off
pip-audit -r requirements.lock
```
```toml
# pyproject.toml
[tool.ruff.lint]
select = ["E", "F", "S", "B", "ASYNC", "T20", "PTH"]   # S = segurança; B = bugbear
[tool.ruff.lint.per-file-ignores]
"tests/**" = ["S101"]                                   # assert é esperado em teste
```
`ruff` com `S` cobre a maior parte do bandit e é instantâneo; mantenha o `bandit` no CI para o que
ele pega melhor (uso de crypto fraca, `subprocess` com `shell=True`). `# noqa: S...` sempre com
motivo escrito.
Tipagem estrita (mypy/pyright) reduz bug, **mas não é controle de segurança**: `Any` na borda de
entrada esconde exatamente o que precisa de validação.

## 4. Desserialização (A08 — o clássico de RCE em Python)
**`pickle` é execução de código arbitrário, por design.** Nunca desserialize de rede, banco
compartilhado, upload, cache não confiável ou arquivo de usuário:
`pickle`, `marshal`, `shelve`, `dill`, `joblib.load`, `numpy.load(allow_pickle=True)`,
`torch.load` sem `weights_only=True`, `pandas.read_pickle`.
- Formato de dado para troca: **JSON** (ou msgpack/protobuf). Para cache/fila, JSON também — o
  custo de serializar é menor que um RCE.
- YAML: **`yaml.safe_load`** sempre. `yaml.load` sem `Loader=SafeLoader` instancia objeto arbitrário.
- XML: **`defusedxml`** (billion laughs, XXE, external entity). A stdlib `xml.etree` não protege.
- Assinatura em dado serializado que precisa voltar do cliente: HMAC com `compare_digest` — e ainda
  assim prefira id opaco + estado no servidor.

## 5. Injeção e execução
```python
subprocess.run(["/usr/bin/ffmpeg", "-i", src, dst], check=True, timeout=30, shell=False)
```
- **`shell=True` com entrada do usuário é RCE.** Use lista de argumentos e caminho absoluto;
  `os.system`/`os.popen` não entram em código novo. `shlex.quote` é último recurso, não solução.
- `eval`, `exec`, `compile`, `__import__` com entrada do usuário: não. Nem com "sanitização".
- SQL: só parâmetro — `cur.execute("... WHERE id = %s AND tenant_id = %s", (id, tenant))`.
  No SQLAlchemy, `text()` com `bindparams`, nunca f-string. Em Django, `raw()`/`extra()` com
  parâmetro e identificador por allowlist.
- **SSTI**: `Environment(autoescape=True)` no Jinja2 e **nunca** `Template(string_do_usuário)` —
  template vindo do usuário dá acesso a `__class__`/`__subclasses__` e viram RCE.
- Mass assignment: Pydantic com `model_config = ConfigDict(extra="forbid")` e DTO explícito;
  Django `ModelForm` com `fields = [...]` explícito (nunca `__all__`).
- Log: não interpole entrada do usuário sem sanitizar quebra de linha.

## 6. Arquivo, arquivo compactado e caminho
```python
base = Path("/app/uploads").resolve()
target = (base / user_name).resolve()
if not target.is_relative_to(base):          # 3.9+
    raise ValueError("fora da base")
```
- `tarfile.extractall(filter="data")` **explícito** — o default virou `data` só na 3.14 e houve
  sequência de CVEs (CVE-2024-12718, CVE-2025-4330/4517 e correções em 2026). Passar explícito dá
  comportamento igual em toda versão, **mas não substitui patch**: mantenha o patch em dia e
  desconfie de arquivo de terceiro.
- `zipfile`: valide cada `namelist()` (zip-slip), limite tamanho descomprimido e número de entradas
  (zip bomb).
- `tempfile.mkstemp`/`TemporaryDirectory`, nunca `mktemp`. Nome de arquivo salvo é gerado pelo
  servidor; valide tipo pelo conteúdo, não pela extensão.

## 7. HTTP de saída e SSRF
```python
r = httpx.get(url, timeout=httpx.Timeout(5.0), follow_redirects=False)
# requests NÃO tem timeout por default — omitir trava o worker para sempre
r = requests.get(url, timeout=(3, 10), allow_redirects=False)
```
URL vinda do usuário: allowlist de esquema e host, **resolva o DNS e rejeite IP privado, loopback e
link-local (169.254.169.254)**, sem seguir redirect, timeout curto.
Nunca `verify=False` — carregue a CA interna em `verify="/caminho/ca.pem"`.

## 8. Criptografia
- Senha: **`argon2-cffi`** com Argon2id (`PasswordHasher(time_cost=2, memory_cost=19456,
  parallelism=1)`), `verify()` + `check_needs_rehash()` no login. `pwdlib` se quiser abstração;
  **`passlib` está sem manutenção ativa** — evite em projeto novo. `hashlib.scrypt` é a alternativa
  da stdlib (N=2**17, r=8, p=1).
- Token, código e senha temporária: **`secrets`** (`token_urlsafe(32)`), nunca `random`
  (Mersenne Twister é previsível).
- Comparação de segredo/HMAC: `hmac.compare_digest`. Nunca `==`.
- Simétrico: `cryptography` (`AESGCM`, `ChaCha20Poly1305`, ou `Fernet` para o caso simples) com
  nonce único. Nada de `pycrypto` (abandonado) nem modo ECB.
- `md5`/`sha1` só para checksum não-segurança — e com `usedforsecurity=False` para não acusar no
  bandit/FIPS.
- JWT: `pyjwt` com `algorithms=["ES256"]` **sempre explícito** em `jwt.decode` (confusão de
  algoritmo) e validação de `iss`/`aud`/`exp`.
- TLS: `ssl.create_default_context()` (verifica cadeia e hostname); nunca
  `ssl._create_unverified_context` nem `CERT_NONE`.

## 9. Configuração de produção
**FastAPI**
- `docs_url=None, redoc_url=None, openapi_url=None` em produção (ou atrás de auth e rede interna).
- `CORSMiddleware` com `allow_origins` explícito; nunca `["*"]` com `allow_credentials=True`.
- `response_model` em toda rota (allowlist de saída) e Pydantic com `extra="forbid"` na entrada.
- Limite de upload no proxy **e** na aplicação; `python-multipart` atualizado (foi fonte de DoS).
- Exceção: handler global devolvendo Problem Details sem traceback; `debug=False`.
**Django**
```bash
python manage.py check --deploy          # portão de CI
```
`DEBUG = False`; `SECRET_KEY` do ambiente (vazar = forjar cookie de sessão e token assinado);
`ALLOWED_HOSTS` explícito; `SECURE_HSTS_SECONDS`, `SECURE_SSL_REDIRECT`,
`SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_CONTENT_TYPE_NOSNIFF`,
`X_FRAME_OPTIONS = "DENY"`; `CSRF_TRUSTED_ORIGINS` explícito; nunca servir mídia de usuário do
mesmo host sem `Content-Disposition`/`nosniff`.
Atualize o Django no **patch da linha LTS** — as releases de segurança são frequentes.

## 10. Runtime e processo
```bash
python -I -P -m uvicorn app.main:app --host 127.0.0.1 --port 8000 \
  --proxy-headers --forwarded-allow-ips 10.0.0.0/8 \
  --limit-concurrency 200 --limit-max-requests 10000 --timeout-keep-alive 75
```
- **`-I`** (isolado: ignora env var do usuário e `sys.path[0]`) e **`-P`/`PYTHONSAFEPATH=1`**
  (não põe o diretório do script no `sys.path`) fecham o sequestro de import por arquivo plantado —
  especialmente em script que processa diretório não confiável.
- `--forwarded-allow-ips` **só** com a faixa do proxy: `*` deixa qualquer um falsificar o IP de
  origem (e com ele o rate limit).
- Bind em `127.0.0.1` ou socket Unix quando o proxy está no mesmo host.
- Audit hooks (PEP 578, `sys.addaudithook`) servem para detectar `subprocess`, `socket.connect` e
  `exec` inesperados em serviço de alto valor — instrumentação, não controle de acesso.
- systemd (appliance/VPS): `User=`, `NoNewPrivileges=yes`, `ProtectSystem=strict`,
  `ProtectHome=yes`, `PrivateTmp=yes`, `ReadWritePaths=` mínimo,
  `RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX`, `MemoryMax=`.

## 11. Imagem
```dockerfile
FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS build
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY . .
RUN uv sync --frozen --no-dev

FROM python:3.14-slim
RUN useradd -u 65532 -m app
ENV PATH="/app/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONSAFEPATH=1
WORKDIR /app
COPY --from=build --chown=65532:65532 /app /app
USER 65532
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```
`.dockerignore` com `.env`, `.git`, `*.pem`, `.venv`, `__pycache__`.
Runtime: read-only rootfs + tmpfs em `/tmp`, `cap_drop: ALL`, `no-new-privileges`, limites.
Sem pip/compilador na imagem final.

## 12. Falha e erro (A10)
- Nunca `except:` nem `except Exception: pass`. Capture o tipo onde o erro nasce; handler global só
  como rede de segurança.
- Recurso em `with`/`finally`: arquivo, conexão, lock, cliente HTTP, sessão do ORM.
- Transação: `with transaction.atomic()` / `async with session.begin()` — rollback completo, nunca
  compensação parcial.
- Nada de traceback para o cliente; log com `requestId` e `redact` de `authorization`, `password`,
  `token`, CPF e e-mail completo (LGPD — ver `observability`).
- Timeout em **toda** chamada externa (HTTP, banco, broker, fila) e `statement_timeout` no Postgres.
- `asyncio`: função síncrona bloqueante no loop (`requests`, `time.sleep`, CPU) congela o serviço
  inteiro — é DoS auto-infligido. Use `asyncio.to_thread` ou cliente async.

## 13. Testes de segurança
- **Authz cruzado obrigatório**: usuário/tenant A pedindo recurso de B → 404.
- Entrada hostil por rota: campo extra (deve ser rejeitado por `extra="forbid"`), id de outro
  tenant, payload no limite, string com `../`, `{{7*7}}` em campo que vai para template.
- `hypothesis` como fuzzer em parser de entrada não confiável (CSV, payload de dispositivo, decoder).
- Caminho de falha: simule Postgres/Redis indisponíveis (porta fechada ou host inválido; nunca derrube serviço compartilhado) → nega, sem traceback, sem recurso preso.
- `pip-audit`, `ruff check`, `bandit` e `manage.py check --deploy` no CI e em schedule semanal.
