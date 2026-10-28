#!/usr/bin/env python3
"""Trava técnica: o orchestrator não escreve código.

PreToolUse (Write|Edit|MultiEdit|NotebookEdit) no frontmatter do orchestrator.
Permite escrever só na base da equipe, na memória e em temporários da sessão.
Qualquer outro caminho é bloqueado (exit 2) com a orientação de delegar.

Chamadas feitas dentro de um subagente (o input traz agent_id) passam direto:
quem decide o que o especialista pode editar são as regras dele.
"""
import json, os, pathlib, sys

HOME = pathlib.Path.home()
PERMITIDOS = (
    HOME / ".claude" / "team-state",
    HOME / ".claude" / "agent-memory" / "orchestrator",
    HOME / ".claude" / "plans",
)
TEMP = pathlib.Path(f"/tmp/claude-{os.getuid()}")


def permitido(caminho: pathlib.Path) -> bool:
    if caminho.is_relative_to(HOME / ".claude" / "projects") and "memory" in caminho.parts:
        return True  # auto memory do Claude Code
    if caminho.is_relative_to(TEMP) and "scratchpad" in caminho.parts:
        return True  # scratchpad da sessão
    return any(caminho.is_relative_to(base) for base in PERMITIDOS)


def main() -> int:
    try:
        dados = json.load(sys.stdin)
    except Exception:
        return 0  # sem input legível: não bloqueia por engano
    if dados.get("agent_id"):
        return 0
    entrada = dados.get("tool_input") or {}
    alvo = entrada.get("file_path") or entrada.get("notebook_path")
    if not alvo:
        return 0
    cwd = dados.get("cwd") or os.getcwd()
    caminho = pathlib.Path(os.path.realpath(os.path.join(cwd, os.path.expanduser(alvo))))
    if permitido(caminho):
        return 0
    print(
        f"Bloqueado: o orchestrator não edita {caminho}. Só escreve na base "
        "(~/.claude/team-state/) e na própria memória. Delegue a alteração ao "
        "especialista dono do arquivo, com briefing.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
