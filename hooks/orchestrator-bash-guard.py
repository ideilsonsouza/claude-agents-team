#!/usr/bin/env python3
"""Trava técnica: o orchestrator só usa Bash para a CLI do Orca (orquestração).

PreToolUse (Bash) no frontmatter do orchestrator. Bloqueia por padrão (exit 2).
Passa só se o comando for UMA chamada simples ao executável do Orca, com
subcomando e flags da allowlist abaixo. O objetivo é deixar o coordenador e o
suborquestrador conversarem pelo Orca sem virarem um shell livre.

Regras:
- Executável: valor de ORCA_CLI_COMMAND, se definido; senão `orca-ide`; `orca`
  puro só dentro de terminal do Orca (no Linux fora dele é o leitor de tela GNOME).
- Metacaracteres de shell (; & | ` $ < > \\ e quebra de linha) são barrados em
  qualquer posição, inclusive entre aspas: texto longo vai por --spec-file ou
  --body-file. Variável de ambiente prefixada falha porque o primeiro token
  precisa ser o executável.
- Fora de aspas também são barrados ( ) { } * ? [ ] ~ # !
- Chamadas feitas dentro de um subagente (o input traz agent_id) passam direto:
  quem decide o que o especialista pode rodar são as regras dele.
"""
import json, os, re, shlex, shutil, sys

ID = re.compile(r"^[A-Za-z0-9_.:-]+$")
MAILBOX = re.compile(r"^(run|dispatch):[A-Za-z0-9_.-]+$")
INTEIRO = re.compile(r"^[0-9]+$")
SEMPRE_BARRADOS = set(";&|`$<>\\\n\r\x00")
FORA_DE_ASPAS = set("(){}*?[]~#!")

# flag -> (recebe valor, validador do valor ou None)
Flag = tuple
COMUNS = {
    "--json": (False, None),
    "--full": (False, None),
    "--environment": (True, lambda v: v == "local"),
    "--retry-request": (True, ID.match),
}


def f(*nomes, valor=True, ok=None):
    return {n: (valor, ok) for n in nomes}


def tabela(*partes):
    t = dict(COMUNS)
    for p in partes:
        t.update(p)
    return t


ID_FLAG = ID.match
ORCHESTRATION = {
    "run-create": tabela(f("--objective")),
    "run-use": tabela(f("--id", ok=ID_FLAG)),
    "run-current": tabela(),
    "run-show": tabela(f("--id", "--cursor", ok=ID_FLAG), f("--removed", valor=False)),
    "run-list": tabela(f("--limit", ok=INTEIRO.match), f("--cursor", ok=ID_FLAG)),
    "task-create": tabela(
        f("--spec", "--spec-file", "--task-title", "--display-name"),
        f("--deps"),
        f("--parent", "--run", ok=ID_FLAG),
    ),
    "task-list": tabela(
        f("--status", "--run", ok=ID_FLAG), f("--ready", "--brief", valor=False)
    ),
    "worker-start": tabela(
        f("--task", "--parent", "--run", "--retry-of", "--base-branch", ok=ID_FLAG),
        f("--spec", "--spec-file", "--task-title", "--deps", "--name", "--display-name", "--comment"),
        f("--worktree", ok=lambda v: v in ("current", "new-child")),
        f("--agent", ok=lambda v: v == "claude"),
        f("--model", "--effort", ok=ID_FLAG),
        f("--setup", ok=lambda v: v in ("run", "skip", "inherit")),
        f("--timeout-ms", ok=INTEIRO.match),
        f("--keep-open", valor=False),
    ),
    "worker-show": tabela(f("--dispatch", ok=ID_FLAG)),
    "worker-read": tabela(
        f("--dispatch", "--cursor", ok=ID_FLAG),
        f("--source", ok=lambda v: v in ("auto", "transcript", "terminal")),
        f("--limit", ok=INTEIRO.match),
    ),
    "worker-stop": tabela(f("--dispatch", ok=ID_FLAG)),
    "worker-release": tabela(f("--dispatch", ok=ID_FLAG)),
    "worker-keep-open": tabela(f("--dispatch", ok=ID_FLAG)),
    "worker-list": tabela(
        f("--run", "--cursor", "--terminal-state", ok=ID_FLAG),
        f("--limit", ok=INTEIRO.match),
        f("--include-remote", valor=False),
    ),
    "check": tabela(
        f("--run", "--ack", ok=ID_FLAG),
        f("--types"),
        f("--timeout-ms", ok=INTEIRO.match),
        f("--unread", "--peek", "--all", "--format", "--wait", valor=False),
    ),
    "inbox": tabela(
        f("--run", ok=ID_FLAG),
        f("--terminal", ok=MAILBOX.match),
        f("--limit", ok=INTEIRO.match),
    ),
    "send": tabela(
        f("--to", ok=MAILBOX.match),
        f("--subject", "--body", "--body-file", "--phase", "--report-path", "--files-modified"),
        f("--type", ok=lambda v: v in (
            "status", "question", "worker_done", "escalation", "heartbeat", "decision_gate")),
        f("--priority", "--thread-id", "--task-id", "--dispatch-id", "--run", "--from", ok=ID_FLAG),
        f("--outcome", ok=lambda v: v in ("succeeded", "failed")),
    ),
    "reply": tabela(
        f("--id", "--run", "--from", ok=ID_FLAG), f("--body", "--body-file")
    ),
    "ask": tabela(
        f("--question", "--options"),
        f("--resume", "--run", "--from", ok=ID_FLAG),
        f("--to", ok=MAILBOX.match),
        f("--timeout-ms", ok=INTEIRO.match),
        f("--wait", valor=False),
    ),
    "gate-create": tabela(
        f("--task", "--from", ok=ID_FLAG), f("--question", "--options")
    ),
    "gate-resolve": tabela(
        f("--id", "--from", ok=ID_FLAG), f("--resolution")
    ),
    "gate-list": tabela(f("--task", "--status", "--run", "--from", ok=ID_FLAG)),
    "request-show": tabela(f("--request", ok=ID_FLAG)),
    "dispatch-show": tabela(
        f("--task", "--from", ok=ID_FLAG), f("--preamble", valor=False)
    ),
}

# Comentário de worktree: só os campos de status do card.
WORKTREE_SET = {
    "--worktree": (True, None),
    "--comment": (True, None),
    "--workspace-status": (True, ID_FLAG),
    "--unread": (False, None),
    "--read": (False, None),
    "--json": (False, None),
}
# Leitura pura: aceita qualquer flag, menos as que mudam o alvo da chamada.
LEITURA = {
    ("status",),
    ("worktree", "list"),
    ("worktree", "show"),
    ("worktree", "current"),
    ("worktree", "ps"),
    ("automations", "list"),
    ("automations", "show"),
    ("automations", "runs"),
    ("skills", "get"),
    ("skills", "list"),
}
FLAGS_PROIBIDAS = ("--pairing-code", "--on", "--on-client", "--from-client")


def bloquear(motivo: str) -> int:
    print(
        f"Bloqueado: {motivo}. O orchestrator só usa Bash para a CLI do Orca "
        "(status, orchestration, worktree list/comentário, automations list/show/runs, "
        "skills get, --help), em chamada única, sem metacaracteres de shell. "
        "Qualquer outra execução (editar, rodar comando, abrir, remover worktree, "
        "digitar em terminal) é de especialista: delegue com briefing. Texto longo: "
        "grave em arquivo no scratchpad e use --spec-file/--body-file.",
        file=sys.stderr,
    )
    return 2


def executavel() -> list[list[str]]:
    """Formas aceitas do executável (cada uma é a lista de tokens iniciais)."""
    cmd = os.environ.get("ORCA_CLI_COMMAND", "").strip()
    if cmd:
        try:
            return [shlex.split(cmd)]
        except ValueError:
            return []
    formas = [["orca-ide"]]
    em_terminal_orca = any(
        os.environ.get(v) for v in ("ORCA_PANE_KEY", "ORCA_TERMINAL_HANDLE", "ORCA_AGENT_PANE")
    )
    achado = shutil.which("orca")
    if em_terminal_orca and achado and os.path.realpath(achado) != "/usr/bin/orca":
        formas.append(["orca"])
    return formas


def varrer(comando: str) -> str | None:
    """Devolve o motivo do bloqueio se houver metacaractere perigoso."""
    aspas = None
    for ch in comando:
        if ch in SEMPRE_BARRADOS:
            return f"metacaractere de shell {ch!r} no comando"
        if aspas:
            if ch == aspas:
                aspas = None
            continue
        if ch in "'\"":
            aspas = ch
        elif ch in FORA_DE_ASPAS:
            return f"metacaractere de shell {ch!r} fora de aspas"
    if aspas:
        return "aspas sem fechar"
    return None


def validar_flags(args: list[str], tabela_flags: dict, nome: str) -> str | None:
    i = 0
    while i < len(args):
        tok = args[i]
        if not tok.startswith("--"):
            return f"argumento solto {tok!r} em {nome}"
        flag, igual, valor = tok.partition("=")
        if flag not in tabela_flags:
            return f"flag {flag} não permitida em {nome}"
        recebe, ok = tabela_flags[flag]
        if recebe:
            if not igual:
                i += 1
                if i >= len(args):
                    return f"flag {flag} sem valor"
                valor = args[i]
            if ok and not ok(valor):
                return f"valor de {flag} fora do permitido em {nome}"
        elif igual:
            return f"flag {flag} não recebe valor"
        i += 1
    return None


def avaliar(comando: str) -> str | None:
    """None = permitido; texto = motivo do bloqueio."""
    if not comando.strip():
        return "comando vazio"
    motivo = varrer(comando)
    if motivo:
        return motivo
    try:
        tokens = shlex.split(comando)
    except ValueError:
        return "comando não interpretável"
    exe = next((e for e in executavel() if tokens[: len(e)] == e), None)
    if exe is None:
        return "o comando não começa com o executável do Orca"
    args = tokens[len(exe):]
    if not args:
        return "faltou o subcomando do Orca"
    for tok in args:
        base = tok.partition("=")[0]
        if base in FLAGS_PROIBIDAS:
            return f"flag {base} não é permitida"
    for i, tok in enumerate(args):
        if tok == "--environment" and (i + 1 >= len(args) or args[i + 1] != "local"):
            return "--environment só aceita local"
        if tok.startswith("--environment=") and tok != "--environment=local":
            return "--environment só aceita local"

    # `open` traz a janela do Orca para a frente: nem a ajuda dele passa
    if args[0] in ("open", "serve"):
        return f"{args[0]} não é permitido"

    # --help: só ajuda pura (palavras e --help, nenhuma outra flag)
    if "--help" in args:
        resto = [a for a in args if a != "--help"]
        if all(re.fullmatch(r"[a-z][a-z-]*", a) for a in resto):
            return None
        return "--help só vale sem outras flags"

    if args[0] == "orchestration":
        if len(args) < 2:
            return "faltou o subcomando de orchestration"
        sub = args[1]
        if sub not in ORCHESTRATION:
            return f"orchestration {sub} não está na allowlist"
        return validar_flags(args[2:], ORCHESTRATION[sub], f"orchestration {sub}")

    if args[:2] == ["worktree", "set"]:
        return validar_flags(args[2:], WORKTREE_SET, "worktree set")

    for chave in LEITURA:
        if tuple(args[: len(chave)]) == chave:
            return None
    return f"subcomando {' '.join(args[:2])} não está na allowlist"


def main() -> int:
    try:
        dados = json.load(sys.stdin)
    except Exception:
        return bloquear("entrada do hook ilegível (bloqueio por padrão)")
    if dados.get("agent_id"):
        return 0
    comando = (dados.get("tool_input") or {}).get("command") or ""
    motivo = avaliar(comando)
    if motivo:
        return bloquear(motivo)
    return 0


if __name__ == "__main__":
    sys.exit(main())
