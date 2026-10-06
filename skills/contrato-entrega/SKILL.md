---
name: contrato-entrega
description: Formato padrão do relatório que todo especialista da equipe devolve ao orquestrador ao terminar uma tarefa.
---

# Contrato de entrega

Ao terminar (com sucesso ou não), responda **exatamente** neste formato. O orquestrador não vê seu trabalho, só este relatório.

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
- Decisão — motivo. (Só as que o orquestrador ou o usuário precisam saber.)

## Riscos e pendências
- O que ficou de fora, o que pode quebrar, perguntas em aberto.

## Próximo passo sugerido
- Qual agente deveria agir a seguir e com qual objetivo.
```

Regras:
- **Nunca** declare sucesso sem evidência. Teste falhou → status PARCIAL e mostre a saída relevante.
- Seja conciso: o relatório é para decisão, não para narrar o processo.
- Não inclua segredos, tokens ou dados pessoais.
