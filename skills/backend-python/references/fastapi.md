# FastAPI (referência da skill backend-python)

Conferido em **10/11/2026**: fastapi.tiangolo.com (release notes até 0.162.4; tutoriais de SQL, dependências, SSE, testes async, deployment e proxy), docs.sqlalchemy.org/en/21 (asyncio e migração 2.0→2.1), alembic.sqlalchemy.org (cookbook e autogenerate).
Versões: FastAPI 0.162.4, Starlette ≥1.0, Pydantic 2.14.3, SQLAlchemy 2.1.8, Alembic 1.20.1, psycopg 3.3.8, uvicorn 0.54.0, httpx 0.28.1.

## 1. O que mudou desde 0.115 (código de memória quebra aqui)
| Versão | Mudança | O que fazer |
|---|---|---|
| 0.118 / 0.121 | Código após o `yield` da dependência roda **depois** da resposta. `Depends(dep, scope="function")` encerra antes da resposta; `"request"` é o padrão | Commit explícito no serviço, nunca no teardown |
| 0.122 | Classes de segurança sem credencial devolvem **401** (era 403) | Ajuste testes e contrato |
| 0.125 / 0.129 | Sem Python 3.8 e 3.9 | Python 3.14 |
| 0.126 / 0.128 | Sem Pydantic v1 e sem `pydantic.v1`; mínimo `pydantic>=2.9` (0.135.2) | Só API da v2 |
| 0.129.2 | Pacote `fastapi-slim` removido | `fastapi` ou `fastapi[standard]` |
| 0.130 | Com tipo de retorno ou `response_model`, o JSON é serializado pelo Pydantic (Rust) | Declare sempre o tipo de saída |
| 0.131 | `ORJSONResponse` e `UJSONResponse` depreciados | Não use |
| 0.132 | `strict_content_type`: corpo JSON exige `Content-Type` JSON | Cliente manda `application/json`; desligar só com motivo |
| 0.133 | Starlette 1.0 | APIs removidas do Starlette 0.x não existem mais |
| 0.134 / 0.135 | Streaming JSON Lines e **SSE nativo** (`fastapi.sse`) | Sem `sse-starlette` em código novo |
| 0.137 | `router.routes` deixa de ser lista plana; `include_router` não copia rotas | Use `iter_route_contexts()` (0.137.2) para inspecionar rotas |
| 0.142 / 0.143 | OpenTelemetry nativo; auto-configuração do exporter é opt-in (`FASTAPI_OTEL_AUTO_CONFIGURE=true` ou `FastAPI(telemetry={"auto_configure": True})`) | Alinhe com `observability` |
| 0.146 | `root_path` no construtor depreciado | Flag `--root-path` do servidor |
| 0.148 | Default omitido de `Query`/`Header`/`Cookie`/`Form` não é validado | `validate_default=True` se precisar |
| 0.151 | No `Body`, `null` é diferente de omitido; tipo não anulável rejeita `null` mesmo com default | Modele `X | None` quando `null` for válido |
| 0.155 | `**extra` em `Path`/`Query`/`Body`/... removido (`TypeError`) | `json_schema_extra={...}` |
| 0.160 | `extra` de parameter model vale para todos os campos do mesmo local | `extra="forbid"` rejeita campo de outra dependência |
| 0.162 | `bool` omitido em formulário não vira `False` | Declare `= False` para checkbox |

## 2. App, lifespan e engine
```python
# src/app/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    configure_logging(s.log_level)
    engine = create_async_engine(
        str(s.database_url),            # postgresql+psycopg://...
        pool_size=s.db_pool_size, max_overflow=0, pool_pre_ping=True,
    )
    app.state.sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    yield
    await engine.dispose()

def create_app() -> FastAPI:
    s = get_settings()
    docs = "/docs" if s.expose_docs else None
    app = FastAPI(lifespan=lifespan, docs_url=docs, redoc_url=None,
                  openapi_url="/openapi.json" if docs else None)
    app.include_router(pedidos_api.router, prefix="/v1")
    register_error_handlers(app)
    return app

app = create_app()
```
- **SQLAlchemy 2.1:** instale `sqlalchemy[asyncio]` (o greenlet não vem mais por padrão); exige Python ≥ 3.11; `postgresql://` passa a usar psycopg 3; autoflush roda também antes de `text()` e Core.
- `pool_size × réplicas` dentro do orçamento de conexões (`postgres-scaling`). `max_overflow=0` mantém a conta previsível.
- `statement_timeout` por role no Postgres (`architecture-scalability`).

## 3. Models, sessão e dependências
```python
# src/app/db.py
from collections.abc import AsyncIterator
from typing import Annotated
from fastapi import Depends, Request
from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    metadata = MetaData(naming_convention={
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    })

async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.sessionmaker() as session:
        yield session                     # fechar sem commit = rollback

SessionDep = Annotated[AsyncSession, Depends(get_session)]
```
```python
# src/app/pedidos/models.py
class Pedido(Base):
    __tablename__ = "pedidos"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(index=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    itens: Mapped[list["Item"]] = relationship(back_populates="pedido", lazy="raise")
```
```python
# src/app/pedidos/service.py
async def criar_pedido(session: AsyncSession, tenant_id: UUID, data: PedidoIn) -> Pedido:
    pedido = Pedido(tenant_id=tenant_id, **data.model_dump())
    session.add(pedido)
    await session.flush()                 # gera id; erro de constraint aparece aqui
    await session.refresh(pedido)         # carrega valores do servidor (criado_em)
    await session.commit()                # antes da resposta
    return pedido

async def listar(session: AsyncSession, tenant_id: UUID) -> list[Pedido]:
    stmt = (select(Pedido).where(Pedido.tenant_id == tenant_id)
            .options(selectinload(Pedido.itens)).order_by(Pedido.id))
    return list((await session.scalars(stmt)).all())
```
- **`async with session.begin()`** falha com "transaction already begun" se algo já usou a sessão na requisição (autobegin, por exemplo uma dependência de auth que consultou o banco). Prefira `commit()` explícito no fim do serviço.
- **Lazy load em async** levanta `MissingGreenlet`. `lazy="raise"` no relacionamento e carga explícita (`selectinload` para coleção, `joinedload` para muitos-para-um).
- Trava: `select(...).with_for_update(skip_locked=True)`. Upsert idempotente: `sqlalchemy.dialects.postgresql.insert(...).on_conflict_do_nothing(index_elements=[...]).returning(...)` (quem decide "criei x já existia" é o `RETURNING`, ver `backend-pitfalls` §2).
- Uma `AsyncSession` por requisição ou tarefa; nunca compartilhe entre tarefas concorrentes.

## 4. Rotas, validação e resposta
```python
router = APIRouter(prefix="/pedidos", tags=["pedidos"])

class PedidoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    criado_em: AwareDatetime

class Filtro(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Status | None = None
    limit: int = Field(default=50, ge=1, le=200)

@router.post("", status_code=201)
async def criar(body: PedidoIn, session: SessionDep, user: CurrentUser) -> PedidoOut:
    return PedidoOut.model_validate(await service.criar_pedido(session, user.tenant_id, body))

@router.get("")
async def listar(f: Annotated[Filtro, Query()], session: SessionDep, user: CurrentUser) -> list[PedidoOut]:
    ...
```
- Tipo de retorno em toda rota: é allowlist da saída e ativa a serialização em Rust.
- Limite de corpo e upload no proxy (Traefik) **e** na aplicação; o FastAPI não limita corpo por padrão.
- Paginação por cursor e formato de erro: `backend-standards`.
- SSE:
```python
from fastapi.sse import EventSourceResponse, ServerSentEvent

@router.get("/eventos", response_class=EventSourceResponse)
async def eventos() -> AsyncIterable[ServerSentEvent]:
    yield ServerSentEvent(data=item, event="pedido", id=str(seq))
```
- `BackgroundTasks` só para trabalho descartável (morre com o processo). O que não pode se perder vai para a fila (Celery, `references/django.md` §9; ou outbox).

## 5. Erros RFC 9457
```python
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

PROBLEM = "application/problem+json"

class DomainError(Exception):
    status = 422
    type_ = "about:blank"
    title = "Regra de negócio violada"
    def __init__(self, detail: str) -> None:
        self.detail = detail

def problem(status: int, title: str, detail: str | None = None, type_: str = "about:blank", **ext: object) -> JSONResponse:
    body = {"type": type_, "title": title, "status": status, **ext}
    if detail:
        body["detail"] = detail
    return JSONResponse(body, status_code=status, media_type=PROBLEM)

def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def _schema(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [{"pointer": "/" + "/".join(map(str, e["loc"][1:])), "detail": e["msg"]} for e in exc.errors()]
        return problem(400, "Requisição inválida", errors=errors)   # regra da equipe: schema = 400

    @app.exception_handler(DomainError)
    async def _domain(_: Request, exc: DomainError) -> JSONResponse:
        return problem(exc.status, exc.title, exc.detail, exc.type_)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        resp = problem(exc.status_code, str(exc.detail))
        if exc.headers:
            resp.headers.update(exc.headers)      # ex.: WWW-Authenticate no 401
        return resp

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception) -> JSONResponse:
        log.exception("erro_nao_tratado")
        return problem(500, "Erro interno")                         # sem traceback
```
- Registre o handler do `HTTPException` **do Starlette** (pega também o 404/405 de rota inexistente) e preserve os headers dele.
- Documente os erros na rota (`responses={400: {...}, 404: {...}}`) para o OpenAPI sair com `application/problem+json`.

## 6. Autenticação e autorização
```python
bearer = HTTPBearer(auto_error=False)

async def get_current_user(cred: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> Principal:
    if cred is None:
        raise HTTPException(401, "Não autenticado", headers={"WWW-Authenticate": "Bearer"})
    claims = decode_jwt(cred.credentials)        # pyjwt com algorithms explícito (security-python §8)
    return Principal(user_id=claims["sub"], tenant_id=UUID(claims["tid"]), roles=claims.get("roles", []))

CurrentUser = Annotated[Principal, Depends(get_current_user)]

def require_role(role: str):
    async def _check(user: CurrentUser) -> None:
        if role not in user.roles:
            raise HTTPException(403, "Sem permissão")
    return Depends(_check)

admin_router = APIRouter(dependencies=[require_role("admin")])
```
- **Autorização por recurso** na query do serviço (`where tenant_id = :t`); recurso de outro tenant = **404**.
- Cookie de sessão exige proteção CSRF; CORS com origens explícitas (`security-python` §9).

## 7. Alembic
```bash
uv run alembic init -t async migrations
uv run alembic revision --autogenerate -m "cria pedidos"   # revise à mão: rename vira drop+add
uv run alembic check                                       # CI: falha se o model divergir das migrations
uv run alembic upgrade head                                # etapa do deploy, nunca no lifespan
```
- No `env.py`: `target_metadata = Base.metadata` e URL lida de `config.get_main_option("sqlalchemy.url")` ou, se vazia, de `get_settings()` (o teste injeta a URL do banco temporário).
- A migration é do `dba` (revisão, expand/contract, `CREATE INDEX CONCURRENTLY` fora de transação): `sql-standards`.

## 8. Testes
```python
# tests/conftest.py
import asyncio, os, uuid
from collections.abc import AsyncIterator
import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

@pytest.fixture(scope="session")
async def engine() -> AsyncIterator[AsyncEngine]:
    admin_url = make_url(os.environ["TEST_DATABASE_ADMIN_URL"])   # postgresql+psycopg://.../postgres
    name = f"test_<projeto>_{uuid.uuid4().hex[:8]}"               # nome gerado aqui: seguro no SQL
    admin = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    async with admin.connect() as c:
        await c.execute(text(f'CREATE DATABASE "{name}"'))
    url = admin_url.set(database=name).render_as_string(hide_password=False)
    eng = create_async_engine(url)
    try:
        cfg = Config("alembic.ini")
        cfg.set_main_option("sqlalchemy.url", url)
        await asyncio.to_thread(command.upgrade, cfg, "head")    # env.py async usa asyncio.run: outra thread
        yield eng
    finally:
        await eng.dispose()
        async with admin.connect() as c:
            await c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        await admin.dispose()

@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with engine.connect() as conn:
        trans = await conn.begin()
        s = AsyncSession(bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint")
        try:
            yield s                              # commit do serviço vira savepoint
        finally:
            await s.close()
            await trans.rollback()               # nada persiste entre testes

@pytest.fixture
async def client(session: AsyncSession) -> AsyncIterator[AsyncClient]:
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
```
- `AsyncClient` **não** dispara o lifespan. Se o teste precisar dele, use `LifespanManager` (pacote `asgi-lifespan`) ou o `TestClient` síncrono como context manager.
- `pytest-asyncio` com `asyncio_mode = "auto"` e loops em escopo de sessão (pyproject do núcleo). Não misture com o plugin do anyio no mesmo teste.
- Casos negativos obrigatórios: sem token (401), papel errado (403), recurso de outro tenant (404), campo extra (400), `Content-Type` errado.
- Para conferir a limpeza: `psql -c "\l"` filtrando `test_<projeto>_` ao terminar.

## 9. Execução
- **Contêiner:** um processo uvicorn por contêiner, sem `--workers`; escala por réplica (doc do FastAPI, "FastAPI in Containers").
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips=<faixa do proxy>
```
- `--forwarded-allow-ips="*"` só se **apenas** o proxy alcança o contêiner (rede interna do Swarm); senão, a faixa do proxy (`security-python` §10).
- Sem orquestrador (VM): `uvicorn --workers N` ou `fastapi run --workers N`. Gunicorn não é necessário para FastAPI. Se o projeto já usa gunicorn: a versão atual tem worker ASGI nativo (`gunicorn app.main:app --worker-class asgi`, `gunicorn.workers.gasgi.ASGIWorker`, desde a 24.0; doc do gunicorn, 2026-11-10); o `UvicornWorker` não faz parte do gunicorn (vem de pacote externo).
- Worker de fila é outro serviço/entrypoint. Celery executa tarefas síncronas: use `Session` síncrona (psycopg) no worker em vez de criar um loop async por tarefa.
