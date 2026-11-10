---
name: appliance-offline-package
description: Pacote de instalação e atualização offline do appliance on-premise — layout do .tar (manifesto, imagens, units Quadlet, configuração, migrações, instalador), manifesto com SHA-256 de cada arquivo e a combinação de versões dos serviços, imagens com podman save/load (oci-archive por imagem, tag reaplicada pelo ID), assinatura com minisign (Ed25519) e verificação embutida no instalador em Go (go-minisign), chave pública embutida e rotação de chave, cosign como alternativa e por que pesa offline, instalação atômica em /var/lib/<produto>/packages/<versão> com link current, ordem de instalação, rollback para a versão anterior, preservação de dados e testes de adulteração. Usar ao montar, assinar, validar, instalar ou atualizar o pacote do appliance, ou ao revisar o appctl.
---

# Pacote offline do appliance

Verificado em 16/10/2026: minisign 0.12 (ISC), `github.com/jedisct1/go-minisign` 0.2.6 (MIT), cosign v3.1.3 (Apache-2.0), Podman 4.9.3 no Ubuntu 24.04. Units: skill `podman-quadlet`.

## Princípios
- **Um arquivo leva tudo.** O appliance não tem internet: nada é baixado na instalação ou na atualização.
- **Nada roda sem assinatura válida.** O instalador verifica a assinatura **antes** de extrair ou executar qualquer coisa do pacote.
- **Instalar e atualizar são a mesma operação**, e o rollback é voltar para a versão anterior já instalada.
- **Dados nunca estão no pacote** e nunca são apagados por instalação, atualização ou rollback.
- **A combinação de versões é testada como um todo:** o pacote é a unidade de release.

## Layout do pacote
```text
<produto>-0.1.0.tar
├── manifest.json            versões, SHA-256 de cada arquivo, compatibilidade
├── manifest.json.minisig    assinatura do manifesto
├── appctl                  instalador da versão nova (Go, estático)
├── images/
│   ├── ingest-0.5.0.oci.tar
│   ├── persistence-0.3.1.oci.tar
│   ├── nats-2.15.1.oci.tar
│   └── postgres-18.x.oci.tar
├── quadlet/                 units .container/.network/.volume
├── config/                  configuração padrão (nats.conf, postgresql.conf...)
└── NOTES.md                 notas da versão
```

- Assina-se **só o manifesto**; ele contém o SHA-256 de todos os outros arquivos. Verificar = validar a assinatura do manifesto e depois o hash de cada arquivo.
- Migrações não ficam soltas no pacote: estão dentro da imagem de cada serviço (`<serviço> migrate`).

## Manifesto
```json
{
  "schema": "<produto>.package/v1",
  "package": "<produto>",
  "version": "0.1.0",
  "createdAt": "2026-10-16T18:00:00Z",
  "gitCommit": "02bb0df",
  "minUpgradeFrom": "0.0.0",
  "services": {
    "ingest":      { "version": "0.5.0", "image": "localhost/<produto>/ingest:0.5.0",      "imageId": "sha256:…" },
    "persistence": { "version": "0.3.1", "image": "localhost/<produto>/persistence:0.3.1", "imageId": "sha256:…" }
  },
  "contracts": ["<produto>.telemetry/v1", "<produto>.event/v1", "<produto>.status/v1"],
  "files": {
    "appctl": "sha256:…",
    "images/ingest-0.5.0.oci.tar": "sha256:…",
    "quadlet/<produto>-ingest.container": "sha256:…"
  }
}
```

- `files` lista **todo** arquivo do pacote, exceto o manifesto e a assinatura. Arquivo presente e fora da lista = pacote inválido.
- `imageId` é o ID da imagem (digest do config), estável entre `save` e `load`; serve para conferir que a imagem carregada é a assinada.
- `minUpgradeFrom` impede pular versões que exigem migração intermediária.

## Imagens
```bash
# build (CI): uma imagem por serviço, tag = versão do serviço
podman save --format oci-archive -o images/ingest-0.5.0.oci.tar localhost/<produto>/ingest:0.5.0
podman image inspect --format '{{.Id}}' localhost/<produto>/ingest:0.5.0   # vai para o manifesto

# instalação (appliance)
podman load -i images/ingest-0.5.0.oci.tar
podman tag <imageId do manifesto> localhost/<produto>/ingest:0.5.0          # garante a tag que a unit usa
```

- Um arquivo por imagem: o hash de cada uma fica no manifesto e a carga falha de forma isolada.
- Depois do `load`, confira o ID contra o manifesto e reaplique a tag pelo ID. Não confie no nome gravado no arquivo.
- Imagens de terceiros (NATS, PostgreSQL, ClickHouse) entram no pacote **fixadas por digest** no build; o CI registra a versão e o digest de origem no manifesto.
- Tamanho: centenas de MB (PostgreSQL e ClickHouse dominam). Compressão `zstd` no `.tar` externo é opcional; meça.

## Assinatura
### Recomendado: minisign
- Ed25519, formato simples, sem dependência de serviço externo: verificação totalmente offline.
- Ferramenta: `minisign` (jedisct1, ISC). Verificação no `appctl` com `github.com/jedisct1/go-minisign` (MIT), sem chamar binário externo.

```bash
# uma vez, em máquina segura: par de chaves com senha
minisign -G -p <produto>-release.pub -s <produto>-release.key

# CI de release: assina o manifesto
minisign -S -s <produto>-release.key -m manifest.json -t "<produto> 0.1.0"

# verificação manual
minisign -V -p <produto>-release.pub -m manifest.json
```

- **Chave privada:** fora do repositório; no CI só como segredo do ambiente de release, com aprovação manual. Guardar cópia offline (cofre físico).
- **Chave pública embutida no `appctl`** no build (constante no código). O `appctl` aceita uma **lista** de chaves confiáveis identificadas pelo key ID do minisign, para permitir rotação:
  1. nova versão do `appctl`, assinada com a chave antiga, passa a confiar nas duas chaves;
  2. versões seguintes são assinadas com a chave nova;
  3. depois de todos os appliances atualizados, a chave antiga sai da lista.
- A assinatura cobre o comentário confiável (`-t`); use-o para versão e nome do pacote e confira no `appctl`.

### Alternativa: cosign
- `cosign sign-blob --key` / `verify-blob --key` funcionam com chave própria, mas o cosign é feito para o ecossistema Sigstore (Rekor, Fulcio, bundles). Offline é preciso desligar o log de transparência na assinatura e na verificação, e o formato de bundle mudou nas versões recentes (v3). Mais peças para um ganho que o appliance não usa.
- Faz sentido se já se assinam imagens em registry com Sigstore.

## Instalação e atualização (`appctl install|update`)
Ordem, com parada no primeiro erro:

1. **Verificar sem extrair:** ler `manifest.json` e `.minisig` do `.tar`, validar assinatura com as chaves embutidas.
2. Extrair em `/var/lib/<produto>/packages/<versão>.tmp/` e conferir o SHA-256 de cada arquivo; arquivo sobrando ou faltando = falha. Renomear para `<versão>/` (atômico).
3. Conferir compatibilidade: versão atual ≥ `minUpgradeFrom`; espaço em disco.
4. **Backup antes de mudar** (atualização): dump do PostgreSQL conforme a política de backup; registrar a versão atual.
5. `podman load` de cada imagem, conferir `imageId`, reaplicar tags.
6. Gerar o que é por appliance só se ainda não existir: CA local, certificados, segredos (`podman secret create`). Reinstalar nunca troca segredos existentes.
7. Copiar units para `/etc/containers/systemd/`, `systemctl daemon-reload`, rodar o generator em `--dryrun` antes.
8. Subir em ordem; as units oneshot de migração rodam antes de cada serviço com banco.
9. **Verificar saúde:** esperar todos `active` e `/readyz` ok, com timeout. Falhou → rollback automático (passo seguinte).
10. Atualizar `/var/lib/<produto>/packages/current` → `<versão>` (link simbólico, troca atômica) e registrar a instalação em `/var/lib/<produto>/packages/history.log`.

- **Quem verifica:** na primeira instalação, o `appctl` que acompanha o pacote na mídia de instalação; na atualização, o `appctl` **já instalado** verifica o pacote novo e só depois executa o `appctl` contido nele para os passos seguintes. Nunca execute nada do pacote antes da verificação.
- Mantenha as duas últimas versões em `/var/lib/<produto>/packages/`; apague as mais antigas.

## Rollback
- `appctl rollback`: aponta `current` para a versão anterior, reinstala as units dela, `daemon-reload`, reinicia. As imagens antigas continuam carregadas.
- **Migração de banco é forward-only** (skill `sql-standards`): rollback do código funciona só se a migração da versão nova foi compatível com o código anterior (expand/contract). Migração incompatível exige restaurar o backup do passo 4; o `appctl` avisa e pede confirmação.
- `appctl uninstall` remove units e imagens e mantém `/var/lib/<produto>` e `/etc/<produto>`; `--purge` apaga dados, com confirmação explícita.

## Testes obrigatórios
- Alterar um byte de qualquer arquivo → instalação recusada.
- Acrescentar ou remover um arquivo do `.tar` → recusada.
- Manifesto assinado com chave fora da lista → recusado.
- Instalar do zero numa VM limpa **sem rede** → todos os serviços saudáveis.
- Reinstalar a mesma versão → nada muda (idempotente), segredos preservados.
- Atualizar com um serviço que não fica saudável → rollback automático e serviços da versão anterior no ar.
- Desinstalar e reinstalar → dados preservados.

## Checklist de revisão
- [ ] Verificação da assinatura acontece antes de extrair ou executar qualquer coisa.
- [ ] Manifesto lista o SHA-256 de todo arquivo; nada fora da lista é aceito.
- [ ] Imagens conferidas pelo ID e tag reaplicada; units com `Pull=never`.
- [ ] Imagens de terceiros fixadas por digest.
- [ ] Chave privada fora do repositório; chave pública embutida, com suporte a rotação.
- [ ] Segredos e certificados gerados só se ausentes; dados fora do pacote.
- [ ] Backup antes de atualizar; rollback testado; migrações compatíveis com a versão anterior.
