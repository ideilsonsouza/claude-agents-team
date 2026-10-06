---
name: delivery-contract
description: Formato padrão do relatório que todo especialista da equipe devolve ao orchestrator ao terminar uma tarefa.
---

# Contrato de entrega

## Antes de começar: leitura enxuta
- O **mapa do projeto** já está no seu contexto (injetado pelo hook). Use-o para localizar código em vez de explorar.
- Leia os arquivos citados no briefing. Para o resto, busca dirigida (`Grep`/`Glob` por símbolo, rota ou nome), e abra só o trecho necessário.
- **Não** varra diretórios inteiros nem releia o projeto para "entender o contexto". Não revalide o que o briefing já afirma.
- Precisa saber se algo já existe? Consulte `implemented.md` na base antes de procurar no código.

## Higiene do repositório
- No repositório entra **só o que é produto**: código, testes, configuração, README/documentação do projeto e, se a política de artefatos for "repositório", PRDs/ADRs.
- Notas, planos, rascunhos, relatórios, scripts temporários e logs da equipe **nunca** vão para o repositório. Temporários: diretório de scratchpad da sessão (ou `/tmp`). Material que deve durar: a base do projeto (`~/.claude/team-state/<slug>/`).
- Não crie arquivos como `NOTES.md`, `TODO.md`, `PLAN.md`, `*.bak` ou pastas de trabalho no projeto. Não altere `.gitignore` do projeto para esconder arquivos da equipe.

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
- Comandos rodados (testes, lint, build) e resultado real. Se não rodou nada, diga "não verificado" e por quê.

## Decisões tomadas
- Decisão — motivo. (Só as que o orchestrator ou o usuário precisam saber.)

## Riscos e pendências
- O que ficou de fora, o que pode quebrar, perguntas em aberto.

## Atualização da base
- O que muda no mapa/implementado (módulo novo, endpoint, tabela, comando, convenção). "Nenhuma" se não mudou nada.

## Próximo passo sugerido
- Qual agente deveria agir a seguir e com qual objetivo.
```

Regras:
- **Nunca** declare sucesso sem evidência. Teste falhou → status PARCIAL e mostre a saída relevante.
- Seja conciso: o relatório é para decisão, não para narrar o processo.
- Não inclua segredos, tokens ou dados pessoais.
