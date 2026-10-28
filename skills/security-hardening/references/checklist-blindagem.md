# Checklist de blindagem por camada

Marque o nível alvo (L1 interno / L2 exposto / L3 crítico — ver SKILL.md §1).
Item marcado `[L2]` vale de L2 para cima; `[L3]` só no nível crítico.

## Identidade e sessão
- [ ] Sessão em cookie `HttpOnly; Secure; SameSite=Lax` com id opaco e estado no servidor (revogável)
- [ ] JWT só para serviço-a-serviço/mobile/IdP: allowlist de algoritmo, `iss`/`aud`/`exp`/`nbf`
      validados, refresh rotativo com detecção de reuso
- [ ] Senha com Argon2id (19 MiB/t=2/p=1) e rehash no login quando o parâmetro muda
- [ ] Bloqueio progressivo e rate limit no login, reset de senha e envio de código
- [ ] Token de reset/convite: uso único, curto, hash no banco
- [ ] Logout invalida no servidor; troca de senha invalida as outras sessões
- [ ] [L2] MFA disponível para conta administrativa; [L3] obrigatório
- [ ] Nenhuma credencial em URL, query string ou log

## Autorização
- [ ] Deny-by-default: rota sem permissão declarada não entra
- [ ] Toda leitura/escrita por id filtra por `tenant_id`/`owner_id` na query (ou RLS)
- [ ] Papel e permissão vêm do servidor, nunca do corpo da requisição
- [ ] Teste automatizado cruzado (usuário A pede recurso de B → 404) para cada recurso
- [ ] [L3] RLS no Postgres e `tenant_id` em FK composta
- [ ] Rota administrativa com guard próprio e teste próprio

## Entrada e saída
- [ ] Schema de entrada com `additionalProperties: false`; nunca espalhar o body no ORM
- [ ] Schema de saída (allowlist) — nada de serializar a entidade inteira
- [ ] Limite de tamanho: body, upload, itens em lote, `limit` de paginação, profundidade de JSON
- [ ] Upload: tipo verificado pelo conteúdo, nome gerado pelo servidor, fora do webroot, sem execução
- [ ] SQL só por parâmetro/placeholder; identificador dinâmico por allowlist
- [ ] Comando externo sem shell (array de argumentos), binário por caminho absoluto
- [ ] Template com autoescape; nunca template montado com entrada do usuário
- [ ] Desserialização só de formato de dado (JSON) — nunca pickle/YAML full/gob de fonte não confiável
- [ ] URL vinda do usuário (SSRF): allowlist de esquema e host, bloqueio de IP privado/loopback/
      link-local **após resolver DNS**, sem seguir redirect, com timeout
- [ ] Caminho de arquivo vindo do usuário: normalizado e confinado (`os.Root` no Go, resolve+prefixo)

## Configuração
- [ ] `NODE_ENV=production` / `DEBUG=False` / modo de produção explícito
- [ ] Sem `/docs`, `/redoc`, `/debug`, `/metrics` público (ou atrás de auth e rede interna)
- [ ] Headers: HSTS, `X-Content-Type-Options: nosniff`, CSP (`frame-ancestors 'none'` no mínimo),
      `Cache-Control: no-store` em resposta sensível, `Referrer-Policy`
- [ ] Banner de servidor/versão desligado (`X-Powered-By`, `Server`)
- [ ] CORS: allowlist exata, sem `*` com credencial, sem refletir `Origin`, com `Vary: Origin`
- [ ] TLS 1.2+ com 1.3 preferido; redirect de HTTP; certificado com renovação automática
- [ ] `trustProxy`/`ProxyHeaders` configurado **só** para o proxy real (senão IP é falsificável)
- [ ] Porta de banco, Redis e broker não publicadas; rede interna do compose/Swarm

## Dependência e build
- [ ] Lockfile commitado; instalação reprodutível (`npm ci`, `uv sync --frozen`, `go mod download`)
- [ ] Install script desligado por padrão, com allowlist mínima
- [ ] Cooldown de versão nova (≥ 1 dia) configurado
- [ ] Scanner de vulnerabilidade no CI e em schedule semanal
- [ ] Imagem: multi-stage, base mínima, `USER` não-root, `.dockerignore` cobrindo `.env`, `.git`
- [ ] Runtime: read-only rootfs, `cap_drop: ALL`, `no-new-privileges`, limites de CPU/memória
- [ ] [L2] SBOM gerado e guardado por release; [L3] artefato assinado e verificado no deploy
- [ ] Workflow do CI: `permissions` mínimo, ação pinada por SHA, OIDC em vez de chave estática

## Dados
- [ ] Segredo só do ambiente, validado no boot; nenhum no repo, imagem ou bundle
- [ ] Rotação com prazo escrito e procedimento testado
- [ ] Dado pessoal minimizado no log (sem CPF, e-mail completo, corpo de request)
- [ ] Backup com restore testado (e cifrado se sair da infra)
- [ ] [L3] cifra em repouso de campo sensível com AEAD e chave fora do banco
- [ ] [L3] trilha de auditoria de acesso a dado pessoal, imutável, com retenção definida

## Falha, log e alerta
- [ ] Caminho de falha de autorização/dependência **nega** (fail closed)
- [ ] Erro não vaza stack trace, SQL, caminho de arquivo nem versão de biblioteca
- [ ] Recurso liberado em `finally`; transação multi-etapa com rollback completo
- [ ] Timeout em toda chamada externa (HTTP, banco, broker, fila) e `statement_timeout`
- [ ] Shutdown gracioso: para de aceitar, termina o que está em voo, fecha conexões
- [ ] Evento de segurança logado **com alerta**: login falho em série, 403 em série, bloqueio,
      troca de credencial, rate limit, falha de HMAC, 5xx em série, deploy/rollback
- [ ] Erro repetido agregado (contador + amostra), não inundando o log

## Processo
- [ ] Nível de blindagem declarado no `design.md`
- [ ] Modelo de ameaças em 5 perguntas respondido e revisado quando a arquitetura muda
- [ ] Runbook de segredo vazado e de dependência maliciosa testado uma vez
- [ ] Inventário de segredos e de dependência direta atualizado
- [ ] [L3] revisão de segurança por release e pentest externo com periodicidade definida
