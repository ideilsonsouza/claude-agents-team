---
name: delivery-contract
description: Formato padrão do relatório que todo especialista da equipe devolve ao orchestrator ao terminar uma tarefa.
---

# Contrato de entrega

## Antes de começar: leitura enxuta
- Os arquivos da base relevantes ao seu papel (`tech.md`, `structure.md`, ...) já estão no seu contexto, injetados pelo hook. Use-os para localizar código em vez de explorar.
- Leia os arquivos citados no briefing. Para o resto, busca dirigida (`Grep`/`Glob` por símbolo, rota ou nome), e abra só o trecho necessário.
- **Não** varra diretórios inteiros nem releia o projeto para "entender o contexto". Não revalide o que o briefing já afirma.
- Precisa saber se algo já existe? Consulte `progress.md` na base antes de procurar no código.

## Busca econômica
1. Antes de buscar, consulte o `structure.md` da base injetada.
2. Primeiro só nomes de arquivo: `Grep` com `output_mode: files_with_matches` e filtro `glob`/`type`.
3. Depois só as linhas: `Grep` com `-n`, `head_limit` e contexto pequeno (`-C` ≤ 3).
4. Leia só o trecho: `Read` com `offset`/`limit` (≤ ~60 linhas). Arquivo inteiro só se for pequeno ou se a tarefa exigir.
5. Agentes com Bash no Linux não recebem as ferramentas `Grep`/`Glob` (comportamento do Claude Code). Use o `grep`/`find` do Bash com limites: `grep -rl`, `grep -n -m N`, `rg -l`/`rg -n -m N`, `sed -n 'a,bp'`. Nunca `cat` de arquivo grande.
6. Não repita uma busca que já respondeu.

## Fontes de verdade (anti-alucinação)
Ordem de confiança — use a mais alta disponível e **nunca** a memória do modelo quando uma fonte melhor existe:
1. **Código e configuração do projeto** (o que está escrito agora).
2. **Versão instalada** das dependências (`go.mod`/`go.sum`, `package.json` + lockfile, tipos em `node_modules`, `go doc`).
3. **Documentação oficial da versão em uso**: Context7 primeiro (`mcp__context7__resolve-library-id` → `mcp__context7__query-docs`, informando a versão instalada); `WebFetch` na doc oficial se o Context7 não tiver a biblioteca. Uma consulta focada por dúvida, não por precaução.
4. Skills da equipe.
5. Memória do modelo — só para o que não pode ser verificado, e marcado como suposição.

Regras:
- **Não invente** APIs, flags, opções de config, nomes de arquivo, rotas ou colunas. Antes de usar, confirme que existe (busca no código ou na dependência instalada).
- Toda afirmação factual no relatório tem evidência: `arquivo:linha`, saída de comando ou link de doc.
- Não sabe ou não conseguiu verificar? Escreva **"não verificado"** ou pergunte. Suposição explícita é aceitável; suposição silenciosa não.
- Requisito ambíguo → pare e liste a dúvida no relatório (status BLOQUEADO) em vez de escolher uma interpretação sozinho.
- Rode o comando de verificação do critério de pronto **antes** de reportar. Reporte o resultado real, inclusive falhas.

## Portão mínimo (quem altera código)
Além do critério de pronto, rode **sempre**, com os comandos do `tech.md` (ou, se faltarem, os scripts do `package.json`/`Makefile`/`go.mod`) — ou o portão padrão `~/.claude/scripts/portao.sh <dir>`, que já usa o portão próprio do projeto quando existe; cole a última linha (`PORTÃO: ...`) como evidência:
1. **Typecheck/build** (`tsc --noEmit`, `vue-tsc`, `go build ./...`, `go vet ./...`).
2. **Lint** do que você alterou.
3. **Testes do módulo afetado**, não só o teste novo. Se o módulo é usado por outros, rode também os testes dos consumidores diretos.

Regras:
- Mudou comportamento e não criou nem alterou teste → status **PARCIAL**, com o motivo.
- **Skip não é verde.** Rode com as variáveis do portão (banco, Redis, objeto, owner) nos pacotes tocados e nos que montam o que mudou: meta 0 SKIP; SKIP > 1 pede motivo no relatório (22 SKIP já esconderam 12 testes quebrados).
- **Prova = o job inteiro do módulo pelo portão** (`portao.sh` ou o script do projeto), não só os pacotes tocados (guarda estática de outro pacote passa batida). FAIL só no portão: suspeite antes de recurso compartilhado (banco, porta, coluna UNIQUE) e de ambiente diferente do CI (superusuário x papéis reais, FORCE RLS) do que do código.
- Portão com container de nome ou porta fixos roda um por vez: serialize com `flock` num arquivo de lock.
- Não desligue, pule (`.skip`, `t.Skip`), afrouxe nem apague teste ou regra de lint para ficar verde. Teste que parece errado → BLOQUEADO, com a explicação.
- Comando inexistente no projeto → diga "não existe no projeto" na Verificação. Não invente o comando.
- Falha que já existia antes da sua mudança → mostre por que ela não é sua (teste de arquivo que você não tocou, mensagem sem relação com o diff, CI da `main` vermelho) e reporte em "Riscos e pendências". Não use `git stash`, `checkout` nem `reset` para provar isso.

## Comandos Bash que travam a sessão
- Não misture `rm` com `eval`, `source`/`.`, `$(...)`, crase, `${!var}`, `$$` nem `cd ... && rm <glob>` no mesmo comando: o Claude Code pede confirmação humana (mesmo em bypass) e agente em segundo plano fica parado. O hook `bash-rm-guard.py` recusa esse formato.
- Faça: `rm` sozinho, com caminhos literais, em comando separado; ou ponha a lógica num script `.sh` e execute o script. Em vez de `eval`, leia um arquivo de estado com variáveis nomeadas.
- Apague só pelo nome exato que você criou (guarde bancos, papéis, volumes e pastas temporárias), nunca por prefixo ou glob (`rm -rf /tmp/tmp.*`, `DROP` por prefixo): outras sessões usam a mesma máquina.
- Espera sempre com teto (`timeout 900`, no máximo 160 s por chamada em laço de CI) e nada em segundo plano ao fim; antes do relatório, `pgrep -af '[s]leep|[u]ntil'` e encerre só o seu, por PID. O colchete evita casar com o próprio `pgrep`.
- Prova ou variável que vale para várias fatias não fica no scratchpad (some no reboot): grave na base do projeto ou deixe recriável a partir dela.

## Higiene do repositório
- No repositório entra **só o que é produto**: código, testes, configuração, README/documentação do projeto e, se a política de artefatos for "repositório", PRDs/ADRs.
- Notas, planos, rascunhos, relatórios, scripts temporários e logs da equipe **nunca** vão para o repositório. Temporários: diretório de scratchpad da sessão (ou `/tmp`). Material que deve durar: a base do projeto (`~/.claude/team-state/<slug>/`).
- Não crie arquivos como `NOTES.md`, `TODO.md`, `PLAN.md`, `*.bak` ou pastas de trabalho no projeto. Não altere `.gitignore` do projeto para esconder arquivos da equipe.

## Idioma
- Escreva o relatório de entrega **em português do Brasil** (identificadores, caminhos e comandos ficam como estão).

## Ao terminar

Ao terminar (com sucesso ou não), responda **exatamente** neste formato. O orchestrator não vê seu trabalho, só este relatório.

```
## Status
CONCLUÍDO | PARCIAL | BLOQUEADO — uma frase explicando.

## O que foi feito
- Item objetivo por linha.

## Arquivos alterados
- caminho/arquivo — criado | alterado | removido — motivo curto

## Verificação
- Portão mínimo: typecheck · lint · testes do módulo e critério de pronto: **comando e saída real em bloco de código** (` ``` `), uma linha `$ comando` seguida da saída (as últimas linhas bastam). Texto solto ou inline não conta; o hook `evidence-guard.py` devolve o relatório sem bloco.
- Se não rodou algo, diga "não verificado" e por quê (status PARCIAL).

## Limpeza
- Criado pela execução → prova de remoção (comando + saída curta). Cobrir: worktree extra criada por você (não a worktree da tarefa, que o `pr` remove ao fechar; a do Orca nunca é removida), bancos `test_*`, chaves Redis, containers, artefatos de teste (`test-results`, `playwright-report`, `coverage`), temporários, processos (por PID). "Nada criado" se for o caso. Seção ausente ou vazia: o hook devolve o relatório.

## Decisões tomadas
- Decisão — motivo. (Só as que o orchestrator ou o usuário precisam saber.)

## Riscos e pendências
- O que ficou de fora, o que pode quebrar, perguntas em aberto.

## Perguntas para especialistas
(Omita se não houver.) Só perguntas cuja resposta muda a entrega.
| # | Para | Pergunta | Por que importa | Suposição adotada se não houver resposta | Bloqueia? |

## Identificadores fora do padrão
(Omita se não houver.) Identificador em português achado no projeto, que você não renomeou:
| arquivo:linha | identificador atual | sugestão em inglês |

## Atualização da base
- Insumo para a curadoria do `docs` (o orchestrator não grava arquivo por arquivo). O que muda: `progress.md` (estado atual), `decisions.md` (decisão nova, com fonte), `structure.md` (pasta/módulo novo), `tech.md` (dependência, comando, convenção), `backlog.md` (pendências). "Nenhuma" se não mudou nada.

## Próximo passo sugerido
- Qual agente deveria agir a seguir e com qual objetivo.
```

## Variante tarefa P (curta)
Quando o briefing disser "tarefa P", entregue só isto (até ~12 linhas, fora a saída colada):
```
## Status
CONCLUÍDO | PARCIAL | BLOQUEADO — uma frase.
## O que mudou
- arquivo — o que mudou (uma linha por arquivo).
## Evidência
(um bloco de código: `$ comando` e a saída real dos testes do módulo)
## Limpeza
Nada criado | o que criou e a prova de remoção.
```
Rode só os testes do módulo (não o portão inteiro). Decisão que o dono precisa saber, risco ou pergunta que muda a entrega: acrescente a seção correspondente do formato completo, só se houver. Mudança sensível (autenticação, autorização, tenant, migration, segredos, pagamento, fiscal, dado pessoal, integração externa) não é tarefa P: use o formato completo.

Regras:
- **Variável de ambiente nova ou alterada** (relatório, descrição do PR e resposta ao dono): `VAR=valor → app X (nome no painel ou variable do GitHub Actions), obrigatória ou opcional, padrão Y, exige Redeploy?`. O dono não deve adivinhar onde ela entra.
- **Versão:** não altere versão (`package.json`, `Cargo.toml`, fixtures, binários) sem pedido do dono; o bump é uma tarefa própria de release.
- **Limpeza obrigatória:** sem a seção "Limpeza" com prova, o status não pode ser CONCLUÍDO. Proibido `prune` de volumes (`docker volume prune`, `docker system prune --volumes`).
- **Tamanho:** relatório de até ~25 linhas, fora as saídas coladas. Não descreva o que não mudou nem narre o processo.
- **Fatias:** quem implementa a fatia roda os testes do módulo e cola a saída no relatório; `qa` e `reviewer` não rodam a cada fatia, só uma vez no fim da feature, sobre o diff inteiro. Exceção: revisão por fatia em mudança sensível (autenticação, autorização, tenant, migration, segredos, pagamento, fiscal, dado pessoal e integração externa).
- **Outra área:** nunca tente chamar outro agente. Pergunte em `## Perguntas para especialistas`, com `Para:` = shop-floor, legal, finance, product-designer, gtm, marketing, data-analyst, architect, dba ou usuário. Se "Bloqueia? = sim", o status é BLOQUEADO; se não, siga com a suposição e marque-a em "Decisões tomadas".
- **Quando você é o consultado:** responda só com:
  ## Respostas
  | # | Resposta | Fonte (lei/artigo/link, arquivo:linha ou skill) | Confiança (alta/média/baixa) |
  Não crie arquivos nem faça perguntas de volta a quem perguntou; dúvida sua vai em "Riscos e pendências" para o usuário.
- **legal e finance:** a primeira linha do relatório, antes de `## Status`, é `> Não é parecer jurídico. Validar com advogado.` ou `> Não é parecer contábil ou fiscal. Validar com contador.`
- **Idioma do código:** todo código em inglês (variáveis, funções, tipos, rotas path e name, tabelas, colunas, chaves de config, nomes de arquivo de código); pt-BR só em texto visível ao usuário. Identificador em português já existente no projeto: não renomeie por conta própria, liste na seção "Identificadores fora do padrão". Dúvida de execução: decida pela skill `decision-defaults` e registre em "Decisões tomadas"; pergunta só nos casos dessa skill.
- **Sigilo:** não transcreva contrato, preço ou dado de cliente no relatório, na base ou na memória; cite o caminho do documento.
- **Nunca** declare sucesso sem evidência. Teste falhou → status PARCIAL e mostre a saída relevante.
- Seja conciso: o relatório é para decisão, não para narrar o processo.
- Não inclua segredos, tokens ou dados pessoais.
