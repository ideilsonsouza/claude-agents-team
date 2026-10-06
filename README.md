# Equipe de agentes — Claude Code

Equipe global de desenvolvimento. Um **orchestrator** (Opus 5.5) que nunca executa — classifica, planeja, delega, confere e mantém o estado — e dez especialistas.

Objetivos, nesta ordem: **entregas corretas** (zero alucinação) · **pouco retrabalho** · **poucos tokens**.

## Uso

```bash
team-init                 # ativa a equipe no projeto atual (uma vez por projeto)
team                      # terminal: abre sessão como orchestrator
team "implementa login"   # já abre com a tarefa
team-init --off           # desativa
```

**Orca (ferramenta principal):** depois do `team-init`, toda sessão Claude Code aberta no projeto — inclusive pelo botão do Orca — começa como orchestrator. Uma vez por repositório, no Orca: *Repository settings → Worktree Shared Paths →* `.claude/settings.local.json`, para que cada worktree novo herde a ativação. O `team-init` não toca no repositório: o arquivo é ignorado via `.git/info/exclude`.

## Equipe

| Agente | Modelo | Effort | Papel |
|---|---|---|---|
| orchestrator | claude-opus-5-5 | high | Classifica, dimensiona, planeja (`tasks.md`), delega, confere evidências, atualiza a base. Só chama os agentes abaixo |
| architect | opus | high | `design.md`, contrato de API, ADRs. Chamado em toda decisão estrutural |
| prd | opus | medium | `requirements.md` com critérios de aceite em EARS |
| dba | sonnet | medium | Schema, migrations, índices, queries |
| backend | sonnet | medium | Go, Fastify, AdonisJS (não cria migrations) |
| frontend | sonnet | medium | Vue, React, Astro + design system e UI/UX |
| qa | sonnet | medium | Valida cada critério de aceite com evidência; não corrige código |
| docs | sonnet | low | README, guias, docs de API, mapeamento inicial da base |
| pr | sonnet | low | Único que faz commit/push/PR; revisa o diff |
| devops | sonnet | medium | Escreve CI/CD, Docker, IaC (não faz deploy) |
| deploy | sonnet | low | Executa release e rollback (não edita nada) |

O orchestrator troca o modelo por chamada (haiku → sonnet → opus, nunca acima). **Escada de escalonamento:** 2 devoluções da mesma tarefa → sobe um nível de modelo; falhou em opus → leva ao usuário. Cada especialista tem `maxTurns` para não entrar em loop.

## Fluxo

1. **Entender** — dúvida essencial vira pergunta ao usuário antes de delegar.
2. **Dimensionar** (skill `spec-workflow`):
   - **P** (bug/ajuste) → briefing direto
   - **M** (feature contida) → `tasks.md`
   - **G** (feature nova, várias camadas) → `requirements.md` → *aprovação* → `design.md` → *aprovação* → `tasks.md`
3. **Planejar** — cada tarefa passa pela *Definition of Ready*: dono, objetivo, arquivos, dependências, critério de pronto verificável.
4. **Delegar** — briefing cirúrgico; paralelo só após o contrato de API existir (backend ∥ frontend em worktrees isolados).
5. **Conferir** — CONCLUÍDO exige evidência; *Definition of Done*: `qa` validou os critérios, testes passando, `pr` revisou, base atualizada.
6. **Corrigir** — devolve ao mesmo agente com o defeito exato; problema de requisito/design volta para a spec.

## Anti-alucinação

Skill `delivery-contract` (pré-carregada em todos os especialistas):
- **Fontes de verdade em ordem:** código do projeto → versão instalada das dependências → doc oficial da versão → skills → memória do modelo (só como suposição explícita).
- Nada de APIs, flags, rotas ou colunas inventadas: confirmar antes de usar.
- Toda afirmação com evidência (`arquivo:linha`, saída de comando, link).
- Ambiguidade → status BLOQUEADO com a pergunta, nunca interpretação silenciosa.
- Relatório padronizado com status, verificação real e "Atualização da base".

## Economia de tokens

| Mecanismo | Onde |
|---|---|
| Contexto isolado por especialista; só o relatório volta | arquitetura |
| Opus só onde precisa (orchestrator, architect, prd); `effort` por papel | frontmatter |
| Base do projeto injetada **por papel** — ninguém relê o código para saber o que existe | `hooks/team-context.py` |
| Skills de stack carregadas sob demanda | prompts de backend/frontend |
| Saída de testes/builds/lint compactada (erros + contexto + resumo) | `hooks/compact-bash.py` + `compact-output.py` |
| Spec proporcional: nada de documento para bug | `spec-workflow` |
| Sem checklist nativo (Opus/Sonnet 5.5 não precisam; economiza contexto) — progresso no `tasks.md` | orchestrator |

O filtro de saída só atua em comandos simples e reconhecidos (`go test`, `npm test`, `vitest`, `tsc`, `node ace test`, ...), não altera permissões e preserva o exit code. Para ver tudo: acrescente `# full-output` ao comando.

## Base de conhecimento por projeto

Fora do repositório, em `~/.claude/team-state/<slug>/` (o slug vem do repositório principal: é o mesmo em todos os worktrees do Orca). Nomes de mercado:

| Arquivo | Origem | Injetado em |
|---|---|---|
| `product.md` | Kiro steering | orchestrator, architect, prd, docs |
| `tech.md` | Kiro steering | orchestrator e quase todos |
| `structure.md` | Kiro steering | orchestrator, architect, dba, backend, frontend, qa, docs, devops |
| `progress.md` | Cline Memory Bank | orchestrator, prd |
| `backlog.md` | — | orchestrator |
| `history.md` | — | consulta |
| `specs/`, `adr/`, `architecture/` | Kiro / ADR | sob demanda |

Política de artefatos por projeto (`structure.md`): `internal` (padrão, fora do repo) ou `repo` (em `docs/`). README e docs de API ficam sempre no repositório.

## Skills

| Skill | Pré-carregada em |
|---|---|
| delivery-contract | todos os especialistas |
| spec-workflow | orchestrator, prd, architect |
| adr-template | architect |
| knowledge-base | docs |
| sql-standards | dba |
| git-conventions | pr |
| deploy-checklist | deploy |
| backend-standards | backend (+ `backend-go` / `backend-fastify` / `backend-adonisjs` sob demanda) |
| frontend-standards, design-system, ui-ux | frontend (+ `frontend-vue` / `frontend-react` / `frontend-astro` sob demanda) |

## Versionamento

Este diretório (`~/.claude`) é um repositório git com **lista de permissão** (`.gitignore`): só entram `agents/`, as skills da equipe, `hooks/` da equipe, `bin/team-init` e este README. Ficam fora: credenciais, histórico, sessões, settings, plugins, memórias dos agentes (`agent-memory/`) e a base dos projetos (`team-state/`).

Memória: todos os agentes têm `memory: user`. A memória concede `Write`/`Edit`; no orchestrator e no deploy o prompt restringe essas ferramentas à memória (e, no orchestrator, à base).

### Outra máquina
```bash
git clone <repo> /tmp/team && cp -r /tmp/team/{agents,skills,hooks,bin,README.md,.gitignore} ~/.claude/
cd ~/.claude && git init && git remote add origin <repo> && git fetch && git reset origin/main
cat >> ~/.zshrc <<'Z'
alias team='claude --agent orchestrator'
alias team-init='~/.claude/bin/team-init'
Z
```

## Próximos passos planejados
- **Camada 1 de tokens:** plugins LSP oficiais (`gopls-lsp`, `typescript-lsp`), ccusage, avaliar rtk.
- **RAG e fine-tuning:** a discutir.
