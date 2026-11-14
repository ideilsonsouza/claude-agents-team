---
name: edge-gateway
description: "Software de gateway de borda que lê equipamentos industriais (Modbus, OPC UA) e envia telemetria à API central: polling, contadores, store-and-forward em SQLite, idempotência, OTA e segurança. Usar ao desenhar, implementar ou revisar o gateway, o endpoint de ingestão ou a atualização remota."
---

# Gateway de borda (leitura, store-and-forward e OTA)

Padrão da equipe, genérico. Fontes ao fim. Pseudocódigo de contador, esquema da fila e exemplo de payload em `references/algoritmos.md`. Conexão persistente, ciclo de leitura x registro, buffer e resumo da janela em `references/conexao-e-janela.md`.
- Detalhes de Rust (async, erros, crates, build cruzado): skill `rust-standards`.
- Transporte MQTT (QoS, tópicos, payload, LWT): skill `mqtt-contract`. Aqui o transporte padrão é HTTPS; as regras de idempotência e ordem valem para os dois.
- Pacote de atualização offline de appliance: skill `appliance-offline-package`.

**Princípios:** a borda **nunca perde produção** e **nunca inventa dado**; tudo o que ela calcula o servidor consegue **recalcular** a partir do bruto; dispositivo em campo **não é atualizado junto** com a API.

## 1. Leitura
- **Um laço por conexão física** (porta serial, IP do equipamento). Tag com erro registra o erro **na própria tag** (`q: "bad"`, contador de erros, último erro) e o laço segue. Erro de conexão marca todas as tags daquela conexão como `bad`, sem afetar as demais.
- **Timeout em toda requisição** (Modbus TCP: 1–3 s; RTU: calcule pelo baud rate e pela quantidade de registradores; HTTP: timeout total, não só de conexão). Retry curto (1–2) dentro do ciclo; depois disso, reconexão com backoff. Nunca retry infinito no mesmo ciclo.
- **Ciclo atrasado não acumula:** se uma leitura estoura o período, pule os ticks perdidos (sem rajada para "recuperar").
- **Modbus:**
  - agrupe registradores contíguos numa leitura (FC03/FC04 aceitam no máximo 125 registradores por requisição);
  - **valor de 32 bits sempre na mesma requisição** que lê os dois registradores; ler em duas requisições mistura palavras de instantes diferentes;
  - ordem de palavra e de byte configurável **por tag** (o Modbus não define a ordem em 32 bits). Valores absurdos e repetitivos indicam ordem trocada;
  - RTU: um mestre por barramento, acesso serializado à porta, `unit id` por equipamento; exceções Modbus (02 endereço ilegal etc.) viram erro da tag, não da conexão.
- **OPC UA:** prefira *subscription* (MonitoredItem com `samplingInterval` e deadband no servidor) quando o equipamento suporta; use Read em lote como fallback. Segurança `SignAndEncrypt` com lista de certificados confiáveis (nunca "aceitar qualquer certificado"). Mapeie o `StatusCode` para `q` e use o `SourceTimestamp` quando confiável.
- **HTTP (equipamento):** limite de tamanho da resposta, TLS verificado quando houver, sem seguir redirect para outro host.
- **Relógios:**
  - **monotônico** para agendar, medir intervalo, timeout, backoff e idade da fila;
  - **de parede (UTC)** só para carimbar o `ts` da leitura;
  - nunca calcule intervalo com relógio de parede: um ajuste do NTP gera delta negativo ou gigante.
- **Sem horário confiável** (placa sem RTC sobe com hora velha; `fake-hwclock` apenas aproxima):
  - o gateway expõe `timeOk` (ex.: `timedatectl show -p NTPSynchronized`, ou o estado do chrony);
  - enquanto `timeOk=false`, **continua lendo e enfileirando**, guarda `monoNs` + `bootId` em cada leitura e envia `timeOk: false`;
  - ao sincronizar, corrige as leituras do **mesmo boot**: `ts = wall_sync − (mono_sync − mono_leitura)`;
  - leituras que não puderem ser corrigidas seguem com `timeOk: false`; o servidor usa `receivedAt` e a ordem do `seq`, e marca o dado;
  - em equipamento crítico, prefira RTC com bateria. No chrony, `makestep` permite saltar o relógio no início em vez de corrigir devagar.
- **Conexão com o equipamento** (persistente x por leitura, ocioso, erro, backoff): `references/conexao-e-janela.md` §1.

## 2. Dado bruto × processado
- **Toda leitura leva o bruto e o processado:** `raw` (valor decodificado do equipamento, antes de escala) e `v` (após escala, offset e unidade), mais `cfgRev`. Para contadores, também `total` (acumulado da borda) e `delta`.
- **Contadores** (algoritmo em `references/algoritmos.md`):
  - **normal:** `delta = atual − anterior`;
  - **rollover:** atual < anterior, anterior perto do máximo e atual perto de zero → `delta = (max − anterior) + atual + 1`. O `max` é por tag (2^16−1, 2^32−1 ou teto decimal como 999999);
  - **reset do equipamento:** atual < anterior sem padrão de rollover → `delta = atual` (o equipamento recomeçou de zero) e evento `counter.reset` com os dois valores;
  - **queda pequena (ruído):** regressão ≤ tolerância → `delta = 0` e **a referência não muda** (se ela baixasse, a produção seria contada de novo na volta);
  - **salto implausível** (acima da taxa máxima × intervalo): `q: "uncertain"`, não soma ao `total`, envia o bruto e um evento; o servidor decide;
  - **reboot do gateway:** `last_raw` e `total` por tag ficam no SQLite, **na mesma transação** que enfileira a leitura. No boot, a primeira leitura compara com o `last_raw` persistido; a produção feita com o gateway desligado entra no delta. **Nunca** use a primeira leitura após o boot como novo zero.
- **Deadband:**
  - analógica: envia se `|v − último enviado| > deadband` (absoluto ou %) **ou** se passou o intervalo máximo sem envio (ex.: 60 s), para provar que a tag está viva;
  - **contador: deadband nunca descarta produção.** O que se envia é o acumulado (`raw` + `total`); pular amostras só reduz resolução. Em contador, prefira "enviar a cada N unidades ou T segundos";
  - mudança de `q` sempre é enviada.
- **Conversão e escala versionadas:**
  - a configuração (tags, endereço, tipo, ordem de palavra, escala, offset, unidade, deadband, `max` do contador, tolerância) tem `cfgRev` (inteiro crescente ou hash do conteúdo);
  - cada leitura leva o `cfgRev` usado;
  - no boot e a cada mudança, inclusive mudança feita na UI local, o gateway envia o **snapshot completo** da configuração; o servidor guarda por `(deviceId, cfgRev)`;
  - assim o servidor recalcula `v` a partir de `raw` quando uma escala estava errada, sem depender da borda.
- **Ciclo de leitura x janela de registro, buffer e resumo da janela:** `references/conexao-e-janela.md` §2–3.

## 3. Store-and-forward
- **Fluxo:** leitura → INSERT na fila local (transação) → envio em lote → resposta 2xx com ack → DELETE → próximo lote. A leitura **nunca** vai direto da memória para a rede.
- **SQLite:**
  - `journal_mode=WAL` + **`synchronous=FULL`**. Com `NORMAL` em WAL, uma transação confirmada pode voltar atrás após queda de energia (doc oficial). Bibliotecas às vezes mudam o padrão: configure explicitamente;
  - `busy_timeout`, um escritor só, `wal_autocheckpoint` padrão e `journal_size_limit` para o WAL não crescer sem limite;
  - agrupe os INSERTs do ciclo numa transação (menos `fsync`, menos desgaste do cartão SD). Prefira mídia industrial ou SSD; ext4 com journaling;
  - `PRAGMA quick_check` no boot. Se falhar: renomeia o arquivo (preserva para análise), cria fila nova, emite evento e continua lendo;
  - sem banco em rede (NFS) e com folga de disco: o checkpoint precisa de espaço.
- **Limite da fila:** por bytes, por linhas e por idade, dimensionado pela taxa × tamanho médio × dias de autonomia desejados (ex.: 7 dias sem rede). Ao encher:
  - descarte primeiro as amostras **analógicas** mais antigas (ou reduza a resolução);
  - **eventos e contadores são os últimos**: como o contador vai acumulado, a amostra mais recente já contém a produção;
  - registre `queue.overflow` com a quantidade descartada (métrica e evento) e mantenha uma reserva mínima de disco livre.
- **Lote:** fecha pelo que ocorrer primeiro entre N leituras, M bytes e T segundos (ex.: 500, 256 KB, 5 s), sempre abaixo do limite de corpo do servidor. Compressão gzip opcional.
- **Apagar só após confirmação:**
  - **2xx com corpo de ack** (`accepted`, `duplicates`, `rejected`) → apaga o lote;
  - timeout ou conexão caída **não é confirmação**: reenvia o mesmo lote, e o servidor deduplica;
  - 400/422 permanente → move as leituras rejeitadas para uma quarentena local (*dead letter*) com o motivo; sem isso, uma leitura ruim trava a fila para sempre;
  - 401/403 → para o envio, sinaliza credencial no heartbeat e **continua enfileirando**;
  - 408, 429, 5xx e erro de rede → retry. Respeite `Retry-After`.
- **Backoff exponencial com *full jitter*:** `espera = aleatório(0, min(teto, base × 2^tentativa))`, teto de 1 a 5 min, volta ao início após sucesso. Na volta da rede, drene com taxa limitada: centenas de gateways voltando juntos derrubam a API.
- **Ordem:** FIFO por padrão. Priorizar o ao vivo sobre o backlog é opcional e exige que o servidor aceite fora de ordem (seção 4).

## 4. Idempotência e ordem
- **Identidade de cada leitura:** `deviceId` (do provisionamento, estável), `bootId` (UUID novo a cada início do processo) e `seq` (monotônico, persistido no SQLite na mesma transação da leitura).
  - **Chave única no servidor: `(deviceId, bootId, seq)`.** Mesmo que o SQLite seja perdido e o `seq` recomece, o `bootId` novo evita colisão.
  - Salto de `seq` no mesmo `bootId` = perda; registre como métrica.
- **Servidor:** `INSERT ... ON CONFLICT DO NOTHING` na chave única; duplicata conta como sucesso no ack, para o gateway apagar. O lote é gravado numa transação, ou o ack lista o que entrou e o que não entrou.
- **Atrasadas e fora de ordem:** o servidor aceita qualquer `ts`. Nada de "descartar se for mais velho que o último". O "valor atual" só é atualizado se `ts` for maior que o atual (o Sparkplug B chama isso de dado histórico). Agregados por janela precisam ser recalculáveis quando chega dado antigo.
- **Três horários:** `ts` (origem, da leitura), `sentAt` (gateway, no envio) e `receivedAt` (servidor). Atraso de ingestão = `receivedAt − ts`. Se `|receivedAt − sentAt|` passar de um limite, o relógio do gateway está errado: sinalize `clockSkew` e trate as leituras como `timeOk: false`.

## 5. Evolução do contrato com dispositivos em campo
- **Só aditivo:** campo novo é opcional, com default no servidor. O servidor **ignora campo desconhecido** em vez de rejeitar (*tolerant reader*). Remover, renomear ou mudar tipo exige rota ou versão nova em paralelo.
- **Versões no payload:** `schema` em cada envio e versão do firmware no heartbeat e no `User-Agent`.
- **Matriz de compatibilidade (obrigatória no PR):**
  - **firmware novo × API velha:** o firmware envia o campo novo e a API velha ignora. O firmware não pode depender de resposta nova: ele detecta a capacidade (versão na resposta do ping) e, sem ela, volta ao comportamento antigo;
  - **firmware velho × API nova:** o formato antigo continua aceito **sem prazo**, enquanto houver dispositivo enviando. Uma métrica de envios por `schema` e versão de firmware mostra quando ele zera; só então se discute remover.
- **Validação em sombra antes de trocar a fonte dos números** (ex.: passar a usar o `total` da borda em vez do cálculo do servidor):
  1. os dois caminhos rodam em paralelo; o servidor recalcula a partir de `raw` + snapshot de configuração e compara com o processado da borda;
  2. divergência por dispositivo e por período (absoluta e %) vira relatório;
  3. critério de corte escrito antes (ex.: divergência < 0,5% por 14 dias nos dispositivos piloto);
  4. troca por flag por dispositivo ou cliente, com reversão imediata para a fonte antiga.

## 6. Atualização remota (OTA)
- **Como trocar:**
  - SO inteiro: imagem **A/B** (RAUC, SWUpdate, Mender), em que o bootloader escolhe a partição e conta tentativas de boot;
  - só o aplicativo: baixe para `releases/<versão>/`, verifique, e troque o link `current` com `rename()` (atômico no mesmo filesystem), mantendo a versão anterior. Nunca sobrescreva o binário em uso.
- **Assinatura verificada antes de instalar**, com a chave pública embutida no firmware:
  - **minisign** (Ed25519): leve, funciona offline. Verifique também o *trusted comment* (versão, alvo), que é assinado; o *untrusted comment* não é;
  - **cosign** (`verify-blob` com bundle): mais dependências; use versão atual (bundles antigos tinham a CVE-2022-36056) e confira a identidade;
  - confira o SHA-256 de cada arquivo do manifesto e **recuse versão abaixo da mínima** (anti-downgrade). Assinatura ausente ou inválida = falha fechada.
- **Rollback automático:**
  - a versão nova sobe "em teste". Health = processo vivo + configuração válida + ao menos uma leitura bem-sucedida + fila gravável, dentro de X minutos;
  - passou → confirma (no RAUC, `rauc status mark-good`, que zera o contador de tentativas); falhou ou travou → o bootloader ou o supervisor volta para a anterior e reporta `update.failed` com o motivo;
  - **não condicione o health só à API:** com a API fora do ar, toda a frota voltaria de versão. Use "envio ok **ou** rede indisponível desde antes da atualização".
- **Canal e pinagem:** cada dispositivo tem um canal (`pilot`, `stable`) e o servidor responde com a versão alvo **pinada** (versão exata + SHA-256 + URL + assinatura). **Nunca** "baixar sempre a última".
- **Gradual:** ondas (1 dispositivo → piloto → 10% → 50% → 100%), com critério de avanço (falha de update, erro por tag, idade da fila, reinícios) e parada automática. Atualize fora do horário de produção, ou em janela configurada.
- **Dispositivos offline:** o pedido fica pendente no servidor e o dispositivo puxa ao voltar (*pull*); download retomável (`Range`); espaço verificado antes. Quem ficou muito tempo offline pode pular versões: o manifesto declara a versão mínima de origem e as migrações do SQLite local. A fila **sobrevive** à atualização (a versão nova lê o formato antigo). Instalação local por mídia segue a mesma verificação (`appliance-offline-package`).

## 7. Saúde e diagnóstico
- **Heartbeat** periódico (ex.: 60 s) com `deviceId`, versão de firmware, `schema`, `cfgRev`, `bootId`, uptime, `timeOk`, fila (linhas, bytes, idade da mais antiga), último envio ok, descartes por overflow, erros por tag (contagem e último erro), disco livre, memória e temperatura. O servidor marca offline após cerca de 3 intervalos sem heartbeat.
- **Logs locais:** journald com `SystemMaxUse`, ou arquivo com rotação por tamanho. Log estruturado, sem segredo, com limite de repetição (o mesmo erro de tag não pode encher o disco). Nível ajustável remotamente com expiração.
- **Watchdog:** `WatchdogSec=` com `sd_notify` a cada ciclo saudável, `Restart=always`. Laço travado = reinício, não processo vivo e inútil.
- Diagnóstico remoto só por comandos de lista fechada (reenviar configuração, coletar logs, forçar heartbeat). Sem shell remoto.

## 8. Segurança
- Implementação em Rust (Argon2id, rate limit por IP, token, SSE, segredo mascarado, https, verificação minisign, systemd e `NoNewPrivileges` x `sudo`): `security-rust`. O que segue é o requisito, não o código.
- **Credencial por dispositivo** (token ou certificado X.509 para mTLS), gerada no provisionamento e nunca compartilhada entre dispositivos; revogação individual no servidor.
  - **Rotação com sobreposição:** o servidor emite a nova, o dispositivo grava e usa, e a antiga só é revogada depois do primeiro uso da nova.
  - Arquivo `0600` do usuário do serviço; TPM ou *secure element* quando houver.
- **TLS sempre com verificação** de cadeia e hostname. Sem `insecure` nem "skip verify", nem em modo debug. Relógio errado faz o TLS falhar ("certificado ainda não válido"): sincronize antes, monitore, e não desligue a verificação.
- **UI local:**
  - desligada por padrão, ou só em localhost ou na rede de manutenção;
  - autenticação obrigatória, **sem senha padrão** (senha única por dispositivo, ou definida na instalação), com rate limit;
  - **falha fechada:** sem configuração de autenticação válida, a UI não abre;
  - mudança de configuração feita nela gera `cfgRev` nova e evento auditável.
- **Superfície mínima:** o gateway só abre conexões de saída; firewall bloqueando a entrada; SSH só com chave; serviços desnecessários desligados; rede do chão de fábrica separada da rede de saída.
- **systemd endurecido:** usuário dedicado sem login, `NoNewPrivileges=yes`, `ProtectSystem=strict` + `ReadWritePaths=/var/lib/<app>`, `ProtectHome=yes`, `PrivateTmp=yes`, `CapabilityBoundingSet=` vazio, `RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX`, `SystemCallFilter=@system-service`, `MemoryMax=`. Para RTU: `DevicePolicy=closed` + `DeviceAllow=/dev/ttyUSB0 rw` e grupo `dialout`. Meça com `systemd-analyze security <unit>`.

## 9. Testes
- **Simulador de equipamento:** servidor Modbus de teste (pymodbus ou equivalente) com cenários: contador crescendo, rollover de 16 e 32 bits, reset, queda pequena, salto, ordem de palavra trocada, sem resposta e exceção Modbus.
- **Rede:** proxy de falhas (ex.: Toxiproxy) ou API de teste controlável com latência, reset, 5xx, 429 + `Retry-After` e, o caso essencial, **timeout depois de o servidor gravar**.
- **Energia e reboot:** `kill -9` no meio do lote; em hardware, corte de energia por relé em laço (dezenas de ciclos). Depois de cada ciclo: `quick_check` ok, nenhuma leitura confirmada perdida, `total` dos contadores igual à produção simulada.
- **Duplicata:** o mesmo lote enviado duas vezes resulta na mesma contagem no servidor, com 2xx.
- **Contador:** testes de tabela e baseados em propriedade (soma dos deltas = produção simulada com rollover, reset, ruído e reboot intercalados).
- **Relógio:** relógio injetável; testes de salto do NTP para frente e para trás e de boot sem horário.
- **Contrato:** fixtures de payload de **cada versão de firmware em campo** rodam contra o servidor no CI; formato antigo que deixa de ser aceito reprova o PR. Schema (JSON Schema ou OpenAPI) compartilhado entre borda e servidor.
- **OTA:** assinatura inválida é rejeitada; versão que não passa no health volta sozinha; queda de energia durante a instalação deixa o dispositivo na versão anterior.

## 10. Checklist de revisão de PR (firmware de borda)
1. Erro de uma tag ou de um equipamento deixa o laço e as outras conexões rodando? Toda chamada tem timeout?
2. Intervalos, timeouts e backoff usam relógio monotônico? O que acontece sem NTP (`timeOk`)?
3. A leitura vai com `raw`, `v` e `cfgRev`? Mudança de configuração gera `cfgRev` nova e snapshot?
4. Contador: rollover, reset, ruído, salto e reboot cobertos por teste? A referência é persistida na mesma transação da fila?
5. O deadband pode descartar produção de contador?
6. SQLite com WAL + `synchronous=FULL`? A fila tem limite e política de overflow que preserva contadores e eventos?
7. Apaga só após 2xx com ack? Timeout reenvia o mesmo lote? 4xx permanente vai para quarentena em vez de travar a fila?
8. Backoff com full jitter e teto? Drenagem com taxa limitada? `Retry-After` respeitado?
9. `(deviceId, bootId, seq)` em toda leitura e chave única no servidor? Duplicata responde como sucesso?
10. Contrato só aditivo? Matriz firmware novo × API velha e firmware velho × API nova verificada, com fixtures das versões em campo?
11. Troca da fonte de números tem validação em sombra e critério de corte?
12. OTA: assinatura verificada antes de instalar, versão pinada, anti-downgrade, rollback por health que não depende só da API, fila preservada?
13. Heartbeat traz versão, fila, último envio e erros por tag? Logs com rotação e sem segredo?
14. Credencial por dispositivo, TLS verificado, UI local sem senha padrão e com falha fechada, unit systemd endurecida?
15. Detalhes de linguagem conferidos contra `rust-standards` e, se houver MQTT, contra `mqtt-contract`?
16. Conexão persistente por equipamento, reconexão + 1 retry só em erro de transporte, backoff, e ciclo de leitura separado da janela de registro?

**Anti-padrões que reprovam o PR:** apagar da fila antes do ack; leitura direto da memória para a rede; primeira leitura após o boot como novo zero; deadband em contador; `synchronous=NORMAL` ou `OFF` na fila; retry sem jitter; intervalo medido com relógio de parede; campo obrigatório novo no contrato; "baixar sempre a última"; binário sem assinatura; TLS sem verificação; senha padrão na UI local; UI que abre sem autenticação quando a configuração falha.

## Fontes
- SQLite, PRAGMA `synchronous`, `journal_size_limit`, `wal_autocheckpoint`: https://www.sqlite.org/pragma.html
- AWS Architecture Blog, "Exponential Backoff And Jitter": https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/
- AWS IoT Greengrass v2, stream manager (lote por tamanho e intervalo, persistência em arquivo, prioridade): https://docs.aws.amazon.com/greengrass/v2/developerguide/work-with-streams.html e https://docs.aws.amazon.com/greengrass/v2/developerguide/configure-stream-manager.html
- AWS, identidade e rotação de credenciais de dispositivo: https://docs.aws.amazon.com/prescriptive-guidance/latest/security-reference-architecture/device-identities.html e https://aws.amazon.com/blogs/iot/how-to-manage-iot-device-certificate-rotation-using-aws-iot/
- Azure IoT Edge, capacidades offline (`storeAndForwardConfiguration.timeToLiveSecs`, armazenamento dedicado): https://learn.microsoft.com/azure/iot-edge/offline-capabilities
- Eclipse Sparkplug 3.0 (bdSeq, seq, dado histórico, STATE): https://www.eclipse.org/tahu/spec/sparkplug_spec.pdf e https://www.hivemq.com/blog/whats-new-eclipse-sparkplug-30-specification-iiot-industry-40
- RAUC, integração (contador de boot, `rauc status mark-good` após o sistema subir, bundles assinados): https://rauc.readthedocs.io/en/latest/integration.html
- SWUpdate (cópia dupla, `sw-description` assinado): https://manpages.debian.org/testing/swupdate/swupdate.1.en.html
- Mender, deployments (rollout em fases, pendente até o dispositivo pedir, "already-installed"): https://docs.mender.io/overview/deployment
- minisign (trusted comment assinado, modo prehash) e verificação em Rust: https://docs.rs/crate/minisign/latest/source/src/lib.rs ; cosign CVE-2022-36056: https://github.com/advisories/GHSA-8gw7-4j42-w388
- systemd sandboxing: https://wiki.debian.org/ServiceSandboxing
- pymodbus simulator: https://pymodbus.readthedocs.io/en/latest/source/simulator.html
