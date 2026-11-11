---
name: backend-python
description: "Padrões para backend em Python 3.14 com uv: estrutura, pyproject, pyright/mypy, ruff, pytest com banco real, Pydantic 2, logs, config por env, Docker non-root, portão e armadilhas. FastAPI e Django em references/. Usar ao criar ou alterar código Python de backend."
---

# Python (backend)

Versões e APIs conferidas em **10/11/2026** nas fontes oficiais: endoflife.date (Python, Django), feeds de release do PyPI, docs.astral.sh/uv, fastapi.tiangolo.com (release notes e docs), docs.sqlalchemy.org/en/21, docs.djangoproject.com/en/6.1, mypy changelog, docs do pyright, README do django-stubs, structlog.org, pytest-asyncio e pytest-django.
- **Segurança** (pip-audit, bandit, desserialização, SSRF, JWT, hardening de imagem): `security-python`. Não repetida aqui.
- API, erros RFC 9457, paginação, authz: `backend-standards`. Defeitos recorrentes: `backend-pitfalls`. Banco: `sql-standards` e `postgres-scaling`. uv a fundo: `uv`. Telemetria: `observability`. Testes: `test-strategy`.

## Referências (ler sob demanda)
- `references/fastapi.md` — **ler antes de tocar em projeto FastAPI**: mudanças 0.115→0.162 que quebram código antigo, app/lifespan, dependências, SQLAlchemy 2.1 async + Alembic, erros RFC 9457, auth, testes com httpx, workers.
- `references/django.md` — **ler antes de tocar em projeto Django**: 6.1 x 5.2 LTS, settings por env, ORM (N+1, transações, `select_for_update`), migrations, Django Ninja x DRF, async, pytest-django, Celery.

## Versões (consulta em 10/11/2026)
| Peça | Versão | Observação |
|---|---|---|
| Python | **3.14.10** (padrão de produção); 3.15.2 | 3.10 em fim de vida desde 01/10/2026; 3.11 até 10/2027 |
| uv | 0.13.7 | pré-1.0: fixe a versão no CI e na imagem |
| ruff | 0.17.4 | lint + format (substitui black, isort, flake8) |
| pyright | 1.1.414 | via PyPI `pyright[nodejs]` |
| mypy | 2.4.1 | só em Django, com `django-stubs` 6.1.2 |
| pytest | 9.2.0 | pytest-asyncio 1.4.1 |
| Pydantic | 2.14.3 | pydantic-settings 2.16.2 |
| structlog | 26.1.0 | |
| psycopg | 3.3.8 | driver Postgres padrão do SQLAlchemy 2.1 |
| httpx | 0.28.1 | a 1.0 só existe como `dev`: não use |
| FastAPI / uvicorn | 0.162.4 / 0.54.0 | `references/fastapi.md` |
| SQLAlchemy / Alembic | 2.1.8 (2.0.57 ainda mantida) / 1.20.1 | |
| Django | 6.1.3; **5.2.19 LTS** até 04/2028 | 6.2 LTS prevista para 04/2027 |
| Django Ninja / DRF | 1.8.0 / 3.18.3 | |
| pytest-django / Celery / gunicorn | 4.14.0 / 5.7.0 / 27.0.0 | |

Fixe a mesma versão do Python em `.python-version`, `requires-python` e no `FROM` do Dockerfile.

## 1. uv e pyproject
```bash
uv init --package <nome>          # layout src/, com build system
uv python pin 3.14
uv add "fastapi[standard]" "sqlalchemy[asyncio]" psycopg pydantic-settings structlog
uv add --dev ruff pyright pytest pytest-asyncio
uv sync --locked                  # falha se o uv.lock estiver desatualizado (CI e imagem)
uv run pytest                     # sempre via uv run, nunca o python do sistema
uv lock --check                   # portão: lock em dia com o pyproject
uv lock --upgrade-package <pacote>
```
- `uv.lock` é versionado. Dependência de dev no `[dependency-groups]` (PEP 735), não em `optional-dependencies`.
- `--locked` confere o lock; `--frozen` usa o lock **sem** conferir (só na primeira camada do Dockerfile, antes de copiar o projeto).
```toml
[project]
requires-python = ">=3.14"

[tool.ruff]
target-version = "py314"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "W", "I", "UP", "B", "S", "ASYNC", "DTZ", "T20", "PTH", "SIM", "RUF"]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["S101"]

[tool.pytest]                      # pytest ≥ 9: tipos nativos do TOML (ini_options ainda vale)
testpaths = ["tests"]
addopts = ["-ra", "--strict-markers", "--strict-config"]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "session"
asyncio_default_test_loop_scope = "session"
```
- `ASYNC` acusa chamada bloqueante dentro de `async def`; `DTZ` acusa `datetime` sem fuso; `S` é o bandit (ver `security-python`).
- O loop em escopo de sessão evita o erro "attached to a different loop" quando o engine async é fixture de sessão.

## 2. Estrutura
```
src/<app>/
  main.py            # monta a app (FastAPI) | config/ (Django: settings, urls, asgi, wsgi)
  config.py          # Settings (pydantic-settings), carregada uma vez
  logging.py         # configuração do structlog
  db.py              # engine e sessão (FastAPI)
  <dominio>/         # api.py (rotas), service.py (regra), repo.py (queries), schemas.py, models.py
tests/{conftest.py, unit/, integration/}
migrations/          # Alembic (FastAPI) | <app>/migrations (Django)
```
- **Pacote por domínio**, não por camada técnica. A rota é fina: valida, chama o serviço, serializa. O serviço não importa nada do framework web.
- Clientes (banco, Redis, HTTP) nascem no `lifespan` (FastAPI) ou sob demanda (Django), **nunca na importação do módulo**.
- Um entrypoint por papel (`api`, `worker`), cada um com seu serviço no orquestrador (`architecture-scalability`).

## 3. Tipagem: pyright ou mypy
**Decisão da equipe:**
- **pyright** (`typeCheckingMode = "strict"` em projeto novo; `"standard"` em legado, subindo aos poucos) para FastAPI, workers e bibliotecas. Motivos: rápido, inferência melhor, entende o `dataclass_transform` do Pydantic e do SQLAlchemy sem plugin, e é o mesmo motor do editor (Pylance).
- **mypy** (`strict = true`) + `django-stubs` em **projeto Django**. Motivo: o django-stubs só tem suporte completo no mypy, via plugin (tipos de campos, managers e querysets); no pyright o suporte é "básico" (README do django-stubs).
- **ty** (Astral, 0.0.100): ainda 0.0.x. Pode rodar como informativo, **não** como portão.
```toml
[tool.pyright]
include = ["src", "tests"]
pythonVersion = "3.14"
typeCheckingMode = "strict"
```
- Em strict, as regras só podem ser **endurecidas** por arquivo. `# pyright: ignore[regra]` e `# type: ignore[code]` sempre com a regra e o motivo.
- **Sem `Any` na borda de entrada:** todo dado externo passa por um modelo Pydantic.

## 4. Pydantic 2 e configuração por ambiente
```python
from functools import lru_cache
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, PostgresDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APP_", extra="forbid")
    database_url: PostgresDsn
    redis_url: str
    jwt_secret: SecretStr            # não aparece em repr nem em log
    log_level: str = "INFO"
    db_pool_size: int = Field(default=5, ge=1, le=50)

@lru_cache
def get_settings() -> Settings:
    return Settings()                # falha no boot se faltar variável: fail fast

class PedidoIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    cliente_id: int
    entrega_em: AwareDatetime       # rejeita datetime sem fuso
```
- **DTO separado** para entrada e saída (`PedidoIn`, `PedidoOut`); nunca devolva o model do ORM direto.
- `model_validate(obj)` e `model_dump(mode="json")`. Os métodos da v1 (`.dict()`, `parse_obj`, `class Config`) não entram em código novo.
- Dinheiro em `Decimal`, nunca `float`.
- **Config só por variável de ambiente.** `.env` apenas no desenvolvimento local, fora do git e da imagem. Segredos como `SecretStr`, lidos com `.get_secret_value()` no ponto de uso.

## 5. Logs estruturados
```python
import logging, structlog

def configure_logging(level: str) -> None:
    structlog.configure(
        cache_logger_on_first_use=True,
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level)),
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.format_exc_info,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
    )

log = structlog.get_logger()
log.info("pedido_criado", pedido_id=p.id, tenant_id=t)   # chave=valor, nunca f-string
```
- Por requisição: `structlog.contextvars.bind_contextvars(request_id=..., tenant_id=...)` num middleware e `clear_contextvars()` no início de cada requisição.
- **Não use `dict_tracebacks`** em produção: ele inclui as variáveis locais dos frames, onde pode haver segredo ou dado pessoal.
- Sem senha, token, CPF nem e-mail completo no log (LGPD, ver `observability`). JSON em stdout; quem coleta é o Loki/agent.

## 6. Testes
- **pytest** com fixtures em `conftest.py`. Unitário para regra pura; integração com **banco real**; contrato da API contra o OpenAPI (`backend-standards`).
- **Sem mock de banco nem de ORM.** Mock só para dependência externa: `httpx.MockTransport` para HTTP de saída.
- **Banco de teste** (ver `~/.claude/CLAUDE.md`, seção Serviços locais): Postgres local da máquina com o usuário de teste; no CI, o serviço da esteira. Nunca crie container.
  - Uma fixture de **sessão** cria `test_<projeto>_<id>`, aplica as migrations reais e **apaga o banco no `finally`**, mesmo com falha. Código em `references/fastapi.md` e `references/django.md`.
  - Isolamento por teste: transação revertida no fim de cada teste.
  - Redis: banco lógico próprio (1 a 15), limpo só ele.
- Credenciais do banco de teste vêm do ambiente (`TEST_DATABASE_ADMIN_URL`), nunca do repositório.
- `hypothesis` em parser de entrada não confiável. Teste de autorização cruzada (tenant A x B) é obrigatório (`test-strategy`, `backend-pitfalls`).
- Tempo controlado: receba um `clock`/`now` por parâmetro; não durma no teste.

## 7. Imagem (non-root)
```dockerfile
FROM python:3.14-slim-trixie AS build
COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0
WORKDIR /app
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-dev --no-install-project --no-editable
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --no-editable

FROM python:3.14-slim-trixie
RUN useradd --uid 65532 --no-create-home app
ENV PATH="/app/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONSAFEPATH=1
COPY --from=build --chown=65532:65532 /app/.venv /app/.venv
USER 65532
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```
- `--no-editable` faz o `.venv` independer do código-fonte: a imagem final copia **só o `.venv`**. Fixe a imagem do uv por versão (ou digest).
- Flags de proxy, limites, rootfs read-only e `cap_drop`: `security-python` §10–11. Healthcheck: `python -c` com `urllib` contra `/health/live` (a slim não tem curl).
- **Uma réplica = um processo** (sem `--workers` dentro do contêiner); escale por réplica no Swarm.

## 8. Portão (rode antes de entregar)
```bash
uv lock --check
uv sync --locked
uv run ruff format --check .
uv run ruff check .
uv run pyright                    # FastAPI, workers, libs
uv run mypy .                     # projeto Django (django-stubs)
uv run pytest                     # unit + integração com banco real
uv run alembic check              # FastAPI/SQLAlchemy: models x migrations
uv run python manage.py makemigrations --check --dry-run   # Django
uv run python manage.py check --deploy                     # Django (settings de produção)
```
Mais `pip-audit` e `bandit` (`security-python`). Comando que não existe no projeto: diga isso no relatório, não invente.

## 9. Armadilhas
1. **Bloqueio dentro de `async def`**: `requests`, `time.sleep`, driver síncrono, ORM do Django ou CPU pesada congelam o loop inteiro. Use biblioteca async, `asyncio.to_thread` ou declare a rota como `def` (o FastAPI roda `def` num threadpool). CPU pesada vai para o worker.
2. **Sessão de banco por requisição ou por tarefa**: nunca global, nunca compartilhada entre tarefas concorrentes (`asyncio.gather` com a mesma `AsyncSession` é bug).
3. **Commit depois da resposta**: no FastAPI, o código após o `yield` de uma dependência roda **depois** de a resposta sair (escopo padrão `"request"`). Faça o commit explícito no serviço (`await session.commit()`), nunca no teardown da dependência.
4. **N+1**: em SQLAlchemy async o lazy load estoura `MissingGreenlet`; use `selectinload`/`joinedload` e `lazy="raise"`. Em Django, `select_related`/`prefetch_related` e `fetch_mode(FETCH_RAISE)` nos testes (6.1).
5. **Fuso horário**: `datetime.utcnow()` está depreciado e devolve datetime ingênuo. Use `datetime.now(UTC)`, coluna `timestamptz`, `USE_TZ = True` no Django e `AwareDatetime` no Pydantic. Banco em UTC; fuso local só na apresentação.
6. **Migrations**: o schema é do `dba`. O backend propõe a mudança do model; a migration é revisada e assinada pelo `dba` (`sql-standards`, expand/contract). Migration **nunca roda no boot das réplicas**: é uma etapa do deploy.
7. **Job enfileirado antes do commit** lê dado que ainda não existe. Django: `delay_on_commit` ou `transaction.on_commit`; SQLAlchemy: depois do commit, ou outbox (`architecture-scalability`). Argumento de job é id/JSON, nunca objeto do ORM.
8. **Job não idempotente**: com `acks_late`, a mensagem volta se o worker morrer. Projete para executar duas vezes sem efeito duplicado (chave de idempotência, `ON CONFLICT`).
9. **Cliente criado na importação** (engine, Redis, httpx) quebra com fork (`gunicorn --preload`) e em teste. Crie no lifespan e feche no shutdown.
10. **httpx sem timeout explícito**: o padrão é 5 s, mas defina por chamada; `requests` não tem timeout padrão (`security-python` §7).
11. **Default mutável** (`def f(x=[])`) e estado global mutável entre requisições.
12. **`--reuse-db` do pytest-django** deixa o banco de teste para trás: proibido na máquina compartilhada.
13. **`except Exception: pass`** e traceback para o cliente: `security-python` §12.

## Checklist de PR (Python)
- [ ] Portão verde (ruff, pyright/mypy, pytest, migrations conferidas).
- [ ] Entrada validada por Pydantic com `extra="forbid"`; saída por DTO explícito.
- [ ] Nada bloqueante em `async def`; timeout em toda chamada externa.
- [ ] Queries sem N+1; transação explícita; commit antes da resposta.
- [ ] Datas com fuso (UTC); dinheiro em `Decimal`.
- [ ] Testes de integração com banco real e caso negativo de autorização; banco de teste apagado ao terminar.
- [ ] Logs estruturados sem segredo nem PII.
- [ ] Migration revisada pelo `dba`; job idempotente e enfileirado depois do commit.
