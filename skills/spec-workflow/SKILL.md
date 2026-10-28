---
name: spec-workflow
description: Fluxo de spec da equipe no padrão Kiro — requirements.md (EARS), design.md e tasks.md — com tamanho proporcional à tarefa, portões de aprovação, Definition of Ready/Done e arquivamento.
---

# Spec workflow

Spec proporcional: só o necessário para entregar certo de primeira. Spec é **descartável**: guia a feature e é arquivada; o conhecimento durável vai para `progress.md` e ADRs.

## Tamanho → spec

| Tamanho | Critério | Spec |
|---|---|---|
| **P** | Bug ou ajuste, 1 agente, poucos arquivos, sem decisão de design | Nenhuma. Briefing direto |
| **M** | Feature contida, 1–2 agentes, sem schema novo nem decisão estrutural | `tasks.md` |
| **G** | Feature nova, várias camadas, schema, integração ou decisão estrutural | `requirements.md` → `design.md` → `tasks.md` |

Na dúvida entre dois tamanhos, escolha o maior.

## Local
`<pasta de specs>/<AAAA-MM-DD>-<feature>/`, onde a pasta segue a política de artefatos do `structure.md`: `internal` → `<base>/specs/`; `repo` → `docs/specs/`. Entregue → mover para `specs/_archive/`.

## Portões (tamanho G)
1. `requirements.md` pronto → **usuário aprova** → segue.
2. `design.md` pronto → **usuário aprova** → segue.
3. `tasks.md` pronto → execução.
Mudou requisito ou design no meio? Atualize o documento e peça nova aprovação antes de mexer no código.

---

## `requirements.md` — dono: `prd`

```markdown
# Requirements — <feature>
Status: rascunho | aprovado · Data: AAAA-MM-DD

## Problema e objetivo
Dor, para quem, como medir sucesso.

## Fora do escopo
- ...

## Histórias
- **H1** Como <persona>, quero <ação>, para <benefício>.

## Critérios de aceite (EARS)
Cada critério é testável e tem ID. Padrões EARS:
- Ubíquo: `O sistema DEVE <resposta>.`
- Evento: `QUANDO <gatilho>, o sistema DEVE <resposta>.`
- Estado: `ENQUANTO <estado>, o sistema DEVE <resposta>.`
- Indesejado: `SE <condição>, ENTÃO o sistema DEVE <resposta>.`
- Opcional: `ONDE <funcionalidade existir>, o sistema DEVE <resposta>.`

- **CA1** (H1) QUANDO o usuário envia o formulário com e-mail inválido, o sistema DEVE exibir "E-mail inválido" junto ao campo e não enviar a requisição.

## Requisitos não funcionais
Desempenho (com número), segurança, acessibilidade, LGPD, observabilidade.

## Perguntas em aberto
- Nada fica implícito: dúvida vai aqui, não vira suposição.
```

Regras: proibido critério vago ("rápido", "amigável"); use números e comportamentos observáveis.

---

## `design.md` — dono: `architect` (com `dba` para dados)

```markdown
# Design — <feature>
Status: rascunho | aprovado · Requisitos: requirements.md

## Visão geral
Abordagem em 3–5 linhas e diagrama Mermaid se ajudar.

## Componentes afetados
| Componente | Onde (caminho) | Mudança |

## Contrato de API
| Método | Rota | Request | Response | Erros |
Exemplos JSON. Este contrato é a fronteira entre backend e frontend.

## Modelo de dados (dba)
Tabelas/colunas/índices novos ou alterados e estratégia de migration (expand/contract se necessário).

## Decisões
- Decisão — motivo. Decisão estrutural relevante → ADR (link).

## Riscos e mitigação

## Estratégia de testes
O que é unitário, integração, e2e. Mapeie critérios de aceite → tipo de teste (skill `test-strategy`). Liste os casos negativos que se aplicam (autorização, tenant cruzado, entrada inválida, duplicata).
```

---

## `tasks.md` — dono: `orchestrator`

```markdown
# Tasks — <feature>
Spec: requirements.md · design.md (ou "tamanho M: sem spec")

| ID | Tarefa | Dono | Depende de | Status |
|----|--------|------|------------|--------|
| T1 | Testes de aceite CA1–CA3 (falhando) | qa | — | pendente |
| T2 | Migration da tabela X | dba | — | pendente |
| T3 | Endpoint POST /x (deixar T1 verde) | backend | T1, T2 | pendente |
| T4 | Revisão do diff | reviewer | T3 | pendente |

## T1 — <título>
- **Objetivo:** ...
- **Arquivos:** ler `...`; alterar/criar `...`
- **Critério de pronto:** comando de verificação + resultado esperado; critérios de aceite cobertos (CA1, CA2)
- **Fora do escopo:** ...
```

**Teste antes:** em M/G com mudança de comportamento, a primeira tarefa é do `qa`. Ele escreve os testes de aceite e mostra que falham pelo motivo certo, e a implementação tem como critério de pronto deixá-los verdes sem alterar o teste. Pule (anotando o motivo) em spike, protótipo, mudança só visual ou só de infra.

Status: `pendente` · `em andamento` · `concluída` · `devolvida (n)` · `bloqueada`.

### Definition of Ready (antes de delegar)
Dono único · objetivo claro · arquivos identificados · dependências concluídas · critério de pronto verificável.

### Definition of Done (antes de marcar concluída)
Evidência de verificação no relatório · portão mínimo verde (typecheck, lint, testes do módulo) · critérios de aceite validados pelo `qa` (quando há comportamento novo) · `reviewer` sem achado bloqueante (M/G ou área sensível) · `pr` conferiu convenções e segredos · base atualizada.

### Ordem típica (G)
`qa` (testes de aceite falhando) → `dba` (schema) → `backend` ∥ `frontend` (após contrato) → `qa` (validação) → `reviewer` → `pr` → `docs` → `devops` (se CI muda) → `deploy` (com OK do usuário).
