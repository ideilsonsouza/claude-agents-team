# Conexão com o equipamento, ciclo de leitura x registro, buffer e resumo da janela

Complemento das seções 1 e 2 do `SKILL.md`. Pesquisa de 2026-11-12 (fontes ao fim). Onde a fonte é fórum ou relato, está marcado como prática de campo, não especificação.

## 1. Gerenciamento da conexão (Modbus TCP e similares)
- **Padrão: uma conexão persistente por equipamento (IP:porta + unit id).** Abrir e fechar a cada leitura é o padrão de alguns clientes (openHAB, Modbus4J), mas é a origem comum de recusa: muitos escravos aceitam só 1 a 4 conexões simultâneas (ex.: ABB PM573 = 4 por padrão; placas de relé Ethernet) e demoram a liberar a vaga. Com ciclo curto (≤ 10 s), conectar a cada leitura multiplica handshakes e pode esgotar as vagas, inclusive as de outros sistemas (SCADA, IHM) que leem o mesmo equipamento.
- **Ocioso:** o Modbus não define timeout de conexão; o equipamento costuma fechar socket ocioso entre 30 e 60 s (switch/firewall: 60 a 300 s) (prática de campo). Regra: manter aberta enquanto o intervalo entre leituras for menor que o **limite de ocioso** configurável por dispositivo (padrão 30 s); acima disso, fechar ao fim da leitura e reconectar na próxima.
- **Erro trata a conexão, não a tag:** timeout, `ECONNRESET`, `EPIPE`, EOF, resposta com transaction id trocado ou quadro inválido → descartar a conexão, reconectar e **repetir uma vez no mesmo ciclo**. Deu certo: leitura boa e aviso no log (não contar como ruim). Falhou: amostra ruim e backoff.
- **Exceção Modbus** (01 função ilegal, 02 endereço ilegal, 03 valor ilegal) é resposta válida do equipamento: erro da tag, **sem** reconectar. Exceção 06 (ocupado) e 0B (gateway sem resposta do escravo) → retry curto, sem reconectar o TCP.
- **Backoff entre falhas consecutivas** (exponencial com jitter, teto ~30 s), por conexão. Sonda de status separada da leitura para mostrar "offline" sem martelar o equipamento.
- **Serializar por conexão:** uma requisição por vez por socket, a menos que a biblioteca e o equipamento suportem pipelining comprovadamente. Um laço por conexão física (SKILL.md §1).
- **Modo de compatibilidade por dispositivo:** "conectar a cada leitura" como opção para equipamento frágil que trava com conexão longa ou que fecha após uma resposta (relatos existem). Nunca como padrão global.
- **Teste obrigatório:** simulador que fecha a conexão ociosa, timeout, reset no meio da resposta, limite de N conexões; métrica de conexões abertas por minuto na carga (deve ficar ~0 em regime, só reconexão em erro).

## 2. Ciclo de leitura x janela de registro
Os produtos de mercado separam **quando lê** de **quando grava/publica**:
- **Kepware IoT Gateway:** scan rate por tag (lê) e publish rate por agente (envia); entre os dois, buffer em memória (100 mil eventos por agente; cheio, descarta o novo). Opção "wide format" publica só o último valor de cada tag por publicação. Deadband opcional por tag.
- **Ignition Tag Historian:** modo de amostragem (On Change, Periodic, Tag Group), deadband (absoluto/percentual) e **Max Time** entre amostras (grava mesmo sem mudança, prova que a tag está viva).
- **AWS IoT SiteWise Edge:** scan rate por fonte Modbus, buffer local antes de publicar, agregação na borda (janelas de até 15 min no processor).

Regras da equipe:
- **Ler a cada ciclo; gravar uma linha por janela por tag.** O SQLite só recebe a linha registrada (fsync por janela, não por leitura), num lote por tick.
- **Escolha da amostra registrada:** a mais recente de melhor qualidade (boa > incerta > ruim). Janela em que **todas** falharam grava a última ruim (rastreabilidade de comunicação). Janela sem tentativa (tag desligada) não grava.
- **Buffer da janela em memória** (anel por tag, com teto de itens) alimenta a tela ao vivo; é limpo quando a janela fecha. Perda em queda de energia limitada à janela corrente; parada graciosa faz flush.
- **Contador nunca depende do buffer:** o registro leva o acumulado; a produção da janela sai da diferença entre registros (SKILL.md §2).

## 3. Resumo da janela (agregado na borda)
Campos opcionais por registro, calculados de forma incremental (O(1) de memória por tag, sem guardar a lista): `n` (leituras), `nGood`, `nBad`, `min`, `max`, `avg`, `first`, `last`, opcionalmente `tFirst`/`tLast`.

Quando vale a pena, por tipo de sinal:
| Sinal | Valor do resumo | Recomendação |
|---|---|---|
| Analógico de processo (corrente, tensão, temperatura, pressão, vazão) | Alto: média representa energia/carga melhor que 1 ponto; `max` pega pico/sobrecarga; `min` revela parada dentro da janela | Ligar |
| Contador de produção (acumulado) | Baixo: o acumulado já contém a produção. `min < first` revela reset dentro da janela | Desligado; só `first`/`last`/`min` se quiser detectar reset |
| Estado/discreto (ligado, alarme) | Médio: `avg` de 0/1 = fração do tempo ligado; transições se perdem | Opcional; para estado, prefira registrar por mudança |
| Peso de balança | Depende do processo (pesagem por evento x carga contínua) | Decidir com o processo |
| Qualidade da comunicação (todas as tags) | Alto e barato: `nGood/n` por janela dá cobertura; a curadoria descarta janela pouco coberta | Ligar (só contagens) |

Custos e riscos:
- **Volume:** alguns números a mais por registrador por linha (dezenas de bytes em JSON; compressão colunar no servidor reduz muito). Ordem de grandeza bem menor que enviar todas as leituras do ciclo (×N leituras por janela).
- **Contrato:** campo novo **opcional** (só aditivo), versionado; servidor velho ignora. O resumo não é recalculável no servidor (ele não tem as leituras do ciclo): documentar como dado de borda, junto com a qualidade da janela.
- **Semântica:** `avg` simples assume leituras igualmente espaçadas; com buracos, prefira média ponderada pelo tempo ou registre `n` para o consumidor julgar. `avg` de contador não tem sentido: configurar por tag.
- **Curadoria:** só gera valor se as lógicas da curadoria passarem a usar os campos; até lá é custo sem retorno. Ligar junto com o indicador que o consome.

## Fontes
- Kepware IoT Gateway (scan x publish, buffer, wide format, deadband): https://www.ptc.com/en/support/help/-/media/86FE5F479F7C49AA9CE348E8D6F08721.ashx ; https://support.ptc.com/help/kepware/kepware_edge/en/kepware/kepware-edge/edge-iot-mqtt.html
- Ignition, Configuring Tag History e How the Tag Historian works: https://docs.inductiveautomation.com/docs/8.1/ignition-modules/tag-historian/configuring-tag-history ; https://docs.inductiveautomation.com/docs/8.1/ignition-modules/tag-historian/how-the-tag-historian-system-works
- AWS IoT SiteWise processor (agregação na borda) e buffered ingestion: https://docs.aws.amazon.com/greengrass/v2/developerguide/iotsitewise-processor-component.html ; https://aws.amazon.com/about-aws/whats-new/2023/11/aws-iot-sitewise-buffered-batched-measurement-data
- Conexões Modbus TCP (prática de campo): https://community.openhab.org/t/modbus-binding-implemented-tcp-connection-mechanism/79422 ; https://community.openhab.org/t/modbus-binding-limit-connections/55958 ; https://ni.lithium.com/t5/LabVIEW/Modbus-Bad-Idea-to-Disconnect-Reconnect-Regulary/m-p/4438269
