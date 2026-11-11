---
name: appliance-docker
description: Serviços em containers em servidor on-premise (appliance) com Docker Engine + Compose v2 + systemd (exemplo de alvo - Ubuntu Server 24.04) — instalação pelo repositório oficial com versão fixada, compose.yaml com restart unless-stopped, healthcheck e depends_on service_healthy, unit do systemd que sobe e desce o projeto (up -d --wait / down), rede e volumes nomeados, stop_grace_period, logs com driver local e rotação, endurecimento (usuário não-root, read_only, cap_drop ALL, no-new-privileges, tmpfs, userns-remap e rootless com o custo de cada um), segredos por arquivo 0400 como secrets do Compose, migração oneshot antes do serviço, operar offline (pull_policy never, docker load), atualização e rollback por tag fixada e digest, e armadilhas (porta publicada que fura o firewall, unhealthy que não reinicia, mode de secret ignorado). Usar ao escrever ou revisar o compose.yaml e a unit do appliance, subir serviços em servidor on-premise ou depurar um serviço que não sobe.
---

# Docker + Compose em servidor on-premise

Verificado em 10/11/2026 na doc oficial da Docker (docs.docker.com): Engine 29.9.3 (release notes, 03/11/2026), `docker compose up` (`--wait`, `--wait-timeout`), referência de `services` (healthcheck, `depends_on`, `stop_grace_period`, `secrets`, `read_only`, `cap_drop`, `security_opt`, `tmpfs`, `init`, `pull_policy`), uso de secrets, driver de log `local`, instalação no Ubuntu, `userns-remap` e rootless. Os caminhos e nomes abaixo (`/etc/app`, `/var/lib/app`, `app-*`, `APP_*`) são exemplos neutros: troque pelos do seu projeto. Itens marcados "não verificado" saíram da experiência, não da doc.

## Instalação e versão
- Instale pelo **repositório apt oficial da Docker** (chave em `/etc/apt/keyrings/docker.asc`, fonte em `/etc/apt/sources.list.d/docker.sources`), não pelo `docker.io` da distribuição. Pacotes: `docker-ce docker-ce-cli containerd.io docker-compose-plugin` (o `docker-buildx-plugin` só se o appliance fizer build, o que não deve).
- **Fixe a versão** do Engine e do plugin, testada no hardware alvo:
  ```bash
  apt list --all-versions docker-ce
  VERSION_STRING=5:29.9.3-1~ubuntu.24.04~noble      # exemplo da doc; use a testada
  apt install docker-ce=$VERSION_STRING docker-ce-cli=$VERSION_STRING containerd.io docker-compose-plugin
  apt-mark hold docker-ce docker-ce-cli docker-compose-plugin
  ```
- Appliance offline não recebe do repositório: os `.deb` fixados entram no pacote de instalação (skill `appliance-offline-package`), com o repositório apt desligado no servidor para ninguém atualizar sem passar pelo pacote.
- Ubuntu 24.04 LTS é alvo suportado pela Docker. Compose v2 é o plugin (`docker compose`); `docker-compose` v1 não se usa.
- Docker roda o daemon como root. Quem está no grupo `docker` é root na prática: ninguém além do instalador/`appctl` entra nele.

## Onde ficam os arquivos
- Projeto Compose: **`/opt/app/compose/compose.yaml`** (versão atual em `/var/lib/app/packages/current/compose/`, link simbólico). Unit: `/etc/systemd/system/app.service`.
- Configuração e segredos: `/etc/app/` (dono root, `0600`/`0700`). Dados: `/var/lib/app/<serviço>/`.
- Nome do projeto fixo (`name: app` no topo do `compose.yaml`), para que rede, volumes e containers tenham nomes previsíveis (`app_default`, `app-db-1`).

## Unit do systemd que sobe o projeto
```ini
# /etc/systemd/system/app.service
[Unit]
Description=App (projeto Compose)
Requires=docker.service
After=docker.service network-online.target
Wants=network-online.target
StartLimitIntervalSec=300
StartLimitBurst=5

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/app/compose
ExecStart=/usr/bin/docker compose up -d --wait --wait-timeout 120
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=180
TimeoutStopSec=90

[Install]
WantedBy=multi-user.target
```
- `up -d --wait` só retorna quando os serviços estão *running* ou *healthy* e implica modo destacado; falha com código diferente de zero se algum não chegar lá, e o systemd marca a unit como falha. `--wait-timeout` é em segundos.
- `down` para e remove containers e rede, **sem** apagar volumes nomeados (só `-v` apaga: nunca use no appliance).
- `TimeoutStopSec` deve ser **maior que o maior `stop_grace_period`** somado (o Compose para em ordem inversa das dependências). Senão o systemd mata o `docker compose` no meio.
- O `restart: unless-stopped` dos serviços faz o daemon relançar container que morre; a unit cobre o **boot** e o estado "projeto no ar". Com `unless-stopped`, container parado por `docker compose stop`/`down` não volta sozinho no boot do daemon: quem sobe é a unit.
- Pacotes novos: `ExecStart` aponta para o diretório `current`; troca de versão = trocar o link e `systemctl restart app`.

## compose.yaml (modelo)
```yaml
name: app

x-hardening: &hardening
  read_only: true
  cap_drop: [ALL]
  security_opt: ["no-new-privileges:true"]
  init: true
  restart: unless-stopped
  pull_policy: never
  logging:
    driver: local
    options: { max-size: 10m, max-file: "5" }

services:
  db:
    <<: *hardening
    image: postgres:18.1@sha256:<digest>
    user: "999:999"
    networks: [app]
    volumes:
      - app-db-data:/var/lib/postgresql
    tmpfs: [/tmp, /run/postgresql]
    secrets: [db_password]
    environment:
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password
    healthcheck:
      test: ["CMD", "pg_isready", "-U", "app"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s
    stop_grace_period: 60s

  worker-migrate:
    <<: *hardening
    restart: "no"                       # oneshot: roda, termina e fica "exited 0"
    image: localhost/app/worker:0.1.0
    command: ["migrate"]
    user: "65532:65532"
    networks: [app]
    secrets: [worker_db_password]
    depends_on:
      db: { condition: service_healthy }

  worker:
    <<: *hardening
    image: localhost/app/worker:0.1.0
    user: "65532:65532"
    networks: [app]
    secrets: [worker_db_password]
    depends_on:
      db: { condition: service_healthy }
      worker-migrate: { condition: service_completed_successfully }
    healthcheck:
      test: ["CMD", "/app/worker", "healthcheck"]
      interval: 10s
      timeout: 3s
      retries: 3
      start_period: 20s
    stop_grace_period: 30s

  gateway:
    <<: *hardening
    image: localhost/app/gateway:0.1.0
    user: "65532:65532"
    networks: [app]
    ports:
      - "8883:8883"
      - "8443:8443"
    depends_on:
      worker: { condition: service_healthy }
    healthcheck:
      test: ["CMD", "/app/gateway", "healthcheck"]
      interval: 10s
      timeout: 3s
      retries: 3
      start_period: 20s
    stop_grace_period: 30s

networks:
  app:
    name: app
    driver: bridge

volumes:
  app-db-data:
    name: app-db-data

secrets:
  db_password:        { file: /etc/app/secrets/db_password }
  worker_db_password: { file: /etc/app/secrets/worker_db_password }
```
- `depends_on: condition: service_healthy` espera o healthcheck da dependência passar; `service_completed_successfully` espera o serviço oneshot (migração) terminar com sucesso. `start_period`/`start_interval` no healthcheck exigem Compose ≥ 2.20.2.
- A ordem do Compose cobre só a **subida**. O serviço continua tolerando dependência indisponível depois (retry com backoff), porque o banco pode cair com o serviço no ar.
- Imagem distroless não tem shell nem `curl`: o healthcheck chama o próprio binário (`healthcheck` faz GET no `/healthz` interno), em forma exec (`CMD`).
- `/healthz` só verifica o processo; `/readyz` verifica dependências. Use `/healthz` no healthcheck do container.
- `init: true` roda um init como PID 1 (repassa sinais, colhe zumbis). Dispensável se o binário já trata SIGTERM e não cria filhos; útil para Node.
- `stop_grace_period` padrão é **10 s**: ajuste para ser maior que a drenagem do serviço e o checkpoint do banco.
- `x-hardening` é um fragmento YAML reaproveitado com `<<:`; o Compose aceita chaves `x-*` livres.

## Rede e portas
- Uma rede nomeada `app`; os serviços se acham pelo nome do serviço (`db:5432`, `bus:4222`).
- **Só publique portas de gateways e usuários.** Bancos e barramento de mensagens **nunca** têm `ports:`. Se precisar de acesso local de diagnóstico, use `127.0.0.1:5432:5432` ou `docker compose exec`.
- Porta publicada pelo Docker **fura o ufw e o firewalld** (a doc oficial avisa: as portas "bypass your firewall rules"). Por isso a única proteção real é não publicar. Para limitar origem, publique em IP específico (`10.0.0.5:8443:8443`) ou use regras na cadeia `DOCKER-USER`. A Docker só suporta `iptables-nft` e `iptables-legacy`: regras feitas direto com `nft` não são suportadas.
- Rede com `internal: true` não encaminha porta publicada: não use na rede dos gateways.

## Volumes
- **Volume nomeado** (`app-db-data`) guarda dados do Docker em `/var/lib/docker/volumes/`. **Bind mount** em `/var/lib/app/<serviço>/` serve quando backup, inspeção ou cota de disco importam. No bind, o dono do diretório no host deve ser o UID do `user:` (`chown 65532:65532`), feito pelo instalador.
- Banco com volume nomeado ou bind: decida e documente; backup é por dump ou pela ferramenta do banco, nunca copiando arquivos de banco no ar.
- Dados nunca dentro da imagem. Desinstalar não apaga `/var/lib/app` nem volumes sem `--purge` explícito.
- `docker volume prune` e `docker system prune --volumes` são proibidos.

## Logs
- Driver **`local`** com rotação: padrão `max-size` 20m, `max-file` 5, `compress` ligado. Configure no `compose.yaml` (modelo acima) ou, para todo o daemon, em `/etc/docker/daemon.json`:
  ```json
  { "log-driver": "local", "log-opts": { "max-size": "10m", "max-file": "5" } }
  ```
- O padrão do Docker, `json-file`, **não rotaciona** e enche o disco. Mudar o padrão do daemon só vale para containers criados depois.
- Serviços logam JSON no stdout; `docker compose logs -f <serviço>` lê. Quem quer tudo no journal usa o driver `journald`, mas então `docker logs` ainda funciona e a retenção passa a ser a do journald (não verificado).

## Endurecimento
Sempre, em todo serviço (fragmento `x-hardening`):
- **`user:` numérico não-root** (ex.: `65532:65532`, o `nonroot` do distroless). Imagens oficiais que rodam como root (PostgreSQL, ClickHouse, NATS): use o UID que a imagem documenta e confirme o entrypoint com `read_only: true`.
- **`read_only: true`** + `tmpfs` para o que precisa gravar (`/tmp`, `/run/...`) e volumes declarados.
- **`cap_drop: [ALL]`**; se um serviço precisar de capability, `cap_add` só dela, com justificativa. Porta abaixo de 1024 dentro do container exige `NET_BIND_SERVICE`; prefira porta alta no container e mapear no `ports:`.
- **`security_opt: ["no-new-privileges:true"]`**.
- Sem `privileged`, sem `network_mode: host`, sem montar `/var/run/docker.sock` em nenhum serviço.

Opções mais fortes (decisão a registrar em ADR), com o custo:

| Opção | Ganho | Custo |
|---|---|---|
| `userns-remap` (daemon) | root do container vira UID sem privilégio no host | vale para **todo** o daemon; armazenamento separado em `/var/lib/docker/<uid>.<gid>` (imagens existentes ficam invisíveis: habilite em instalação nova e faça `docker load` depois); incompatível com `network_mode: host`/`pid: host`; bind mounts exigem dono pré-arranjado; `privileged` exige `--userns=host`; `/etc/subuid` e `/etc/subgid` sem sobreposição |
| Modo rootless | o próprio daemon deixa de ser root | pacote `uidmap`, 65.536 subuids; daemon é unit **de usuário** (`systemctl --user`) e precisa de `loginctl enable-linger <usuário>` para subir no boot; a unit do appliance muda para `--user`; limitações de rede e porta < 1024 (consulte a doc de rootless antes; não verificado aqui) |

Padrão recomendado: **rootful com container não-root e endurecido**, que é o que o modelo acima faz. Adote `userns-remap` se o risco justificar e o appliance for instalado do zero; rootless só se o requisito de segurança superar a complexidade de operar no appliance.

## Segredos
- Segredo **nunca** em `environment:`, `.env`, `ARG` nem imagem. Use `secrets:` do Compose: arquivo no host montado em `/run/secrets/<nome>` (bind mount do arquivo do host, não tmpfs).
- Crie o arquivo na instalação, **só se não existir** (reinstalar não troca segredo): `install -m 0400 -o 65532 -g 65532 /dev/stdin /etc/app/secrets/worker_db_password`.
- **Armadilha:** para `secrets` com origem `file`, o Compose usa bind mount e **ignora `uid`, `gid` e `mode`** (a doc diz que são ignorados em silêncio; o default seria 0444). Valem o dono e a permissão **do arquivo no host**. Logo, o arquivo precisa pertencer ao UID do `user:` do serviço (0400). Dono root com 0400 faz o serviço não-root receber "permission denied". Um segredo por serviço que o usa, quando UIDs diferem.
- A aplicação lê o arquivo (`*_FILE`, como `POSTGRES_PASSWORD_FILE`). Variável de ambiente só com o caminho, nunca com o valor.
- Rotação: gerar o arquivo novo, `docker compose up -d --wait` (recria o serviço, que relê o arquivo) e apagar o antigo. Segredo é lido na criação do container: mudar o arquivo sem recriar não basta.
- Diretório `/etc/app/secrets` `0700` root; `docker compose config` mostra caminhos, não valores, mas não cole sua saída em ticket sem revisar.

## Operar offline
- `pull_policy: never` em todo serviço: nunca tenta baixar imagem; imagem ausente falha de forma clara em vez de travar.
- Imagens entram por `docker load` a partir do pacote assinado, com a tag exata do `compose.yaml` (skill `appliance-offline-package`).
- Imagens de terceiros ficam fixadas por digest no `compose.yaml` (`image: nome:tag@sha256:...`).
- Sem Watchtower nem atualização automática: atualização é sempre pelo pacote.

## Atualização e rollback
- Toda imagem com **tag de versão fixa** (`0.1.0`), nunca `latest`; para terceiros, tag **mais digest**. O digest vale mesmo se a tag mudar.
- Atualizar: `docker load` das imagens novas, trocar o link `current`, `systemctl restart app` (ou `docker compose up -d --wait`, que recria só o que mudou de imagem ou configuração).
- Rollback: apontar `current` para a versão anterior (as imagens antigas continuam carregadas) e `docker compose up -d --wait`. Migração de banco é forward-only: o rollback do código só vale com migração compatível (skill `sql-standards`); senão, restaurar o backup.
- `docker image prune` pode apagar a imagem do rollback se nenhum container a usa. Não rode `prune -a`; o `appctl` descarrega só versões fora das duas últimas.

## Limites de recurso
- No Compose: `mem_limit`, `cpus`, `pids_limit` por serviço (ou `deploy.resources.limits`, aceito pelo Compose v2). Valores conservadores e documentados até medir no hardware alvo (sintaxe não verificada nesta revisão; confirme com `docker compose config`).
- Bancos têm limite na própria configuração (`shared_buffers`, `max_server_memory_usage`), coerente com o limite do container.

## Diagnóstico
```bash
docker compose config -q                       # valida o arquivo e a interpolação
docker compose ps --format 'table {{.Name}}\t{{.Status}}'
docker compose logs -f --tail 100 gateway
docker inspect --format '{{json .State.Health}}' app-gateway-1
systemctl status app && journalctl -u app -b
docker compose up -d --wait --wait-timeout 60   # mostra qual serviço não ficou saudável
```

## Armadilhas
- **`unhealthy` não reinicia o container.** O Docker só marca o estado; `restart: unless-stopped` reage a **saída** do processo. Não há equivalente nativo a "matar container doente". Faça o processo sair quando seu próprio estado é irrecuperável, ou monitore `docker inspect`/o evento `health_status` e reinicie por um watcher do appliance. Imagens de terceiros (ex.: `autoheal`) acrescentam acesso ao socket do Docker: evite.
- O healthcheck do Compose só é consultado na subida (`--wait`, `depends_on`); depois ele não bloqueia nada.
- `depends_on` ordena a subida de **um** `up`; se só o banco reiniciar depois, os dependentes seguem rodando. Retry com backoff nos serviços.
- `restart: unless-stopped` + `docker compose down` na unit: no `stop` do host o daemon para os containers e, no boot, só sobem os que não foram parados explicitamente. Confirme por teste de reboot, não por leitura.
- Bind mount com dono errado: serviço não-root não grava. Tmpfs some a cada restart.
- `ports:` sem IP publica em `0.0.0.0` e ignora o ufw.
- `docker compose down -v`, `volume prune` e `system prune --volumes` apagam dados. Proibidos.
- Mudar `daemon.json` (log, userns) exige reiniciar o daemon, o que derruba os containers sem `live-restore`; faça em janela.
- Daemon parado na instalação offline: `docker load` precisa dele no ar.

## Checklist de revisão
- [ ] Versão do Engine e do plugin Compose fixadas e `apt-mark hold`; repositório apt desligado no appliance.
- [ ] `image:` com tag exata do pacote (terceiros: tag + digest) e `pull_policy: never`.
- [ ] `user:` não-root, `read_only: true`, `cap_drop: [ALL]`, `no-new-privileges:true`.
- [ ] Nenhum `ports:` em banco ou barramento; portas de gateway com IP quando possível.
- [ ] Segredos por `secrets:`, arquivo 0400 com o dono igual ao `user:`; nada sensível em `environment:`.
- [ ] `healthcheck` + `depends_on: service_healthy`; migração oneshot com `service_completed_successfully`.
- [ ] `restart: unless-stopped` e unit do systemd com `TimeoutStopSec` maior que o maior `stop_grace_period`.
- [ ] Logs com `local` e rotação; volumes nomeados ou bind com dono correto.
- [ ] Limites de memória e CPU definidos; dados fora da imagem.
- [ ] Teste de reboot do servidor: tudo volta saudável sem intervenção.
