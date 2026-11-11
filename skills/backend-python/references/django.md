# Django (referência da skill backend-python)

Conferido em **10/11/2026**: docs.djangoproject.com/en/6.1 (release notes 6.0 e 6.1, async, bancos), djangoproject.com/download (suporte e LTS), docs do Django Ninja (via Context7), pytest-django (banco), Celery 5.7 (what's new, Django, configuração, tasks), README do django-stubs e do django-tasks.
Versões: Django 6.1.3 e 5.2.19 LTS, Django Ninja 1.8.0, DRF 3.18.3, pytest-django 4.14.0, django-stubs 6.1.2, Celery 5.7.0, gunicorn 27.0.0, psycopg 3.3.8.

## 1. Qual versão
| Linha | Suporte | Quando usar |
|---|---|---|
| **6.1** (Python 3.12–3.15) | até 12/2027 | Projeto novo; migre para a **6.2 LTS** (prevista para 04/2027, suporte até 04/2030) |
| **5.2 LTS** (última com Python 3.10/3.11) | até 04/2028 | Projeto que já está nela ou que não acompanha upgrade anual (ex.: on-premise) |
| 6.0 | até 04/2027 | Suba para 6.1 |

- Depois da 6.2, as versões viram ano: **Django 2028** (01/2028). `RemovedInDjango70Warning` virou `RemovedInDjango2028Warning`.
- Atualize sempre o **patch** da linha: saem correções de segurança com frequência.
- **6.0:** Python ≥ 3.12; `DEFAULT_AUTO_FIELD` padrão = `BigAutoField`; framework de Tasks (`django.tasks`); CSP nativo (`SECURE_CSP`); template partials; remoção de coluna sem `CASCADE`.
- **6.1:** *fetch modes* (`FETCH_ONE`, `FETCH_PEERS`, `FETCH_RAISE`); `on_delete=DB_CASCADE`/`DB_SET_NULL`/`DB_SET_DEFAULT` (no banco, **sem** sinais); `MAILERS`; Postgres ≥ 15, MySQL ≥ 8.4, MariaDB ≥ 10.11; `first()`/`last()` não reordenam por PK depois de `order_by()`; depreciados `select_related()` sem argumentos e `values_list(flat=True)` sem campo.

## 2. Estrutura e settings por ambiente
```
src/
  config/{settings.py, urls.py, api.py, asgi.py, wsgi.py, celery.py}
  pedidos/{models.py, services.py, api.py, schemas.py, tasks.py, admin.py, migrations/, tests/}
manage.py
```
- **Um `settings.py`** que lê o ambiente; sem `settings/dev.py`/`prod.py` divergindo. Regra de negócio em `services.py`; view/endpoint fino; `models.py` sem chamada externa.
```python
# config/settings.py
class Env(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DJANGO_", extra="ignore")
    secret_key: SecretStr
    debug: bool = False
    allowed_hosts: list[str] = []          # JSON na env: '["api.exemplo.com"]'
    db_host: str; db_name: str; db_user: str; db_password: SecretStr; db_port: int = 5432
    db_test_name: str | None = None        # test_<projeto>_<id>, gerado pela execução de teste
    redis_url: str

env = Env()
SECRET_KEY = env.secret_key.get_secret_value()
DEBUG = env.debug
ALLOWED_HOSTS = env.allowed_hosts
USE_TZ = True
TIME_ZONE = "UTC"
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "HOST": env.db_host, "PORT": env.db_port, "NAME": env.db_name,
        "USER": env.db_user, "PASSWORD": env.db_password.get_secret_value(),
        "CONN_HEALTH_CHECKS": True,
        "OPTIONS": {"pool": {"min_size": 1, "max_size": 5}},   # requer psycopg[pool]; CONN_MAX_AGE fica 0
        "TEST": {"NAME": env.db_test_name},
    }
}
```
- Com o pool do psycopg, **`CONN_MAX_AGE` tem de ser 0**; vida da conexão por `max_lifetime` no pool.
- PgBouncer em *transaction pooling*: `"DISABLE_SERVER_SIDE_CURSORS": True` e sem pool no Django.
- `max_size × réplicas × processos` dentro do orçamento de conexões (`postgres-scaling`).
- Segurança de produção (`check --deploy`, HSTS, cookies, CSRF): `security-python` §9.

## 3. ORM
**N+1**
```python
pedidos = (Pedido.objects.filter(tenant_id=t)
           .select_related("cliente")                       # FK/1:1 → JOIN
           .prefetch_related(Prefetch("itens", queryset=Item.objects.order_by("id"))))
```
- `select_related("campo")` sempre com campo (sem argumento está depreciado na 6.1). `prefetch_related` para reverso e M2M.
- **6.1:** `Pedido.objects.fetch_mode(models.FETCH_RAISE)` levanta `FieldFetchBlocked` em acesso preguiçoso; use em teste e em caminho quente. `FETCH_PEERS` é um prefetch sob demanda (duas queries no total).
- `only()`/`defer()` criam N+1 quando o campo adiado é lido no loop.
- Teste que trava a contagem: `django_assert_num_queries(n)` (pytest-django).

**Transações e concorrência**
```python
from django.db import transaction
from django.db.models import F

@transaction.atomic
def debitar(conta_id: int, tenant_id: UUID, valor: Decimal) -> None:
    conta = Conta.objects.select_for_update().get(pk=conta_id, tenant_id=tenant_id)
    if conta.saldo < valor:
        raise SaldoInsuficiente()
    Conta.objects.filter(pk=conta.pk).update(saldo=F("saldo") - valor)
    notificar_debito.delay_on_commit(conta.pk)          # só enfileira se o commit acontecer
```
- `select_for_update()` só dentro de `atomic` e o queryset tem de ser avaliado lá dentro. Opções: `nowait`, `skip_locked` (fila de trabalho), `of=("self",)` com joins, `no_key=True` quando não muda chave.
- `ATOMIC_REQUESTS` fica desligado; transação explícita no serviço.
- `get_or_create`/`update_or_create` só são seguros com **`UniqueConstraint`** no banco; sem ela, corrida gera duplicata.
- Contador e saldo com `F()` no `update()`, nunca ler-somar-salvar em Python.
- `bulk_create(objs, batch_size=1000, update_conflicts=True, unique_fields=[...], update_fields=[...])` para lote idempotente; não chama `save()` nem sinais.
- Constraints no `Meta`: `UniqueConstraint(fields=[...], name=...)` e `CheckConstraint(condition=Q(...), name=...)`.
- **Tenant em toda query**: manager com `for_tenant(t)`; nunca `get(pk=...)` sem o tenant. SQL bruto só com parâmetros (`security-python` §5).

## 4. Migrations
- `makemigrations` gera a partir do model; o **`dba` revisa e assina** (`sqlmigrate <app> <numero>` mostra o SQL). `sql-standards` para expand/contract e locks.
- CI: `manage.py makemigrations --check --dry-run`.
- Índice em tabela grande: `django.contrib.postgres.operations.AddIndexConcurrently` com `atomic = False` na `Migration`.
- Migração de dados: `RunPython(forward, reverse)` com `apps.get_model(...)` (nunca importe o model), em lotes.
- Remover campo em dois deploys (`SeparateDatabaseAndState`): o código para de usar → depois a coluna sai.
- `migrate` é etapa do deploy; nunca no entrypoint das réplicas.

## 5. API: Django Ninja (decisão da equipe)
**Django Ninja 1.8 em API nova.** Motivos: usa Pydantic 2 (mesmos DTOs e modelo mental do FastAPI), gera OpenAPI, suporta views e paginação async, e exige menos código que serializers.
**DRF 3.18** quando o projeto já usa DRF ou depende do ecossistema dele (filtros, browsable API, permissões por objeto prontas). Não misture os dois no mesmo projeto sem ADR.
Risco do Ninja: comunidade menor e manutenção concentrada; fixe a versão e leia o changelog antes de subir.
```python
# config/api.py
api = NinjaAPI(title="<projeto>", version="1", docs_url=None)   # docs só fora de produção
api.add_router("/v1/pedidos", pedidos_router)

# pedidos/schemas.py
class PedidoIn(Schema):
    model_config = ConfigDict(extra="forbid")
    cliente_id: int
    entrega_em: AwareDatetime

class PedidoOut(ModelSchema):
    class Meta:
        model = Pedido
        fields = ["id", "status", "criado_em"]           # lista explícita, nunca "__all__"

# pedidos/api.py
router = Router(tags=["pedidos"], auth=JWTAuth())

@router.post("", response={201: PedidoOut})
def criar(request, payload: PedidoIn):
    return 201, services.criar_pedido(tenant_id=request.auth.tenant_id, data=payload)

@router.get("", response=list[PedidoOut])
@paginate(LimitOffsetPagination)
def listar(request):
    return Pedido.objects.for_tenant(request.auth.tenant_id).select_related("cliente")
```
- **Auth:** subclasse de `ninja.security.HttpBearer` com `authenticate(self, request, token)` devolvendo o principal (ou `None` = 401); pode ser `async def`. JWT com algoritmo explícito (`security-python` §8).
- **Erros RFC 9457:** `@api.exception_handler(DomainError)` e um handler para `ninja.errors.ValidationError` (schema → **400**), ambos com `api.create_response(request, body, status=...)` e `response["Content-Type"] = "application/problem+json"`. Handler de `Exception` só com `log.exception` e corpo sem detalhe.

## 6. Async: onde faz sentido
- **Use** em fan-out de I/O sem ORM (várias chamadas HTTP externas), SSE e long-polling, servindo por **ASGI**. CRUD com ORM: view síncrona sob WSGI é mais simples e não perde nada.
- **Transações não funcionam em modo async.** O bloco transacional fica numa função síncrona chamada com `sync_to_async(...)`.
- ORM async: `aget`, `acreate`, `afirst`, `asave`, `aset`, `async for`. ORM síncrono num contexto async levanta `SynchronousOnlyOperation`: corrija com `sync_to_async`; **nunca** `DJANGO_ALLOW_ASYNC_UNSAFE` em produção.
- Em async, conexões persistentes (`CONN_MAX_AGE`) ficam desligadas; use o pool.
- Middleware síncrono no meio da pilha ASGI prende uma thread por requisição: confira com log de debug de `django.request`.
- Cliente que desconecta gera `asyncio.CancelledError` na view: limpe e **relance**.

## 7. Execução
```bash
gunicorn config.wsgi --worker-class gthread --workers 1 --threads 8 --bind 0.0.0.0:8000
uvicorn config.asgi:application --host 0.0.0.0 --port 8000 --proxy-headers   # só se houver views async
```
- Um processo por contêiner, escala por réplica; threads entram na conta de conexões do pool.
- Gunicorn 26 removeu o worker `eventlet`; o 27 responde **400** a `Transfer-Encoding` que não termine em `chunked`.
- `collectstatic` no build da imagem; estático servido pelo proxy ou object storage.
- Portão de produção: `manage.py check --deploy`.

## 8. Testes (pytest-django)
```toml
[tool.pytest]
DJANGO_SETTINGS_MODULE = "config.settings"
testpaths = ["src", "tests"]
addopts = ["-ra", "--strict-markers"]          # sem --reuse-db: o banco de teste tem de sumir no fim
```
- A execução define `DJANGO_DB_TEST_NAME=test_<projeto>_<id>`; o pytest-django cria esse banco, aplica as migrations reais e o **destrói no fim** (com xdist, cada processo ganha sufixo próprio). Se a execução for morta, confira e apague o que sobrou.
- `@pytest.mark.django_db` (ou fixture `db`): cada teste numa transação revertida. `transaction=True` só para testar concorrência real; para `on_commit`, use `django_capture_on_commit_callbacks(execute=True)`.
- Cliente: fixture `client` do pytest-django (pilha completa com middleware) ou `ninja.testing.TestClient` para o router isolado.
- Celery em teste: chame a função da task direto no unitário; `CELERY_TASK_ALWAYS_EAGER = True` só na integração.
- Casos negativos: 401, 403, tenant cruzado (404), campo extra (400), N+1 travado com `django_assert_num_queries`.
- Tipos: `mypy` com o plugin do `django-stubs`:
```toml
[tool.mypy]
python_version = "3.14"
strict = true
plugins = ["mypy_django_plugin.main"]

[tool.django-stubs]
django_settings_module = "config.settings"
```

## 9. Filas: Celery 5.7 (decisão da equipe)
**Celery 5.7 com Redis como broker** é o padrão em Python (Django e workers de FastAPI). Motivos: maduro, `delay_on_commit` integrado ao Django, retry com backoff e jitter, beat para agendamento.
Alternativa: API `django.tasks` (6.0+) com o backend `django-tasks-db` 0.13 (fila no Postgres, sem Redis). Ainda é 0.x; adote só com ADR e para carga simples. Os backends embutidos do `django.tasks` são só para desenvolvimento e teste, e o Django não traz worker.
```python
# config/celery.py
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
app = Celery("<projeto>")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# settings.py
CELERY_BROKER_URL = env.redis_url                 # banco lógico próprio
CELERY_TASK_ACKS_LATE = True                      # reentrega se o worker morrer → task idempotente
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_TIME_LIMIT = 300
CELERY_TASK_SOFT_TIME_LIMIT = 270
CELERY_TASK_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]                  # nunca pickle (security-python §4)
CELERY_BROKER_TRANSPORT_OPTIONS = {"visibility_timeout": 3600}   # > maior tempo de task/ETA

# pedidos/tasks.py
@shared_task(bind=True, autoretry_for=(ErroTransitorio,), retry_backoff=True,
             retry_backoff_max=600, retry_jitter=True, max_retries=5)
def emitir_nota(self, pedido_id: int) -> None:
    ...                                           # idempotente: confere estado antes de agir
```
- Enfileire com `emitir_nota.delay_on_commit(pedido.id)` (Celery ≥ 5.4) ou `transaction.on_commit(...)`. Classe base própria de task herda de `DjangoTask`.
- Argumento é id ou JSON, nunca objeto do ORM (o objeto estaria velho quando a task rodar).
- `autoretry_for` só para erro **transitório**; erro de dado vai para falha definitiva (`backend-pitfalls` §2).
- **Beat é instância única** (uma réplica); duas réplicas duplicam o agendamento.
- Worker: `celery -A config worker --concurrency=auto` (5.7 respeita o limite de CPU do cgroup). Celery 5.7 é a última com Python 3.11.
