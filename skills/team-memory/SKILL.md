---
name: team-memory
description: Como consultar a memória da equipe (qmd) — specs, ADRs, histórico e aprendizados de todos os projetos — para reaproveitar decisões e evitar erros repetidos, sem desperdiçar tokens.
---

# Memória da equipe (qmd)

Busca local (nada sai da máquina) sobre duas coleções:
- `team-state` — base de **todos** os projetos: product/tech/structure/progress/backlog/history, specs (inclusive `_archive`), ADRs, docs de arquitetura. Cada subpasta é um projeto.
- `agent-memory` — memória dos agentes: aprendizados, preferências do usuário, causas de retrabalho.

O índice é atualizado automaticamente por hook. Use `mcp__qmd__query` para buscar e `mcp__qmd__get` para ler um trecho.

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

## Como usar o resultado
- Cite a fonte no relatório: `qmd://team-state/<projeto>/adr/0003-....md`.
- Contexto de outro projeto é **referência, não regra**: confira se as premissas valem para o projeto atual.
- Nada encontrado → diga isso e siga; não force analogia.
