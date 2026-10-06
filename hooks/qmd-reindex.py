#!/usr/bin/env python3
"""Reindexa a memória da equipe no qmd (team-state e agent-memory) em segundo plano.

Disparado pelo orchestrator em:
- PostToolUse (Write|Edit) — só quando o arquivo está na base ou na memória;
- SubagentStop — um especialista pode ter gravado na memória dele;
- SessionStart — garante índice fresco no início.
Não bloqueia a sessão: dispara `qmd update && qmd embed` desacoplado, com trava
para não rodar duas indexações ao mesmo tempo.
"""
import json, os, pathlib, shutil, subprocess, sys

RAIZES = ("/.claude/team-state/", "/.claude/agent-memory/")
TRAVA = pathlib.Path.home() / ".cache" / "qmd" / "team-reindex.lock"


def main() -> None:
    try:
        dados = json.load(sys.stdin)
    except Exception:
        return
    if dados.get("hook_event_name") == "PostToolUse":
        caminho = str((dados.get("tool_input") or {}).get("file_path", ""))
        if not any(r in caminho for r in RAIZES):
            return
    if not shutil.which("qmd"):
        return
    TRAVA.parent.mkdir(parents=True, exist_ok=True)
    comando = (f'exec 9>"{TRAVA}"; flock -n 9 || exit 0; '
               "qmd update >/dev/null 2>&1 && qmd embed >/dev/null 2>&1")
    subprocess.Popen(["bash", "-c", comando], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True, env=os.environ.copy())


if __name__ == "__main__":
    main()
