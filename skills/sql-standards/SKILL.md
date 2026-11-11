---
name: sql-standards
description: "Padrões de banco (PostgreSQL 18, notas MySQL 8.4): modelagem, migrations seguras com zero downtime, locks, índices, expand/contract, correção de dados em produção, grants, LGPD e checklist de revisão. Usar ao modelar tabelas, escrever ou revisar migrations e consultas."
---

# Padrões SQL e migrations

Referência: **PostgreSQL 18** (fontes: docs 18 `sql-altertable`, `sql-createindex`, `explicit-locking` e release notes 18; GitLab migration style guide; squawkhq.com; verificado em 15/10/2026). Vale para qualquer ferramenta de migration (drizzle-kit, goose, golang-migrate, Lucid). Esta skill não cobre:
- escala, tuning, PgBouncer, TimescaleDB e backup: `postgres-scaling`;
- código Drizzle: `backend-drizzle`;
- RLS e desenho multi-tenant: `architecture-scalability`.

## 1. Modelagem
- **Nomes:** `snake_case`, tabelas no plural e FKs `<entidade>_id`.
- **Convenção de nomes de constraints e índices** (sempre nomeie, até 63 bytes):

| Objeto | Nome |
|---|---|
| PK | `<tabela>_pkey` |
| Unique constraint | `<tabela>_<cols>_key` |
| Unique index | `<tabela>_<cols>_uq` |
| FK | `<tabela>_<cols>_fkey` |
| Check | `<tabela>_<col>_check` |
| Not null nomeado | `<tabela>_<col>_nn` |
| Índice | `<tabela>_<cols>_idx` |

- **PK:**
  - `bigint GENERATED ALWAYS AS IDENTITY` é o padrão interno;
  - **`uuid DEFAULT uuidv7()`** (nativo no PG 18, ordenado no tempo) quando o id é exposto na API, gerado fora do banco (edge) ou mesclado entre bancos;
  - nunca `serial`.
  - O UUIDv7 revela o instante de criação e ocupa 16 bytes.
- **Tipos:**
  - texto: `text` + `CHECK (char_length(x) <= n)`, em vez de `varchar(n)`. Mudar o limite é só trocar a constraint;
  - tempo: sempre `timestamptz`;
  - dinheiro: `bigint` em centavos (uma moeda, somas rápidas) ou `numeric(14,2)` ou mais casas (regra fiscal ou câmbio). **Nunca `float` nem `money`.**
- **`jsonb`** serve para payload externo, atributos esparsos e configuração. **Não use** para campo filtrado ou ordenado com frequência, campo que precisa de FK ou `NOT NULL`, nem campo atualizado isoladamente com frequência (cada update reescreve o documento). O planner não tem estatística por chave.
- **Enumerações:**
  - `CHECK (status IN (...))` para valores estáveis;
  - tabela de referência com FK quando o valor tem atributos ou é editado pelo negócio;
  - `ENUM` só em legado: não remove valor, e o `ADD VALUE` só pode ser usado depois do commit.
- **Auditoria:** `created_at timestamptz NOT NULL DEFAULT now()` e `updated_at` mantido por **trigger**. O `$onUpdate` do ORM não cobre SQL bruto. Use `created_by`/`updated_by` quando o domínio exigir.
- **FK:**
  - **toda FK tem índice na coluna que referencia.** O PG não cria esse índice, e sem ele o `DELETE` do pai varre a tabela filha;
  - `ON DELETE RESTRICT` é o padrão. `CASCADE` só para composição (itens do pedido), e `SET NULL` para vínculo opcional;
  - cascata grande, como apagar um tenant, roda em lotes, de baixo para cima.
- **Multi-tenant, FK composta:** ela impede que o pedido do tenant A aponte para o cliente do tenant B.
```sql
ALTER TABLE customers ADD CONSTRAINT customers_tenant_id_id_key UNIQUE (tenant_id, id);
ALTER TABLE orders ADD CONSTRAINT orders_tenant_id_customer_id_fkey
  FOREIGN KEY (tenant_id, customer_id) REFERENCES customers (tenant_id, id);
```
- **Unicidade sem diferenciar maiúsculas e minúsculas:** índice único em `lower(email)`, e as consultas usam `lower(email) = lower($1)`. A alternativa é uma collation ICU nondeterministic (`und-u-ks-level2`), mas no PG 18 PK e FK precisam usar a mesma.
- **NULL em unique:** por padrão o unique aceita vários NULL. Use `NULLS NOT DISTINCT` quando NULL significar "um valor só":
```sql
CREATE UNIQUE INDEX settings_tenant_id_key_uq ON settings (tenant_id, key) NULLS NOT DISTINCT;
```
- **Sem sobreposição** (turno, reserva, vigência):
  - `EXCLUDE USING gist (machine_id WITH =, during WITH &&)`, com `btree_gist`;
  - ou, no PG 18, `PRIMARY KEY (id, valid WITHOUT OVERLAPS)` e `FOREIGN KEY ... PERIOD`.
- **Colunas geradas:** no PG 18 o padrão é VIRTUAL, que não reescreve a tabela. Indexar exige `STORED`, que reescreve.
- **Soft delete:** só com requisito. O padrão é `DELETE` real com tabela `<tabela>_archive` ou trigger de auditoria. Se usar `deleted_at`, todo unique vira parcial (`WHERE deleted_at IS NULL`) e toda consulta filtra por ele. A FK não enxerga o `deleted_at`.
- **Domínio com constraint:** evite em tabela grande. O `ADD COLUMN` com um domínio assim reescreve a tabela, e o `ALTER DOMAIN ADD CONSTRAINT` varre todas as tabelas que o usam.

## 2. Migrations seguras (zero downtime)
### Lock de cada operação
| Operação | Lock | Bloqueia |
|---|---|---|
| Quase todo `ALTER TABLE` (ADD/DROP/RENAME COLUMN, SET NOT NULL, ALTER TYPE, ADD CHECK/UNIQUE/PK) | ACCESS EXCLUSIVE | **tudo, inclusive SELECT** |
| `ADD FOREIGN KEY` | SHARE ROW EXCLUSIVE **nas duas tabelas** | escritas |
| `CREATE INDEX` (sem CONCURRENTLY) e `CREATE TRIGGER` | SHARE / SHARE ROW EXCLUSIVE | escritas |
| `VALIDATE CONSTRAINT`, `CREATE/DROP INDEX CONCURRENTLY`, `REINDEX CONCURRENTLY` | SHARE UPDATE EXCLUSIVE | só DDL e VACUUM |

- **O ACCESS EXCLUSIVE entra numa fila.** Se ele esperar atrás de uma transação longa, **todo SELECT que chega depois fica parado atrás dele**, e a aplicação para. Por isso, toda migration começa com:
```sql
SET lock_timeout = '3s';
SET statement_timeout = '15min';
```
- Quando estoura o `lock_timeout`, o runner (ou script de deploy) **tenta de novo com backoff**, de 5 a 10 vezes. A migration é curta: o que demora vai para backfill ou script à parte.

### O que reescreve a tabela (evite em tabela grande)
- **Não reescreve:**
  - `ADD COLUMN` nullable ou com default **constante**;
  - coluna VIRTUAL;
  - `varchar(n)` para `text` ou para um `n` maior;
  - `DROP COLUMN`, que só marca a coluna.
- **Reescreve:**
  - default **volátil** (`now()` é estável e não reescreve; `clock_timestamp()`, `random()` e `uuidv7()` reescrevem);
  - coluna `STORED` ou identity nova;
  - `ALTER TYPE` não binário-compatível (`int` para `bigint` e afins);
  - domínio com constraint.

### Receitas
- **NOT NULL em coluna existente:**
```sql
-- PG 18
ALTER TABLE t ADD CONSTRAINT t_col_nn NOT NULL col NOT VALID;
ALTER TABLE t VALIDATE CONSTRAINT t_col_nn;
-- PG ≤ 17: CHECK auxiliar
ALTER TABLE t ADD CONSTRAINT t_col_nn CHECK (col IS NOT NULL) NOT VALID;
ALTER TABLE t VALIDATE CONSTRAINT t_col_nn;
ALTER TABLE t ALTER COLUMN col SET NOT NULL;   -- pula a varredura graças ao CHECK válido
ALTER TABLE t DROP CONSTRAINT t_col_nn;
```
  Confirme a forma do PG 18 num teste antes do primeiro uso.
- **CHECK e FK novos:** `... NOT VALID` e depois `VALIDATE CONSTRAINT` em comando separado.
- **Índice em tabela existente:** `CREATE INDEX CONCURRENTLY`.
  - Não roda em transação, então fica **fora do migrator** quando ele usa transação (ver `backend-drizzle`).
  - É um por tabela de cada vez.
  - **Se falhar, sobra um índice `INVALID`**: não é usado nas consultas, mas custa nas escritas e, se for UNIQUE, **ainda impõe unicidade**. Verifique e limpe:
```sql
SELECT indexrelid::regclass FROM pg_index WHERE NOT indisvalid;
DROP INDEX CONCURRENTLY IF EXISTS orders_x_idx;   -- e recrie
```
- **UNIQUE e PK sem lock longo:**
```sql
CREATE UNIQUE INDEX CONCURRENTLY users_code_uq ON users (code);
ALTER TABLE users ADD CONSTRAINT users_code_key UNIQUE USING INDEX users_code_uq;
```
  O `USING INDEX` não aceita índice parcial nem de expressão (esses ficam só como índice único). Para PK, a coluna já tem que ser NOT NULL.
- **Índice inchado:** `REINDEX INDEX CONCURRENTLY`.
- **Tabela particionada:** índice `CONCURRENTLY` em cada partição e depois no pai, sem `CONCURRENTLY`.

### Expand/contract: mudança incompatível em vários deploys
1. **Expand:** coluna ou tabela nova (nullable ou com default constante). O código escreve nas duas, ou um trigger sincroniza.
2. **Backfill em lotes:** fora da migration, num script ou job. Avança pela PK, faz commit por lote, pausa entre lotes e é idempotente:
```sql
UPDATE orders SET total_cents = (total * 100)::bigint
WHERE id IN (SELECT id FROM orders WHERE id > $1 AND total_cents IS NULL ORDER BY id LIMIT 5000)
RETURNING id;   -- guarda o max(id), pg_sleep(0.1), repete até 0 linhas; acompanhe lag e autovacuum
```
3. **Leitura migra** para a estrutura nova.
4. **Contract:** remove o antigo num **deploy posterior**.

- **Renomear coluna ou tabela** que a aplicação usa quebra o deploy, então use os 4 passos acima. Views de compatibilidade só valem com ferramenta própria (pgroll).
- **Drop de coluna:**
  - no deploy N, o código para de ler e escrever a coluna, e ela **sai do schema do ORM**, que pode fazer `SELECT *` ou listá-la;
  - no deploy N+1, `DROP`;
  - se a coluna for `NOT NULL` sem default, faça `DROP NOT NULL` no expand, senão o `INSERT` da versão antiga quebra.
- **Mudar tipo de coluna grande** (`int` para `bigint` em PK): coluna nova + trigger + backfill + índices `CONCURRENTLY` + troca numa transação curta, incluindo FKs filhas. É um projeto, não uma migration.

### Ordem de deploy e política de rollback
- A migration de **expand roda antes** do código novo: a versão N-1 precisa funcionar com o schema novo (rolling deploy com várias réplicas, ver `cd-practices`). A de **contract roda num deploy posterior**.
- **Produção é forward-only.** O rollback é sempre do **app** (o schema já é compatível com N-1), e o erro de migration se corrige com outra migration.
  - Escreva `down` quando ele for trivial e seguro, e teste `up → down → up` no CI.
  - Migration destrutiva leva no arquivo e no PR: `-- irreversível: recuperação via backup/PITR`.
- Nunca edite uma migration já aplicada em outro ambiente: crie uma nova. **Uma mudança lógica por migration.**

### Linter e teste
- **squawk** (2.x) no CI sobre os `.sql` gerados:
  - serve para qualquer ferramenta (o Lucid precisa gerar o SQL antes);
  - `.squawk.toml` com `pg_version = "18.0"` e `assume_in_transaction = true`;
  - regras-chave: `require-lock-timeout`, `require-concurrent-index-creation`, `constraint-missing-not-valid`, `adding-field-with-default`, `changing-column-type`, `renaming-column`, `ban-drop-column`, `prefer-bigint-over-int`, `prefer-timestamptz`, `prefer-text-field`;
  - exceção só com `-- squawk-ignore <regra>` justificado no PR.
- **Migration em tabela grande** é testada contra uma cópia com volume real e dados mascarados (`CREATE DATABASE t TEMPLATE base_mascarada`), medindo tempo e locks com carga em paralelo.

## 3. MySQL 8.4 LTS (quando o projeto usar)
- Sempre declare `ALGORITHM=INSTANT` (ou `INPLACE`) e `LOCK=NONE`: o comando **falha** em vez de cair silenciosamente para cópia.
- **INSTANT:** `ADD`/`DROP COLUMN`, rename, `SET/DROP DEFAULT` e acréscimo de valor no fim do `ENUM`. O limite é de **64 versões de linha** por tabela; depois disso exige rebuild.
- **INPLACE:** índice secundário. **COPY:** mudança de tipo. Em tabela grande, use **gh-ost** (binlog ROW) ou pt-online-schema-change.
- DDL **não é transacional** no MySQL: o `down` testado importa mais. Use `lock_wait_timeout` baixo.

## 4. Índices e consultas
- **Índices:**
  - **ordem das colunas:** igualdade primeiro, depois intervalo ou ordenação: `(tenant_id, status, created_at DESC)`;
  - **parcial** para subconjunto quente (`WHERE status = 'pending'`);
  - **de expressão** (`lower(email)`): a consulta precisa usar a mesma expressão;
  - **covering** com `INCLUDE (col)` para evitar acesso ao heap;
  - **BRIN** para tabela enorme append-only correlacionada com o tempo;
  - **GIN** `jsonb_path_ops` para `@>` e `gin_trgm_ops` (pg_trgm) para `ILIKE '%x%'`;
  - **redundante:** `(a)` quando já existe `(a, b)`. Cada índice custa escrita: nada de índice "por via das dúvidas".
- **Plano:** valide com `EXPLAIN (ANALYZE, BUFFERS)`. Diagnóstico e `pg_stat_statements` estão em `postgres-scaling`.
- **Keyset com desempate:**
```sql
SELECT ... WHERE tenant_id = $1 AND (created_at, id) < ($2, $3)
ORDER BY created_at DESC, id DESC LIMIT 50;   -- índice (tenant_id, created_at DESC, id DESC)
```
- **Evite:**
  - `OFFSET` grande, que lê e descarta as linhas;
  - `COUNT(*)` exato em tabela grande (use "1.000+" com `LIMIT 1001`, `reltuples` ou contador agregado);
  - `ORDER BY random()` (use `TABLESAMPLE` ou id aleatório no intervalo);
  - **N+1** (use `= ANY($1)` ou JOIN). No `pg_stat_statements`, ele aparece como muitas `calls` com cerca de 1 linha cada.
- **Upsert sem escrita inútil:**
```sql
INSERT INTO t (...) VALUES (...) ON CONFLICT (tenant_id, code)
DO UPDATE SET name = EXCLUDED.name WHERE t.name IS DISTINCT FROM EXCLUDED.name;
```
  O alvo do conflito tem que casar com o índice único (inclusive o predicado do índice parcial). No PG 18, `RETURNING old.*, new.*` mostra o antes e o depois.
- **Fila no banco:** `SELECT ... FOR UPDATE SKIP LOCKED LIMIT n` dentro de `UPDATE ... WHERE id IN (...)`.
- **Deadlock:** trave sempre na mesma ordem (`ORDER BY id` antes do `FOR UPDATE` em lote), mantenha a transação curta e faça retry no SQLSTATE `40P01` (e no `40001` em `serializable`).
- **CTE:** desde o PG 12, a CTE é inlined quando usada uma vez. Force com `MATERIALIZED` ou `NOT MATERIALIZED` quando o plano precisar.

## 5. Correção de dados em produção (runbook)
1. **Ticket** com o motivo, o SQL, o filtro e a **contagem esperada**. **Revisão por par obrigatória.**
2. **Rede de segurança:** confirme o PITR (ver `postgres-scaling`) e, para correção pontual, `CREATE TABLE fix_<chave>_bkp AS SELECT * FROM t WHERE <mesmo filtro>`.
3. **Script idempotente** (o filtro exclui o que já foi corrigido). Rode no `psql` com usuário **nominal**, nunca o `app`:
```sql
\set ON_ERROR_STOP on
BEGIN;
SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '60s';
SET LOCAL application_name = 'fix PROJ-123 <pessoa>';
UPDATE invoices SET status = 'void'
WHERE tenant_id = '<tenant>' AND id = ANY('{...}') AND status = 'open';
-- psql mostra "UPDATE n": se n = contagem esperada → COMMIT; senão → ROLLBACK
```
4. Acima de cerca de 10 mil linhas, rode **em lotes**, como no backfill.
5. **Registre** quem, quando, o SQL e a contagem antes e depois (no ticket ou numa tabela `ops_log`). Faça um `SELECT` de verificação depois do commit.
6. **Nunca** `UPDATE` ou `DELETE` sem `WHERE`, e sempre um `SELECT` com o mesmo filtro antes.

## 6. Segurança e LGPD
- **Roles:** `migrator` é dono e faz DDL; `app` e `readonly` não são donos (ver `postgres-scaling`). Em banco novo ou atualizado:
```sql
REVOKE ALL ON DATABASE app FROM PUBLIC;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;   -- bancos vindos do PG ≤ 14 ainda permitem
ALTER DEFAULT PRIVILEGES FOR ROLE migrator IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app;
ALTER DEFAULT PRIVILEGES FOR ROLE migrator IN SCHEMA public GRANT SELECT ON TABLES TO readonly;
ALTER DEFAULT PRIVILEGES FOR ROLE migrator IN SCHEMA public GRANT USAGE ON SEQUENCES TO app;
```
- **RLS:** desenho em `architecture-scalability`. Migration que desliga RLS ou dropa policy é revisada com atenção redobrada.
- **Dados pessoais:**
  - classifique as colunas (`COMMENT ON COLUMN users.email IS 'pii:contact'`) e mantenha um inventário;
  - dado sensível é **criptografado na aplicação** (envelope, chave fora do banco). Com `pgcrypto`, a chave passa pelo SQL e vaza em log e `pg_stat_statements`;
  - busca por dado criptografado usa uma coluna à parte com HMAC.
- **Fora de produção:** só dump **mascarado** (script de mascaramento ou PostgreSQL Anonymizer). Nunca copie produção crua para dev ou staging.
- **Retenção e direito de exclusão:**
  - job de expurgo ou anonimização por política (`retention_until`);
  - a exclusão do titular segue um roteiro testado, que inclui as tabelas de arquivo e de auditoria;
  - o backup expira pela retenção dele.

## 7. Checklist de revisão de migration (DBA e revisor do PR)
1. O schema novo funciona com o código N-1 (expand)? O contract ficou para um deploy posterior?
2. Tem `lock_timeout` e `statement_timeout`, e retry no runner?
3. Tem ACCESS EXCLUSIVE longo? (Rewrite, `ALTER TYPE`, CHECK, FK ou NOT NULL sem `NOT VALID`, default volátil, coluna STORED ou identity.)
4. Índice em tabela existente usa `CONCURRENTLY`, fora de transação, com checagem de `INVALID`?
5. UNIQUE e PK em tabela existente via `USING INDEX`? FK nova com índice? FK composta com tenant quando aplicável?
6. Backfill separado, em lotes, idempotente e com tempo estimado?
7. Nomes de constraints e índices seguem a convenção?
8. `DROP` ou rename: o código (e o schema do ORM) já parou de usar? A irreversibilidade está declarada?
9. `down` testado (`up → down → up`) ou marcado como irreversível com plano de PITR?
10. squawk verde? Exceções justificadas?
11. Tabela grande: testada em cópia com volume real, tempo e locks medidos?
12. Grants de `app` e `readonly` cobrem as tabelas e sequências novas? Colunas com PII classificadas?
13. MySQL: `ALGORITHM` e `LOCK` explícitos? Limite de versões do INSTANT verificado?
