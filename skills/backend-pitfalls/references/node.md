# Armadilhas específicas de Node/TypeScript

Confirme sempre na versão instalada (`.d.ts` e fonte em `node_modules/<pacote>`).

## Timeouts
- `Promise.race` com prazo não cancela nada. Ex.: `close()` do transporte SMTP do nodemailer (sem pool) só emite `close`; a conexão em voo segue e o envio acontece depois do "tempo esgotado". Leia na fonte o que o `abort`/`close` encerra; prefira `AbortSignal` suportado pela biblioteca.
- O prazo pode disparar antes de o `abort` ser atribuído: crie o controlador antes de iniciar a operação.
- Teste de timeout com fake que só conta `close()` prova a chamada, não o efeito: confira que nada é enviado depois.

## Banco e logs
- knex (e ORMs sobre ele, como Lucid) põe o SQL com os valores em `err.message` (salvo `compileSqlOnError: false`); o reporter de erro loga a mensagem e o redact do pino por chave não pega. Dado pessoal ou segredo em consulta → confira a config.
- Chamada a terceiro dentro da transação do request: segura conexão do pool e travas pelo tempo da rede.
- Resposta montada em `afterCommit` que engole exceção: corpo padrão vira 200 vazio.
- Duas travas consultivas, a segunda tomada dentro do primeiro write: o snapshot lido antes fica fora dela.

## Entrada e HTML
- Validação de tamanho antes de `toLowerCase`/`normalize`: valide o valor final.
- Deny-list de HTML sobre htmlparser2: o parser não implementa o breakout de `<svg>`/`<math>` do navegador e trata alguns elementos como RCDATA de forma diferente; payloads como `<svg><p><style><a title="</style><img src=x onerror=...>">` passam. Use sanitizador de allowlist (DOMPurify no servidor com jsdom, ou equivalente mantido).
- Exceção na validação de URL ("começa com `{{`") vira bypass.

## Credenciais e formulários
- Edição parcial de credencial: cifra que não abre (`saved === null`) não pode contar como "campo mudou"; formulário que reenvia todos os campos sem ETag desfaz mudança alheia.
- Upsert público por contato não verificado (e-mail, telefone) permite sobrescrever dado de outra pessoa.

## Filas (BullMQ) e sandbox
- Ver classe 3 do `SKILL.md` (jobId determinístico x conjunto de falhas). jobId com versão que reinicia volta a colidir com job `completed` retido.
- Teto de saída de código em sandbox (isolated-vm) medido no host depois de copiar/parsear o valor inteiro: meça dentro do Isolate. Builtins capturados ainda chamam `toJSON` de protótipos trocados; acumule em string primitiva ou `Object.create(null)`.
- Pool do app x `CONNECTION LIMIT` do role: some réplicas e deploy start-first.
