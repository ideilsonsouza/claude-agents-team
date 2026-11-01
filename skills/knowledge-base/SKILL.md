---
name: knowledge-base
description: Estrutura e regras da base de conhecimento de projeto da equipe (fora do repositório), com nomes de mercado — product, tech, structure (steering do Kiro), progress (Memory Bank do Cline), backlog e history — e como fazer o mapeamento inicial.
---

# Base de conhecimento do projeto

Cada projeto tem uma base **fora do repositório**, em `~/.claude/team-state/<slug>/`. O caminho exato é injetado no contexto pelo hook da equipe. Ela substitui reler o código para descobrir "o que já existe".

Os nomes seguem padrões de mercado: **steering files do Kiro** (`product.md`, `tech.md`, `structure.md`) e **Memory Bank do Cline** (`progress.md`). Se um dia a base for levada para dentro de um projeto, a estrutura é reconhecível por outras ferramentas.

## Arquivos

| Arquivo | Conteúdo | Injetado em | Tamanho alvo |
|---|---|---|---|
| `product.md` | O quê e para quem: visão, usuários, proposta de valor, funcionalidades principais, regras de negócio-chave | orchestrator, architect, prd, docs | ≤ 1 página |
| `tech.md` | Com o quê: stack, versões, banco, ferramentas, **comandos** (rodar, testar, lint, build, migrations), convenções técnicas, integrações externas | orchestrator e quase todos | ≤ 1 página |
| `structure.md` | Onde: árvore de pastas comentada, módulos e responsabilidades, convenções de nomes, **política de artefatos** | orchestrator, architect, dba, backend, frontend, qa, docs, devops | ≤ 1 página |
| `domain.md` | Domínio: glossário, entidades e invariantes, fórmulas e regras de cálculo (com fonte), normas aplicáveis | prd, dba, product-designer, shop-floor, finance, data-analyst | **≤ 2.000 caracteres** |
| `business.md` | Negócio: modelo, ICP, posicionamento, planos e preço de **lista**, canais e metas, restrições | legal, finance, gtm, marketing | **≤ 2.000 caracteres** |
| `progress.md` | Estado: o que já foi entregue (onde está, endpoints, tabelas), o que está em andamento, problemas conhecidos | orchestrator, prd | resumo, não changelog |
| `backlog.md` | Próximos passos, riscos, dívidas técnicas, perguntas em aberto | orchestrator | lista viva |
| `history.md` | Uma linha por entrega: `AAAA-MM-DD · agente(s) · resumo` | ninguém (consulta) | só acrescenta |
| `specs/<data>-<feature>/` | `requirements.md`, `design.md`, `tasks.md` (skill `spec-workflow`); entregues vão para `specs/_archive/` | sob demanda | — |
| `domain/`, `business/{legal,finance,gtm,marketing}/`, `design/`, `analytics/` | Material detalhado dos agentes de domínio | sob demanda | — |
| `adr/`, `architecture/` | ADRs e docs de arquitetura quando a política for **internal** | sob demanda | — |

O hook injeta até 9.500 caracteres por agente. Mantenha `product`, `tech`, `structure` e `progress` com até 3.000 caracteres cada; o detalhe vai para arquivos à parte.

Se um arquivo passar de uma ou duas páginas, mova o detalhe para um arquivo à parte na base e deixe um link.

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

### `progress.md`
```markdown
# Progress — <projeto>
Atualizado: AAAA-MM-DD
## Entregue
- <funcionalidade> — arquivos-chave, endpoints, tabelas
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
3. Escreva `product.md`, `tech.md`, `structure.md` e um `progress.md` inicial. Política de artefatos: **internal**, salvo instrução contrária.

## Regras de manutenção
- O orchestrator atualiza a base após cada entrega, usando a seção "Atualização da base" do relatório (skill `delivery-contract`).
- Fatos, não intenções. Se algo foi removido do código, remova da base.
- `domain.md` nasce de uma tarefa do `shop-floor` (produto industrial) ou do `prd` (outros), e `business.md` de uma tarefa do `gtm` com consulta ao `finance`. O texto vem em "Atualização da base" e o orchestrator grava.
- Contratos e preços de cliente nunca entram na base.
- Nunca grave segredos, credenciais ou dados pessoais de clientes.
