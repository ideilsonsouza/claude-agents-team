# Equipe de agentes — Claude Code

Equipe global de desenvolvimento: um orquestrador (Opus 5.5) que nunca executa, só delega, e dez especialistas.

## Uso
```bash
equipe                          # abre sessão com o orquestrador (alias de: claude --agent orquestrador)
equipe "implementa login OAuth" # já abre com a tarefa
```
Dentro de uma sessão comum também dá para usar `@agent-orquestrador ...`, mas sem a trava de agentes permitidos.

## Equipe
| Agente | Modelo | Papel |
|---|---|---|
| orquestrador | claude-opus-5-5 | Classifica, planeja, delega, confere. Só pode chamar os agentes abaixo |
| arquiteto | opus | Arquitetura, decisões técnicas, ADRs (chamado sempre que houver decisão estrutural) |
| prd | opus | PRD, critérios de aceite, contrato de API |
| dba | sonnet | Schema, migrations SQL, índices, performance de queries |
| backend | sonnet | Go, Fastify, AdonisJS (não cria migrations) |
| frontend | sonnet | Vue, React, Astro + design system e UI/UX |
| qa | sonnet | Testes e validação contra critérios de aceite |
| docs | sonnet | README, guias, documentação de API |
| pr | sonnet | Único que faz commit/push/PR; revisa diff |
| devops | sonnet | Escreve CI/CD, Docker, IaC (não faz deploy) |
| deploy | sonnet | Executa release e rollback (não edita pipeline) |

O orquestrador pode trocar o modelo por chamada (haiku → sonnet → opus), nunca acima de opus.

## Skills
| Skill | Pré-carregada em |
|---|---|
| contrato-entrega | todos os especialistas |
| prd-template | prd |
| adr-template | arquiteto |
| padroes-sql | dba |
| base-conhecimento | docs (o orquestrador segue as regras pelo prompt) |
| git-convencoes | pr |
| deploy-checklist | deploy |
| padroes-backend | backend (+ `backend-go`/`backend-fastify`/`backend-adonisjs` sob demanda, conforme a stack) |
| padroes-frontend, design-system, ui-ux | frontend (+ `frontend-vue`/`frontend-react`/`frontend-astro` sob demanda) |

## Instalar em outra máquina
```bash
git clone <repo> /tmp/equipe && cp -r /tmp/equipe/{agents,skills,README.md,.gitignore} ~/.claude/
cd ~/.claude && git init && git remote add origin <repo> && git fetch && git reset origin/main
echo "alias equipe='claude --agent orquestrador'" >> ~/.zshrc
```

## Base de conhecimento por projeto
Fica **fora do repositório**, em `~/.claude/equipe-estado/<slug>/` (`mapa.md`, `implementado.md`, `pendencias.md`, `historico.md` e, se a política for interna, `prd/`, `adr/`, `arquitetura/`). O `<slug>` vem do repositório principal, então é o mesmo em todos os worktrees.

O hook `hooks/equipe-contexto.py`, declarado no frontmatter do orquestrador, injeta a base no orquestrador (`SessionStart`) e o mapa em cada especialista (`SubagentStart`). Assim ninguém relê o projeto para saber o que já existe. Não é versionado (contém dados de projetos).

## Memória
Todos os agentes têm `memory: user` (em `~/.claude/agent-memory/`, não versionado). A memória concede `Write`/`Edit` automaticamente; no orquestrador e no deploy o prompt restringe essas ferramentas à pasta de memória.

## O que NÃO é versionado
Credenciais, histórico, sessões, memórias dos agentes (`agent-memory/`), settings, plugins e arquivos de contexto. Ver `.gitignore`.
