# Instruções globais

## Idioma
- Responda e entregue tudo em **português do Brasil**: respostas ao usuário, relatórios de entrega dos agentes, specs, ADRs, planos e resumos.
- Vale para todos os agentes (orchestrator e especialistas) e para qualquer projeto.
- Exceções: identificadores de código, nomes de arquivos, comandos e termos técnicos consagrados ficam como estão. Em código, comentários, commits e documentação do repositório, siga o idioma já usado no projeto; sem convenção definida, use português.

## Ambiente de trabalho: Orca IDE
- O trabalho é feito no **Orca IDE**, que organiza os agentes por **worktree** (um pane por agente). Tarefas chegam como issues do Jira (ex.: `PROJ-21`).
- **Uma tarefa = uma worktree.** Em geral o usuário cria a worktree no Orca; o agente só cria (`git worktree add`) quando isso for pedido explicitamente. Worktree criada por agente fica sempre em `.worktree/<nome>` dentro do projeto, em pasta não versionada: ignore-a via `.git/info/exclude`, sem alterar `.gitignore` nem fazer commit na branch padrão.
- **Nunca troque a branch da pasta principal do repo**: ela fica na branch padrão (`main`). Trabalho em branch acontece na worktree da tarefa.
- Os hooks do Orca em `~/.claude/settings.json` e os arquivos em `~/.orca/` pertencem ao Orca: não edite nem remova. Nunca leia `~/.orca/jira-tokens`.

## Serviços locais para teste e desenvolvimento
- Agentes não criam containers de banco ou cache para teste (Testcontainers, `docker run`, compose próprio). Usam os serviços de `/worksapce/opt`: Postgres (5432), MariaDB (3306), Redis (6379), ClickHouse (8123/9000). Serviço parado: `docker compose up -d` na pasta dele.
- Serviço que não existe em `/worksapce/opt` (ex.: broker MQTT): perguntar ao dono antes; não criar por conta própria.
- Usuário restrito `agent_test`, com credenciais em `~/.config/agent-db/credentials.env` (nunca imprimir nem copiar para o repositório). Se os usuários sumirem após zerar `data/`, rodar `/worksapce/opt/scripts/agent-test-users.sh`.
- Isolamento: cada execução cria seu banco `test_<projeto>_<id>` e o apaga ao terminar, mesmo se o teste falhar. No Redis, testes da aplicação usam banco lógico próprio entre 1 e 15, nunca o 0, e só limpam o banco que reservaram. O `agent_test` do Redis só alcança chaves `test:*`; aplicação que usa outros prefixos (ex.: filas) conecta com a credencial de dev do README de `/worksapce/opt`, respeitando a mesma regra de banco lógico.
- Proibido: `docker compose down -v`, apagar `data/`, `FLUSHALL`, `FLUSHDB` no db 0, mexer em banco que a execução não criou. Não derrubar serviços compartilhados.
- Conferir ao terminar que não sobrou banco ou chave da execução.
- Acesso: MCP de Redis e ClickHouse nos agentes `dba`, `backend` e `qa`. Postgres e MariaDB via `docker exec` com `psql`/`mariadb` e o usuário `agent_test`.
- Se o `agent_test` não bastar (ex.: extensão que exige superusuário), usar admin só dentro do banco de teste da execução e registrar no relatório.
- Vale só nesta máquina. No CI, usar os serviços da própria esteira.
- Todo banco roda em UTC, inclusive bancos novos.

## Processos compartilhados
- Esta máquina roda várias sessões de agentes ao mesmo tempo. Ao encerrar processos, mate só os que a sua execução criou, sempre por PID (`kill <pid>`, com o PID guardado ao iniciar o processo).
- Proibido `pkill -f`, `pkill` por nome e `killall` para navegador, Node, Vite, Go, Docker ou qualquer padrão que possa casar com processo de outra sessão. Ex.: `pkill -f chrome-headless-shell` derruba os testes de todas as sessões.
- Se não souber o PID, localize com `pgrep -a` ou `ps`, confira o diretório de trabalho e o pai de cada processo, e mate só o que comprovadamente é seu. Na dúvida, deixe o processo vivo e relate.

## Perfis de projeto
O hook da equipe informa o perfil ("Perfil do projeto: equipe|solo"). Sem o hook, deduza o perfil assim: (1) arquivo `perfil` em `~/.claude/team-state/<slug>/`; (2) remote ou caminho do projeto que casa com as regex de `~/.claude/team-orgs` (arquivo local, não versionado) = **equipe**; (3) senão = **solo**.

**Equipe (projeto marcado como equipe; há outras pessoas no repo):**
- Branch `<tipo>/<CHAVE>-<descricao>` com a chave do Jira em maiúsculas (ex.: `docs/PROJ-21-arquitetura-core`).
- Commits em Conventional Commits com rodapé `Refs: <CHAVE>`; título do PR com a chave (ex.: `docs: levanta arquitetura do core (PROJ-21)`).
- **Tarefa finalizada e revisada** (testes/typecheck verdes e diff revisado) → push da branch e **abertura do PR para a `main` automaticamente**, seguindo o template do repo.
- **Merge na `main` só com pedido expresso do usuário.** Nunca push direto na `main`.
- Não mexa em branches, PRs ou worktrees de outras pessoas; nunca rebase nem force push em branch compartilhada.

**Solo (demais projetos):** fluxo a definir por projeto. Até lá: branch por tarefa e Conventional Commits; push, PR e merge só com pedido explícito.

## Commits e PRs
- Autor é sempre o usuário git autenticado. Sem `Co-Authored-By`, sem "Generated with ..." e sem link de sessão (atribuição desligada em `settings.json`).

# graphify
- **graphify** (`~/.claude/skills/graphify/SKILL.md`) - any input to knowledge graph. Trigger: `/graphify`
When the user types `/graphify`, use the installed graphify skill or instructions before doing anything else.
