---
name: mqtt-broker
description: Escolha, configuração e operação de broker MQTT para chão de fábrica — comparativo Mosquitto 2.1 x EMQX 6 (licença BSL, cluster pago) x HiveMQ CE x NanoMQ, mosquitto.conf seguro (plugins password/acl da 2.1, limites, persistência), EMQX em Docker/Swarm (node name fixo, ACL deny-all, shared subscription e redispatch), autenticação por dispositivo, ACL de menor privilégio, TLS/mTLS, exposição via Traefik/Coolify/Dokploy, CVEs, monitoramento, backup e teste de carga. Usar ao subir, configurar, expor, monitorar ou escolher um broker MQTT.
---

# Broker MQTT

Versões verificadas em 14/10/2026: **Mosquitto 2.1.2**, **EMQX 6.3.1 LTS**, HiveMQ CE 2026.5, NanoMQ 0.25.6. Tópicos e payload: skill `mqtt-contract`. Cliente no serviço: `backend-fastify-mqtt`.

## Escolha
| | Mosquitto 2.1 | EMQX 6 | HiveMQ CE | NanoMQ |
|---|---|---|---|---|
| Licença | EPL/EDL | **BSL 1.1** desde a 5.9: **single node grátis em produção**, **cluster exige licença paga** | Apache 2.0 | MIT |
| Cluster | não | sim (pago) | não (só Enterprise) | não |
| Auth/ACL | arquivo, dynsec, plugins | built-in DB, JWT (JWKS), HTTP, LDAP, ACL em arquivo ou DB | só extensões Java | user/senha, JWT, HTTP |
| Dashboard / Prometheus | não / via exporter de `$SYS` | sim (18083) / nativo | não / extensão | não / nativo |
| Recursos | C, 1 core, poucos MB | Erlang, multi-core, centenas de MB | JVM | C, mínimo |

- **Padrão da equipe:**
  - **Mosquitto 2.1** para planta pequena ou média, quando a prioridade é simplicidade.
  - **EMQX single node** quando o projeto precisa de dashboard, Prometheus nativo, auth por DB/JWT/HTTP ou estratégias de shared subscription.
  - A escolha vai para um ADR.
- **HA:** Mosquitto, HiveMQ CE e NanoMQ não fazem cluster. Bridge entre dois brokers **não é HA** (não replica sessão).
  - Para uma planta, o realista é um broker com volume persistente e restart rápido, combinado com **store-and-forward nos gateways** e consumidor idempotente.
  - Cluster de verdade é EMQX licenciado ou HiveMQ Enterprise.
- **Capacidade:** uma fábrica média (de 1k a 20k msg/s) cabe em qualquer um. Benchmarks do fabricante indicam Mosquitto em cerca de 40–80k msg/s (limitado a 1 core) e EMQX e NanoMQ em mais de 250k msg/s. **Em geral o gargalo é o consumidor e o banco**, não o broker.

## Mosquitto 2.1
Mudanças da 2.1 que pegam:
- `password_file`, `acl_file` e `per_listener_settings` estão **deprecated** (saem na 3.0). Use os plugins `mosquitto_password_file` e `mosquitto_acl_file`.
- O **`max_packet_size` agora tem padrão de 2 MB**.
- `mosquitto_passwd` usa argon2id.
- Não use `persistence true` junto com o plugin `persist-sqlite`.
- TLS exige OpenSSL ≥ 3.
- Há suporte a PROXY protocol v1/v2 (para preservar o IP atrás do Traefik).

```conf
# /mosquitto/config/mosquitto.conf
persistence true
persistence_location /mosquitto/data/
autosave_interval 60                 # padrão 1800: num crash perde até 30 min de estado
persistent_client_expiration 7d      # sem isso, sessões abandonadas ficam para sempre

max_packet_size 262144               # ajuste ao maior lote do contrato
max_inflight_messages 20
max_queued_messages 10000            # excedente é descartado em silêncio
max_queued_bytes 104857600

allow_anonymous false
global_plugin /usr/lib/mosquitto_password_file.so     # confira o caminho na imagem
plugin_opt_password_file /mosquitto/config/passwd
global_plugin /usr/lib/mosquitto_acl_file.so
plugin_opt_acl_file /mosquitto/config/acl

listener 8883
cafile   /mosquitto/certs/ca.crt
certfile /mosquitto/certs/server.crt
keyfile  /mosquitto/certs/server.key
tls_version tlsv1.2
# mTLS: require_certificate true + use_identity_as_username true (CN = identidade)

listener 1884 127.0.0.1              # só para healthcheck local
log_dest stdout
```
ACL (`%u` = username, `%c` = clientId; o padrão ocupa um nível inteiro):
```conf
user svc-ingest
topic read acme/+/+/+/+/telemetry/#
topic read acme/+/+/+/+/event/#
topic read acme/+/+/+/+/status
topic write acme/+/+/+/+/cmd/#

pattern write acme/+/+/+/%u/#
pattern read  acme/+/+/+/%u/cmd/#
```
- O `pattern` acima deixa o gateway escolher site, área e linha. Para menor privilégio real, gere regras `user`/`topic` explícitas por gateway ou use o **dynsec** (`mosquitto_ctrl dynsec ...`, gerenciado em tempo real sem reload).
- Teste a ACL de verdade: publicação negada costuma ser **descartada em silêncio**.
- Docker: `eclipse-mosquitto:2.1.2-alpine`, com volumes `/mosquitto/config` (ro), `/mosquitto/data` e `/mosquitto/log`, e `stop_grace_period: 30s` para gravar o `mosquitto.db`.
- Healthcheck: use `mosquitto_sub -t '$SYS/broker/uptime' -C 1 -W 5` num listener local com credencial de health.
- Limitações: single-thread, sem cluster, sem Prometheus nativo, persistência por snapshot.

## EMQX 6
```yaml
services:
  emqx:
    image: emqx/emqx-enterprise:6.3.1
    hostname: emqx1.mqtt.internal                 # FIXO e FQDN
    environment:
      EMQX_NODE_NAME: emqx@emqx1.mqtt.internal    # igual ao hostname
      EMQX_DASHBOARD__DEFAULT_PASSWORD: ${EMQX_DASH_PASS}
    volumes: [emqx-data:/opt/emqx/data, emqx-log:/opt/emqx/log]
    healthcheck: { test: ["CMD", "/opt/emqx/bin/emqx", "ctl", "status"], interval: 10s, timeout: 25s, retries: 5 }
    deploy: { replicas: 1, placement: { constraints: [node.hostname == fab-srv1] } }
```
- **Node name e hostname fixos.** Os dados ficam em `data/mnesia/<node_name>`: trocar o node name (no Swarm, o hostname padrão muda a cada deploy) **apaga** usuários, ACL, retained e configuração feita pela UI.
- **ACL:**
  - o exemplo vem com `{allow, all}` no fim: troque por `{deny, all}` e configure `authorization.no_match = deny`;
  - editar pela UI grava em `data/authz/acl.conf`, e o arquivo original deixa de ser lido;
  - com centenas de regras, use o built-in DB.
```erlang
{allow, {user, "svc-ingest"}, subscribe, ["$share/ingest/acme/+/+/+/+/telemetry/#", "$share/ingest/acme/+/+/+/+/event/#"]}.
{allow, all, publish, ["acme/+/+/+/${clientid}/#"]}.
{allow, all, subscribe, ["acme/+/+/+/${clientid}/cmd/#"]}.
{deny, all, subscribe, ["$SYS/#", {eq, "#"}, {eq, "+/#"}]}.
{deny, all}.
```
- **Auth:** use built-in DB (credencial por dispositivo) ou JWT com TTL curto (claims `${clientid}` e `${username}`, claim `acl` opcional). Usar JWT exige TLS.
- **Shared subscription:**
  - `mqtt.shared_subscription_strategy` vem como `round_robin` por padrão. Use `hash_clientid` ou `hash_topic` para manter a ordem por device.
  - **O redispatch das QoS 1/2 pendentes a outro membro só ocorre quando a sessão expira**, não quando a conexão cai. Para isso, os consumidores em `$share` usam:
    - **`clientId` estável por réplica** (slot do Swarm), para que um restart reassuma a própria sessão em segundos;
    - **session expiry finito**, dimensionado para o downtime aceitável (ex.: 1 h). Expiry longo prende mensagens de réplicas removidas; expiry curto perde a fila numa queda longa do consumidor.
- **Durable sessions** (RocksDB) custam throughput e disco e não funcionam em NFS/SMB. Só ligue com motivo.
- **Observabilidade:**
  - `GET /api/v5/prometheus/stats` (**exige Basic auth com API key de escopo `monitoring` desde a 6.3**);
  - health em `/api/v5/status`.
- **Segurança:**
  - **nunca exponha a 18083 (dashboard)**;
  - troque a senha padrão;
  - use API keys com o menor papel possível;
  - fique em 6.3.1 ou 6.2.3+ (CVE-2026-44725, RCE via instalação de plugin).

## Segurança (qualquer broker)
- **TLS 1.2+ na 8883.** A 1883 fica desligada ou só em rede interna.
- **Uma credencial por dispositivo**, com `clientId` = username = `edge_id`.
  - **mTLS** (CN como identidade) é mais forte e exige PKI (step-ca) e renovação.
  - **Usuário e senha** são mais simples para o Node-RED. Na rotação, mantenha duas credenciais em paralelo durante a troca.
- **Menor privilégio:**
  - o gateway escreve só no próprio ramo e lê só o próprio `cmd/#`;
  - o consumidor só lê, exceto `cmd` se for ele quem comanda;
  - ninguém assina `#`;
  - termine com deny-all.
- **Não exponha o broker à internet.** Com o broker num VPS (Coolify/Dokploy) e gateways na fábrica, use VPN (WireGuard/Tailscale). Se não houver VPN, use 8883 com mTLS e firewall por IP de origem.
- **Atrás do Traefik (Coolify/Dokploy)**, precisa de um entrypoint TCP dedicado. As opções:
  1. **Publicar a 8883 direto do contêiner, sem Traefik.** É a mais simples e robusta; no Swarm, use `mode: host` para preservar o IP.
  2. **Terminar o TLS no Traefik.** Router TCP `HostSNI` + certresolver, apontando para a 1883. Perde o mTLS do cliente e o IP de origem (sem PROXY protocol).
  3. **Passthrough.** TLS e mTLS fim a fim, mas **exige SNI**, e muitos firmwares e conexões por IP não enviam.
- Mantenha o broker atualizado: Mosquitto ≥ 2.1.2, EMQX ≥ 6.3.1/6.2.3.

## Operação
- **Monitore:**
  - clientes conectados contra o inventário de gateways;
  - msgs in/out por segundo;
  - **dropped** (fila cheia, expirada);
  - fila e inflight por sessão;
  - retained;
  - falhas de auth e ACL;
  - disco da persistência.
- **Onde ler as métricas:**
  - Mosquitto: tópicos `$SYS/broker/...` (a cada `sys_interval`, 10 s) com exporter;
  - EMQX: `/api/v5/prometheus/stats`;
  - NanoMQ: `/api/v4/prometheus`.
- **Backup:**
  - **Mosquitto:** `mosquitto.db` (após `kill -USR1`), `passwd`, `acl` e `dynamic-security.json`.
  - **EMQX:** `emqx ctl data export` e o volume `data` com node name fixo.
  - **Config no git, segredos fora.**
  - Estado de sessão é perecível: a garantia de não perder dado está no gateway e no consumidor idempotente.
- **Teste de carga:**
  - `emqtt-bench` (`pub -c 200 -I 10 -s 512 -q 1`, `sub -t '$share/ingest/...'`) ou `mqtt-benchmark`;
  - sempre com TLS, QoS 1, payload real e o consumidor gravando no banco.
