---
name: team-memory
description: Como consultar a memória da equipe (qmd) — specs, ADRs, histórico e aprendizados de todos os projetos — para reaproveitar decisões e evitar erros repetidos, sem desperdiçar tokens.
---

# Memória da equipe (qmd)

Busca local (nada sai da máquina) sobre duas coleções:
- `team-state` — base de **todos** os projetos: product/tech/structure/progress/backlog/history, specs (inclusive `_archive`), ADRs, docs de arquitetura. Cada subpasta é um projeto.
- `agent-memory` — memória dos agentes: aprendizados, preferências do usuário, causas de retrabalho.

O índice é atualizado automaticamente por hook. Use `mcp__qmd__query` para buscar e `mcp__qmd__get` para ler um trecho. **Sem qmd na sessão**, siga a seção "Sem qmd (fallback)".

## Quando buscar
Antes de **decidir**, não antes de tudo:
- architect: antes de uma decisão estrutural ("já decidimos algo parecido? qual ADR?").
- prd: antes de escrever requisitos de um tipo de feature já feito em outro projeto.
- dba: antes de uma migration arriscada ("que problema de migration já tivemos?").
- orchestrator: ao planejar uma feature G e ao investigar retrabalho recorrente.

Não busque para tarefas P nem para o que está na base do projeto atual (ela já está no seu contexto).

## Como buscar (rápido e barato)
**Sempre passe sub-consultas tipadas.** Nunca envie texto livre sem tipo: isso dispara a expansão por LLM local, que leva ~1–2 min nesta máquina.

```
lex: "refresh token" jwt
vec: como implementamos autenticação para app mobile?
```
- `lex` — palavras-chave/termos exatos (instantâneo).
- `vec` — pergunta em linguagem natural (segundos).
- `hyde` — só se lex+vec não acharem nada.
- Filtre por coleção quando souber onde está.

**Limite: até 2 buscas por decisão.** Leia só o trecho necessário com `get` (`fromLine`, `maxLines`), não o documento inteiro.

## Sem qmd (fallback)
Se as ferramentas `mcp__qmd__*` não existirem na sessão ou falharem (MCP não conectou ou o executável `qmd` não está instalado), **não desista da consulta**: busque direto nos arquivos com Grep e Read, que é o que o qmd indexa.
- Coleções: `~/.claude/team-state/` (uma subpasta por projeto) e `~/.claude/agent-memory/` (uma subpasta por agente). Só arquivos `*.md`.
- Mesmo orçamento: **até 2 buscas por decisão**.
  1. Use `Grep` com `output_mode: "files_with_matches"` e termos exatos (o equivalente ao `lex`), por exemplo `pattern: "refresh token|jwt"`, `path: ~/.claude/team-state`, `glob: "**/*.md"`, `-i: true`. Para decisões, restrinja a `**/adr/*.md`. Para aprendizados, use `path: ~/.claude/agent-memory`.
  2. Leia com `Read` só o trecho relevante (`offset`/`limit`), nunca o arquivo inteiro.
- Não existe busca semântica (`vec`) no fallback. Tente sinônimos em PT e EN numa única regex (`autentica|auth|login`).
- Na fonte, cite o caminho do arquivo (`~/.claude/team-state/<projeto>/adr/0003-....md`) e diga no relatório que a consulta foi feita sem qmd.

## Como usar o resultado
- Cite a fonte no relatório: `qmd://team-state/<projeto>/adr/0003-....md`.
- Contexto de outro projeto é **referência, não regra**: confira se as premissas valem para o projeto atual.
- Nada encontrado → diga isso e siga; não force analogia.
