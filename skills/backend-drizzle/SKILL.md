---
name: backend-drizzle
description: Padrões para Drizzle ORM (TypeScript) com PostgreSQL — versão estável 0.45.x (≥ 0.45.2 pela CVE-2026-39356) e preparo para a 1.0 (RQB v2/defineRelations, casing por tabela, nova pasta de migrations, validators em drizzle-orm/zod). Cobre schema em pg-core, índices e constraints, migrations com drizzle-kit (armadilha de timestamp entre branches), migrator fora do boot, ingestão em lote idempotente, TimescaleDB, transações, SQL bruto seguro e testes. Usar ao criar ou alterar tabelas, gerar ou aplicar migrations, escrever queries ou transações em projetos com drizzle-orm ou drizzle.config.ts.
---

# Drizzle ORM

Versões verificadas em 14/10/2026:
- **`drizzle-orm` 0.45.4** (latest) com **`drizzle-kit` 0.31.11**;
- a **1.0 está em release candidate** (`1.0.0-rc.4`, dist-tag `rc`), com breaking changes.

Fontes: https://orm.drizzle.team/docs, `/docs/upgrade-v1`, `/docs/v0-v1-changes`, `/docs/relations-v1-v2` e os releases no GitHub. **Siga a versão do `package.json` do projeto.** As diferenças entre 0.x e 1.0 estão marcadas no texto.

## Versão e segurança
- **Padrão da equipe: `drizzle-orm` ^0.45.4 e `drizzle-kit` ^0.31.11.** Não use a RC em produção. Adote a 1.0 quando sair a estável, seguindo o checklist do fim desta skill.
- **CVE-2026-39356 (GHSA-gpj5-g38j-94v9, alta):**
  - `sql.identifier()` e `sql.as()` não escapavam os valores, o que permitia SQL injection;
  - afeta `drizzle-orm` ≤ 0.45.1 e é corrigida na **0.45.2** (na linha 1.0, a partir da beta.20);
  - **Projeto abaixo da 0.45.2 tem que atualizar.**
- Escala e operação do banco (PgBouncer, réplicas com `withReplicas`, tuning, backup): skill `postgres-scaling`.
- Driver padrão: **`pg` (node-postgres) 8.x** com `Pool`. O `postgres` (postgres.js) 3.4 também é suportado. Na 0.45.4 foi corrigido um bug em que o `.prepare(name)` com postgres-js não preparava a query.

## Conexão
```ts
import { drizzle } from 'drizzle-orm/node-postgres';
import { Pool } from 'pg';
import * as schema from './schema';

const pool = new Pool({ connectionString: url, max: 10, idleTimeoutMillis: 30_000, connectionTimeoutMillis: 5_000 });
pool.on('error', (err) => log.error({ err }, 'pg pool error'));   // sem isso, erro em conexão ociosa derruba o processo
export const db = drizzle({ client: pool, schema });                // 1.0: drizzle({ client: pool, relations })
export type Db = typeof db;
```
- No Fastify, um plugin `fp` decora `db` e fecha o pool no `onClose` (ver `backend-fastify`).
- O tamanho do pool **somado entre réplicas** tem que caber no `max_connections` do Postgres (ou no PgBouncer). Com PgBouncer ≥ 1.21 em transaction mode, prepared statements de protocolo funcionam (`max_prepared_statements`). Já `SET` de sessão e advisory lock de sessão não funcionam (ver `postgres-scaling`).
- **Não use `drizzle({ casing: 'snake_case' })`.** A 1.0 remove essa opção. Dê nome explícito às colunas, como abaixo.

## Schema
- Defina as tabelas com `pgTable` em `src/db/schema/` (ou no caminho de `schema` do `drizzle.config.ts`). Exporte tudo o que o drizzle-kit precisa enxergar.
- **Nomes de coluna em `snake_case` e explícitos.** Sem nome, a coluna fica com o nome da chave TS (`createdAt`), e no Postgres isso exige aspas.
- PK sintética: `uuid().defaultRandom()`, UUIDv7 gerado na aplicação ou `integer().generatedAlwaysAsIdentity()`. Para PK numérica, prefira identity a `serial`.
- Índices e constraints vão no terceiro argumento, **como array** (a forma de objeto foi descontinuada):
```ts
export const devices = pgTable('devices', {
  id: uuid('id').primaryKey().defaultRandom(),
  tenantId: uuid('tenant_id').notNull().references(() => tenants.id, { onDelete: 'cascade' }),
  edgeId: text('edge_id').notNull(),
  status: text('status', { enum: ['active', 'retired'] }).notNull().default('active'),
  createdAt: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
  updatedAt: timestamp('updated_at', { withTimezone: true }).notNull().defaultNow().$onUpdate(() => new Date()),
}, (t) => [
  uniqueIndex('devices_tenant_edge_uq').on(t.tenantId, t.edgeId),
  index('devices_tenant_created_idx').on(t.tenantId, t.createdAt.desc()),
  check('devices_edge_id_check', sql`${t.edgeId} <> ''`),
]);
```
- Casos compostos: `uniqueIndex`, `primaryKey({ name, columns: [...] })` e `foreignKey({ name, columns, foreignColumns })`. **Nomeie** índices e constraints.
- Use **sempre `timestamp(..., { withTimezone: true })`** (timestamptz). Para `numeric`/`bigint`, escolha `mode` (`'number'` ou `'bigint'`) de propósito: o padrão volta como `string`.
- O `$onUpdate` roda só em updates feitos pelo Drizzle, não em SQL bruto nem em updates de outros sistemas.
- Tipos derivados: `typeof table.$inferSelect` e `typeof table.$inferInsert`. Não duplique interfaces à mão.
- Validação a partir do schema: `drizzle-zod` 0.8 (aceita Zod 4) com `createInsertSchema`/`createSelectSchema`. **Na 1.0 o import vira `drizzle-orm/zod`.** O schema de **entrada** da API continua escrito à mão (allowlist): não exponha o insert schema da tabela inteira.
- Evolução de schema com zero downtime (expand/contract, `NOT NULL` em etapas, índice `CONCURRENTLY`): siga a skill `sql-standards`.

## Migrations (drizzle-kit)
Fluxo para equipe e produção: **generate + migrate**, com o SQL versionado no git.
1. Altere o schema em TypeScript.
2. Rode `drizzle-kit generate --name=<descricao>`, que gera o SQL em `out` (ex.: `./drizzle`).
3. **Revise o SQL gerado** antes de commitar. Um rename pode virar drop + add (o kit pergunta, e na dúvida a resposta é "rename"), e uma mudança de tipo pode reescrever a tabela.
4. Aplique com `drizzle-kit migrate` ou com o migrator programático (`migrate(db, { migrationsFolder: './drizzle' })` de `drizzle-orm/node-postgres/migrator`). O controle fica em `drizzle.__drizzle_migrations`.

Regras:
- **Migrations de branches paralelas (armadilha da 0.x):**
  - o migrator da 0.x pula **em silêncio** toda migration cujo timestamp (`when` no `_journal.json`) seja menor que o da última aplicada;
  - isso acontece quando a branch A gera uma migration antes da B, mas faz merge depois. A migration de A nunca roda;
  - para evitar:
    - depois de atualizar a branch com a `main`, se outra migration entrou, **apague a sua e gere de novo** (`generate`) para que ela fique por último;
    - rode `drizzle-kit check` no CI. A partir da 0.31.11 ele **avisa** sobre timestamps fora de ordem, mas **não muda o exit code**, então o CI precisa falhar quando o aviso aparecer na saída.
  - a 1.0 corrige isso: aplica todas as pendentes, em qualquer ordem, e verifica comutatividade entre branches.
- **Rode as migrations como etapa própria do deploy** (job one-off, ou comando antes de subir a nova versão), e não no boot de cada réplica. O migrator não serializa réplicas concorrentes. Se precisar rodar no boot, proteja com `pg_advisory_lock` numa conexão dedicada.
- SQL manual (backfill, `CREATE INDEX CONCURRENTLY`, extensões, hypertable): `drizzle-kit generate --custom --name=<nome>`.
  - No Postgres, o migrator aplica as migrations pendentes **dentro de uma transação**, e o `CONCURRENTLY` não roda em transação. Faça esses comandos fora do migrator, com um script de deploy à parte, e registre isso no PR.
- `drizzle-kit push` só em protótipo ou banco local descartável. **Nunca** em banco compartilhado ou de produção.
- Nunca edite uma migration já aplicada em outro ambiente: crie uma nova.
- `drizzle.config.ts` com `dialect: 'postgresql'`, `schema`, `out` e `dbCredentials.url` vindo do ambiente. Se o banco tiver schemas fora do seu controle, declare o `schemaFilter`. Na 1.0, o padrão passa a gerenciar **todos** os schemas.

## Queries
- Prefira o query builder (`db.select({...}).from(t).where(and(eq(...), ...))`).
- Relational Query API: na 0.x é `db.query.<tabela>.findMany`, com `relations()` por tabela e `where` como callback. Na 1.0 isso vira `db._query` e o RQB v2 assume (ver o checklist).
- Selecione **colunas explícitas** em listagens. Pagine por cursor (`where(lt(t.createdAt, cursor))` + índice) em vez de `offset` grande.
- Use `.returning()` em insert/update quando precisar do registro, em vez de um select extra.
- Contagem: `db.$count(table, filtro)`.
- Upsert: `onConflictDoUpdate({ target, set: { col: sql\`excluded.col\` } })` ou `onConflictDoNothing({ target })`.
- Query quente: `.prepare('nome')` com `sql.placeholder('x')`.

## Ingestão em lote (telemetria)
- **Insert em lote** com `db.insert(t).values(rows)`. O Postgres aceita no máximo **65.535 parâmetros** por query: quebre em blocos de `floor(65535 / colunas)` linhas (na prática, de 500 a 2.000).
- **Idempotência** por constraint única + `onConflictDoNothing({ target: [t.deviceId, t.seq] })`, que casa com o contrato `(deviceId, seq)` da skill `mqtt-contract`. Use `.returning({ seq: t.seq })` se precisar saber o que foi gravado de fato.
- Grave o lote e a quarentena na mesma transação, e só então dê o ack da mensagem (ver `backend-fastify-mqtt`).
- Para volume muito alto (dezenas de milhares de linhas/s), use `COPY` pelo driver (`pg-copy-streams`) fora do Drizzle. Meça antes.

## TimescaleDB
- O drizzle-kit não conhece hypertable, compressão nem retenção. Declare a tabela normalmente e crie o resto numa migration `--custom`:
```sql
CREATE EXTENSION IF NOT EXISTS timescaledb;
SELECT create_hypertable('readings', by_range('ts', INTERVAL '1 day'), if_not_exists => TRUE);
ALTER TABLE readings SET (timescaledb.enable_columnstore, timescaledb.segmentby = 'device_id', timescaledb.orderby = 'ts DESC');
SELECT add_columnstore_policy('readings', after => INTERVAL '2 days');   -- maior que o atraso máximo do store-and-forward
SELECT add_retention_policy('readings', drop_after => INTERVAL '400 days');
```
- Use a API de columnstore (TimescaleDB 2.18+). `timescaledb.compress` e `add_compression_policy` estão deprecadas. Chunk interval, continuous aggregates e operação: skill `postgres-scaling`.
- **Toda PK ou unique de hypertable precisa incluir a coluna de tempo.** Exemplo: `primaryKey({ columns: [t.deviceId, t.seq, t.ts] })`, ou unique `(device_id, seq, ts)`. Isso muda a chave de idempotência: o `ts` precisa ser determinístico no reenvio, e é (`ts` de origem).
- Agregações contínuas e `time_bucket` ficam em SQL (migration custom ou `` sql`` ``).
- Rode `drizzle-kit generate` e confira que ele não tenta dropar objetos do Timescale. Nunca use `push` nem `pull` num banco Timescale de produção.

## SQL bruto
- `` sql`... ${valor}` `` parametriza valores (`$1`) e é seguro.
- `sql.raw()` **não** escapa nada: use só com literais internos, nunca com entrada do usuário.
- Para identificadores dinâmicos (coluna de ordenação, por exemplo), use `sql.identifier()` **com allowlist**. Ele só escapa corretamente a partir da 0.45.2.
- Monte fragmentos com `sql.join(chunks, sql`, `)`. Tipe o resultado com `` sql<number>`...` `` e `.mapWith(Number)` quando o driver devolver string (`numeric`, `count`).

## Transações
```ts
await db.transaction(async (tx) => {
  await tx.update(accounts).set({ balance: sql`${accounts.balance} - ${amount}` }).where(eq(accounts.id, from));
  await tx.update(accounts).set({ balance: sql`${accounts.balance} + ${amount}` }).where(eq(accounts.id, to));
}, { isolationLevel: 'read committed' });
```
- Dentro do callback, use **sempre `tx`**, nunca `db`. Senão a operação escapa da transação.
- `tx.rollback()` aborta (lança erro). Uma `tx.transaction(...)` aninhada vira savepoint.
- Em funções de repositório que podem rodar dentro ou fora de uma transação, receba `db: Db | Tx` por parâmetro.
- Não faça I/O externo (HTTP, filas, publish MQTT) dentro da transação. Publique depois do commit, ou use outbox.
- Com `serializable`, trate o erro `40001` com retry.

## Testes
- Use **Postgres real** (Testcontainers `@testcontainers/postgresql`, com a imagem do TimescaleDB se for o caso) com as migrations aplicadas pelo migrator. Não teste contra mocks do ORM.
- Isole cada caso por transação revertida ou por `TRUNCATE ... RESTART IDENTITY CASCADE` entre casos.
- Teste a migration nova contra um banco com dados (incluindo backfill), não só contra um banco vazio.
- Para dados de teste, use factories próprias. O `drizzle-seed` (0.3.x, parado desde 01/2025) serve para popular ambiente de dev.

## Migração 0.45 → 1.0 (quando a estável sair)
1. Fique na 0.45.4, com `drizzle-kit check` limpo e todas as migrations aplicadas em todos os ambientes.
2. Instale as versões 1.0 do `drizzle-orm` e do `drizzle-kit` e rode **`drizzle-kit up`**. Ele converte a pasta de migrations: some o `_journal.json`, cada migration ganha uma pasta com SQL e snapshot, e a tabela de migrations ganha `name` e `applied_at`. Commite a conversão sozinha num PR.
3. **Relations v2:**
   - troque os `relations()` por tabela por um único `defineRelations(schema, (r) => ({ ... }))`, com `from`/`to` no lugar de `fields`/`references`, `alias` no lugar de `relationName` e `through` para many-to-many. O `drizzle-kit pull` gera um rascunho;
   - no `drizzle()`, passe `{ relations }` no lugar de `{ schema }`;
   - nas queries, `where` e `orderBy` viram objetos (`where: { id: 1 }`, `orderBy: { id: 'asc' }`, com `AND`/`OR`/`NOT`/`RAW`). Enquanto migra, o código antigo segue em `db._query`.
4. Casing: se o projeto usava `casing` no `drizzle()`, troque por `snakeCase.table(...)` (de `drizzle-orm/pg-core`).
5. Outras trocas:
   - `drizzle-zod` vira `drizzle-orm/zod`;
   - `getTableColumns` vira `getColumns`;
   - `.array().array()` vira `.array('[][]')`;
   - `.enableRLS()` vira `pgTable.withRLS(...)`;
   - `.generatedAlwaysAs('...')` passa a aceitar só `` sql`...` ``.
6. drizzle-kit:
   - `drop` e `push --strict` foram removidos (o `push` pede confirmação por padrão; use `--explain` para ver o SQL);
   - o `schemaFilter` passa a gerenciar todos os schemas (aceita glob);
   - o `--output json` e o SDK `drizzle-kit/cli` servem para CI.
7. Opcional: `drizzle({ ..., jit: true })` com queries `.prepare()` reduz a latência de mapeamento. Ligue com medição.
