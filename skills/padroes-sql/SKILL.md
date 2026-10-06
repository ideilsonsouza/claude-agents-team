---
name: padroes-sql
description: Padrões de banco de dados da equipe — modelagem, migrations seguras e reversíveis, zero downtime (expand/contract), índices, análise de queries e correção de dados. Foco em PostgreSQL, válido para MySQL com ajustes.
---

# Padrões SQL e migrations

## Modelagem
- Nomes `snake_case`, tabelas no plural (`users`), PK `id` (bigint identity ou UUID v7 — siga o projeto), FKs `<entidade>_id`.
- `created_at` / `updated_at` com `timestamptz` (sempre UTC). Dinheiro em `numeric(…)` ou inteiro em centavos, nunca `float`.
- Constraints no banco, não só na aplicação: `NOT NULL`, `FOREIGN KEY` com `ON DELETE` pensado, `UNIQUE`, `CHECK`.
- Enum: tabela de referência ou `CHECK`; evite tipo `ENUM` difícil de alterar.
- Soft delete só se houver requisito; se usar, índices parciais `WHERE deleted_at IS NULL`.

## Migrations
- Uma mudança lógica por migration, nome descritivo com timestamp.
- **Sempre com `down`** funcional. Se a reversão for impossível (perda de dados), diga explicitamente no arquivo e no relatório.
- Nunca edite migration já aplicada em outro ambiente: crie uma nova.
- Teste local: `up` → `down` → `up`.

## Zero downtime (expand / contract)
Mudanças incompatíveis em várias etapas, cada uma num deploy:
1. **Expand**: adicionar coluna/tabela nova (nullable ou com default), código escreve nas duas.
2. **Migrar dados** em lotes.
3. **Trocar leitura** para a estrutura nova.
4. **Contract**: remover o antigo num deploy posterior.

Operações perigosas no PostgreSQL:
- Índice em tabela grande: `CREATE INDEX CONCURRENTLY` (fora de transação).
- `NOT NULL` em coluna existente: adicionar `CHECK (col IS NOT NULL) NOT VALID`, depois `VALIDATE CONSTRAINT`, depois `SET NOT NULL`.
- FK nova em tabela grande: `NOT VALID` + `VALIDATE` separado.
- Renomear coluna/tabela usada pela aplicação = quebra: use expand/contract.
- Defina `lock_timeout` (ex.: `SET lock_timeout = '5s'`) em migrations que pegam lock.

## Índices e performance
- Indexe FKs e colunas de `WHERE`/`JOIN`/`ORDER BY` frequentes; índice composto na ordem de seletividade e uso.
- Valide com `EXPLAIN (ANALYZE, BUFFERS)`; procure Seq Scan em tabela grande, estimativas ruins, sort em disco.
- Não crie índice "por via das dúvidas": cada índice custa escrita.
- Paginação por keyset (`WHERE id > $1 ORDER BY id LIMIT n`) em tabelas grandes.

## Correção e carga de dados
- Scripts idempotentes, em lotes (ex.: 1.000 linhas por transação), com contagem antes/depois.
- `SELECT` de conferência antes de todo `UPDATE`/`DELETE`; `WHERE` sempre presente.
- Backup/snapshot antes de operações destrutivas em produção.

## Segurança
- Usuário da aplicação com privilégio mínimo (sem DDL em produção, se possível).
- Dados pessoais (LGPD): identifique colunas sensíveis; considere criptografia ou mascaramento em ambientes não produtivos.
