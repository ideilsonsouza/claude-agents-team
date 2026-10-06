---
name: prd-template
description: Estrutura padrão de PRD (Product Requirements Document) com histórias de usuário, critérios de aceite testáveis e contrato de API.
---

# Template de PRD

Salve em `docs/prd/AAAA-MM-DD-<slug>.md` (ou onde o projeto já guarda PRDs).

```markdown
# <Nome da feature>

**Status:** rascunho | aprovado · **Data:** AAAA-MM-DD

## 1. Problema
Qual dor resolve, para quem, e como sabemos que é real.

## 2. Objetivos e métricas de sucesso
- Objetivo → métrica mensurável.

## 3. Fora do escopo
- O que explicitamente NÃO será feito agora.

## 4. Usuários e histórias
- Como <persona>, quero <ação>, para <benefício>.

## 5. Requisitos funcionais
| ID | Requisito | Prioridade (MoSCoW) |
|----|-----------|---------------------|
| RF01 | ... | Must |

## 6. Critérios de aceite
Formato Dado/Quando/Então, um por comportamento. Cada um precisa ser testável pelo QA.
- **CA01** (RF01) — Dado ..., quando ..., então ...

## 7. Requisitos não funcionais
Desempenho, segurança, acessibilidade, LGPD, observabilidade.

## 8. Contrato de API (se houver backend + frontend)
| Método | Rota | Request | Response | Erros |
|--------|------|---------|----------|-------|
Inclua exemplos JSON e códigos HTTP de erro.

## 9. UX
Fluxos principais, estados (vazio, carregando, erro, sucesso), referências.

## 10. Riscos, dependências e perguntas em aberto
```

Regras: critérios de aceite sem ambiguidade ("rápido" não serve; "p95 < 300 ms" serve). Pergunta sem resposta vai para a seção 10, nunca vira suposição silenciosa.
