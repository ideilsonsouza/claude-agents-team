---
name: backend-laravel
description: "Padrões para backend em PHP 8.5 e Laravel 13: Composer, estrutura, Eloquent (N+1, transações, locks), Form Requests, API Resources, policies, filas com Horizon, config/env, testes com Pest, Larastan e Pint, portão e armadilhas. Usar ao criar ou alterar código em projetos Laravel."
---

# Laravel (backend)

Versões e APIs conferidas em **10/11/2026**: endoflife.date (PHP, Laravel), laravel.com/docs/13.x (release notes, upgrade 12→13, Eloquent, filas, Horizon, erros, deploy, testes; via Context7 e site), `composer.json` do `laravel/laravel` 13.x, Packagist (pest, pest-plugin-laravel, phpunit, larastan, phpstan, pint, horizon), pestphp.com (upgrade 4→5, arch, configuração), php.net/releases/8.5, getcomposer.org.
- Padrões de API, erros RFC 9457, paginação e authz: `backend-standards`. Defeitos recorrentes: `backend-pitfalls`. Banco: `sql-standards` e `postgres-scaling`. Telemetria: `observability`. Testes: `test-strategy`.

## Versões (consulta em 10/11/2026)
| Peça | Versão | Observação |
|---|---|---|
| PHP | **8.5.12** (padrão); 8.4.27 | 8.4 sai do suporte ativo em 31/12/2026; 8.2 sem segurança em 31/12/2026 |
| Laravel | **13.42.0** (PHP 8.3–8.5) | bugs até T3/2027, segurança até 17/03/2028 |
| Laravel 12 | 12.72.0 | só segurança, até 24/02/2027: planeje o upgrade |
| Composer | 2.11.2 | |
| Pest | 5.3.5 (PHP ≥ 8.4, PHPUnit 13) | `pest-plugin-laravel` 5.0.1 exige `laravel/framework` ≥ 13.23 |
| PHPUnit | 13.4.6 / 12.5.43 | o skeleton 13.x vem com `phpunit/phpunit ^12.5.12` |
| Larastan / PHPStan | 3.14.0 / 2.3.5 | níveis 0 a 10 |
| Pint | 1.32.2 | |
| Horizon | 5.51.0 | exige Redis |

**PHP 8.5** traz pipe `|>`, `clone($obj, [...])`, `#[\NoDiscard]`, `array_first()`/`array_last()` e a extensão `Uri`. **PHP 8.4**: property hooks, visibilidade assimétrica, `new` sem parênteses. Fixe a mesma versão no `composer.json` (`"php": "^8.5"`), no CI e no `FROM` da imagem.

## 1. Composer e estrutura
```bash
composer create-project laravel/laravel <nome>
composer require --dev pestphp/pest pestphp/pest-plugin-laravel larastan/larastan
composer install --no-interaction --prefer-dist          # CI: respeita o composer.lock
composer validate --strict && composer audit             # portão
```
- `composer.lock` versionado. Em produção: `composer install --no-dev --classmap-authoritative`.
- Estrutura do Laravel 11+ (bootstrap enxuto): middleware, exceções e rotas em `bootstrap/app.php`.
```
app/
  Http/{Controllers/Api, Requests, Resources, Middleware}
  Models/                   # Eloquent: relações, casts, scopes; sem regra de negócio pesada
  Actions/ ou Services/     # regra de negócio, um caso de uso por classe
  Policies/  Jobs/  Events/  Listeners/
bootstrap/app.php            # withRouting, withMiddleware, withExceptions
config/                      # único lugar que chama env()
database/{migrations, factories, seeders}
routes/api.php
tests/{Feature, Unit, Pest.php}
```
- Controller fino: Form Request valida, Policy autoriza, Action executa, Resource serializa.
- **Laravel 13** acrescentou atributos: `#[Middleware]` e `#[Authorize]` em controller, `#[Tries]`, `#[Backoff]`, `#[Timeout]`, `#[FailOnTimeout]` em job, `#[Fillable]` em model; `Queue::route(Job::class, connection: ..., queue: ...)` centraliza o roteamento de filas. O CSRF passou a ser `PreventRequestForgery` (aliases antigos depreciados).

## 2. Eloquent
**Modo estrito (AppServiceProvider::boot):**
```php
Model::preventLazyLoading(! $this->app->isProduction());               // LazyLoadingViolationException
Model::preventSilentlyDiscardingAttributes(! $this->app->isProduction());
```
- **N+1:** `with('cliente', 'itens')` na query, `load()`/`loadMissing()` depois; `withCount()` para contagem. `Model::automaticallyEagerLoadRelationships()` ainda é **beta**: não use como solução.
- **Mass assignment:** declare o que pode ser preenchido (`#[Fillable(['nome', 'status'])]` no 13.x, ou `$fillable` em código existente) e preencha **só** com `$request->validated()`. Nunca `#[Unguarded]`/`$guarded = []` com `$request->all()`.
- **Transação e trava:**
```php
DB::transaction(function () use ($contaId, $tenantId, $valor) {
    $conta = Conta::whereKey($contaId)->where('tenant_id', $tenantId)->lockForUpdate()->firstOrFail();
    if ($conta->saldo < $valor) {
        throw new SaldoInsuficiente();
    }
    $conta->decrement('saldo', $valor);                  // atômico no SQL
    EmitirNota::dispatch($conta->id)->afterCommit();
}, attempts: 3);                                         // repete em deadlock
```
  - `lockForUpdate()` só faz sentido dentro de `DB::transaction`. `sharedLock()` para leitura que não pode mudar até o commit.
  - `firstOrCreate`/`updateOrCreate` só são seguros com **índice único** no banco; trate a violação.
  - `upsert($rows, uniqueBy: [...], update: [...])` para lote idempotente (no 13, `uniqueBy` vazio lança exceção).
- **Lotes:** `chunkById()`/`lazyById()` quando o loop altera as linhas; nunca `all()` em tabela grande.
- **Tenant em toda query:** global scope ou scope explícito (`Pedido::forTenant($t)`); recurso de outro tenant = 404. Route model binding com `scopeBindings()` para recurso aninhado.
- **Datas:** `casts` com `'immutable_datetime'`; banco e `config('app.timezone')` em **UTC**; fuso local só na apresentação.

## 3. Entrada, saída e autorização
```php
final class StorePedidoRequest extends FormRequest
{
    public function authorize(): bool
    {
        return $this->user()->can('create', Pedido::class);
    }

    public function rules(): array
    {
        return [
            'cliente_id' => ['required', 'integer', Rule::exists('clientes', 'id')->where('tenant_id', $this->user()->tenant_id)],
            'itens' => ['required', 'array', 'max:100'],
            'itens.*.sku' => ['required', 'string', 'max:64'],
            'entrega_em' => ['required', 'date'],
        ];
    }
}

final class PedidoResource extends JsonResource
{
    public function toArray(Request $request): array
    {
        return [
            'id' => $this->id,
            'status' => $this->status,
            'criado_em' => $this->created_at?->toIso8601String(),
            'itens' => ItemResource::collection($this->whenLoaded('itens')),
        ];
    }
}
```
- **Resource é a allowlist da saída**; nunca devolva o model (`toArray()` vaza colunas novas). `whenLoaded` evita lazy load na serialização.
- Regra `exists`/`unique` **com o tenant**; senão o usuário referencia registro de outro tenant.
- **Policy** por model (`PedidoPolicy`), chamada no Form Request, com `$this->authorize()` ou `#[Authorize]`. Gate só para permissão sem model. Teste a negação.
- API autenticada: Sanctum (token ou cookie SPA). Cookie exige CSRF (`PreventRequestForgery`).
- O 13 trouxe resources JSON:API nativos (doc "Eloquent: API Resources"), mas o padrão da equipe é o `backend-standards`; use JSON:API só se o contrato pedir.

## 4. Erros RFC 9457
```php
// bootstrap/app.php
->withExceptions(function (Exceptions $exceptions): void {
    $exceptions->shouldRenderJsonWhen(fn (Request $r) => $r->is('api/*') || $r->expectsJson());
    $exceptions->render(function (ValidationException $e, Request $r) {
        if (! $r->is('api/*')) return null;
        return response()->json([
            'type' => 'about:blank', 'title' => 'Requisição inválida', 'status' => 400,
            'errors' => collect($e->errors())->map(fn ($m, $campo) => ['pointer' => '/'.str_replace('.', '/', $campo), 'detail' => $m[0]])->values(),
        ], 400, ['Content-Type' => 'application/problem+json']);
    });
    $exceptions->render(fn (DomainException $e, Request $r) => $r->is('api/*')
        ? response()->json(['type' => 'about:blank', 'title' => $e->getMessage(), 'status' => 422], 422, ['Content-Type' => 'application/problem+json'])
        : null);
})
```
- Regra da equipe: falha de schema = **400** (o Laravel devolve 422 por padrão, por isso o render acima); regra de negócio = 422. Faça o mesmo para `NotFoundHttpException`, `AuthorizationException` e `AuthenticationException`.
- `APP_DEBUG=false` em produção: sem trace na resposta.

## 5. Configuração e ambiente
- **`env()` só dentro de `config/*.php`.** Com `php artisan config:cache` (ou `optimize`), o `.env` não é carregado e `env()` fora de config devolve `null`. No código, `config('servico.url')`.
- Deploy: `php artisan optimize` (cacheia config, eventos, rotas e views). `.env` não entra na imagem; variáveis vêm do orquestrador; `APP_KEY` é segredo.
- **Laravel 13:** cache com `serializable_classes = false` e sessão com `serialization = json` no skeleton (bloqueiam gadget chain se o `APP_KEY` vazar). Não guarde objeto PHP em cache nem sessão.
- Defina `CACHE_PREFIX`, `REDIS_PREFIX` e `SESSION_COOKIE` explícitos (o padrão mudou de `_` para `-` no 13).

## 6. Filas e Horizon
- **Redis + Horizon** é o padrão (dashboard, métricas, balanceamento por supervisor). Supervisores e filas por classe de carga em `config/horizon.php`; Horizon roda como serviço próprio (`php artisan horizon`).
- **`'after_commit' => true`** na conexão da fila (ou `->afterCommit()` no dispatch): job disparado dentro de transação só sai depois do commit; rollback descarta.
- **Job idempotente:** pode rodar mais de uma vez (retry, worker morto, timeout). Confira o estado antes de agir, use chave de idempotência ou `upsert`. Payload com id, não com model grande (`SerializesModels` relê do banco).
- `ShouldBeUnique` evita job duplicado na fila; `WithoutOverlapping($chave)` evita execução simultânea para a mesma chave.
- Retry: `#[Tries(5)]`, `#[Backoff([10, 60, 300])]`, `#[Timeout(120)]` (ou propriedades `$tries`, `$backoff`, `$timeout`). **`retry_after` da conexão > maior `timeout` de job**, senão o job roda duas vezes em paralelo. Erro de dado vai para `fail()`, não para retry (`backend-pitfalls` §2–3).
- Deploy: `php artisan horizon:terminate` (termina os jobs em andamento e o supervisor sobe a versão nova).
- Agendamento: `Schedule::...->onOneServer()` com várias réplicas; cron só chama `schedule:run` (ou `schedule:work`) em **uma** réplica.

## 7. Migrations
- **Na equipe, migration é do `dba`.** O backend descreve a mudança de schema; o `dba` escreve, revisa e assina (`sql-standards`: expand/contract, índice concorrente, locks).
- `php artisan migrate --force` é etapa do deploy, nunca no entrypoint das réplicas. `migrate:fresh`/`db:wipe` jamais fora do banco de teste da execução.

## 8. Testes (Pest)
**Decisão da equipe: Pest.** Roda sobre o PHPUnit (testes PHPUnit existentes continuam rodando), sintaxe enxuta, testes de arquitetura (`arch()->preset()->laravel()`, `->security()`), paralelismo. **Pest 5** com PHP ≥ 8.4 e Laravel ≥ 13.23; **Pest 4** se o projeto estiver em PHP 8.3. Projeto legado só com PHPUnit: mantenha e adicione Pest quando for escrever teste novo.
```php
// tests/Pest.php
pest()->extend(Tests\TestCase::class)->use(Illuminate\Foundation\Testing\RefreshDatabase::class)->in('Feature');

// tests/Feature/PedidoTest.php
it('não deixa ler pedido de outro tenant', function () {
    $pedido = Pedido::factory()->for(Tenant::factory())->create();
    $intruso = User::factory()->for(Tenant::factory())->create();

    $this->actingAs($intruso)->getJson("/api/pedidos/{$pedido->id}")->assertNotFound();
});

arch()->preset()->laravel();
arch()->preset()->security();
```
- **Banco real**, sem mock de Eloquent (`~/.claude/CLAUDE.md`, seção Serviços locais; no CI, o serviço da esteira). A execução cria `test_<projeto>_<id>`, passa em `DB_DATABASE` e **apaga no fim, mesmo com falha** (ex.: `trap` no script que roda os testes). Nunca SQLite no lugar do Postgres de produção.
- `--parallel` cria um banco por processo com sufixo e **mantém entre execuções**: na máquina compartilhada, apague-os ao terminar.
- Redis de teste: banco lógico próprio (1 a 15). Fakes do framework (`Queue::fake()`, `Http::fake()`, `Mail::fake()`) para efeitos externos; `Http::preventStrayRequests()`.
- Casos negativos: 401, 403 (policy), tenant cruzado (404), campo inválido (400), job disparado só após commit.

## 9. Qualidade
```neon
# phpstan.neon
includes:
    - vendor/larastan/larastan/extension.neon
parameters:
    paths: [app/]
    level: 6          # projeto novo: suba até 10; legado: baseline (--generate-baseline) e suba aos poucos
```
- **Pint** com o preset do projeto (`pint.json`), `--test` no CI. `declare(strict_types=1);` e classes `final` em código novo.

## 10. Portão (rode antes de entregar)
```bash
composer validate --strict
composer audit
vendor/bin/pint --test
vendor/bin/phpstan analyse --memory-limit=1G
php artisan test            # ou vendor/bin/pest (com --parallel se o projeto usar)
```
Comando que não existe no projeto: diga isso no relatório, não invente.

## 11. Armadilhas
1. **Mass assignment:** `create($request->all())` com model desprotegido deixa o cliente gravar `tenant_id`, `is_admin`, `status`. Só `validated()` e lista explícita.
2. **`env()` fora de `config/`** devolve `null` depois do `config:cache`: funciona no dev e quebra em produção.
3. **N+1 escondido no Resource ou na view:** ative `preventLazyLoading` fora de produção e use `whenLoaded`.
4. **Job não idempotente** + retry/timeout = cobrança, e-mail ou nota em dobro.
5. **Job disparado dentro da transação** sem `after_commit` lê dado que ainda não existe (ou que sofreu rollback).
6. **`retry_after` menor que o `timeout`** do job: o mesmo job roda em paralelo consigo mesmo.
7. **Timezone:** `app.timezone` diferente de UTC grava hora local sem fuso; `now()` comparado com data de outro fuso. Banco, PHP e app em UTC.
8. **Validação `exists`/`unique` sem tenant** e route model binding sem escopo: BOLA.
9. **Objeto PHP em cache/sessão** e `unserialize` de dado externo: gadget chain (Laravel 13 endureceu os defaults; não desfaça).
10. **Scheduler em todas as réplicas** sem `onOneServer()`: tarefa duplicada.
11. **Lock sem transação:** `lockForUpdate()` fora de `DB::transaction` não segura nada.
12. **Chamada HTTP sem timeout:** `Http::timeout(5)->connectTimeout(2)` sempre; retry só em operação idempotente.
13. **Teste com SQLite em memória** esconde diferença de SQL, locks e tipos do Postgres.

## Checklist de PR (Laravel)
- [ ] Portão verde (Pint, Larastan, Pest, `composer audit`).
- [ ] Form Request + Policy + Resource em toda rota; nada de `all()` em create/update.
- [ ] Sem N+1 (`with`/`whenLoaded`); transação explícita; `lockForUpdate` dentro dela.
- [ ] Jobs idempotentes, `after_commit`, `retry_after` > `timeout`.
- [ ] `env()` só em `config/`; datas em UTC.
- [ ] Testes com banco real, incluindo tenant cruzado; bancos de teste apagados ao terminar.
- [ ] Migration escrita/revisada pelo `dba`.
