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
    "rust": ("tech.md", "structure.md"),
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
    "mining-process": ("product.md", "domain.md"),
    "production-manager": ("product.md", "domain.md"),
    "skills-curator": ("tech.md",),
}
MAX_ARQUIVOS = 4  # por papel, em ordem de prioridade (o primeiro é o último a ser cortado)
LIMITE = 12000  # teto individual por arquivo
LIMITE_TOTAL = 9500  # texto inteiro injetado (acima de 10.000 o Claude Code reduz a uma prévia de 2.000)
MIN_TRUNCAR = 1500  # abaixo disso, o arquivo não é injetado: só uma nota
MAX_LINHAS = 80  # teto de linhas por arquivo injetado
LINHAS_TOTAL = 300  # teto de linhas de tudo que é injetado
NUNCA_INJETAR = ("history.md",)  # log histórico: nunca entra no contexto, só sob demanda

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


# Agentes de código que recebem a linha de stack detectada.
AGENTES_STACK = {"backend", "rust", "qa", "reviewer", "frontend", "devops", "dba"}
IGNORAR_DIRS = {"node_modules", ".git", ".worktree", "vendor", "dist"}
MAX_LEITURAS = 30  # teto de arquivos lidos na detecção
SKILLS_DIR = pathlib.Path.home() / ".claude" / "skills"
DEPS_NODE = (  # (dependência, rótulo, skill)
    ("fastify", "Fastify", "backend-fastify"), ("@adonisjs/core", "AdonisJS", "backend-adonisjs"),
    ("bullmq", "BullMQ", "backend-bullmq"), ("drizzle-orm", "Drizzle", "backend-drizzle"),
    ("mqtt", "MQTT.js", "backend-fastify-mqtt"), ("vue", "Vue", "frontend-vue"),
    ("react", "React", "frontend-react"), ("astro", "Astro", "frontend-astro"),
)
BACKEND_NODE = {"backend-fastify", "backend-adonisjs", "backend-bullmq", "backend-drizzle", "backend-fastify-mqtt"}


MAX_CANDIDATOS = 200  # teto de diretórios examinados (stat/glob) na detecção
NOME_SEGURO = re.compile(r"[A-Za-z0-9._@-]+")  # nome de diretório só entra no contexto se casar


def _dirs_candidatos(cwd: pathlib.Path) -> list[pathlib.Path]:
    """Raiz, filhos diretos e filhos de apps/packages/services (sem pastas ignoradas), até MAX_CANDIDATOS."""
    def filhos(d: pathlib.Path) -> list[pathlib.Path]:
        saida = []
        try:
            for c in d.iterdir():
                if c.name in IGNORAR_DIRS or c.name.startswith(".") or not c.is_dir():
                    continue
                saida.append(c)
                if len(saida) >= MAX_CANDIDATOS:
                    break
        except OSError:
            pass
        return sorted(saida)
    saida = [cwd]
    for c in filhos(cwd):
        if len(saida) >= MAX_CANDIDATOS:
            break
        saida.append(c)
        if c.name in ("apps", "packages", "services"):
            saida += filhos(c)[:MAX_CANDIDATOS - len(saida)]
    return saida


def detectar_stack(cwd: str) -> str:
    """Uma linha com a stack do projeto e as skills existentes a carregar. Vazio se nada for detectado.

    Só lê manifestos pequenos (teto MAX_LEITURAS), sem subprocess. Erros de I/O viram "não existe".
    """
    raiz = pathlib.Path(cwd).resolve()
    leituras = 0

    def ler_pequeno(arq: pathlib.Path) -> str | None:
        nonlocal leituras
        if leituras >= MAX_LEITURAS:
            return None
        try:
            if not arq.is_file():
                return None
            leituras += 1
            with open(arq, encoding="utf-8", errors="replace") as f:
                return f.read(200_000)
        except OSError:
            return None

    itens: list[str] = []
    skills: list[str] = []

    def add(rotulo: str, d: pathlib.Path, *nomes: str) -> None:
        rel = "" if d == raiz else d.relative_to(raiz).as_posix()
        # caminho vai cru ao contexto: só aceita nomes seguros (senão omite o caminho)
        if d == raiz:
            loc = "raiz/"
        elif all(NOME_SEGURO.fullmatch(parte) for parte in rel.split("/")):
            loc = rel + "/"
        else:
            loc = ""
        itens.append(f"{rotulo} ({loc})" if loc else rotulo)
        skills.extend(nomes)

    for d in _dirs_candidatos(raiz):
        if (t := ler_pequeno(d / "go.mod")) is not None:
            m = re.search(r"^go\s+(\d+(?:\.\d+)*)", t, re.M)
            add(f"Go {m.group(1)}" if m else "Go", d, "backend-go", "security-go")
        if (t := ler_pequeno(d / "package.json")) is not None:
            try:
                pj = json.loads(t)
                if not isinstance(pj, dict):
                    raise ValueError
                deps: dict = {}
                for chave in ("devDependencies", "dependencies"):
                    bloco = pj.get(chave)
                    if isinstance(bloco, dict):
                        deps.update(bloco)
            except (ValueError, TypeError):
                deps = {}
            achados = [(r, sk, deps[dep]) for dep, r, sk in DEPS_NODE if dep in deps]
            if achados:
                rotulos = []
                for r, _, ver in achados:
                    mj = re.search(r"\d+", str(ver))
                    rotulos.append(f"{r} {mj.group(0)}" if mj and r in ("Vue", "React", "Astro", "Fastify") else r)
                if "vite" in deps and any(r == "Vue" for r, _, _ in achados):
                    rotulos.append("Vite")
                sks = [sk for _, sk, _ in achados]
                if BACKEND_NODE & set(sks):
                    sks.append("security-node")
                add(" + ".join(rotulos), d, *sks)
        if ler_pequeno(d / "Cargo.toml") is not None:
            add("Rust", d, "rust-standards", "security-rust")
        pyproj = ler_pequeno(d / "pyproject.toml")
        try:
            reqs = sorted(d.glob("requirements*.txt"))[:3]
        except OSError:
            reqs = []
        if pyproj is not None or reqs:
            blob = "\n".join(x for x in [pyproj, *[ler_pequeno(r) for r in reqs]] if x).lower()
            fws = [rot for fw, rot in (("fastapi", "FastAPI"), ("django", "Django"))
                   if re.search(rf"(?<![\w-]){fw}(?![\w-])", blob)]
            add("Python/" + "+".join(fws) if fws else "Python", d, "backend-python", "security-python")
        if (t := ler_pequeno(d / "composer.json")) is not None and "laravel/framework" in t:
            add("Laravel", d, "backend-laravel")

    try:
        unicas = [s for i, s in enumerate(skills) if s not in skills[:i] and (SKILLS_DIR / s / "SKILL.md").is_file()]
    except OSError:
        unicas = []
    if not itens:
        return ""
    carregar = f" → carregue: {', '.join(unicas)}" if unicas else ""
    return f"Stack detectada: {', '.join(itens)}{carregar}"


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
            if agente in AGENTES_STACK:
                try:
                    if stack := detectar_stack(cwd):
                        partes.append(stack)
                except Exception:
                    pass
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
