# Merge em lote, CI parado e PR empilhado

Prática de campo da equipe (sem fonte externa; origem: incidentes registrados pelo orchestrator). Só vale com o merge autorizado pelo dono (frase exata no briefing do `pr`).

## Squash cruzado deixa a main vermelha
PRs verdes isolados podem quebrar juntos quando existe guarda global (harness de auditoria, teste de autorização por rota, catálogo). A cada 2-3 squashes, rode o portão local completo na `main` atualizada (serializado com `flock`) e confira as rotas dos PRs ainda abertos contra a guarda nova.

## CI remoto parado: "CLEAN" não prova nada
1. Monte uma branch de integração local: `git merge --no-ff` do PR mais antigo para o mais novo; conflito = aborte e deixe esse PR para o fim.
2. O `qa` roda o portão do `ci.yml` na branch de integração (em rodadas pequenas).
3. O `pr` faz o squash conferindo que o `headRefOid` do PR é o testado e exige `git diff origin/main <integracao>` vazio.
4. Teste que depende do relógio reprova por fuso horário: separe falha conhecida de falha real.

## PR empilhado
Troque a base com `gh api -X PATCH repos/<org>/<repo>/pulls/<n> -f base=main` (`gh pr edit --base` falhou em campo) e faça merge da `main` na branch.

## Limpeza depois do merge
`gh pr list --state merged --head <branch>` antes de `git branch -D`; `git worktree remove` sempre sem `--force`.
