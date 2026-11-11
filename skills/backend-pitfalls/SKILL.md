---
name: backend-pitfalls
description: "Classes de defeito recorrentes em backend (concorrência, idempotência, filas, autorização, entrada, timeouts, segredos, datas, testes que não provam, montagem), com perguntas para fazer antes de entregar. Usar antes de entregar código de backend e ao revisar."
---

# Armadilhas de backend

Destilado de defeitos reais pegos em revisão e QA, 1–2 rodadas depois de o código ser escrito. Use **antes de entregar**: para cada classe que o diff toca, responda às perguntas. Resposta "não sei" = escreva o teste que responde.

Específico de linguagem: `references/go.md` (pgx, River, chi, slog) e `references/node.md` (nodemailer, knex, htmlparser2).

## 1. Concorrência e TOCTOU
- **Leitura fora da trava decide o que acontece sob a trava?** Toda condição checada antes (vínculo, papel, status, prazo, "organização viva") precisa ser **revalidada sob a trava**, todas, não só a que motivou a correção. Corrigir um atributo e esquecer o vizinho é o defeito mais comum.
- **A ordem das travas é a mesma dos fluxos irmãos?** Fluxo novo que trava B depois A, onde os existentes travam A depois B, gera deadlock sob carga. Segunda trava tomada "preguiçosamente" no meio da escrita deixa a leitura anterior desprotegida.
- **A mesma leitura derivada é feita duas vezes na transação?** Em READ COMMITTED cada comando vê um snapshot novo: duas leituras podem discordar. Leia uma vez, ou trave.
- `EXISTS` sem trava como guarda (pai vivo, sem duplicata) não segura um DELETE/INSERT concorrente entre o EXISTS e o commit: use `FOR KEY SHARE`/`FOR UPDATE` no pai ou restrição no banco.
- Reconciliação "estado externo x linha do banco": carimbe o instante da leitura externa e só compare linhas que mudaram antes dele.
- Cache invalidado por pub/sub precisa de **geração/versão**: o preenchimento em voo (leu antes, grava depois do aviso) reinstala o valor revogado.

## 2. Idempotência e reenvio
- **Quem decide "criei" x "já existia"?** `INSERT ... ON CONFLICT DO NOTHING` seguido de releitura faz o perdedor da corrida (mesmo id) também se ver como criador. Use `RETURNING` (linha voltou = criou) ou `xmax = 0`. Teste as duas corridas: mesmo id e ids diferentes.
- **Erro determinístico de dado vira "tente de novo"?** Item com dado que o banco sempre recusa (NUL, valor fora do domínio, SQLSTATE classe 22/23) respondido como 5xx num lote com reenvio integral é **poison message**: trava a fila para sempre. Erro de dado → rejeição do item (4xx/`rejected`); só falha transitória → retry.
- Idempotência por timestamp ou por "parece igual" quando a tabela não guarda o id do objeto: guarde a chave de idempotência.
- Cota/limite de reenvio que o fluxo de criação não consome, ou cuja chave inclui a rota quando a regra trata duas rotas como uma cota só.
- Contrato "erro = nada aplicado" com efeito posterior ao commit (revogação, publicação): a falha depois do commit precisa de um código distinto ou de tolerância.

## 3. Jobs e filas
- **Como o job sai de `running` se o processo morre?** Todo ramo da última tentativa (erro, panic, timeout, cancelamento) precisa fechar o estado; senão o índice único parcial "vivo" bloqueia a próxima execução para sempre.
- **Timeout do job x resgate de job preso:** o resgate tem de ser maior que o maior timeout de execução, senão o job é reexecutado em paralelo consigo mesmo. Confira qual timeout a biblioteca usa no cálculo (o por worker pode não entrar).
- **jobId determinístico + item que falha sempre:** o job falho retido no conjunto de falhas faz o `add` virar no-op; com `ORDER BY antigo LIMIT N`, N falhas antigas param a fila de todos. Pergunte: o que tira o item da seleção? O que reenfileira quando a lógica muda? Decida pelo estado do job na fila, não por um registro que pode não ter sido gravado.
- **Varredura global** (job que percorre todas as linhas/tenants) precisa de lote com teto, métrica de pendente vencido e não pode depender de um índice ausente na FK (DELETE em pai sem índice na filha varre tudo).
- Uma ordem "por nó" que falha de modo persistente e é re-reivindicada pelo mesmo nó segura a vez de todas as outras. Identidade da réplica (hostname) vazia ou repetida: trate o erro.

## 4. Autorização
- **A rota nova é irmã de outra que já tem guarda?** Anti-escalada (não conceder papel acima do próprio, não mexer no dono) tem de valer em **toda** rota que concede papel: convite, aceite, adição de membro, troca de papel. Reusar só metade da checagem é o caso típico.
- **BOLA provada com vínculo real?** O teste "usuário A acessa recurso de B" precisa que A tenha sessão válida e vínculo real em outro tenant; sem vínculo o 403 vem de outra guarda e o teste não prova nada.
- **A guarda está só no handler?** Serviço, job e função SQL chamados por outros caminhos precisam da própria checagem (ou o caminho alternativo fura).
- Tenant vindo de duas fontes (cabeçalho validado, URL usada); filtro opcional que substitui o escopo; parâmetro `tenantID` recebido e não usado; upsert com `SET tenant_id = EXCLUDED.tenant_id` (troca o dono).
- Escrita com escopo que devolve OK quando afeta 0 linhas: o teste por status passa com a condição quebrada; releia o efeito.
- Papel global e papel de tenant com o mesmo nome; sessão que guarda papel e não é revogada ao rebaixar/desativar.
- Rota pública que lê sessão opcional: sessão inválida deve virar anônimo, não 500 nem privilégio.
- Identificador "não forjável" exposto como tipo convertível (alias) não isola nada.

## 5. Entrada e limites
- **Algum teto (memória, linhas, laço, alocação) é derivado de campo que o cliente envia?** Limite fixo no servidor, sempre.
- **Valida antes de normalizar?** `maxLength` antes de `toLowerCase`/NFKC/trim mede outra string. Normalize, depois valide.
- Texto livre: rejeite NUL e caracteres de controle (o Postgres recusa `\u0000` em `text`).
- **Open redirect:** "começa com `/` e não com `//`" deixa passar `/\evil.com` e variantes; parse a URL e compare origem.
- **SSRF:** allowlist de "rede privada" inclui faixas IPv6 (fc00::/7) onde há endpoint de metadados de nuvem; negue metadados (IPv4 e IPv6, IPv4-mapeado) **antes** de liberar. Resolva e valide o IP no momento da conexão.
- Limite por IP atrás de proxy: use só o cabeçalho que o proxy reescreve; cabeçalho que o cliente controla gira o balde.
- Exceções na validação ("valor que começa com `{{` é template") viram bypass.
- Deny-list de HTML feita sobre parser que não é o do navegador: prefira sanitizador de allowlist mantido.
- `ORDER BY created_at DESC LIMIT 1` como "a vigente" quando a unicidade é parcial: filtre pelo mesmo predicado do índice.

## 6. Timeouts e I/O externo
- **O timeout fecha o recurso ou só para de esperar?** `Promise.race`/`select` com prazo sem cancelar o socket deixa a operação seguir (o e-mail sai depois do "tempo esgotado"). Confira na fonte da biblioteca o que o `close`/`abort` encerra.
- O prazo pode estourar antes de o cancelador existir (abort atribuído depois)?
- **Upload/stream longo:** estender só o prazo de leitura com o prazo de escrita do servidor intacto corta a resposta.
- **Chamada externa (HTTP, SMTP, bucket) dentro da transação do banco?** Segura conexão e trava pelo tempo da rede. Reserve no banco, chame fora, grave o resultado condicionalmente.
- Resposta montada dentro de callback pós-commit que engole exceção vira 200 vazio.

## 7. Segredos e logs
- **A redação cobre todos os caminhos de impressão?** Tipo segredo com `String()` pode sair cru como campo de outra struct, via `%+v` ou handler de log que não chama o método. Teste imprimindo a struct que contém o segredo.
- **Erro de consulta leva SQL com valores?** Drivers/query builders podem pôr parâmetros na mensagem do erro, e o redact de logger por chave não pega.
- "Segredo não está na auditoria" provado por busca numa tabela/coluna onde ele nunca estaria; procure também codificado (bytea, base64, hex).
- Não monte comando de shell com credencial em variável; mascare saída.

## 8. Data e fuso
- **A regra usa data civil do negócio?** "Hoje", "fim do mês", "72 h" no fuso do negócio, calculados num único lugar; não reproduza a regra em SQL e em código com fusos diferentes.
- **Teste com relógio fixo**, inclusive datas de borda (virada de mês, horário de verão). Teste que depende do dia em que roda passa hoje e falha amanhã — ou sobrevive ao mutante.
- Banco em UTC; conversão para o fuso só na borda.

## 9. Testes que não provam
Pergunte de cada teste: **se eu apagar a linha que ele protege, ele fica vermelho pelo motivo certo?**
- **Mutante sobrevivente:** remova a guarda/condição e rode. Verde = o teste não prova. Vermelho conta só se a mensagem for a asserção esperada (não 429, não erro de preparo). Mutante equivalente se justifica por escrito.
- **Fixture igual nos ciclos:** "pega o último" com dados idênticos em cada ciclo passa pegando o primeiro. Varie os dados.
- **Estímulo trocado depois da coleta**, ou falha indistinguível do vazio: o teste precisa distinguir "não achou" de "não rodou".
- **Fixture que mente:** solte o recurso "ocupado" e rode de novo; se continuar verde, o próprio sujeito gerava o erro.
- **Teste que pendura:** sinal de sincronização fechado também no caminho de erro; prazo que termina em falha descritiva; nunca asserção abortiva (`Fatal`) dentro de callback de transação.
- **Banco compartilhado entre pacotes/sessões:** estado global, catálogo global ou job que varre tudo deixam o teste instável ou cego. Isole por banco/tenant próprio e afirme só sobre o que criou.
- **Prova por nil/panic:** "a ordem das checagens" provada deixando dependência nil prova o panic, não a ordem.
- **SKIP conta como verde:** rode com saída verbosa e conte SKIP; `Skip` no erro de montagem esconde fixture quebrada.
- **Asserção na tabela errada**, ou contagem por JOIN que zera sozinha quando o lado que deveria sobrar some.
- **Filtro de execução (`-run`, `--grep`) que não casa o teste** ou não cobre os pacotes onde as provas estão. Cole a saída por nome.
- Teste de corrida "afrouxado" para aceitar dois códigos de recusa não prova qual guarda agiu; espera que filtra pelo texto da consulta quebra ao renomear.
- Mudança simétrica (dois ramos de UNION, duas rotas irmãs) testada em um ramo só.
- Prazo interno (`WithTimeout` da própria função) sem teste próprio: o teste com prazo do pai continua verde se ele for apagado.
- Banco de teste persistente migrado antes da edição da migration: prove em banco recém-migrado.

## 10. Montagem e ligação
- **O serviço novo está montado no caminho de produção?** Dependência opcional montada só sob `if db != nil` (ou só no teste) passa em todos os testes e fica nula em produção. Teste o construtor público/`main`, não o interno.
- Regra de boot em `main` sem teste: extraia para função testável.
- Default de variável de ambiente que anula o "vazio" (vazio vira default): ramo "desligado" inalcançável.
- Reverter a imagem com o env novo reativa comportamento antigo (seed que redefine senha)? Pense no rollback.
- Handler sem rota, ou rota legada que o design dizia "delegar ao novo" e não foi tocada.
- Recurso de versão nova do banco/runtime usado onde a decisão disse que a versão de produção não está confirmada.

## Antes de entregar (resumo)
1. Para cada guarda nova: existe teste que fica vermelho sem ela, pela mensagem certa?
2. Para cada leitura antes de trava: todas as condições são revalidadas sob a trava?
3. Para cada erro: é de dado (rejeita) ou transitório (retry)? Para cada estado de job: todo ramo fecha?
4. Para cada rota nova: as irmãs têm guarda que esta não tem?
5. Para cada limite e prazo: vem do servidor e fecha o recurso?
6. O serviço está ligado em produção, não só no teste?
