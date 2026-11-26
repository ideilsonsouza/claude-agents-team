---
name: knowledge-base
description: Estrutura e regras da base de conhecimento de projeto da equipe (fora do repositório), com nomes de mercado — product, tech, structure (steering do Kiro), conventions, progress (Memory Bank do Cline), backlog e history — e como fazer o mapeamento inicial e a curadoria.
---

# Base de conhecimento do projeto

Cada projeto tem uma base **fora do repositório**, em `~/.claude/team-state/<slug>/`. O caminho exato é injetado no contexto pelo hook da equipe. Ela substitui reler o código para descobrir "o que já existe".

Os nomes seguem padrões de mercado: **steering files do Kiro** (`product.md`, `tech.md`, `structure.md`) e **Memory Bank do Cline** (`progress.md`). Se um dia a base for levada para dentro de um projeto, a estrutura é reconhecível por outras ferramentas.

## Arquivos

| Arquivo | Conteúdo | Injetado em | Tamanho alvo |
|---|---|---|---|
| `product.md` | O quê e para quem: visão, usuários, proposta de valor, funcionalidades principais, regras de negócio-chave | orchestrator, architect, prd, docs | ~80 linhas |
| `tech.md` | Com o quê: stack, versões, banco, ferramentas, **comandos** (rodar, testar, lint, build, migrations), convenções técnicas, integrações externas | orchestrator e quase todos | ~80 linhas |
| `structure.md` | Onde: árvore de pastas comentada, módulos e responsabilidades, convenções de nomes, **política de artefatos** | orchestrator, architect, dba, backend, frontend, qa, docs, devops | ~80 linhas |
| `conventions.md` | Como se escreve neste projeto: idioma dos identificadores, padrão de rotas, componentes e tokens de UI em uso, telas-modelo (caminhos), padrões de pasta. Manda sobre as skills; o orchestrator cola o trecho relevante no briefing | backend, frontend, rust, dba, supabase, qa, reviewer, devops, product-designer, docs (orchestrator lê sob demanda) | ~40 linhas |
| `domain.md` | Domínio: glossário, entidades e invariantes, fórmulas e regras de cálculo (com fonte), normas aplicáveis | prd, dba, product-designer, shop-floor, finance, data-analyst | ~80 linhas |
| `business.md` | Negócio: modelo, ICP, posicionamento, planos e preço de **lista**, canais e metas, restrições | legal, finance, gtm, marketing | ~80 linhas |
| `decisions.md` | **Fonte única das decisões**: id `D-xx`, data, decisão (1–2 linhas), status (`vigente` \| `substituída por D-xx`), fonte (ADR/spec). Os demais arquivos não repetem decisões, apontam para `D-xx` | orchestrator, architect, prd | só decisões; compacta ao passar de ~80 linhas |
| `progress.md` | **Só o estado atual**: entregue (onde está, endpoints, tabelas), em andamento, problemas conhecidos. É **reescrito**, nunca recebe acréscimos | orchestrator, prd | **≤ ~40 linhas** |
| `backlog.md` | Próximos passos, riscos, dívidas técnicas, perguntas em aberto | orchestrator | lista viva |
| `history.md` | Uma linha por entrega: `AAAA-MM-DD · agente(s) · resumo`; uma por devolução ao especialista: `AAAA-MM-DD · devolução: <agente> · <tarefa> · causa: <categoria>` com categoria fixa: `briefing incompleto`, `requisito`, `convenção`, `teste`, `evidência`, `outro` | **não é injetado** (consulta) | só acrescenta |
| `specs/<data>-<feature>/` | `requirements.md`, `design.md`, `tasks.md` (skill `spec-workflow`); entregues vão para `specs/_archive/` | sob demanda | — |
| `domain/`, `business/{legal,finance,gtm,marketing}/`, `design/`, `analytics/` | Material detalhado dos agentes de domínio | sob demanda | — |
| `adr/`, `architecture/` | ADRs e docs de arquitetura quando a política for **internal** | sob demanda | — |

O hook injeta até 9.500 caracteres por agente. Limites: ~80 linhas por arquivo de steering e ~40 linhas no `progress.md`; o detalhe vai para arquivos à parte.

Limite por arquivo de steering (`product`, `tech`, `structure`, `decisions`): **~80 linhas**. Passou, o `docs` compacta na curadoria (detalhe vai para arquivo à parte na base, com link).

## Modelos

### `product.md`
```markdown
# Product — <projeto>
## Visão
## Usuários
## Funcionalidades principais
## Regras de negócio-chave
```

### `tech.md`
```markdown
# Tech — <projeto>
## Stack
Linguagens/versões, frameworks, banco, ORM/migrations, testes, CI, hospedagem.
## Comandos
| Ação | Comando |
## Convenções técnicas
Padrões do projeto que divergem ou especializam as skills da equipe.
## Integrações externas
```

### `structure.md`
```markdown
# Structure — <projeto>
## Árvore
Pastas principais com uma linha de comentário cada (só o que ajuda a localizar código).
## Módulos
| Módulo | Onde | Responsabilidade |
## Convenções de nomes
## Artefatos da equipe
Política: internal | repo
- internal → specs, ADRs e docs de arquitetura em `<base>/specs`, `<base>/adr`, `<base>/architecture`
- repo → em `docs/specs`, `docs/adr`, `docs/architecture` do projeto
```

### `conventions.md`
```markdown
# Conventions — <projeto>
## Idioma
Identificadores em inglês (regra da equipe); pt-BR só em texto visível ao usuário. Comentários, commits e docs: idioma do projeto.
Legado em português (não renomear sem decisão): arquivo:linha → sugestão em inglês (lista curta; o resto vai ao `backlog.md`).
## Rotas
Padrão de path e de `name` (exemplo real: arquivo:linha).
## Pastas
Onde cada tipo de arquivo vai (módulo, componente, teste, migration).
## UI
Biblioteca e tokens em uso (caminho do `@theme`/tema), componentes compartilhados (caminho), layouts, padrões de formulário/tabela/estados.
## Telas-modelo
| Tipo de tela | Caminho |
## Outras
Erros, logs, testes, config: só o que diverge das skills.
```
Só fatos verificados no código, cada um com caminho de exemplo. Convenção ausente fica de fora (não invente).

### `progress.md`
```markdown
# Progress — <projeto>
Atualizado: AAAA-MM-DD  (arquivo reescrito a cada curadoria; ≤ ~40 linhas)
## Entregue
- <funcionalidade> — arquivos-chave, endpoints, tabelas (decisões: só `D-xx`)
## Em andamento
## Problemas conhecidos
```

### `domain.md`
```markdown
# Domain — <projeto>
Tipo de produto: chão de fábrica | SaaS | ERP | CRM | e-commerce
## Glossário
| Termo | Definição | Não confundir com |
## Entidades e invariantes
## Fórmulas e regras de cálculo (com fonte)
## Normas e regulação aplicáveis (nome + link) → detalhes em domain/ ou business/
```
Entra: termos, regras e fórmulas do negócio com fonte, nome e link de norma. Não entra: texto integral de lei, dado de cliente, contrato.

### `business.md`
```markdown
# Business — <projeto>
## Modelo de negócio (quem paga, por quê, como)
## ICP e personas
## Posicionamento e diferencial
## Planos e preço de lista (públicos; nunca preço negociado com cliente)
## Canais e metas (com número e prazo)
## Restrições (regime tributário da empresa, contratos-padrão, LGPD) → links para business/
```
Entra: preço de lista público, planos, ICP, metas, regime tributário da empresa. Não entra: contrato de cliente, preço negociado ou desconto por cliente, dados de cliente. Quando o especialista precisar de um contrato, o usuário passa o caminho no pedido.

## Mapeamento inicial (feito uma vez pelo `docs`)
1. Leia manifestos e configuração (`go.mod`, `package.json`, configs de framework, CI, `docker-compose`), README existente e a árvore de diretórios (`git ls-files` resumido por pasta).
2. Abra apenas arquivos de entrada e um exemplo representativo por módulo. **Não leia o projeto inteiro.**
3. Escreva `product.md`, `tech.md`, `structure.md`, **`conventions.md`** e um `progress.md` inicial. Para o `conventions.md`: leia 1 tela, 1 rota/controller e 1 teste representativos, o `@theme`/tema e a pasta de componentes compartilhados; registre idioma dos identificadores, padrão de rotas, componentes e tokens em uso, telas-modelo (caminhos) e padrões de pasta, sempre com um caminho de exemplo. Política de artefatos: **internal**, salvo instrução contrária.

## Regras de manutenção
- O orchestrator **não atualiza a base arquivo por arquivo**. Tarefa P: acrescenta 1 linha ao `history.md`. Tarefa M/G: ao fechar, delega ao `docs` a **curadoria** (abaixo), numa chamada só, com as seções "Atualização da base" de todos os relatórios (skill `delivery-contract`). O orchestrator decide o que entra; o `docs` executa.
- Fatos, não intenções. Se algo foi removido do código, remova da base.
- `domain.md` nasce de uma tarefa do `shop-floor` (produto industrial) ou do `prd` (outros), e `business.md` de uma tarefa do `gtm` com consulta ao `finance`. O texto é proposto pelos agentes de domínio em "Atualização da base", aprovado pelo orchestrator e gravado pelo `docs` na curadoria.
- Contratos e preços de cliente nunca entram na base.
- Nunca grave segredos, credenciais ou dados pessoais de clientes.

### `decisions.md`
```markdown
# Decisions — <projeto>
| Id | Data | Decisão | Status | Fonte |
| D-01 | AAAA-MM-DD | <1–2 linhas> | vigente \| substituída por D-xx | adr/0001 ou specs/<feature> |
```
Decisão nova que contradiz uma antiga: a antiga passa a `substituída por D-xx`. Outros arquivos citam só `D-xx`, sem repetir o texto.

## Curadoria da base (feita pelo `docs`, ao fechar tarefa M/G)
Escreve apenas em `~/.claude/team-state/<slug>/`. Não decide conteúdo novo: aplica o que o orchestrator aprovou.
1. **Aplicar** as seções "Atualização da base" recebidas: entregas em `progress.md` (reescrito), decisões em `decisions.md` (inclusive as **decisões autônomas** do orchestrator e dos especialistas, cada uma com fonte), estrutura/stack em `structure.md`/`tech.md`, convenção nova ou componente/token/tela-modelo novo em `conventions.md` (e identificadores em português que os relatórios listaram em "Identificadores fora do padrão" no `backlog.md`), pendências em `backlog.md`, 1 linha por entrega em `history.md` (se o orchestrator ainda não acrescentou).
2. **Detectar contradição**: decisão nova → marcar a antiga como `substituída por D-xx` e **remover o texto conflitante** dos demais arquivos (trocando por `D-xx`). Fato removido do código sai da base.
3. **Compactar**: `progress.md` ≤ ~40 linhas, `conventions.md` ≤ ~40 linhas, steering ≤ ~80 linhas; sem duplicação entre arquivos.
4. **Contar retrabalho**: conte no `history.md` as linhas `devolução:` por categoria de causa. Categoria com **3 ou mais** ocorrências e sem item aberto vira item no `backlog.md`: `melhoria para o team-builder: causa <categoria> repetida Nx (tarefas: ...)`, com 1 linha do padrão visto. Você não corrige a equipe; o orchestrator leva o item ao `team-builder`. Item atendido ou descartado sai do `backlog.md` e a contagem recomeça dali.
5. **Devolver diff resumido**: por arquivo, o que foi acrescentado, alterado, removido e quais decisões foram substituídas.

### Migração das bases existentes
Preguiçosa: cada base é convertida (criar `decisions.md` extraindo decisões espalhadas, reescrever `progress.md`) na **primeira curadoria daquele projeto**. Não há conversão em lote.
