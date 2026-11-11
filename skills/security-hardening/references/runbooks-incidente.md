# Runbooks de incidente

Ordem sempre: **conter → erradicar → recuperar → registrar**. Não comece investigando.
Registre horário (UTC e local), quem fez o quê e qual evidência — pode virar obrigação de reporte.

## 1. Segredo vazou (commit, log, print, canal público, pacote publicado)
1. **Rotacione agora.** Gere o novo, publique no destino (secret do Swarm/Coolify/Dokploy/GH),
   suba o serviço, **revogue o antigo**. Ordem importa: revogar antes de ter o novo = indisponibilidade.
2. Marque o antigo como comprometido no inventário de segredos.
3. Procure uso indevido: log de acesso do provedor, `git log` do período, acesso ao banco,
   e-mail de login novo, cobrança inesperada.
4. **Não conte com reescrita de histórico.** Se o repo é público ou já foi clonado/forkado, o
   segredo é público para sempre. `git filter-repo` só limpa a cópia nova.
5. Se era chave de assinatura (pacote, release, minisign/cosign): rotacione a chave **e** reemita
   os artefatos; publique a chave pública nova e o procedimento de verificação.
6. Feche o buraco que permitiu: `gitleaks` no pre-commit, `.gitignore`, `redact` no logger.

## 2. Dependência maliciosa / pacote comprometido
1. **Pare instalações.** Não rode `npm install`, `pip install` nem `go get` até saber a versão boa.
   Congele o CI (desabilite o workflow de release).
2. Identifique a janela: qual versão, publicada quando, instalada onde (lockfile, imagem, cache de
   CI, máquina de dev).
3. Fixe a última versão boa (`overrides`/`resolutions` no npm, `==` no Python, `replace`/`require`
   no Go), limpe cache e árvore (`rm -rf node_modules`, `npm cache clean --force`,
   `uv cache clean`, `go clean -modcache`) e reconstrua.
4. **Rotacione todo segredo alcançável** pela máquina ou pelo runner que executou o pacote: token
   npm/PyPI, PAT do GitHub, chave de cloud, credencial de banco, chave SSH, token de gestão de tarefas/chamados.
   Suponha exfiltração; os worms de 2025–2026 fazem exatamente isso.
5. Procure persistência: `.github/workflows/` novo ou alterado, script `postinstall`/`prepare`,
   `.git/hooks`, chave SSH nova em `~/.ssh/authorized_keys`, pacote publicado no seu nome
   (verifique a lista de versões no registry), runner self-hosted.
6. Reconstrua imagens e redeploye; não confie em imagem construída na janela.
7. Depois: aumente o cooldown (`minimumReleaseAge`), desligue script de instalação, reduza o número
   de dependências diretas.

## 3. CVE crítica em dependência
1. **É alcançável pelo nosso código?** `govulncheck` (Go) dá resposta por caminho de chamada;
   `osv-scanner`/`npm audit`/`pip-audit` dão presença, não alcance. Leia o advisory.
2. Patch disponível → atualize, rode a suíte, deploy. É sempre a primeira opção.
3. Sem patch → mitigação no código (desligar o recurso vulnerável, validar antes), ou regra no
   proxy como medida temporária **com data de revisão**.
4. Registre a decisão (ADR curto ou comentário no PR) com versão, data e quem decidiu.
5. Se o componente está abandonado, abra tarefa de substituição — A03 cobra isso.

## 4. Suspeita de invasão no serviço
1. **Preserve**: snapshot do contêiner/volume e cópia dos logs antes de reiniciar.
   Reiniciar apaga evidência em memória.
2. Contenha: tire da rede (escale para 0 réplicas ou bloqueie no proxy) em vez de apagar.
3. Revogue sessões e tokens; force rotação de credencial de serviço.
4. Reconstrua a partir de imagem confiável; não "limpe" um host comprometido.
5. Avalie dado pessoal envolvido → seção 5.

## 5. Dado pessoal exposto (LGPD)
1. Determine: quais titulares, quais campos, por quanto tempo, quem acessou.
2. Comunique o encarregado (DPO) / responsável do produto imediatamente; a decisão de notificar a
   ANPD e os titulares é dele, com prazo legal.
3. Não apague log nem registro de acesso — é evidência.
4. Reduza a superfície: o dado precisava estar ali? (minimização é controle, não burocracia.)

## 6. Reporte obrigatório — Cyber Resilience Act (UE)
Aplica-se se o produto com elemento digital é colocado no mercado da UE sob nome próprio
(pago, monetizado ou gratuito). Em vigor desde **11/09/2026**.

| Gatilho | Alerta inicial | Notificação | Relatório final |
|---|---|---|---|
| Vulnerabilidade **explorada ativamente** | 24 h | 72 h | 14 dias após medida corretiva disponível |
| Incidente severo | 24 h | 72 h | 1 mês após a notificação |

Submissão pela Single Reporting Platform da ENISA. Tenha pronto: identificação do produto e versão,
descrição técnica, medida de mitigação, usuários afetados.
Confirme o estado da plataforma e o texto vigente antes de depender disso — as fontes de 2026
divergem sobre a operação da plataforma na data de entrada em vigor.

## 7. Pós-incidente
Em até 5 dias úteis: linha do tempo, causa raiz (técnica **e** de processo), o que detectou (e o
que deveria ter detectado), ações com responsável e prazo. Sem busca de culpado.
Toda ação de prevenção que puder virar portão de CI ou teste automatizado deve virar.
