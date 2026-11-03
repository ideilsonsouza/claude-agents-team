---
name: podman-quadlet
description: Serviços em containers em servidor on-premise (appliance) com Podman + Quadlet + systemd (exemplo de alvo - Ubuntu Server 24.04, Podman 4.9.3) — onde ficam as units (/etc/containers/systemd), .container/.network/.volume, o que existe no 4.9 e o que só existe no 5.x (Notify=healthy, Memory=, StopTimeout=, .pod, .build), rootful com container não-root (User, ReadOnly, DropCapability, NoNewPrivileges), rede interna sem expor bancos, dependências e ordem (Requires/After, migração oneshot antes do serviço), health check com HealthOnFailure=kill, limites de CPU e memória pelo systemd, Podman secrets, Pull=never para operar offline, logs no journald e diagnóstico (generator --dryrun). Usar ao escrever ou revisar units Quadlet, subir serviços em servidor on-premise ou depurar um serviço que não sobe.
---

# Podman + Quadlet em servidor on-premise

Verificado em 16/10/2026 contra o manual `podman-systemd.unit(5)` das tags v4.9.3 e v5.6.0 (https://docs.podman.io/en/latest/markdown/podman-systemd.unit.5.html). Os caminhos e nomes abaixo (`/etc/app`, `/var/lib/app`, `app-*`, `APP_*`) são exemplos neutros: troque pelos do seu projeto.

## Versão alvo
- **Ubuntu Server 24.04 traz Podman 4.9.3** (`libpod 4.9.3+ds1`, pocket Updates). Escreva units que funcionem no 4.9.
- Backports trazem versões mais novas, mas se o servidor usa só o repositório principal, subir a versão do Podman é decisão a registrar (ADR) e testar no hardware alvo.

| Recurso | 4.9.3 | 5.x | No 4.9, use |
|---|---|---|---|
| `.container`, `.network`, `.volume`, `.image`, `.kube` | sim | sim | — |
| `HealthCmd=`, `HealthOnFailure=`, `HealthStartupCmd=` | sim | sim | — |
| `Secret=`, `ReadOnly=`, `ReadOnlyTmpfs=`, `NoNewPrivileges=`, `DropCapability=`, `User=`, `UserNS=` | sim | sim | — |
| `Pull=`, `Tmpfs=`, `Sysctl=`, `Ulimit=`, `Exec=`, `PodmanArgs=` | sim | sim | — |
| `Notify=healthy` (só considera iniciado quando saudável) | **não** (só `Notify=true`) | sim | `ExecStartPost=` com espera pelo `/readyz` |
| `Memory=` | **não** | sim | `MemoryMax=` na seção `[Service]` ou `PodmanArgs=--memory=` |
| `StopTimeout=` | **não** | sim | `TimeoutStopSec=` em `[Service]` + `PodmanArgs=--stop-timeout=` |
| `Entrypoint=`, `GroupAdd=`, `StopSignal=` | **não** | sim | `PodmanArgs=` |
| Units `.pod` e `.build` | **não** | sim | containers separados numa `.network` |
| Drop-ins `<unit>.container.d/*.conf` | **não** | sim | editar o próprio `.container` |

Se uma chave não existir na versão instalada, o generator ignora a unit inteira e o serviço "não existe". Sempre rode o dry-run (seção Diagnóstico).

## Onde ficam os arquivos
- Units do sistema (rootful): **`/etc/containers/systemd/`**. O generator do systemd converte cada arquivo em `<nome>.service` no `daemon-reload`.
- Nada vai em `~/.config/containers/systemd`: o servidor não depende de sessão de usuário.
- Configuração e segredos: `/etc/app/` (`0600`, dono root). Dados: `/var/lib/app/<serviço>/`. Pacotes instalados: `/var/lib/app/packages/<versão>/`.
- No repositório, as units ficam num diretório próprio (ex.: `deploy/quadlet/`); o instalador copia para `/etc/containers/systemd/` e roda `systemctl daemon-reload`.

## Rootful com container não-root
O Quadlet roda como sistema (sobe no boot sem login, porta 443 sem truque), mas o processo dentro do container nunca é root:

```ini
# /etc/containers/systemd/app-gateway.container
[Unit]
Description=App — gateway (broker + HTTP)
Requires=app-bus.service
After=app-bus.service

[Container]
ContainerName=app-gateway
Image=localhost/app/gateway:0.1.0
Pull=never
Network=app.network
PublishPort=8883:8883
PublishPort=8443:8443
User=65532:65532
ReadOnly=true
ReadOnlyTmpfs=true
NoNewPrivileges=true
DropCapability=ALL
Secret=app-gateway-bus-password,type=env,target=APP_BUS_PASSWORD
EnvironmentFile=/etc/app/gateway.env
Volume=/etc/app/tls/gateway:/etc/app/tls:ro,Z
HealthCmd=/app/gateway healthcheck
HealthInterval=10s
HealthRetries=3
HealthStartPeriod=20s
HealthOnFailure=kill
LogDriver=journald

[Service]
Restart=always
RestartSec=2
TimeoutStartSec=60
TimeoutStopSec=30
MemoryMax=512M
CPUQuota=200%

[Install]
WantedBy=multi-user.target
```

- `User=` numérico (ex.: 65532, o `nonroot` das imagens distroless). Volumes graváveis precisam pertencer a esse UID no host (`chown 65532:65532 /var/lib/app/<serviço>`), feito pelo instalador.
- `ReadOnly=true` + `ReadOnlyTmpfs=true`: rootfs imutável; só `/tmp` e volumes declarados são graváveis.
- `DropCapability=ALL` e `NoNewPrivileges=true` sempre. Se um serviço precisar de capability, adicione só ela com `AddCapability=` e justifique.
- Imagens oficiais que rodam como root por padrão (PostgreSQL, ClickHouse, NATS): use o UID não-root que a imagem documenta e confirme que o entrypoint funciona com `ReadOnly=true` antes de fixar.
- `:Z` em volumes só vale com SELinux; no Ubuntu (AppArmor) é inofensivo, então mantenha para portabilidade.

## Rede
```ini
# /etc/containers/systemd/app.network
[Network]
NetworkName=app
Subnet=10.89.10.0/24
```

- Uma rede `app` para todos os serviços; eles se acham pelo nome do container (`app-bus:4222`, `app-db:5432`).
- **Só publique portas de gateways e usuários** (8883, 8443, 443). Bancos e barramento de mensagens **nunca** têm `PublishPort=`.
- Não use `Internal=true` na rede `app`: rede interna corta o encaminhamento de portas publicadas. Isolamento vem de não publicar portas e do firewall do host.
- `Network=app.network` cria a dependência da unit de rede automaticamente.

## Volumes
```ini
# /etc/containers/systemd/app-db-data.volume
[Volume]
VolumeName=app-db-data
```

- Prefira bind mount em `/var/lib/app/<serviço>/` quando backup, inspeção ou cota de disco forem importantes (é o caso de bancos e brokers com persistência). Volume nomeado serve para dados descartáveis.
- Dados nunca dentro da imagem; desinstalar não apaga `/var/lib/app` sem um `--purge` explícito.

## Ordem de subida e migrações
```text
app.network ─┬─ app-bus ─────────────── app-gateway
             ├─ app-db ─ app-worker-migrate (oneshot) ─ app-worker
             └─ app-analytics-db ─ app-etl-migrate (oneshot) ─ app-etl
```

- Dependência dura: `Requires=` + `After=`. Use `Wants=` quando o serviço deve subir mesmo com a dependência fora (ex.: uma API que sobe com o banco analítico fora e responde `503`).
- Migração por serviço é uma unit oneshot que o serviço exige:

```ini
# /etc/containers/systemd/app-worker-migrate.container
[Unit]
Requires=app-db.service
After=app-db.service

[Container]
Image=localhost/app/worker:0.1.0
Pull=never
Network=app.network
Exec=migrate
User=65532:65532
ReadOnly=true
NoNewPrivileges=true
DropCapability=ALL
Secret=app-worker-db-password,type=env,target=APP_DB_PASSWORD

[Service]
Type=oneshot
RemainAfterExit=yes
TimeoutStartSec=300
```

  e no serviço: `Requires=app-worker-migrate.service` + `After=app-worker-migrate.service`.
- `After=` do banco garante só que o container iniciou, não que aceita conexão. A migração e o serviço **tentam conectar com retry e backoff** até um limite, em vez de confiar na ordem.
- No 4.9 não há `Notify=healthy`. Se precisar de "só depois de saudável", use no dependente um `ExecStartPre=` que espera o health da dependência com timeout. Preferível: o próprio serviço tolerar dependência indisponível (é o que `/readyz` reporta).

## Health e reinício
- `HealthCmd=` chama o próprio binário (`/app/<serviço> healthcheck` faz GET no `/healthz` interno). Imagem distroless não tem `curl` nem shell.
- `HealthOnFailure=kill` + `Restart=always`: container doente morre e o systemd reinicia com `RestartSec=`. Defina a meta de tempo de reinício nos requisitos do projeto (ex.: até 30 s).
- `/healthz` só verifica o processo; `/readyz` verifica dependências. Health do Podman usa `/healthz`, para não reiniciar o serviço quando o banco cai.
- Limite de reinícios em loop: `StartLimitIntervalSec=` e `StartLimitBurst=` em `[Unit]`, com alerta quando o limite estoura.

## Limites de recurso
- No 4.9, use as diretivas do systemd em `[Service]`: `MemoryMax=`, `MemoryHigh=`, `CPUQuota=`, `TasksMax=`. O Quadlet gera o serviço com `--cgroups=split` e `Delegate=yes` (confirmado no código da v4.9.3), então o container fica no cgroup do serviço e os limites valem para ele.
- Bancos também têm limite na própria configuração (`shared_buffers` do PostgreSQL, `max_server_memory_usage` do ClickHouse), coerente com o `MemoryMax=`.
- Ajuste fino depende do hardware alvo; até lá, valores conservadores e documentados.

## Segredos
- Gerados na instalação: `podman secret create app-<serviço>-<nome> <arquivo>` (driver `file`, guardado com permissão restrita). Nunca em imagem, unit ou `EnvironmentFile`.
- Na unit: `Secret=<nome>,type=env,target=VAR` ou `Secret=<nome>,type=mount,target=/run/secrets/<nome>` (arquivo é melhor para certificados e chaves).
- Rotação: criar o secret novo, trocar o nome na unit, `daemon-reload` e reiniciar o serviço; remover o antigo depois.

## Operar offline
- `Pull=never` em todo container: o serviço nunca tenta baixar imagem. Imagem ausente = falha imediata e clara, em vez de travar tentando a internet.
- Imagens entram por `podman load` a partir de um pacote de instalação assinado, com a tag exata da unit.
- Não use `AutoUpdate=registry` (precisa de registry). Atualização é sempre pelo pacote.

## Diagnóstico
```bash
# valida as units sem aplicar (mostra erros de chave e o .service gerado)
/usr/lib/systemd/system-generators/podman-system-generator --dryrun

systemctl daemon-reload
systemctl status app-gateway
journalctl -u app-gateway -f            # logs JSON do serviço (LogDriver=journald)
podman ps --format '{{.Names}} {{.Status}}'
podman healthcheck run app-gateway
systemctl list-dependencies app-gateway
```

- Unit que "não aparece" depois do `daemon-reload` quase sempre é chave inválida para a versão: rode o `--dryrun`.
- Não edite o `.service` gerado em `/run/systemd/generator/`; ele é refeito a cada reload. Ajustes vão no próprio `.container`; drop-ins `app-gateway.container.d/*.conf` só funcionam no Podman 5.x.

## Checklist de revisão de unit
- [ ] Chaves existem no Podman 4.9.3 (dry-run sem erro).
- [ ] `Image=` com tag exata do pacote e `Pull=never`.
- [ ] `User=` não-root, `ReadOnly=true`, `DropCapability=ALL`, `NoNewPrivileges=true`.
- [ ] Nenhum `PublishPort=` em banco ou barramento de mensagens.
- [ ] Segredos por `Secret=`, nada sensível em `Environment=`.
- [ ] `Requires=`/`After=` corretos; migração oneshot antes do serviço com banco.
- [ ] `HealthCmd=` + `HealthOnFailure=kill` + `Restart=always`.
- [ ] `MemoryMax=` e `CPUQuota=` definidos.
- [ ] Dados em `/var/lib/app/<serviço>/`, com dono igual ao `User=`.
- [ ] `LogDriver=journald` e logs em JSON no stdout.
