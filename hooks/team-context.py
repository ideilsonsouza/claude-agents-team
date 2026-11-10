#!/usr/bin/env python3
"""Injeta a base de conhecimento do projeto (fora do repositório) no contexto da equipe.

Nomes de arquivo seguem o mercado: steering do Kiro (product/tech/structure)
e Memory Bank do Cline (progress), mais backlog e history.

SessionStart (orchestrator): steering + progress + decisions (só `vigente`) + backlog.
history.md nunca é injetado. Tetos: 80 linhas por arquivo e 300 no total, com aviso do corte.
SubagentStart (especialistas): só os arquivos relevantes ao papel.
Base: ~/.claude/team-state/<slug>/, onde <slug> vem do repositório principal
(estável entre worktrees, como os do Orca).
"""
import datetime, json, pathlib, re, subprocess, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
try:
    from team_base import base_dir, raiz_projeto, slug  # noqa: E402
except Exception:  # hook roda em toda sessão: nunca derruba por falha de import
    base_dir = raiz_projeto = slug = None

STEERING = ("product.md", "tech.md", "structure.md")

# Arquivos injetados em cada especialista. O resto ele lê sob demanda.
POR_AGENTE = {
    "architect": ("product.md", "tech.md", "structure.md", "decisions.md"),
    "prd": ("product.md", "progress.md", "domain.md", "decisions.md"),
    "dba": ("tech.md", "structure.md", "domain.md"),
    "backend": ("tech.md", "structure.md"),
    "frontend": ("tech.md", "structure.md"),
    "native": ("tech.md", "structure.md"),
    "qa": ("tech.md", "structure.md"),
    "reviewer": ("product.md", "tech.md", "structure.md"),
    "docs": ("product.md", "tech.md", "structure.md"),
    "pr": ("tech.md",),
    "devops": ("tech.md", "structure.md"),
    "deploy": ("tech.md",),
    "product-designer": ("product.md", "domain.md", "structure.md"),
    "shop-floor": ("product.md", "domain.md"),
    "legal": ("product.md", "business.md"),
    "finance": ("product.md", "business.md", "domain.md"),
    "gtm": ("product.md", "business.md", "progress.md"),
    "marketing": ("product.md", "business.md"),
    "data-analyst": ("product.md", "domain.md", "tech.md"),
    "skills-curator": ("tech.md",),
}
MAX_ARQUIVOS = 4  # por papel, em ordem de prioridade (o primeiro é o último a ser cortado)
LIMITE = 12000  # teto individual por arquivo
LIMITE_TOTAL = 9500  # texto inteiro injetado (acima de 10.000 o Claude Code reduz a uma prévia de 2.000)
MIN_TRUNCAR = 1500  # abaixo disso, o arquivo não é injetado: só uma nota
MAX_LINHAS = 80  # teto de linhas por arquivo injetado
LINHAS_TOTAL = 300  # teto de linhas de tudo que é injetado
NUNCA_INJETAR = ("history.md",)  # log histórico: nunca entra no contexto, só sob demanda

# Grafo central do graphify (piloto): ~/.claude/graphs/<slug>/, fora do repositório.
AGENTES_GRAFO = ("architect", "backend", "frontend", "qa", "reviewer", "data-engineer", "dba", "docs")
SCRIPT_GRAFO = pathlib.Path.home() / ".claude" / "scripts" / "grafo-atualizar.sh"


def dir_grafo(raiz: pathlib.Path) -> pathlib.Path:
    return pathlib.Path.home() / ".claude" / "graphs" / slug(raiz)


def disparar_atualizacao_grafo(cwd: str, raiz: pathlib.Path) -> None:
    """SessionStart: roda grafo-atualizar.sh desacoplado (não espera; o flock do script evita corrida)."""
    try:
        d = dir_grafo(raiz)
        if not d.is_dir() or not SCRIPT_GRAFO.exists():
            return
        with open(d / "update.log", "a", encoding="utf-8") as log:
            subprocess.Popen([str(SCRIPT_GRAFO), cwd], stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                             start_new_session=True, close_fds=True)
    except Exception:
        return


def bloco_grafo(raiz: pathlib.Path) -> str:
    """Bloco de até 6 linhas com o grafo central, só se graph.json existir."""
    try:
        d = dir_grafo(raiz)
        grafo = d / "graphify-out" / "graph.json"
        if not grafo.exists():
            return ""
        marca = d / ".main_commit"
        data = datetime.datetime.fromtimestamp(marca.stat().st_mtime).strftime("%Y-%m-%d %H:%M") if marca.exists() else "data desconhecida"
        return (f"## Grafo do código (graphify)\n"
                f"Grafo: {grafo}\n"
                f"Reflete a `main` (atualizado em {data}); mudanças da tarefa veja com `git diff`.\n"
                f"Consultas: `graphify query \"<pergunta>\" --graph {grafo}` e "
                f"`graphify explain \"<arquivo>::<símbolo>\" --graph {grafo}`.\n"
                f"Consulte o grafo antes de varrer arquivos com grep, para achar onde algo está e o que depende dele.")
    except Exception:
        return ""


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


def so_vigentes(texto: str) -> str:
    """decisions.md: mantém títulos, cabeçalho da tabela e só as decisões com a coluna Status == `vigente`."""
    saida = []
    col = 3  # | Id | Data | Decisão | Status | Fonte |  (índice após tirar as bordas)
    for linha in texto.splitlines():
        celulas = [c.strip() for c in linha.strip().strip("|").split("|")]
        if linha.lstrip().startswith("|"):
            if celulas and celulas[0].lower() == "id" and "status" in [c.lower() for c in celulas]:
                col = [c.lower() for c in celulas].index("status")
            elif re.match(r"D-\d+", celulas[0]):
                if len(celulas) <= col or celulas[col].lower() != "vigente":
                    continue
        saida.append(linha)
    return "\n".join(saida)


def ler(arquivo: pathlib.Path, max_linhas: int = MAX_LINHAS) -> str:
    if not arquivo.exists() or arquivo.name in NUNCA_INJETAR:
        return ""
    texto = arquivo.read_text(encoding="utf-8", errors="replace")
    if arquivo.name == "decisions.md":
        texto = so_vigentes(texto)
    linhas = texto.splitlines()
    if not texto.strip():
        return ""
    if max_linhas <= 0:
        return f"[... cortado; leia {arquivo}]"
    if len(linhas) > max_linhas:
        texto = "\n".join(linhas[:max(max_linhas, 0)]) + f"\n[... cortado em {max(max_linhas, 0)} de {len(linhas)} linhas; leia {arquivo}]"
    return texto if len(texto) <= LIMITE else texto[:LIMITE] + "\n\n[... truncado; leia o arquivo completo se precisar]"


def nota_curta(base: pathlib.Path, nome: str) -> str:
    return f"[{nome} não injetado por orçamento; leia {base / nome}]"


def secoes(base: pathlib.Path, nomes, restante: int = LIMITE_TOTAL, linhas_restantes: int = LINHAS_TOTAL) -> list[str]:
    """Seções que cabem em `restante` caracteres, em ordem de prioridade.

    Cabe (já reservando as notas dos arquivos seguintes) -> inclui. Não cabe e sobram
    >= MIN_TRUNCAR -> inclui truncada com nota. Senão -> nota de uma linha.
    Cada item custa len + 2 (separador "\n\n" do join). O custo das notas dos arquivos que
    ainda vêm é sempre reservado, então o total nunca passa de `restante`.
    """
    saida = []
    nomes = [n for n in nomes if n not in NUNCA_INJETAR and (base / n).exists()]
    # orçamento menor que as notas de todos os arquivos: nem as notas cabem -> só o cabeçalho
    if restante < sum(len(nota_curta(base, n)) + 2 for n in nomes):
        return []
    for i, nome in enumerate(nomes):
        conteudo = ler(base / nome, min(MAX_LINHAS, linhas_restantes))
        if not conteudo:
            continue
        linhas_restantes -= conteudo.count("\n") + 2
        reserva = sum(len(nota_curta(base, n)) + 2 for n in nomes[i + 1:])
        secao = f"## {nome}\n{conteudo}"
        custo = len(secao) + 2
        if custo + reserva <= restante:
            saida.append(secao)
            restante -= custo
            continue
        nota = f"\n\n[... truncado por orçamento; leia {base / nome}]"
        corte = restante - reserva - 2 - len(f"## {nome}\n") - len(nota)
        if restante - reserva >= MIN_TRUNCAR and corte > 0:
            secao = f"## {nome}\n{conteudo[:corte]}{nota}"
        else:
            secao = nota_curta(base, nome)
        saida.append(secao)
        restante -= len(secao) + 2
    return saida


def montar(dados: dict) -> tuple[str, str] | None:
    evento = dados.get("hook_event_name")
    agente = dados.get("agent_type") or ""
    cwd = dados.get("cwd") or "."
    if evento not in ("SessionStart", "SubagentStart"):
        return None
    if evento == "SessionStart" and agente != "orchestrator":
        return None
    if evento == "SubagentStart" and agente not in POR_AGENTE:
        return None
    try:
        raiz, base = raiz_projeto(cwd), base_dir(cwd)
    except Exception:
        return evento, f"# Base de conhecimento da equipe\nProjeto: {cwd}\n(base indisponível: erro ao localizar a base do projeto)"
    try:
        prof = perfil(raiz, base)
    except Exception:
        prof = "solo"
    cabecalho = (f"# Base de conhecimento da equipe\nProjeto: {raiz}\nBase (fora do repositório): {base}\n"
                 f"Perfil do projeto: **{prof}** (regras do perfil no ~/.claude/CLAUDE.md, seção \"Perfis de projeto\")")
    try:
        if evento == "SessionStart":
            try:
                base.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
            disparar_atualizacao_grafo(cwd, raiz)
            partes = [cabecalho]
            if not any((base / n).exists() for n in STEERING):
                partes.append("**Projeto ainda sem base.** Antes da primeira tarefa, delegue ao `docs` o mapeamento inicial "
                              f"(skill `knowledge-base`), gravando em {base}.")
            else:
                ordem = (*STEERING, "progress.md", "decisions.md", "backlog.md")
                extras = [str(base / n) for n in ("domain.md", "business.md") if (base / n).exists()]
                linha = ("Existem também (leia sob demanda): " + ", ".join(extras)) if extras else ""
                partes += secoes(base, ordem, LIMITE_TOTAL - len(cabecalho) - len(linha) - 4,
                                 LINHAS_TOTAL - cabecalho.count("\n") - 4)
                if linha:
                    partes.append(linha)
        else:
            intro = (cabecalho + "\nUse estes arquivos antes de explorar o código. Outros arquivos da base "
                     "(product, tech, structure, domain, business, progress, decisions, backlog e as pastas domain/, business/, "
                     "design/, analytics/, specs/) estão no caminho acima — leia só se o briefing não bastar.")
            nomes_ag = POR_AGENTE[agente][:MAX_ARQUIVOS]
            corpo = secoes(base, nomes_ag, LIMITE_TOTAL - len(intro) - 2, LINHAS_TOTAL - intro.count("\n") - 2)
            if not corpo and not any((base / n).exists() for n in nomes_ag):
                corpo = ["(projeto ainda sem base)"]
            partes = [intro, *corpo] if corpo else [cabecalho]  # sem corpo por orçamento: só o cabeçalho
            if agente in AGENTES_GRAFO and (bg := bloco_grafo(raiz)):
                partes.append(bg)  # fora do teto de arquivos
    except Exception:
        partes = [cabecalho]  # pior caso: ao menos o cabeçalho
    return evento, "\n\n".join(partes)


def main() -> None:
    try:
        dados = json.load(sys.stdin)
        if not isinstance(dados, dict):
            return
        resultado = montar(dados)
        if resultado is None:
            return
        evento, contexto = resultado
        print(json.dumps({"hookSpecificOutput": {"hookEventName": evento, "additionalContext": contexto}}, ensure_ascii=False))
    except Exception:
        return  # nunca derruba a sessão


if __name__ == "__main__":
    main()
