---
name: git-conventions
description: Convenções de git da equipe — Conventional Commits, nomes de branch, template de PR e checklist de revisão.
---

# Convenções de git

O perfil do projeto (`equipe` ou `solo`) vem do hook da equipe; regras completas no `~/.claude/CLAUDE.md`, seção "Perfis de projeto".

## Branches
`<tipo>/<descricao-curta>` — tipos: `feat`, `fix`, `chore`, `docs`, `refactor`, `test`, `ci`, `perf`.
- **Equipe:** `<tipo>/<CHAVE>-<descricao>` com a chave do Jira em maiúsculas. Ex.: `docs/PROJ-21-arquitetura-core`.
- **Solo:** `<tipo>/<descricao>` (chave só se houver issue). Ex.: `feat/login-oauth`.
- Nunca trabalhe direto na branch principal nem troque a branch da pasta principal do repo: use a worktree da tarefa.

## Commits — Conventional Commits
```
<tipo>(<escopo opcional>): <resumo no imperativo, até 72 caracteres>

<corpo opcional: o porquê, não o como>

<rodapé: BREAKING CHANGE:, Refs: PROJ-21>
```
- Um commit = uma mudança lógica. Separe refatoração de mudança de comportamento.
- Respeite o idioma de mensagens já usado no repositório.
- **Equipe:** rodapé `Refs: <CHAVE>` em todo commit da tarefa (é o que liga o commit à issue no Jira).
- **Sem atribuição de ferramenta:** não adicione `Co-Authored-By` (de Claude ou de qualquer IA), `Generated with ...` nem link de sessão em commits e PRs. O autor é o usuário git autenticado (`git config user.name`/`user.email`); nunca altere a identidade nem use `--author`.

## Push, PR e merge
- **Equipe:** tarefa finalizada e revisada (testes/typecheck verdes, diff revisado) → push da branch e abertura do PR para a `main` **automaticamente**. Título com a chave: `<tipo>: <resumo> (PROJ-21)`. Use o template do repo (`.github/PULL_REQUEST_TEMPLATE.md`) se existir; senão, o abaixo.
- **Solo:** push, PR e merge só com pedido explícito (fluxo definido por projeto).
- **Merge na `main` só com pedido expresso do usuário**, nos dois perfis. Nunca push direto na `main`.
- Equipe: não mexa em branches, PRs ou worktrees de outras pessoas.

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
Sem rodapé de ferramenta (`Generated with ...`) na descrição do PR.

## Checklist de revisão
1. Faz o que o PRD pede? Critérios de aceite cobertos?
2. Bugs: nulos, erros não tratados, concorrência, limites.
3. Segurança: injeção, autorização, segredos, dados sensíveis em log.
4. Testes cobrem o comportamento novo e casos de erro?
5. Código morto, duplicação, nomes ruins.
6. Migrations reversíveis? Mudança quebra clientes da API?

## Proibido sem autorização explícita
`push --force`, `reset --hard` em branch compartilhada, merge na principal, apagar branch remota, reescrever histórico publicado.
