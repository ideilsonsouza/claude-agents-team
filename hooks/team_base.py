#!/usr/bin/env python3
"""Código compartilhado pelos hooks da equipe: raiz do projeto, slug e base de conhecimento.

Importado por team-context.py e domain-guard.py para que ambos calculem o mesmo slug.
Uso: sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent)); from team_base import ...
"""
import hashlib, pathlib, re, subprocess


def raiz_projeto(cwd: str) -> pathlib.Path:
    try:
        common = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True, text=True, timeout=5, check=True,
        ).stdout.strip()
        return pathlib.Path(common).parent
    except Exception:
        return pathlib.Path(cwd)


def slug(raiz: pathlib.Path) -> str:
    nome = re.sub(r"[^a-z0-9]+", "-", raiz.name.lower()).strip("-") or "projeto"
    return f"{nome}-{hashlib.sha1(str(raiz).encode()).hexdigest()[:6]}"


def base_dir(cwd: str) -> pathlib.Path:
    """~/.claude/team-state/<slug> (fora do repositório)."""
    return pathlib.Path.home() / ".claude" / "team-state" / slug(raiz_projeto(cwd))


def worktree_root(cwd: str) -> pathlib.Path | None:
    """Raiz da worktree atual (git rev-parse --show-toplevel); None em qualquer erro."""
    try:
        saida = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5, check=True,
        ).stdout.strip()
        return pathlib.Path(saida) if saida else None
    except Exception:
        return None
