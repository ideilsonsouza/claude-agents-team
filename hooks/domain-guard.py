#!/usr/bin/env python3
"""Trava técnica dos agentes de domínio: cada papel escreve só nos próprios caminhos.

PreToolUse (Bash|Write|Edit|MultiEdit|NotebookEdit) no frontmatter de cada agente de domínio.
Regras em REGRAS (dados, não código por papel). Bloqueio = exit 2 com a orientação no stderr.

FALHA FECHADA: JSON ilegível, agent_type ausente/desconhecido ou qualquer erro interno
bloqueiam. Diferente de orchestrator-guard e reviewer-guard, que liberam nesses casos.
"""
import sys

try:  # FALHA FECHADA também no import: exit 1 seria erro não bloqueante e o Write passaria
    import datetime, json, os, pathlib, re

    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    from team_base import base_dir, worktree_root  # noqa: E402

    HOME = pathlib.Path.home()  # pode lançar RuntimeError (HOME indefinido): também falha fechada
    CLAUDE = HOME / ".claude"
    SKILLS = CLAUDE / "skills"
    APROVADAS = CLAUDE / "team-state" / "_skills" / "approved"
    TEMP = pathlib.Path(f"/tmp/claude-{os.getuid()}")
except BaseException as _e:  # noqa: BLE001
    print(f"Bloqueado (domain-guard): falha ao carregar o guard ({type(_e).__name__})", file=sys.stderr)
    sys.exit(2)

FERRAMENTAS_ESCRITA = ("Write", "Edit", "MultiEdit", "NotebookEdit")

# spec: nomes permitidos em SPEC/<feature>/ ; base: subpastas de BASE ; skills: nomes ou "*" ;
# repo: globs no worktree ; global/nega: pastas absolutas (nega tem precedência sobre tudo).
REGRAS = {
    "product-designer": {"spec": ("ui.md",), "base": ("design",), "skills": ("ui-patterns",)},
    # consultores: só a própria memória (a memória liga Write/Edit sozinha)
    "shop-floor": {"spec": (), "base": (), "skills": ()},
    "edge": {"spec": (), "base": (), "skills": ()},
    "legal": {"spec": ("legal.md",), "base": ("business/legal",), "skills": ("lgpd",)},
    "finance": {"spec": ("finance.md",), "base": ("business/finance",), "skills": ("erp-fiscal-br",)},
    "gtm": {"spec": ("gtm.md",), "base": ("business/gtm",), "skills": ()},
    "marketing": {"spec": ("marketing.md",), "base": ("business/marketing",), "skills": (),
                  "repo": ("src/content/**/*.md", "src/content/**/*.json", "src/content/**/*.yaml")},
    # consultores de mineração: só leitura (sem Write/Edit nas tools; o guard é a segunda trava)
    "mining-process": {"spec": (), "base": (), "skills": ()},
    "production-manager": {"spec": (), "base": (), "skills": ()},
    "data-analyst": {"spec": (), "base": (), "skills": ()},
    "skills-curator": {"spec": (), "base": (), "skills": "*",
                       "global": ("~/.claude/team-state/_skills",),
                       "nega": ("~/.claude/team-state/_skills/approved",)},
}
RESERVADAS = {"synced", "anthropic-skills"}


def bloqueia(msg: str) -> int:
    print(f"Bloqueado (domain-guard): {msg}", file=sys.stderr)
    return 2


def real(p) -> pathlib.Path:
    return pathlib.Path(os.path.realpath(os.path.expanduser(str(p))))


def glob_regex(padrao: str) -> re.Pattern:
    """'**/' casa zero ou mais pastas; '*' não cruza '/'. Sem depender de PurePath.full_match (3.13+)."""
    saida, i = "", 0
    while i < len(padrao):
        if padrao.startswith("**/", i):
            saida += "(?:.*/)?"
            i += 3
        elif padrao[i] == "*":
            saida += "[^/]*"
            i += 1
        elif padrao[i] == "?":
            saida += "[^/]"
            i += 1
        else:
            saida += re.escape(padrao[i])
            i += 1
    return re.compile(saida + r"\Z")


def marcador_valido(nome: str) -> bool:
    """Marcador ~/.claude/team-state/_skills/approved/<nome>.md com `valido-ate: AAAA-MM-DD` >= hoje."""
    arquivo = APROVADAS / f"{nome}.md"
    try:
        if not arquivo.is_file():
            return False
        for linha in arquivo.read_text(encoding="utf-8").splitlines():
            m = re.match(r"\s*valido-ate:\s*(\d{4}-\d{2}-\d{2})\s*$", linha)
            if m:
                return datetime.date.fromisoformat(m.group(1)) >= datetime.date.today()
    except Exception:
        return False
    return False


def permitido(papel: str, alvo: pathlib.Path, cwd: str) -> bool:
    regra = REGRAS[papel]
    # sempre permitido: memória do próprio papel e scratchpad da sessão
    if alvo.is_relative_to(real(CLAUDE / "agent-memory" / papel)):
        return True
    if alvo.is_relative_to(real(TEMP)) and "scratchpad" in alvo.parts:
        return True
    # nega vence qualquer permissão abaixo
    if any(alvo.is_relative_to(real(n)) for n in regra.get("nega", ())):
        return False
    base = real(base_dir(cwd))
    wt = worktree_root(cwd)
    wt = real(wt) if wt else None
    # SPEC: <BASE>/specs/<feature>/<nome> ou <worktree>/docs/specs/<feature>/<nome> (um nível; _archive fora)
    specs = [base / "specs"] + ([wt / "docs" / "specs"] if wt else [])
    if alvo.name in regra["spec"] and alvo.parent.name and not alvo.parent.name.startswith("_") \
            and any(alvo.parent.parent == s for s in specs):
        return True
    # base: subpastas de BASE
    if any(alvo.is_relative_to(base / sub) for sub in regra["base"]):
        return True
    # repo: globs relativos à raiz da worktree
    if wt and regra.get("repo") and alvo.is_relative_to(wt):
        rel = alvo.relative_to(wt).as_posix()
        if any(glob_regex(g).match(rel) for g in regra["repo"]):
            return True
    # global
    if any(alvo.is_relative_to(real(g)) for g in regra.get("global", ())):
        return True
    # skills: nome permitido (fora das reservadas) + marcador de aprovação válido
    skills = regra["skills"]
    skills_real = real(SKILLS)
    if alvo.is_relative_to(skills_real) and len(alvo.relative_to(skills_real).parts) >= 2:
        nome = alvo.relative_to(skills_real).parts[0]
        nome_ok = (nome not in RESERVADAS and not nome.startswith(".")) if skills == "*" else nome in skills
        return nome_ok and marcador_valido(nome)
    return False


def lista_permitidos(papel: str, cwd: str) -> str:
    regra = REGRAS[papel]
    base = base_dir(cwd)
    itens = [f"~/.claude/agent-memory/{papel}/"]
    if regra["spec"]:
        itens.append(f"{base}/specs/<feature>/{{{', '.join(regra['spec'])}}}")
    itens += [f"{base}/{s}/" for s in regra["base"]]
    itens += [f"<worktree>/{g}" for g in regra.get("repo", ())]
    itens += list(regra.get("global", ()))
    if regra["skills"]:
        nomes = "qualquer skill (exceto reservadas)" if regra["skills"] == "*" else ", ".join(regra["skills"])
        itens.append(f"~/.claude/skills/<{nomes}>/ (com marcador de aprovação válido em {APROVADAS})")
    return "; ".join(itens)


def main() -> int:
    try:
        dados = json.load(sys.stdin)
        if not isinstance(dados, dict):
            raise ValueError("input não é objeto")
    except Exception:
        return bloqueia("papel não identificado (input ilegível)")
    papel = dados.get("agent_type")
    if not isinstance(papel, str) or papel not in REGRAS:
        return bloqueia("papel não identificado")
    ferramenta = dados.get("tool_name", "")
    if ferramenta == "Bash":
        return bloqueia(f"{papel} não usa Bash; reporte no relatório")
    if ferramenta not in FERRAMENTAS_ESCRITA:
        return 0  # leitura e demais ferramentas não passam por este guard
    try:
        entrada = dados.get("tool_input") or {}
        chave = "notebook_path" if ferramenta == "NotebookEdit" else "file_path"
        alvo_bruto = entrada.get(chave) or ""
        if not isinstance(alvo_bruto, str) or not alvo_bruto:
            return bloqueia("caminho de destino ausente")
        cwd = dados.get("cwd") or os.getcwd()
        alvo = real(os.path.join(cwd, os.path.expanduser(alvo_bruto)))
        if permitido(papel, alvo, cwd):
            return 0
        return bloqueia(f"{papel} não escreve em {alvo}. Permitido: {lista_permitidos(papel, cwd)}. "
                        "Reporte o conteúdo no relatório ou peça ao orchestrator.")
    except Exception as e:  # falha fechada
        return bloqueia(f"erro ao avaliar a regra ({type(e).__name__}); papel {papel}")


def seguro() -> int:
    try:
        return main()
    except BaseException as e:  # noqa: BLE001  falha fechada fora do try interno
        try:
            print(f"Bloqueado (domain-guard): erro inesperado ({type(e).__name__})", file=sys.stderr)
        except Exception:
            pass
        return 2


if __name__ == "__main__":
    sys.exit(seguro())
