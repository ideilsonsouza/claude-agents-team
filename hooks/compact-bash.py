#!/usr/bin/env python3
"""PreToolUse (Bash): passa a saída de testes, builds e lint pelo compact-output.py.

Só reescreve comandos simples e reconhecidos (sem ; & | ` $( < > nem quebra de linha),
e não altera a decisão de permissão: a chamada segue o fluxo normal.
Para ver a saída completa, o agente acrescenta o comentário `# full-output`.
"""
import json, re, sys

PADRAO = re.compile(
    r"^\s*(?:[A-Z_][A-Z0-9_]*=\S+\s+)*"  # variáveis de ambiente opcionais
    r"(?:go\s+(?:test|build|vet)"
    r"|golangci-lint"
    r"|(?:npm|pnpm|yarn|bun)\s+(?:test|run\s+(?:test|build|lint|typecheck|check)\S*)"
    r"|(?:npx|pnpm\s+exec|yarn)\s+(?:vitest|jest|tsc|eslint|playwright|astro\s+check|vue-tsc)"
    r"|vitest|jest|tsc|eslint|vue-tsc|astro\s+check"
    r"|node\s+ace\s+test"
    r"|docker\s+(?:build|compose\s+build)"
    r"|make\s+(?:test|build|lint))\b"
)
PROIBIDO = re.compile(r"[;&|`<>\n]|\$\(")


def main() -> None:
    dados = json.load(sys.stdin)
    comando = (dados.get("tool_input") or {}).get("command", "")
    if "# full-output" in comando or PROIBIDO.search(comando) or not PADRAO.match(comando):
        return
    novo = f"set -o pipefail; {comando.strip()} 2>&1 | python3 ~/.claude/hooks/compact-output.py"
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "updatedInput": {**dados["tool_input"], "command": novo},
    }}))


if __name__ == "__main__":
    main()
