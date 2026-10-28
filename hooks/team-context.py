#!/usr/bin/env python3
"""Injeta a base de conhecimento do projeto (fora do repositório) no contexto da equipe.

Nomes de arquivo seguem o mercado: steering do Kiro (product/tech/structure)
e Memory Bank do Cline (progress), mais backlog e history.

SessionStart (orchestrator): todos os arquivos de steering + progress + backlog.
SubagentStart (especialistas): só os arquivos relevantes ao papel.
Base: ~/.claude/team-state/<slug>/, onde <slug> vem do repositório principal
(estável entre worktrees, como os do Orca).
"""
import hashlib, json, pathlib, re, subprocess, sys

STEERING = ("product.md", "tech.md", "structure.md")

# Arquivos injetados em cada especialista. O resto ele lê sob demanda.
POR_AGENTE = {
    "architect": ("product.md", "tech.md", "structure.md"),
    "prd": ("product.md", "progress.md"),
    "dba": ("tech.md", "structure.md"),
    "backend": ("tech.md", "structure.md"),
    "frontend": ("tech.md", "structure.md"),
    "qa": ("tech.md", "structure.md"),
    "reviewer": ("product.md", "tech.md", "structure.md"),
    "docs": ("product.md", "tech.md", "structure.md"),
    "pr": ("tech.md",),
    "devops": ("tech.md", "structure.md"),
    "deploy": ("tech.md",),
}
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


def remote_origin(raiz: pathlib.Path) -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(raiz), "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5, check=True,
        ).stdout.strip()
    except Exception:
        return ""


# Padrões que marcam um projeto como "equipe" ficam fora do repositório, em
# ~/.claude/team-orgs: uma regex por linha, comparada com o remote origin e com o
# caminho do projeto. Linhas vazias e começadas por # são ignoradas.
# Exemplo:  [:/]minha-org/
TEAM_ORGS = pathlib.Path.home() / ".claude" / "team-orgs"


def padroes_equipe() -> list[str]:
    if not TEAM_ORGS.exists():
        return []
    linhas = TEAM_ORGS.read_text(encoding="utf-8").splitlines()
    return [l.strip() for l in linhas if l.strip() and not l.strip().startswith("#")]


def perfil(raiz: pathlib.Path, base: pathlib.Path) -> str:
    """equipe (padrões em ~/.claude/team-orgs) ou solo. O arquivo `perfil` na base fixa o valor à mão."""
    fixo = base / "perfil"
    if fixo.exists() and (valor := fixo.read_text(encoding="utf-8").strip().lower()) in ("equipe", "solo"):
        return valor
    alvos = (remote_origin(raiz), str(raiz))
    for padrao in padroes_equipe():
        try:
            if any(re.search(padrao, alvo, re.IGNORECASE) for alvo in alvos):
                return "equipe"
        except re.error:
            continue
    return "solo"


def ler(arquivo: pathlib.Path) -> str:
    if not arquivo.exists():
        return ""
    texto = arquivo.read_text(encoding="utf-8", errors="replace")
    return texto if len(texto) <= LIMITE else texto[:LIMITE] + "\n\n[... truncado; leia o arquivo completo se precisar]"


def secoes(base: pathlib.Path, nomes) -> list[str]:
    return [f"## {nome}\n{conteudo}" for nome in nomes if (conteudo := ler(base / nome))]


def main() -> None:
    dados = json.load(sys.stdin)
    evento = dados.get("hook_event_name")
    agente = dados.get("agent_type") or ""
    raiz = raiz_projeto(dados.get("cwd") or ".")
    base = pathlib.Path.home() / ".claude" / "team-state" / slug(raiz)
    cabecalho = (f"# Base de conhecimento da equipe\nProjeto: {raiz}\nBase (fora do repositório): {base}\n"
                 f"Perfil do projeto: **{perfil(raiz, base)}** (regras do perfil no ~/.claude/CLAUDE.md, seção \"Perfis de projeto\")")

    if evento == "SessionStart" and agente == "orchestrator":
        base.mkdir(parents=True, exist_ok=True)
        partes = [cabecalho]
        if not any((base / n).exists() for n in STEERING):
            partes.append("**Projeto ainda sem base.** Antes da primeira tarefa, delegue ao `docs` o mapeamento inicial "
                          f"(skill `knowledge-base`), gravando em {base}.")
        else:
            partes += secoes(base, (*STEERING, "progress.md", "backlog.md"))
    elif evento == "SubagentStart" and agente in POR_AGENTE:
        corpo = secoes(base, POR_AGENTE[agente]) or ["(projeto ainda sem base)"]
        partes = [cabecalho + "\nUse estes arquivos antes de explorar o código. Outros arquivos da base "
                  "(product, tech, structure, progress, backlog) estão no caminho acima — leia só se o briefing não bastar.",
                  *corpo]
    else:
        return

    contexto = "\n\n".join(partes)
    print(json.dumps({"hookSpecificOutput": {"hookEventName": evento, "additionalContext": contexto}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
