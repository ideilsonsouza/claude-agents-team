#!/usr/bin/env python3
"""Injeta a base de conhecimento do projeto (fora do repositório) no contexto da equipe.

SessionStart (orquestrador): mapa + implementado + pendências.
SubagentStart (especialistas): mapa + caminho da base.
Base: ~/.claude/equipe-estado/<slug>/, onde <slug> vem do repositório principal
(estável entre worktrees, como os do Orca).
"""
import hashlib, json, pathlib, re, subprocess, sys

EQUIPE = {"arquiteto", "prd", "dba", "backend", "frontend", "qa", "docs", "pr", "devops", "deploy"}
LIMITE = 12000


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


def ler(arquivo: pathlib.Path) -> str:
    if not arquivo.exists():
        return ""
    texto = arquivo.read_text(encoding="utf-8", errors="replace")
    return texto if len(texto) <= LIMITE else texto[:LIMITE] + "\n\n[... truncado; leia o arquivo completo se precisar]"


def main() -> None:
    dados = json.load(sys.stdin)
    evento = dados.get("hook_event_name")
    agente = dados.get("agent_type") or ""
    raiz = raiz_projeto(dados.get("cwd") or ".")
    base = pathlib.Path.home() / ".claude" / "equipe-estado" / slug(raiz)

    if evento == "SessionStart" and agente == "orquestrador":
        base.mkdir(parents=True, exist_ok=True)
        partes = [f"# Base de conhecimento da equipe\nProjeto: {raiz}\nBase: {base}"]
        mapa = ler(base / "mapa.md")
        if not mapa:
            partes.append("**Projeto ainda sem mapa.** Antes da primeira tarefa, delegue ao `docs` o mapeamento inicial "
                          f"(skill `base-conhecimento`), gravando em {base}.")
        else:
            partes.append("## mapa.md\n" + mapa)
            for nome in ("implementado.md", "pendencias.md"):
                conteudo = ler(base / nome)
                if conteudo:
                    partes.append(f"## {nome}\n{conteudo}")
        contexto = "\n\n".join(partes)
    elif evento == "SubagentStart" and agente in EQUIPE:
        mapa = ler(base / "mapa.md") or "(projeto ainda sem mapa)"
        contexto = (f"# Base de conhecimento da equipe\nProjeto: {raiz}\nBase (fora do repositório): {base}\n"
                    "Use este mapa antes de explorar o código. O que já foi entregue está em "
                    f"{base}/implementado.md — leia só se o briefing não bastar.\n\n## mapa.md\n{mapa}")
    else:
        return

    print(json.dumps({"hookSpecificOutput": {"hookEventName": evento, "additionalContext": contexto}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
