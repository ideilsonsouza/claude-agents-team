#!/usr/bin/env python3
"""Testes do hooks/evidence-guard.py com entradas simuladas e exit codes reais.
Uso: python3 ~/.claude/scripts/test-evidence-guard.py  (exit 0 = todos passaram)"""
import json, pathlib, subprocess, sys, tempfile

HOOK = pathlib.Path.home() / ".claude" / "hooks" / "evidence-guard.py"
F = "```"
OK = f"""## Status
CONCLUÍDO — feito.

## Verificação
{F}
$ go test ./internal/orders
ok  orders 0.4s
{F}

## Limpeza
Nada criado.
"""
P = f"""## Status
CONCLUÍDO — ajuste.

## O que mudou
- a.go

## Evidência
{F}
$ go test ./x
ok
{F}

## Limpeza
Nada criado.
"""
SEM_BLOCO = OK.replace(F, "").replace("$ go test", "`go test") + ""
SEM_LIMPEZA = OK.split("## Limpeza")[0]
SEM_VERIF = "## Status\nCONCLUÍDO — x.\n\n## Limpeza\nNada criado.\n"
SEM_STATUS = "Terminei, ficou tudo certo."
BLOQ = "## Status\nBLOQUEADO — falta o objetivo.\n\n## Perguntas para especialistas\n| 1 | usuário | ? |\n"
PARC_NV = "## Status\nPARCIAL — sem banco.\n\n## Verificação\n- Testes: não verificado, banco parado.\n\n## Limpeza\nNada criado.\n"
CONC_NV = PARC_NV.replace("PARCIAL", "CONCLUÍDO")
RESP = "## Respostas\n| 1 | sim | arquivo:1 | alta |\n"
BLOCO_VAZIO = f"## Status\nCONCLUÍDO — x.\n\n## Verificação\n{F}\n{F}\n\n## Limpeza\nNada criado.\n"

def roda(entrada):
    p = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(entrada) if not isinstance(entrada, str) else entrada,
                       capture_output=True, text=True)
    return p.returncode, p.stderr.strip()

def ev(tipo, msg, ativo=False, **extra):
    d = {"hook_event_name": "SubagentStop", "stop_hook_active": ativo, "agent_type": tipo, "last_assistant_message": msg}
    d.update(extra)
    return d

casos = [
    ("executor, relatório completo", ev("backend", OK), 0),
    ("executor, tarefa P (Evidência)", ev("pr", P), 0),
    ("sem bloco de código", ev("backend", SEM_BLOCO), 2),
    ("bloco de código vazio", ev("qa", BLOCO_VAZIO), 2),
    ("sem seção Limpeza", ev("dba", SEM_LIMPEZA), 2),
    ("sem seção Verificação", ev("devops", SEM_VERIF), 2),
    ("sem seção Status", ev("frontend", SEM_STATUS), 2),
    ("BLOQUEADO passa", ev("rust", BLOQ), 0),
    ("PARCIAL com 'não verificado' passa", ev("docs", PARC_NV), 0),
    ("CONCLUÍDO com 'não verificado' sem bloco volta", ev("deploy", CONC_NV), 2),
    ("resposta de consulta passa", ev("supabase", RESP), 0),
    ("stop_hook_active=true nunca devolve de novo", ev("backend", SEM_BLOCO, ativo=True), 0),
    ("agente de leitura fora (reviewer)", ev("reviewer", SEM_STATUS), 0),
    ("agente de domínio fora (shop-floor)", ev("shop-floor", SEM_STATUS), 0),
    ("orchestrator fora", ev("orchestrator", SEM_STATUS), 0),
    ("mensagem vazia sem transcript: passa", ev("data-engineer", ""), 0),
    ("stdin inválido: passa (falha aberta)", "isto nao e json", 0),
]
falhas = 0
for nome, entrada, esperado in casos:
    rc, err = roda(entrada)
    ok = rc == esperado
    falhas += not ok
    print(f"{'OK  ' if ok else 'FAIL'} exit={rc} (esperado {esperado}) {nome}" + (f"\n       stderr: {err[:230]}" if rc == 2 else ""))

# Fallback por transcript (sem last_assistant_message)
with tempfile.TemporaryDirectory() as d:
    for nome, texto, esperado in (("transcript incompleto", SEM_BLOCO, 2), ("transcript completo", OK, 0)):
        t = pathlib.Path(d) / "t.jsonl"
        t.write_text(json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": texto}]}}) + "\n")
        e = ev("qa", ""); e.pop("last_assistant_message"); e["agent_transcript_path"] = str(t)
        rc, _ = roda(e)
        ok = rc == esperado
        falhas += not ok
        print(f"{'OK  ' if ok else 'FAIL'} exit={rc} (esperado {esperado}) fallback {nome}")

# Sequência de duas paradas: 1ª devolve (exit 2), 2ª com stop_hook_active=true passa (exit 0)
r1, _ = roda(ev("backend", SEM_BLOCO, ativo=False)); r2, _ = roda(ev("backend", SEM_BLOCO, ativo=True))
ok = (r1, r2) == (2, 0); falhas += not ok
print(f"{'OK  ' if ok else 'FAIL'} sequência sem laço: 1ª parada exit={r1}, 2ª (ativo) exit={r2}")
print(f"\n{len(casos)+3-falhas}/{len(casos)+3} passaram")
sys.exit(1 if falhas else 0)
