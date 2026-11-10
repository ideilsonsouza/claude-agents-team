---
name: backend-fastify-mqtt
description: Cliente MQTT em serviço Fastify 5 com MQTT.js (mqtt 5.16) — plugin fastify-plugin com manualConnect/onReady/onClose, recepção com ack só após persistir via handleMessage (pump serial, backpressure, deadlock de publish no handler), sessão persistente MQTT 5 (sessionExpiryInterval, clientId estável por réplica), shared subscriptions, roteamento por tópico (mqtt-pattern), validação de payload e quarentena, idempotência, publicação de comandos (offline, timeout, message expiry, request/response), erros de auth e reconexão, health/readiness, métricas, graceful shutdown e testes (broker Mosquitto, Aedes, simulação de queda). Usar ao criar ou alterar código que usa o pacote mqtt num serviço Node.js/Fastify.
---

# MQTT em serviço Fastify (MQTT.js)

Versão de referência: **`mqtt` 5.16.x**. Fixe `^5.16.0`, porque a 5.16.0 corrigiu 6 advisories (crash por topic alias ou AUTH não solicitado, entre outros). Fontes: README e código em https://github.com/mqttjs/MQTT.js (`src/lib/client.ts`, `src/lib/handlers/publish.ts`) e a spec MQTT 5. Leia junto com `backend-fastify` e `mqtt-contract` (tópicos, payload e semântica). O broker está em `mqtt-broker`.

- **Tipos:** vêm embutidos. **Não instale `@types/mqtt`** (é um stub deprecado).
- **Import:** `import { connect, type MqttClient } from 'mqtt'` funciona em ESM no Node.
- **Não existe plugin Fastify mantido** (`fastify-mqtt` é de 2022 e `@fastify/mqtt` não existe). Use o plugin próprio desta skill.

## Como o MQTT.js recebe (entenda antes de codar)
- **O processamento é serial por conexão.** O cliente processa um pacote por vez, e o próximo só sai quando o `handleMessage` chama `done`. Enquanto isso, a leitura do socket pausa e o backpressure volta por TCP até o broker. **Isso vale também para PINGRESP e para os PUBACKs das suas próprias publicações.**
- **Ordem por QoS:**
  - **QoS 1:** `emit('message')` → `handleMessage(packet, done)` → **PUBACK só depois de `done()`**. É assim que se garante "ack só depois de persistir".
  - **QoS 2:** o PUBREC sai na chegada. `'message'` e `handleMessage` só rodam no PUBREL, e o PUBCOMP sai depois do `done()`.
- **`done(err)`:**
  - **não envia ack e não emite `error`**: o erro some em silêncio, então logue você;
  - o processamento segue para a próxima mensagem;
  - a mensagem só é reentregue (`packet.dup = true`) **na reconexão com sessão persistente**;
  - cada mensagem sem ack ocupa um slot do in-flight do broker, e esgotados os slots o broker para de enviar QoS 1/2 até reconectar.
- **`done` nunca chamado** trava o cliente. Depois de cerca de 1,5×keepalive vem um `Keepalive timeout` e a reconexão.
- **Deadlock:** **nunca faça `await client.publishAsync(..., { qos: 1 })` (nem espere qualquer resposta MQTT) dentro do `handleMessage`.** O PUBACK dessa publicação fica atrás do processamento bloqueado (issue #2026, sem correção).
- **Vazão:** cerca de 1/latência do handler por conexão (2 ms por insert dá cerca de 500 msg/s). Para escalar:
  1. faça o handler gravar rápido (insert simples numa tabela de entrada ou num job BullMQ) e processe o pesado de forma assíncrona;
  2. use **N clientes** (no mesmo processo ou em réplicas) no mesmo grupo `$share`.
  - **Não dá para agrupar mensagens e dar ack depois**: o ack está amarrado ao callback de cada mensagem.
- **Escolha um lugar só para processar:** o `'message'` dispara antes do `handleMessage`, e usar os dois duplica o trabalho. **Padrão: só `handleMessage`.**
- **Topic alias:** com alias, `packet.topic` pode chegar `''` no `handleMessage`. Não configure `topicAliasMaximum` como receptor (o default é 0).
- **Reason code no ack** (`customHandleAcks`, só MQTT 5): um código ≥ 0x80 é **descarte definitivo**, não retry, e em `$share` não vai para outro membro. A equipe não usa: payload inválido vai para a quarentena e recebe ack normal.

## Opções do cliente (receptor)
| Opção | Default | Padrão da equipe |
|---|---|---|
| `protocolVersion` | 4 | **5** |
| `clientId` | aleatório | **estável e único por réplica**, ex.: `svc-ingest-${SLOT}` (`{{.Task.Slot}}` no Swarm). **Nunca o mesmo id em duas réplicas** (loop de "session taken over", reason 142) e nunca o hostname aleatório (deixa sessões órfãs a cada deploy) |
| `clean` | true | **false** (Clean Start = 0) |
| `properties.sessionExpiryInterval` | 0 | **definir sempre** (ex.: 3600). Com `clean:false` e sem expiry, a sessão morre ao desconectar. Cubra o downtime esperado. No EMQX, o redispatch de `$share` só ocorre quando a sessão expira |
| `properties.receiveMaximum` | 65535 | 20–100 (limita o in-flight do broker para esta conexão) |
| `properties.maximumPacketSize` | — | o maior lote do contrato com folga (protege a memória) |
| `reconnectPeriod` | 1000 ms fixo, sem backoff | 2000–5000 |
| `connectTimeout` | 30000 | 10000 |
| `keepalive` | 60 s | 30–60; o handler precisa ser muito mais rápido que isso |
| `reconnectOnConnackError` | false | ver "Auth recusada" |
| `queueQoSZero` | true | false (não acumula QoS 0 offline) |
| TLS | `rejectUnauthorized: true` | `mqtts://` + `ca` (+ `cert`/`key` em mTLS). Nunca desligue a verificação |
| `manualConnect` | false | **true** no plugin (handlers instalados antes de conectar) |

## Plugin Fastify (receptor e publicador)
```ts
// src/plugins/mqtt.ts
import fp from 'fastify-plugin';
import { connect, ErrorWithReasonCode, type IClientOptions, type IPublishPacket, type MqttClient } from 'mqtt';

declare module 'fastify' {
  interface FastifyInstance { mqtt: MqttClient; mqttReady: () => boolean }
}
type Opts = { url: string; client: IClientOptions; subscriptions: string[]; handle: (p: IPublishPacket) => Promise<void> };
const AUTH_RC = new Set([4, 5, 134, 135, 138]);

export default fp<Opts>(async (app, opts) => {
  const client = connect(opts.url, {
    protocolVersion: 5, clean: false, reconnectPeriod: 5000, connectTimeout: 10_000, queueQoSZero: false,
    ...opts.client, manualConnect: true,
    properties: { sessionExpiryInterval: 3600, receiveMaximum: 50, ...opts.client.properties },
  });
  let draining = false;
  let inflight = 0;
  let lastPacketAt = Date.now();

  client.handleMessage = (packet, done) => {
    if (draining) return done(new Error('draining'));      // sem ack: reentregue na próxima sessão
    inflight++;
    opts.handle(packet)
      .then(() => done(), (err: Error) => { app.log.error({ err, topic: packet.topic }, 'mqtt: falha, sem ack'); done(err); })
      .finally(() => { inflight--; });
  };
  client.on('packetreceive', () => { lastPacketAt = Date.now(); });
  client.on('connect', (ck) => {
    app.log.info({ sessionPresent: ck.sessionPresent }, 'mqtt conectado');
    if (!ck.sessionPresent) app.log.warn('mqtt: sessão nova (mensagens de enquanto offline perdidas, se houver)');
  });
  client.on('offline', () => app.log.warn('mqtt offline'));
  client.on('disconnect', (p) => app.log.warn({ rc: p.reasonCode }, 'mqtt: DISCONNECT do broker')); // 142 = takeover
  client.on('error', (err) => {
    if (err instanceof ErrorWithReasonCode && AUTH_RC.has(err.code)) app.log.fatal({ err }, 'mqtt: auth recusada');
    else app.log.error({ err }, 'mqtt error');
  });

  app.decorate('mqtt', client);
  app.decorate('mqttReady', () => client.connected && !draining);

  app.addHook('onReady', async () => {
    client.connect();
    await new Promise<void>((resolve) => {                 // sobe não-pronto se o broker estiver fora
      const t = setTimeout(resolve, 10_000);
      client.once('connect', () => { clearTimeout(t); resolve(); });
    });
    client.subscribe(opts.subscriptions, { qos: 1 }, (err) => err && app.log.error({ err }, 'mqtt subscribe'));
  });

  app.addHook('preClose', async () => { draining = true; });
  app.addHook('onClose', async () => {
    const deadline = Date.now() + 8_000;
    while ((inflight > 0 || Object.keys(client.outgoing).length > 0) && Date.now() < deadline) {
      await new Promise((r) => setTimeout(r, 50));
    }
    // end(false) espera 'outgoingEmpty' SEM timeout e uma 2ª chamada a end() vira no-op: decida o force antes
    await client.endAsync(!client.connected || Object.keys(client.outgoing).length > 0);
  });
}, { name: 'mqtt', fastify: '5.x' });
```
- **Não use `connectAsync` com o broker possivelmente fora:** ele rejeita no primeiro `ECONNREFUSED` e encerra o cliente (e com `manualConnect` nunca resolve).
- O deadline do `onClose` precisa ser **menor** que o `delay` do `close-with-grace`, e esse menor que o `stop_grace_period`.
- **Desligamento:**
  - `end(false)` envia DISCONNECT 0 e não publica o Will;
  - `end(true)` só destrói o socket, e o broker publica o Will;
  - **`client.reconnect()` sem argumentos zera os stores** e perde o in-flight.
- **Auth recusada (5.16):** por padrão **não reconecta** e o cliente fica parado sem `end` (issue #2072). Escolha uma:
  - **(a) padrão:** logar fatal, readiness falha e o alerta dispara;
  - **(b)** `reconnectOnConnackError: true` com `reconnectPeriod` alto (tenta para sempre, sem backoff).
- **Watchdog:** há bugs abertos em que o cliente não reconecta mais (PR #2068: socket em black-hole). Se ficar mais de N min sem `connected`, encerre o processo com erro e deixe o orquestrador reiniciar.

## Handler: roteamento, validação, idempotência
```ts
import { exec } from 'mqtt-pattern';
const TELEMETRY = 'acme/+site/+area/+linha/+edgeId/telemetry/+grupo';

async function handle(packet: IPublishPacket) {
  const t = exec(TELEMETRY, packet.topic);            // { site, area, linha, edgeId, grupo } | null
  if (!t) return quarantine(packet, 'topico_desconhecido');
  let body: unknown;
  try { body = JSON.parse((packet.payload as Buffer).toString('utf8')); } catch { return quarantine(packet, 'json_invalido'); }
  const parsed = telemetryV1.safeParse(body);          // Zod (contrato em mqtt-contract)
  if (!parsed.success) return quarantine(packet, 'schema_invalido', parsed.error);
  if (parsed.data.deviceId !== t.edgeId) return quarantine(packet, 'device_divergente_do_topico');
  await ingest.receber(parsed.data, { origem: 'mqtt', topico: packet.topic, dup: packet.dup }); // INSERT ... ON CONFLICT DO NOTHING
}
```
- **Roteamento:** use `mqtt-pattern` (mantido; wildcards nomeados extraem site, linha e device). Com dezenas de milhares de filtros, use `qlobber`. `mqtt-wildcard` está abandonado.
- **Payload é sempre `Buffer`.** Faça `JSON.parse` dentro de `try`. **Mensagem inválida vai para a quarentena** (tabela com tópico, payload bruto e motivo) **e recebe ack**. Deixar sem ack para sempre esgota o in-flight e trava o consumo.
- **Erro transitório** (banco fora): lance para não dar ack e logue. Retry interno, se houver, cabe no orçamento do keepalive.
- **Idempotência obrigatória:** QoS 1 e reentregas geram duplicatas. Chave única `(deviceId, seq)` ou `msgId` + `ON CONFLICT DO NOTHING`. Conte as duplicatas como métrica.
- **Mesmo serviço para MQTT e HTTP:** `ingest.receber()` é chamado pelo handler MQTT e pela rota `POST /v1/ingest` (resposta `202`), com o mesmo schema Zod.
- **Ordem:** com `$share` e reentregas não há ordem global. Use o `ts`/`seq` do payload. Grave o dado fora de ordem e nunca descarte "porque é mais velho".
- `packet.properties?.userProperties` (MQTT 5) traz `schema` e `traceId` quando o publicador manda. Propague o `traceId` nos logs.

## Shared subscription e escala
- Assine `'$share/ingest/acme/+/+/+/+/telemetry/#'`. O MQTT.js não trata `$share` de forma especial: o `packet.topic` chega com o **tópico real**, sem o prefixo.
- Cada réplica (ou cada cliente extra no processo) usa um **clientId próprio** no mesmo grupo. Não há ordem entre os membros.
- Retained não é entregue ao criar uma shared subscription. Estado (`status`, `state`) deve ser lido numa assinatura normal, num consumidor único.
- Ao reduzir réplicas, a sessão do slot removido fica órfã até expirar, prendendo mensagens (no EMQX, redistribuídas na expiração). Por isso o `sessionExpiryInterval` é finito.

## Publicar comandos
```ts
async function enviarComando(app: FastifyInstance, edgeId: string, acao: string, cmd: Comando) {
  if (!app.mqtt.connected) throw app.httpErrors.serviceUnavailable('broker indisponível'); // falha rápido
  const topic = `acme/${cmd.site}/${cmd.area}/${cmd.linha}/${edgeId}/cmd/${acao}`;
  await withTimeout(app.mqtt.publishAsync(topic, JSON.stringify(cmd), {
    qos: 1,
    properties: { contentType: 'application/json', messageExpiryInterval: 30,
                  userProperties: { traceId: cmd.traceId }, correlationData: Buffer.from(cmd.msgId) },
  }), 5_000);
}
```
- **`publishAsync` QoS 1/2 offline não falha:** vai para o `outgoingStore` (em memória e **sem limite**) e a promise fica pendente até reconectar. O mesmo acontece se o broker derrubar a conexão por ACL. **Sempre use timeout**. Ao desistir, chame `client.removeOutgoingMessage(messageId)` para não reenviar um comando velho.
- **`messageExpiryInterval` é obrigatório em comandos** (um comando não executa horas depois).
- PUBACK com reason ≥ 0x80 rejeita com `ErrorWithReasonCode` (ex.: 0x87 não autorizado). `0x10` (sem assinantes) conta como sucesso.
- **Request/response (MQTT 5):** assine `svc/replies/<clientId>`, publique com `responseTopic` + `correlationData` e resolva num `Map<msgId, { resolve, timer }>` alimentado pelo `handleMessage`. **Nunca espere a resposta dentro do próprio handler.**
- O `maximumPacketSize` do broker não é verificado na saída. Respeite o limite do contrato.

## Health e métricas
- **Liveness não depende do broker** (senão todas as réplicas são mortas numa queda do broker).
- **`/health/ready`** retorna `app.mqttReady()` + banco OK + (opcional) `Date.now() - lastPacketAt` abaixo de um limite, para detectar o cliente travado.
- **Métricas:**
  - mensagens recebidas por tópico ou classe;
  - processadas, em quarentena (por motivo), duplicadas e com falha (sem ack);
  - latência do handler;
  - `inflight`;
  - reconexões e `sessionPresent = false`;
  - lacunas de `seq` por device.

## Testes
- **Unitário:** chame `handle()` com um `IPublishPacket` fake (`{ topic, payload: Buffer.from(json), qos: 1, dup: false }`). Cubra cada motivo de quarentena e a deduplicação.
- **Integração (MQTT 5):** Postgres dos serviços locais da máquina (ver `~/.claude/CLAUDE.md`, seção Serviços locais) (banco `test_<projeto>_<id>` apagado ao terminar; no CI, serviço da esteira). O Mosquitto não existe nos serviços locais da máquina (ver `~/.claude/CLAUDE.md`, seção Serviços locais): pergunte ao dono antes de criar um; no CI, use o broker da esteira.
  - Publique com um **cliente cru** (`connectAsync` + `publishAsync`), igual ao gateway, e verifique o banco.
  - Casos obrigatórios:
    1. a mesma mensagem duas vezes grava uma só;
    2. com o banco fora, não há ack, e depois de reconectar com `clean:false` chega a reentrega com `dup` e a gravação acontece;
    3. payload inválido vai para a quarentena e o consumo segue;
    4. `app.close()` encerra sem perder o in-flight.
- **Queda de conexão:**
  - `client.stream.destroy()` derruba o socket abruptamente (o broker publica o Will);
  - reiniciar o broker (só em broker que a própria execução criou com autorização do dono; nunca serviço compartilhado);
  - toxiproxy (latência ou black-hole) não existe nos serviços locais da máquina (ver `~/.claude/CLAUDE.md`, seção Serviços locais): pergunte ao dono antes de criar.
- **Aedes 1.2** (ESM, em memória) **não suporta MQTT 5**. Use-o só em testes unitários rápidos com `protocolVersion: 4`, ou para simular auth recusada (`aedes.authenticate`). Para MQTT 5, use Mosquitto (ver regra acima sobre criar o broker).
- Encerre tudo no `afterAll`: `app.close()`, o cliente de teste e os containers.

## Armadilhas (checklist de revisão)
1. Com MQTT 5, `clean:false` **sem** `sessionExpiryInterval` deixa a sessão descartável.
2. `clientId` repetido entre réplicas causa loop de takeover. Hostname aleatório deixa sessões órfãs.
3. `done(err)` é silencioso e não dá ack. Mensagem inválida sem ack trava o consumo: use a quarentena.
4. `await` de publish QoS 1 ou de resposta dentro do `handleMessage` causa deadlock.
5. Processar no `'message'` e no `handleMessage` ao mesmo tempo duplica o trabalho.
6. `publishAsync` offline fica pendente para sempre e as filas não têm teto: timeout e `messageExpiryInterval`.
7. Auth recusada (5.16) para de reconectar: alerte.
8. `endAsync(false)` pode travar e uma 2ª chamada a `end` é no-op: decida o `force` antes.
9. Topic alias no receptor deixa `packet.topic` vazio.
10. Use `mqtt@^5.16.0`; não instale `@types/mqtt`.
