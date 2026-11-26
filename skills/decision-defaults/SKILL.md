---
name: decision-defaults
description: Padrões que a equipe adota na dúvida para decidir em vez de devolver pergunta ao orchestrator ou ao dono — nomes (código em inglês, pt-BR só em texto visível), pastas, biblioteca, erros, testes, UI — e a lista curta do que realmente vai ao dono. Usar sempre que surgir dúvida de nome, estrutura, dependência, tratamento de erro, teste ou componente de UI, e antes de escrever "Perguntas" no relatório, mesmo que a dúvida pareça pequena.
---

# Decisões padrão (decida, registre, siga)

Devolver uma pergunta custa uma rodada inteira de briefing; decidir com um padrão claro e registrar a escolha custa uma linha no relatório. Por isso, na dúvida de execução, **decida** com a ordem abaixo e deixe a escolha visível para quem quiser contestar.

## Ordem de precedência
1. `conventions.md` do projeto (na base, injetado ou citado no briefing).
2. Padrão já existente no código (procure 1 exemplo vizinho antes de criar).
3. Skill da stack (`backend-*`, `frontend-*`, `rust-standards`...).
4. Este default.

Níveis mais altos vencem porque refletem decisões já tomadas no projeto; divergir deles cria dois jeitos de fazer a mesma coisa.

## Defaults

**Nomes.** Todo código em **inglês**: variáveis, funções, classes/tipos, rotas (path e `name`), tabelas e colunas, chaves de config, nomes de arquivo de código. Português (pt-BR) só em texto visível ao usuário (labels, mensagens, copy). Comentários, commits e docs seguem o idioma do projeto; sem convenção, português. Projeto com identificadores em português: não renomeie por conta própria (renomear é mudança de contrato e de migration); siga o escopo e liste os achados na seção "Identificadores fora do padrão" do relatório, com `arquivo:linha → sugestão em inglês`. Código novo no padrão em inglês mesmo que o vizinho esteja em português.

**Pastas e módulos.** Siga a estrutura existente (`structure.md`, `conventions.md`). Arquivo novo vai ao lado de quem faz coisa parecida. Pasta ou camada nova só com razão registrada.

**Biblioteca.** Use a já instalada. Dependência nova só com justificativa de uma linha no relatório (o que a instalada não resolve), versão estável e fonte oficial verificada (skill `security-supply-chain` ao adicionar).

**Erros.** Siga o formato de erro do projeto; sem formato definido, RFC 9457 em API HTTP. Erro tratado na fronteira, mensagem ao usuário em pt-BR, detalhe técnico no log. Nunca engolir erro em silêncio.

**Testes.** Mudou comportamento, teste junto, no nível mais baixo que prova o comportamento (`test-strategy`), com o framework que o projeto já usa. Banco e serviços reais da máquina, nunca mock do que o teste quer provar.

**Ambiente local (banco, cache).** Nunca crie container próprio: use os serviços de `/worksapce/opt`, que são descartáveis (só teste e dev local). Teste automatizado: `agent_test` e banco `test_*` efêmero, apagado ao fim. "Subir local" (dev para o dono usar, só com pedido explícito): admin de `~/.config/agent-db/admin.env`, banco e usuário `dev_<projeto>` com senha gerada só no `.env` da worktree, Redis em banco lógico livre de 1 a 15; o ambiente persiste e o relatório lista o que foi criado, sem senha. Serviço quebrado: recrie (`docker compose up -d`) e registre; nunca derrube, apague `data/` nem faça `FLUSHALL` ou `down -v`, porque há outras sessões usando. Detalhe: seção "Serviços locais" do `~/.claude/CLAUDE.md`. Serviço que não está em `/worksapce/opt` (MinIO, MQTT) é pergunta ao dono.

**UI.** Reuse componente, token, layout e tela-modelo que já existem. Componente ou estilo novo só com justificativa no relatório (o que faltou). Sem biblioteca no projeto, siga a skill `design-system`.

**Dúvida de requisito pequena** (limite, ordenação padrão, tamanho de página, texto de mensagem): escolha o valor mais conservador e comum, registre como suposição.

**Antes de perguntar, procure.** Busca dirigida só daquela dúvida em spec, `decisions.md`, README do serviço, `.env.example`, issues, código e contrato do legado, e cite `arquivo:linha`. Dúvida de teste ou banco: leia a seção "Serviços locais" do `~/.claude/CLAUDE.md` e o README de `/worksapce/opt` antes de levar bloqueio ao dono; nota de ambiente na base é retrato antigo, confirme.

**Versão.** Não altere versão (`package.json`, `Cargo.toml`, fixtures, binários); features e correções entram sem bump, e várias alterações se acumulam numa versão só. O bump é uma tarefa própria de release, só quando o dono pedir.

## Como registrar
Em "Decisões tomadas" do relatório: `decisão — nível da ordem que a sustenta (conventions.md, código em arquivo:linha, skill X, default)`. O orchestrator leva as relevantes ao `decisions.md` da base.

## Quando perguntar de verdade
Só estes casos (e "Para: usuário"):
- **Regra de negócio nova**: o que o produto faz, preço, quem pode o quê.
- **Ação irreversível**: apagar dado, force push, publicar externo.
- **Jurídico ou fiscal**.
- **Merge, deploy ou produção**.
- **Falta o objetivo** da tarefa (sem ele não há o que decidir).

Pergunta fora dessa lista é decisão sua: decida e registre. Mesmo nos casos acima, siga com a suposição adotada no que não depende da resposta e marque "Bloqueia? = não" quando for verdade; o orchestrator junta as perguntas numa lista única no fim, sem parar o trabalho.

## Fontes
Política da equipe, decisão do dono em 2026-11-26. Complementa `delivery-contract` (relatório) e `~/.claude/CLAUDE.md` (idioma).
