---
name: adr-template
description: Template de ADR (Architecture Decision Record) da equipe — contexto, decisão, alternativas, consequências — e regras de numeração e substituição.
---

# ADR — Architecture Decision Record

Salve em `<pasta de ADRs>/NNNN-<titulo-curto>.md` (a pasta depende da política de artefatos do `structure.md`: `<base>/adr/` ou `docs/adr/`), numeração sequencial com 4 dígitos (`0001`, `0002`...). Crie `README.md` na pasta com o índice se não existir e mantenha-o atualizado.

```markdown
# NNNN. <Título da decisão no imperativo>

**Status:** proposta | aceita | substituída por [NNNN](NNNN-x.md) | depreciada
**Data:** AAAA-MM-DD

## Contexto
Problema, forças em jogo, restrições (técnicas, prazo, equipe, custo). Fatos, não opinião.

## Decisão
O que foi decidido, de forma direta: "Vamos usar X para Y."

## Alternativas consideradas
| Opção | Prós | Contras |
|-------|------|---------|

## Consequências
- Positivas
- Negativas / custos assumidos
- O que passa a ser obrigatório para a equipe

## Referências
Links, PRD relacionado, benchmarks.
```

Regras:
- Uma decisão por ADR. Curta: cabe em uma tela.
- ADR aceita **não é editada** (só o status). Para mudar, crie nova ADR que a substitua e atualize o status da antiga.
- Escreva ADR quando a decisão for difícil de reverter, afetar mais de um módulo ou introduzir tecnologia/dependência nova.
