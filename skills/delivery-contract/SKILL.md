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
Além do critério de pronto, rode **sempre**, com os comandos do `tech.md` (ou, se faltarem, os scripts do `package.json`/`Makefile`/`go.mod`):
1. **Typecheck/build** (`tsc --noEmit`, `vue-tsc`, `go build ./...`, `go vet ./...`).
2. **Lint** do que você alterou.
3. **Testes do módulo afetado**, não só o teste novo. Se o módulo é usado por outros, rode também os testes dos consumidores diretos.

Regras:
- Mudou comportamento e não criou nem alterou teste → status **PARCIAL**, com o motivo.
- Não desligue, pule (`.skip`, `t.Skip`), afrouxe nem apague teste ou regra de lint para ficar verde. Teste que parece errado → BLOQUEADO, com a explicação.
- Comando inexistente no projeto → diga "não existe no projeto" na Verificação. Não invente o comando.
- Falha que já existia antes da sua mudança → mostre por que ela não é sua (teste de arquivo que você não tocou, mensagem sem relação com o diff, CI da `main` vermelho) e reporte em "Riscos e pendências". Não use `git stash`, `checkout` nem `reset` para provar isso.

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
- Portão mínimo: typecheck · lint · testes do módulo — comando e resultado real de cada um (ex.: `pnpm vitest run src/orders` → 42 passed).
- Critério de pronto: comando e resultado.
- Se não rodou algo, diga "não verificado" e por quê.

## Decisões tomadas
- Decisão — motivo. (Só as que o orchestrator ou o usuário precisam saber.)

## Riscos e pendências
- O que ficou de fora, o que pode quebrar, perguntas em aberto.

## Perguntas para especialistas
(Omita se não houver.) Só perguntas cuja resposta muda a entrega.
| # | Para | Pergunta | Por que importa | Suposição adotada se não houver resposta | Bloqueia? |

## Atualização da base
- O que muda em cada arquivo da base: `progress.md` (o que foi entregue), `structure.md` (pasta/módulo novo), `tech.md` (dependência, comando, convenção), `backlog.md` (pendências). "Nenhuma" se não mudou nada.

## Próximo passo sugerido
- Qual agente deveria agir a seguir e com qual objetivo.
```

Regras:
- **Outra área:** nunca tente chamar outro agente. Pergunte em `## Perguntas para especialistas`, com `Para:` = shop-floor, legal, finance, product-designer, gtm, marketing, data-analyst, architect, dba ou usuário. Se "Bloqueia? = sim", o status é BLOQUEADO; se não, siga com a suposição e marque-a em "Decisões tomadas".
- **Quando você é o consultado:** responda só com:
  ## Respostas
  | # | Resposta | Fonte (lei/artigo/link, arquivo:linha ou skill) | Confiança (alta/média/baixa) |
  Não crie arquivos nem faça perguntas de volta a quem perguntou; dúvida sua vai em "Riscos e pendências" para o usuário.
- **legal e finance:** a primeira linha do relatório, antes de `## Status`, é `> Não é parecer jurídico. Validar com advogado.` ou `> Não é parecer contábil ou fiscal. Validar com contador.`
- **Sigilo:** não transcreva contrato, preço ou dado de cliente no relatório, na base ou na memória; cite o caminho do documento.
- **Nunca** declare sucesso sem evidência. Teste falhou → status PARCIAL e mostre a saída relevante.
- Seja conciso: o relatório é para decisão, não para narrar o processo.
- Não inclua segredos, tokens ou dados pessoais.
