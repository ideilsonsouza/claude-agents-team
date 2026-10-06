---
name: base-conhecimento
description: Estrutura e regras da base de conhecimento de projeto da equipe (fora do repositório) — mapa, implementado, pendências, histórico e artefatos internos — e como fazer o mapeamento inicial.
---

# Base de conhecimento do projeto

Cada projeto tem uma base **fora do repositório**, em `~/.claude/equipe-estado/<slug>/`. O caminho exato é injetado no contexto pelo hook da equipe. Ela substitui reler o código para descobrir "o que já existe".

## Arquivos

| Arquivo | Conteúdo | Tamanho alvo |
|---|---|---|
| `mapa.md` | Retrato atual do projeto (ver modelo abaixo). Injetado em **todos** os agentes | ≤ 150 linhas |
| `implementado.md` | Funcionalidades entregues: o quê, onde (arquivos-chave), endpoints, tabelas | conciso, 1–3 linhas por item |
| `pendencias.md` | Backlog, riscos, dívidas técnicas, perguntas em aberto | lista viva |
| `historico.md` | Uma linha por entrega: `AAAA-MM-DD · agente(s) · resumo` | só acrescenta |
| `prd/`, `adr/`, `arquitetura/` | Artefatos da equipe quando a política for **interno** | — |

## Modelo de `mapa.md`

```markdown
# Mapa — <projeto>
Atualizado: AAAA-MM-DD

## Visão
O que o sistema faz, em 2–3 linhas.

## Stack
Linguagens, frameworks, banco, ferramenta de migrations, testes, CI.

## Estrutura
Pastas principais → o que vive em cada uma (só o que ajuda a localizar código).

## Módulos
| Módulo | Onde | Responsabilidade |

## Comandos
Rodar, testar, lint, build, migrations.

## Convenções
Padrões do projeto que divergem ou especializam as skills da equipe.

## Artefatos da equipe
Política: interno | repositório
- interno → PRDs, ADRs e docs de arquitetura em `<base>/prd`, `<base>/adr`, `<base>/arquitetura`
- repositório → em `docs/prd`, `docs/adr`, `docs/architecture` do projeto
```

## Mapeamento inicial (feito uma vez pelo `docs`)
1. Leia manifestos e configuração (`go.mod`, `package.json`, configs de framework, CI, `docker-compose`), README existente e a árvore de diretórios (`git ls-files` resumido por pasta).
2. Abra apenas arquivos de entrada e um exemplo representativo por módulo. **Não leia o projeto inteiro.**
3. Escreva `mapa.md` e um `implementado.md` inicial. Política de artefatos: **interno**, salvo instrução contrária.

## Regras de manutenção
- O orquestrador atualiza a base após cada entrega, usando a seção "Atualização da base" do relatório (skill `contrato-entrega`).
- Fatos, não intenções. Se algo foi removido do código, remova da base.
- Nunca grave segredos, credenciais ou dados pessoais de clientes.
