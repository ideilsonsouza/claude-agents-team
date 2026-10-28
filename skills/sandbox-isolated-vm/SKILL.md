---
name: sandbox-isolated-vm
description: Padrões para executar código não confiável em Node.js com isolated-vm — criação de Isolate e Context, limites de memória e tempo, transferência segura de dados (ExternalCopy, Reference, copy), exposição controlada de funções do host, descarte de recursos e testes de escape. Usar ao escrever ou revisar código que roda scripts de usuário, regras ou fórmulas dinâmicas com isolated-vm.
---

# Sandbox com isolated-vm

Fonte: https://github.com/laverdet/isolated-vm (README é a documentação oficial).
Rodar código não confiável é difícil: trate todo código desta área como sensível à segurança e peça revisão.

## Requisitos
- Node ≥ 20 exige a flag `--no-node-snapshot` em **todo** processo que carrega o módulo (dev, start, testes, Docker `CMD`).
- A versão maior do isolated-vm acompanha o Node (ex.: Node 24 → 6.x/5.x, Node 26 → 7.x). Confira a tabela do README ao atualizar o Node.
- Mantenha o Node atualizado: patches de V8 são correções de segurança do sandbox.
- Não use `vm`/`vm2` do Node como sandbox; eles não isolam.

## Padrão de execução
```ts
import ivm from 'isolated-vm';

export async function runUntrusted(code: string, input: unknown) {
  const isolate = new ivm.Isolate({ memoryLimit: 32 }); // MB; mínimo 8
  try {
    const context = await isolate.createContext();
    await context.global.set('input', new ivm.ExternalCopy(input).copyInto());
    const script = await isolate.compileScript(code);
    return await script.run(context, { timeout: 1000, copy: true }); // ms
  } finally {
    if (!isolate.isDisposed) isolate.dispose();
  }
}
```
- **Sempre** `timeout` em `run`, `eval`, `apply` e chamadas de `Reference`. Sem timeout, um `while(true)` trava o processo.
- **Sempre** `memoryLimit` explícito. O limite é aproximado: o código pode passar 2–3× antes de morrer. Dimensione o container com folga e não rode muitos isolates simultâneos no mesmo processo.
- Um isolate por execução (ou pool com descarte após N usos); não reaproveite contexto entre tenants ou usuários.
- `dispose()` no `finally`. Libere `Reference`, `ExternalCopy`, `Script` e `Context` com `.release()` quando forem de longa duração.

## Transferência de dados
- Entrada: `new ivm.ExternalCopy(valor).copyInto()` ou `context.global.set(nome, valor, { copy: true })`. Só passam dados clonáveis (primitivos, objetos simples, arrays, Date, ArrayBuffer/TypedArray).
- Saída: `{ copy: true }` no `run`/`eval`/`apply`, ou `{ promise: true }` para resultados assíncronos.
- **Valide a saída** (ex.: com Zod) como qualquer entrada externa. Ela é controlada pelo código não confiável.

## Expondo funções do host
- Funções, módulos e libs **não** entram no isolate. Exponha um shim mínimo do host:
```ts
await context.global.set('log', new ivm.Callback((msg: string) => logger.info({ msg: String(msg).slice(0, 500) })));
```
- **Nunca** entregue objetos do isolated-vm (`Reference`, `ExternalCopy`, `Isolate`, `Context`) ao código não confiável: servem de trampolim de volta ao processo principal.
- Cada função exposta é superfície de ataque: valide argumentos, limite tamanho e quantidade de chamadas, aplique autorização do tenant no host e não exponha `fetch`, fs ou env genéricos. Exponha operações específicas (ex.: `getReading(id)`), e não primitivas genéricas.
- Funções assíncronas do host: use `Reference` com `applySyncPromise`/`apply` e `{ result: { promise: true, copy: true } }`, sempre com timeout.

## Erros e observabilidade
- Diferencie timeout, estouro de memória (isolate é descartado; verifique `isolate.isDisposed`) e erro do script, e devolva mensagens sanitizadas.
- Meça `isolate.cpuTime` e `isolate.wallTime` (BigInt, ns) e logue por execução. `isolate.referenceCount` ajuda a achar vazamentos.
- Use `onCatastrophicError` no `Isolate` para logar e encerrar o processo de forma controlada.
- CPU pesado dentro de fila: rode em worker thread ou processo separado para não bloquear o event loop (ver skill `backend-bullmq`).

## Testes obrigatórios
Inclua casos que **devem falhar de forma controlada**:
- loop infinito → timeout;
- alocação gigante (`new Array(1e9).fill(0)`, string crescente) → erro de memória sem derrubar o host;
- acesso a `process`, `require`, `globalThis.constructor.constructor('return process')()` → indefinido ou erro;
- saída malformada → rejeitada pela validação;
- chamadas abusivas às funções expostas → limitadas.
