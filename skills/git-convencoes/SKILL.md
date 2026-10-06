---
name: git-convencoes
description: Convenções de git da equipe — Conventional Commits, nomes de branch, template de PR e checklist de revisão.
---

# Convenções de git

## Branches
`<tipo>/<descricao-curta>` — tipos: `feat`, `fix`, `chore`, `docs`, `refactor`, `test`, `ci`, `perf`.
Ex.: `feat/login-oauth`, `fix/timeout-relatorio`. Nunca trabalhe direto na branch principal.

## Commits — Conventional Commits
```
<tipo>(<escopo opcional>): <resumo no imperativo, até 72 caracteres>

<corpo opcional: o porquê, não o como>

<rodapé: BREAKING CHANGE:, Refs #123>
```
- Um commit = uma mudança lógica. Separe refatoração de mudança de comportamento.
- Respeite o idioma de mensagens já usado no repositório.
- Se houver linha de atribuição exigida pela sessão, inclua no final.

## Template de PR
```markdown
## O que muda
## Por quê
Link do PRD/issue.
## Como testar
Passos e comandos.
## Checklist
- [ ] Testes passando
- [ ] Sem segredos ou .env
- [ ] Documentação atualizada (se aplicável)
- [ ] Breaking changes descritas
```

## Checklist de revisão
1. Faz o que o PRD pede? Critérios de aceite cobertos?
2. Bugs: nulos, erros não tratados, concorrência, limites.
3. Segurança: injeção, autorização, segredos, dados sensíveis em log.
4. Testes cobrem o comportamento novo e casos de erro?
5. Código morto, duplicação, nomes ruins.
6. Migrations reversíveis? Mudança quebra clientes da API?

## Proibido sem autorização explícita
`push --force`, `reset --hard` em branch compartilhada, merge na principal, apagar branch remota, reescrever histórico publicado.
