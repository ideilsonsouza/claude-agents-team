# Equipe de agentes — Claude Code

Equipe global de desenvolvimento: um orchestrator (Opus 5.5) que nunca executa, só delega, e dez especialistas.

## Uso
```bash
team                            # abre sessão com o orchestrator (alias de: claude --agent orchestrator)
team "implementa login OAuth" # já abre com a tarefa
```
Dentro de uma sessão comum também dá para usar `@agent-orchestrator ...`, mas sem a trava de agentes permitidos.

## Equipe
| Agente | Modelo | Papel |
|---|---|---|
| orchestrator | claude-opus-5-5 | Classifica, planeja, delega, confere. Só pode chamar os agentes abaixo |
| architect | opus | Arquitetura, decisões técnicas, ADRs (chamado sempre que houver decisão estrutural) |
| prd | opus | PRD, critérios de aceite, contrato de API |
| dba | sonnet | Schema, migrations SQL, índices, performance de queries |
| backend | sonnet | Go, Fastify, AdonisJS (não cria migrations) |
| frontend | sonnet | Vue, React, Astro + design system e UI/UX |
| qa | sonnet | Testes e validação contra critérios de aceite |
| docs | sonnet | README, guias, documentação de API |
| pr | sonnet | Único que faz commit/push/PR; revisa diff |
| devops | sonnet | Escreve CI/CD, Docker, IaC (não faz deploy) |
| deploy | sonnet | Executa release e rollback (não edita pipeline) |

O orchestrator pode trocar o modelo por chamada (haiku → sonnet → opus), nunca acima de opus.

## Skills
| Skill | Pré-carregada em |
|---|---|
| delivery-contract | todos os especialistas |
| prd-template | prd |
| adr-template | architect |
| sql-standards | dba |
| knowledge-base | docs (o orchestrator segue as regras pelo prompt) |
| git-conventions | pr |
| deploy-checklist | deploy |
| backend-standards | backend (+ `backend-go`/`backend-fastify`/`backend-adonisjs` sob demanda, conforme a stack) |
| frontend-standards, design-system, ui-ux | frontend (+ `frontend-vue`/`frontend-react`/`frontend-astro` sob demanda) |

## Instalar em outra máquina
```bash
git clone <repo> /tmp/equipe && cp -r /tmp/equipe/{agents,skills,README.md,.gitignore} ~/.claude/
cd ~/.claude && git init && git remote add origin <repo> && git fetch && git reset origin/main
echo "alias team='claude --agent orchestrator'" >> ~/.zshrc
```

## Base de conhecimento por projeto
Fica **fora do repositório**, em `~/.claude/team-state/<slug>/`, com nomes de mercado:

| Arquivo | Origem | Conteúdo |
|---|---|---|
| `product.md` | Kiro steering | Visão, usuários, funcionalidades, regras de negócio |
| `tech.md` | Kiro steering | Stack, comandos, convenções técnicas |
| `structure.md` | Kiro steering | Pastas, módulos, política de artefatos |
| `progress.md` | Cline Memory Bank | O que foi entregue, em andamento, problemas |
| `backlog.md` | — | Pendências, riscos, dívidas |
| `history.md` | — | Uma linha por entrega |
| `prd/`, `adr/`, `architecture/` | — | Artefatos quando a política é `internal` |

O `<slug>` vem do repositório principal, então é o mesmo em todos os worktrees. O hook `hooks/team-context.py` (no frontmatter do orchestrator) injeta tudo no orchestrator (`SessionStart`) e, em cada especialista (`SubagentStart`), só os arquivos do papel dele. Não é versionado (contém dados de projetos).

## Memória
Todos os agentes têm `memory: user` (em `~/.claude/agent-memory/`, não versionado). A memória concede `Write`/`Edit` automaticamente; no orchestrator e no deploy o prompt restringe essas ferramentas à pasta de memória.

## O que NÃO é versionado
Credenciais, histórico, sessões, memórias dos agentes (`agent-memory/`), settings, plugins e arquivos de contexto. Ver `.gitignore`.
