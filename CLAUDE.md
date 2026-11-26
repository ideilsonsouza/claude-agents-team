# Instruções globais

## Idioma
- Responda e entregue tudo em **português do Brasil**: respostas ao usuário, relatórios de entrega dos agentes, specs, ADRs, planos e resumos.
- Vale para todos os agentes (orchestrator e especialistas) e para qualquer projeto.
- Exceções: comandos e termos técnicos consagrados ficam como estão.
- **Código em inglês, sempre:** variáveis, funções, classes/tipos, rotas (path e name), tabelas e colunas, chaves de config e nomes de arquivo de código. pt-BR só em texto visível ao usuário (labels, mensagens, copy).
- Comentários, commits e documentação do repositório: siga o idioma já usado no projeto; sem convenção definida, use português.
- Identificador em português encontrado num projeto: não renomeie por conta própria; liste no relatório, em "Identificadores fora do padrão" (arquivo:linha → sugestão em inglês).

## Ambiente de trabalho: Orca IDE
- O trabalho é feito no **Orca IDE**, que organiza os agentes por **worktree** (um pane por agente). Cada tarefa tem a sua worktree; a origem das tarefas (issue do GitHub ou, no futuro, a central dos agentes) pode fornecer um id.
- **Uma tarefa = uma worktree.** Em geral o usuário cria a worktree no Orca; o agente só cria (`git worktree add`) quando isso for pedido explicitamente. Worktree criada por agente fica sempre em `.worktree/<nome>` dentro do projeto, em pasta não versionada: ignore-a via `.git/info/exclude`, sem alterar `.gitignore` nem fazer commit na branch padrão.
- **Nunca troque a branch da pasta principal do repo**: ela fica na branch padrão (`main`). Trabalho em branch acontece na worktree da tarefa.
- Os hooks do Orca em `~/.claude/settings.json` e os arquivos em `~/.orca/` pertencem ao Orca: não edite nem remova. Nunca leia arquivos de token em `~/.orca/`.

## Serviços locais para teste e desenvolvimento
- Agentes não criam containers de banco ou cache, nem para teste nem para dev (Testcontainers, `docker run`, compose próprio). Usam os serviços de `/worksapce/opt`: Postgres (5432), TimescaleDB (5433), MariaDB (3306), Redis (6379), ClickHouse (8123/9000). Serviço parado: `docker compose up -d` na pasta dele.
- Serviço que não existe em `/worksapce/opt` (ex.: broker MQTT): perguntar ao dono antes; não criar por conta própria.
- Usuário restrito `agent_test`, com credenciais em `~/.config/agent-db/credentials.env` (nunca imprimir nem copiar para o repositório). Se os usuários sumirem após zerar `data/`, rodar `/worksapce/opt/scripts/agent-test-users.sh`.
- Isolamento: cada execução cria seu banco `test_<projeto>_<id>` e o apaga ao terminar, mesmo se o teste falhar. No Redis, testes da aplicação usam banco lógico próprio entre 1 e 15, nunca o 0, e só limpam o banco que reservaram. O `agent_test` do Redis só alcança chaves `test:*`; aplicação que usa outros prefixos (ex.: filas) conecta com a credencial admin de `admin.env` (Redis, usuário `default`), respeitando a mesma regra de banco lógico.
- Proibido, porque há outras sessões usando os mesmos serviços ao mesmo tempo (não por causa dos dados, que são descartáveis): `docker compose down -v`, apagar `data/`, `FLUSHALL`, `FLUSHDB` no db 0, mexer em banco que a execução não criou, derrubar ou reiniciar serviço em uso.
- Conferir ao terminar que não sobrou banco ou chave da execução.
- Acesso: MCP de Redis e ClickHouse nos agentes `dba`, `backend` e `qa`. Postgres e MariaDB via `docker exec` com `psql`/`mariadb` e o usuário `agent_test`.
- Admin em `~/.config/agent-db/admin.env` (chmod 600; nunca imprimir nem copiar para o repositório): para o que o `agent_test` não alcança em testes (extensão que exige superusuário, papel), só dentro do banco da execução, registrado no relatório; e para "subir local" (abaixo).
- Vale só nesta máquina. No CI, usar os serviços da própria esteira.
- Todo banco roda em UTC, inclusive bancos novos.
- **Subir local** (dev, para o dono usar; só com pedido explícito, pois o boot da app roda migrations; pedido de `.env` sozinho não basta): use os serviços de `/worksapce/opt` com as credenciais de `~/.config/agent-db/admin.env`. Crie banco e usuário próprios do projeto (`dev_<projeto>`, senha gerada e gravada só no `.env` da worktree) e, no Redis, um banco lógico livre de 1 a 15. O ambiente de dev persiste: não apague ao fim. O relatório lista o que foi criado (banco, usuário, banco lógico; nunca a senha). Sem containers próprios para banco ou cache; serviço que não está em `/worksapce/opt` (MinIO, MQTT): pergunte ao dono.
- Os serviços de `/worksapce/opt` são descartáveis (só teste e dev local, nada importante): se um quebrar, o agente pode recriá-lo (`docker compose up -d`, `scripts/agent-test-users.sh`) e registra no relatório. As proibições acima continuam por causa das outras sessões em uso.

## Processos compartilhados
- Esta máquina roda várias sessões de agentes ao mesmo tempo. Ao encerrar processos, mate só os que a sua execução criou, sempre por PID (`kill <pid>`, com o PID guardado ao iniciar o processo).
- Proibido `pkill -f`, `pkill` por nome e `killall` para navegador, Node, Vite, Go, Docker ou qualquer padrão que possa casar com processo de outra sessão. Ex.: `pkill -f chrome-headless-shell` derruba os testes de todas as sessões.
- `pgrep -f <script>` casa com a própria linha: use o colchete (`'[s]cripts/x.sh'`) e sempre com `timeout`. Espera de comando só com teto, nunca `until pgrep` sem limite.
- Se não souber o PID, localize com `pgrep -a` ou `ps`, confira o diretório de trabalho e o pai de cada processo, e mate só o que comprovadamente é seu. Na dúvida, deixe o processo vivo e relate.

## Perfis de projeto
O hook da equipe informa o perfil ("Perfil do projeto: equipe|solo"). Sem o hook, deduza o perfil assim: (1) arquivo `perfil` em `~/.claude/team-state/<slug>/`; (2) remote ou caminho do projeto que casa com as regex de `~/.claude/team-orgs` (arquivo local, não versionado) = **equipe**; (3) senão = **solo**.

**Equipe (projeto marcado como equipe; há outras pessoas no repo):**
- Branch `<tipo>/<descricao-curta>` (ex.: `docs/arquitetura-core`); se a tarefa tiver id (issue do GitHub ou, no futuro, da central), pode ser `<tipo>/<id>-<descricao>`.
- Commits em Conventional Commits, sem rodapé `Refs:` obrigatório (use `Refs: #<n>` só se houver issue); título do PR sem chave obrigatória (ex.: `docs: levanta arquitetura do core`).
- **Tarefa finalizada e revisada** (testes/typecheck verdes e diff revisado) → push da branch e **abertura do PR para a `main` automaticamente**, seguindo o template do repo.
- **Merge na `main` só com pedido expresso do usuário.** Nunca push direto na `main`.
- Não mexa em branches, PRs ou worktrees de outras pessoas; nunca rebase nem force push em branch compartilhada.

**Solo (demais projetos):** fluxo a definir por projeto. Até lá: branch por tarefa e Conventional Commits; push, PR e merge só com pedido explícito.

## Commits e PRs
- Autor é sempre o usuário git autenticado. Sem `Co-Authored-By`, sem "Generated with ..." e sem link de sessão (atribuição desligada em `settings.json`).
