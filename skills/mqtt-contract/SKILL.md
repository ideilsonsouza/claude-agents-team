---
name: mqtt-contract
description: "Contrato MQTT da equipe para dados de chão de fábrica: semântica do MQTT 5 (QoS, sessão, retained, LWT), tópicos em UNS ISA-95, payload JSON com ts, seq e qualidade, Sparkplug B. Usar ao desenhar ou revisar tópicos, payloads, ACLs ou produtor/consumidor MQTT."
---

# Contrato MQTT (tópicos, payload e semântica)

Fontes: especificação MQTT 5.0 (https://docs.oasis-open.org/mqtt/mqtt/v5.0/os/mqtt-v5.0-os.html), HiveMQ sobre UNS e Eclipse Sparkplug 3.0. O contrato de tópicos e payload é **padrão da equipe** (não normativo): todo projeto o documenta em `docs/mqtt-contract.md` e versiona mudanças.

## Semântica do MQTT 5 que muda o código
- **QoS 1 é o padrão.** Ele entrega pelo menos uma vez e **gera duplicatas** (reenvio com `dup` após reconexão). Por isso todo consumidor é **idempotente**.
  - QoS 0 perde mensagem em qualquer queda.
  - QoS 2 é "exatamente uma vez" **só em cada salto** (cliente↔broker), não fim a fim, e é mais lento. Não resolve o que a idempotência resolve.
- O broker entrega com a **menor** QoS entre a da publicação e a da assinatura.
- **Sessão:**
  - `Session Expiry Interval` 0 ou ausente: a sessão morre junto com a conexão.
  - Expiry maior que 0: o broker guarda as assinaturas e **enfileira QoS 1/2 enquanto o cliente está offline**.
  - `Clean Start = 1` descarta a sessão anterior.
  - Fila cheia (`max_queued_messages` no Mosquitto, `max_mqueue_len` no EMQX) **descarta em silêncio**. Monitore os descartes.
- **Retained:** o último valor fica guardado no tópico e é entregue a quem assina depois.
  - Use **só para estado e config** (status online/offline, modo, receita ativa). **Nunca use em telemetria**, porque o assinante novo receberia um valor velho como se fosse atual.
  - Para apagar, publique um payload vazio com retain.
  - Na assinatura, `rh` (retain handling) vale 0 = recebe, 1 = só em assinatura nova, 2 = nunca.
- **Will (LWT) + Will Delay:** publicado quando a conexão cai sem DISCONNECT, depois do delay (ou no fim da sessão). Se o cliente reconecta antes do delay, o Will não sai, o que evita flapping.
- **Message Expiry:** o broker descarta a mensagem vencida. **Obrigatório em comandos** (um comando não pode ser executado horas depois).
- **Receive Maximum:** quantas QoS 1/2 ficam em voo por conexão (padrão 65535). É o controle de fluxo do consumidor: mantenha baixo (50–200) quando o ack só sai depois de persistir.
- **User Properties:** metadados (`schema`, `traceId`) sem mexer no payload. Exigem MQTT 5 nos dois lados.
- **Ordem** é garantida só por tópico, mesma QoS, mesmo publicador e mesmo assinante.
  - **Shared subscription quebra a ordem entre os membros do grupo.** Use `ts`/`seq` do payload como verdade de ordem, ou a estratégia `hash_clientid` (EMQX).
- **PUBACK com reason code:**
  - `0x10` (sem assinantes) é sucesso.
  - Falha de ACL (`0x87`) muitas vezes é **descartada em silêncio** pelo broker, e o publicador não fica sabendo. Teste as ACLs explicitamente.
- Tópicos diferenciam maiúsculas e minúsculas. A `/` inicial cria um nível vazio. Tópicos `$...` não casam com `#`. Pacote acima do `Maximum Packet Size` derruba a conexão (`0x95`).

## Tópicos: Unified Namespace (ISA-95)
```
<empresa>/<site>/<area>/<linha>/<edge_id>/telemetry/<grupo>    QoS 1, sem retain
<empresa>/<site>/<area>/<linha>/<edge_id>/event/<tipo>         QoS 1 (alarme, parada, troca de lote)
<empresa>/<site>/<area>/<linha>/<edge_id>/state/<item>         QoS 1, retain
<empresa>/<site>/<area>/<linha>/<edge_id>/status               QoS 1, retain + LWT
<empresa>/<site>/<area>/<linha>/<edge_id>/cmd/<acao>           QoS 1, message expiry curto
<empresa>/<site>/<area>/<linha>/<edge_id>/cmd/<acao>/res       resposta (ou Response Topic + Correlation Data)
```
- Use minúsculas, `snake_case`, sem espaço, sem acento e sem `/` no início ou no fim. Não use `$`, `+` ou `#` em nomes.
- **O `edge_id` fica em posição fixa** e é igual ao `clientId`/username do gateway, para que a ACL por padrão (`%u`, `${clientid}`) funcione.
- **Não coloque no tópico dados de alta cardinalidade** (timestamp, lote, ordem de produção, valor). Eles vão no payload.
- Separe as classes (`telemetry`, `event`, `state`, `status`, `cmd`). Elas têm QoS, retain e expiry diferentes, e os consumidores assinam por classe.
- **Consumidor nunca assina `#` amplo.** Use filtros por classe (`acme/+/+/+/+/telemetry/#`) e escale com `$share/<grupo>/<filtro>`.
- Mudança de hierarquia é breaking change: versione e publique em paralelo durante a transição.

### Status do gateway (padrão)
- Na conexão, o Will é `{"online":false,"ts":...}` em `.../status`, com retain, QoS 1 e Will Delay de cerca de 30 s.
- Logo após o CONNACK, o gateway publica `{"online":true,"ts":...}` com retain no mesmo tópico.
- O receptor mantém o estado online/offline de cada gateway a partir desse tópico.

## Payload JSON
**Telemetria em lote:**
```json
{
  "schema": "acme.telemetry/v1",
  "deviceId": "gw-env-l1",
  "msgId": "01J9Z6K8N3Q4R5S6T7V8W9X0YZ",
  "seq": 184223,
  "sentAt": "2026-10-14T13:05:02.120Z",
  "readings": [
    { "tag": "envasadora1.temp_bico", "ts": "2026-10-14T13:05:00.000Z", "v": 82.4, "unit": "Cel", "q": "good" },
    { "tag": "envasadora1.contador",  "ts": "2026-10-14T13:05:01.000Z", "v": 15873, "unit": "count", "q": "good" }
  ]
}
```
**Evento:**
```json
{ "schema": "acme.event/v1", "deviceId": "gw-env-l1", "msgId": "01J9Z6M...", "seq": 184224,
  "ts": "2026-10-14T13:05:03.500Z", "type": "alarm.raised",
  "data": { "code": "E-104", "severity": "high", "text": "Pressão baixa" } }
```
Regras:
- **`ts` é o horário da leitura na origem, em UTC**, num formato só por projeto: ISO 8601 com `Z` ou epoch em ms. O receptor grava `receivedAt` à parte e não substitui o `ts`.
- **Idempotência:** chave única `(deviceId, seq)` ou `msgId` (ULID/UUIDv7).
  - O `seq` é monotônico e persistido no gateway (sobrevive a reboot).
  - Um salto no `seq` indica perda: registre como métrica.
- **`unit`:** use UCUM/SI declarada (`Cel`, `bar`, `m3/h`, `count`).
- **`q`:** `good`, `uncertain` ou `bad`. O código bruto vai opcionalmente em `qCode`.
- **Versão:** `schema` no payload, ou na User Property `schema`.
  - Campo novo opcional é mudança aditiva e mantém a versão. Remover, renomear ou mudar tipo gera `v2`, publicada em paralelo durante a transição.
  - O consumidor rejeita versão desconhecida (vai para a quarentena, não é descartada em silêncio).
- **Lote** agrupado por tempo ou quantidade (ex.: 1 s ou 100 leituras), com dezenas de KB e **bem abaixo do `max_packet_size`** do broker.
- O store-and-forward do gateway reenvia lotes atrasados com o `ts` original. O consumidor aceita dado fora de ordem.
- **Comandos** levam `msgId`, `expiresAt` (além do Message Expiry) e resposta com o mesmo `msgId` (ou Correlation Data).
- Payload inválido nunca derruba o consumidor: ele vai para uma tabela ou tópico de quarentena com o motivo.

## Sparkplug B: quando usar
- O Sparkplug B (Eclipse, v3.0) define tópico `spBv1.0/<group>/<NBIRTH|NDEATH|DBIRTH|DDATA|NCMD|...>/<edge_node>[/<device>]`, payload **protobuf**, sessão com `bdSeq`/`seq` e o estado do host em `spBv1.0/STATE/<host_id>`. As versões 2.2 e 3.0 são incompatíveis no mesmo broker.
- **Adote** quando houver SCADA ou historian que fala Sparkplug (Ignition etc.), muitos tags e necessidade de *state awareness* padronizada.
- **Padrão da equipe: JSON no UNS ISA-95.** Quem consome é um serviço próprio (Fastify), e JSON é depurável e simples no Node-RED. O Sparkplug fica para uma integração futura via bridge ou conversão.
