---
name: deploy-checklist
description: Checklist de deploy da equipe — pré-deploy, execução, verificação pós-deploy, critérios de rollback e portão de confirmação humana para produção.
---

# Checklist de deploy

## 0. Portão humano
- Ambiente é **produção**? Só prossiga se o briefing disser explicitamente que o usuário autorizou. Caso contrário, status BLOQUEADO pedindo confirmação.

## 1. Pré-deploy
- [ ] Versão/commit a publicar identificado (tag ou hash).
- [ ] CI verde para esse commit.
- [ ] Migrations: existem? são reversíveis? há backup recente do banco?
- [ ] Variáveis de ambiente/segredos novos já configurados no ambiente alvo.
- [ ] Plano de rollback conhecido (versão anterior e comando).

## 2. Execução
- Use o mecanismo existente do projeto (pipeline, script, CLI). Não improvise comandos manuais se houver automação.
- Registre horário de início e fim.

## 3. Verificação pós-deploy (primeiros minutos)
- [ ] Health check respondendo.
- [ ] Smoke test dos fluxos críticos.
- [ ] Taxa de erro e latência dentro do normal nos logs/métricas.

## 4. Critérios de rollback (qualquer um dispara)
- Health check falhando após o tempo de estabilização.
- Erros 5xx ou latência claramente acima do patamar anterior.
- Fluxo crítico quebrado no smoke test.

Rollback em produção é ação de recuperação: execute e reporte imediatamente. Se a migration não for reversível, **pare e escale** em vez de reverter código.

## 5. Relatório
Versão, ambiente, horários, resultado de cada verificação, rollback (sim/não) e links de logs.
