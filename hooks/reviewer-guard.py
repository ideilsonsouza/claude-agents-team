#!/usr/bin/env python3
"""Trava técnica do reviewer: só leitura.

PreToolUse no frontmatter do reviewer.
- Write/Edit: só na memória do próprio reviewer (a memória liga Write/Edit sozinha).
- Bash: só comandos de leitura (git diff/log/show/status/blame..., ls, cat, grep...),
  sem redirecionamento, encadeamento ou substituição de comando. Pipe só para filtros.
  sed e awk ficam de fora: conseguem escrever arquivo e executar comando.
"""
import json, os, pathlib, re, shlex, sys

MEMORIA = pathlib.Path.home() / ".claude" / "agent-memory" / "reviewer"
GIT_LEITURA = {"diff", "log", "show", "status", "blame", "merge-base", "rev-parse", "ls-files", "branch", "describe", "grep"}
LEITURA = {"ls", "cat", "head", "tail", "wc", "grep", "rg", "find", "stat", "file", "tree", "jq", "sort", "uniq", "cut", "diff"}
FILTROS = {"head", "tail", "wc", "grep", "rg", "sort", "uniq", "cut", "jq"}
PROIBIDO = re.compile(r"[;&<>`]|\$\(|\|\|")


def bloqueia(msg: str) -> int:
    print(f"Bloqueado (reviewer é só leitura): {msg}", file=sys.stderr)
    return 2


def comando_ok(segmento: str, primeiro: bool) -> str | None:
    try:
        partes = shlex.split(segmento)
    except ValueError:
        return "comando mal formado"
    if not partes:
        return "comando vazio"
    cmd = partes[0]
    if cmd == "git":
        resto, sub = partes[1:], ""
        while resto:
            p = resto.pop(0)
            if p == "-c" or p.startswith("--config"):
                return "git -c pode executar comando (pager, diff externo)"
            if p in ("-C", "--git-dir", "--work-tree"):
                resto = resto[1:]  # opção com valor
            elif not p.startswith("-"):
                sub = p
                break
        if sub not in GIT_LEITURA:
            return f"git {sub} não é leitura"
        if any(p.startswith("--output") or p == "-o" or p.startswith("--ext-diff") for p in partes):
            return "saída para arquivo ou diff externo"
        if sub == "branch" and any(not p.startswith("-") for p in resto):
            return "git branch com argumento cria ou altera ref; use só para listar"
        return None
    if cmd == "find" and any(p in ("-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint", "-fprint0", "-fprintf", "-fls") for p in partes):
        return "find com ação"
    permitidos = LEITURA if primeiro else FILTROS
    if cmd not in permitidos:
        return f"`{cmd}` fora da lista de leitura"
    return None


def main() -> int:
    try:
        dados = json.load(sys.stdin)
    except Exception:
        return 0
    ferramenta = dados.get("tool_name", "")
    entrada = dados.get("tool_input") or {}
    if ferramenta in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        alvo = entrada.get("file_path") or entrada.get("notebook_path") or ""
        cwd = dados.get("cwd") or os.getcwd()
        caminho = pathlib.Path(os.path.realpath(os.path.join(cwd, os.path.expanduser(alvo))))
        if caminho.is_relative_to(MEMORIA):
            return 0
        return bloqueia(f"não edita {caminho}; reporte o achado com arquivo:linha.")
    if ferramenta == "Bash":
        comando = entrada.get("command", "")
        if PROIBIDO.search(comando):
            return bloqueia("sem ; & > < ` $( ou || — um comando de leitura por vez.")
        for i, seg in enumerate(comando.split("|")):
            erro = comando_ok(seg.strip(), i == 0)
            if erro:
                return bloqueia(erro)
    return 0


if __name__ == "__main__":
    sys.exit(main())
