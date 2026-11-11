# AdonisJS: upgrade v6 para v7

Detalhe de `../SKILL.md`. Fonte: guia de upgrade v7, 2026-11-10.

1. Node 24 no local, no CI e na imagem.
2. Atualize todos os `@adonisjs/*`, o `@vinejs/vine` e os plugins `@japa/*`.
3. Troque `ts-node`/`@swc/core` por `@poppinss/ts-exec` (import no `ace.js`) e instale `youch` como dev.
4. `adonisrc.ts`: `hooks.init: [indexEntities()]`, remova `assetsBundler`, globs de teste `*.spec.{ts,js}` e hooks do assembler renomeados (`onBuildCompleted` virou `buildFinished`).
5. Remova `appKey` de `config/app.ts` e crie `config/encryption.ts` com o driver **`legacy`** para ler dados cifrados na v6.
6. `router.makeUrl` vira `urlFor`; `getDirname` vira `import.meta.dirname`; `cuid` vira UUID.
7. Adicione os imports `#generated/*`, `#transformers/*` e `#database/*` no `package.json`.
8. Revise nomes de rota que colidem, `request.all()` (agora inclui arquivos) e a ordem dos shutdown hooks.
9. Migre as respostas para transformers e os validators para `vine.create`, aos poucos.
10. Valide com `node ace build`, `npm run dev` e `node ace test`.

