#!/usr/bin/env python3
"""Trava de evidência no fim do especialista executor (SubagentStop).

Ligada no frontmatter dos executores como `Stop` (o Claude Code converte para SubagentStop).
Contrato: exit 0 deixa o agente terminar; exit 2 o mantém trabalhando e entrega o stderr
como próxima instrução (docs: code.claude.com/docs/en/hooks, seção SubagentStop).

Regras (relatório final = campo `last_assistant_message`):
- Só executores (EXECUTORES). Leitura/domínio ficam de fora.
- No máximo 1 devolução por parada: `stop_hook_active` true => deixa passar.
- Resposta de consulta (`## Respostas` sem `## Status`) e status BLOQUEADO passam.
- Senão exige: `## Status` com CONCLUÍDO|PARCIAL, seção de verificação
  (`## Verificação` ou `## Evidência`) com bloco de código (comando e saída real) e
  seção `## Limpeza` não vazia.
- PARCIAL pode trocar o bloco por "não verificado" explícito (não força evidência inventada).
- Qualquer erro interno => exit 0 (falha aberta: uma trava quebrada não pode prender o agente).
"""
import json
import re
import sys

EXECUTORES = {
    "backend", "frontend", "rust", "dba", "supabase", "data-engineer",
    "qa", "devops", "docs", "pr", "deploy",
}

H2 = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
CERCA = re.compile(r"^\s*(```|~~~)", re.MULTILINE)


def secoes(texto: str) -> dict:
    """Mapa título normalizado -> corpo da seção (até o próximo `## `)."""
    achados = list(H2.finditer(texto))
    saida = {}
    for i, m in enumerate(achados):
        fim = achados[i + 1].start() if i + 1 < len(achados) else len(texto)
        saida.setdefault(m.group(1).strip().lower(), texto[m.end():fim])
    return saida


def pega(sec: dict, *prefixos):
    for titulo, corpo in sec.items():
        if any(titulo.startswith(p) for p in prefixos):
            return corpo
    return None


def tem_bloco_com_conteudo(corpo: str) -> bool:
    """Bloco de código fechado e com ao menos uma linha não vazia dentro."""
    linhas = corpo.splitlines()
    dentro, conteudo = False, 0
    for linha in linhas:
        if CERCA.match(linha):
            if dentro and conteudo > 0:
                return True
            dentro, conteudo = not dentro, 0
        elif dentro and linha.strip():
            conteudo += 1
    return False


def ultima_mensagem_do_transcript(caminho: str) -> str:
    """Fallback quando `last_assistant_message` não vem: último texto do assistente."""
    ultimo = ""
    with open(caminho, encoding="utf-8") as f:
        for linha in f:
            try:
                ev = json.loads(linha)
            except ValueError:
                continue
            msg = ev.get("message") or {}
            if ev.get("type") != "assistant" and msg.get("role") != "assistant":
                continue
            conteudo = msg.get("content")
            if isinstance(conteudo, str):
                texto = conteudo
            else:
                texto = "\n".join(
                    b.get("text", "") for b in (conteudo or []) if isinstance(b, dict) and b.get("type") == "text"
                )
            if texto.strip():
                ultimo = texto
    return ultimo


def avalia(texto: str) -> list:
    """Lista do que falta no relatório (vazia = ok)."""
    sec = secoes(texto)
    status = pega(sec, "status")
    if status is None:
        if pega(sec, "respostas") is not None:
            return []  # resposta de consulta ("Quando você é o consultado")
        return ["a seção `## Status` (CONCLUÍDO, PARCIAL ou BLOQUEADO em uma frase)"]
    m = re.search(r"CONCLU[IÍ]DO|PARCIAL|BLOQUEADO", status, re.IGNORECASE)
    if not m:
        return ["o valor em `## Status`: CONCLUÍDO, PARCIAL ou BLOQUEADO"]
    estado = m.group(0).upper()
    if estado == "BLOQUEADO":
        return []

    faltas = []
    verif = pega(sec, "verificação", "verificacao", "evidência", "evidencia")
    if verif is None:
        faltas.append("a seção `## Verificação` (ou `## Evidência` em tarefa P) com o comando rodado e a saída real em bloco de código")
    elif not tem_bloco_com_conteudo(verif):
        if estado == "PARCIAL" and re.search(r"n[aã]o verificado|n[aã]o rodou", verif, re.IGNORECASE):
            pass  # PARCIAL honesto: declarou o que não foi verificado
        else:
            faltas.append("em `## Verificação`, o comando e a saída real dentro de bloco de código (``` ... ```), não só texto ou inline")
    limpeza = pega(sec, "limpeza")
    if limpeza is None or not limpeza.strip():
        faltas.append("a seção `## Limpeza` com o que foi criado e a prova de remoção (ou \"Nada criado\")")
    return faltas


def main() -> int:
    try:
        dados = json.load(sys.stdin)
    except ValueError:
        return 0
    try:
        if dados.get("stop_hook_active"):
            return 0  # já devolvido uma vez nesta parada: nunca em laço
        if dados.get("agent_type") not in EXECUTORES:
            return 0
        texto = dados.get("last_assistant_message") or ""
        if not texto.strip() and dados.get("agent_transcript_path"):
            texto = ultima_mensagem_do_transcript(dados["agent_transcript_path"])
        if not texto.strip():
            return 0
        faltas = avalia(texto)
    except Exception:
        return 0
    if not faltas:
        return 0
    print(
        "Relatório incompleto (formato `delivery-contract`). Falta: "
        + "; ".join(faltas)
        + ". Rode o que faltar, cole a saída real e reenvie o relatório completo. "
        "Se algo não pôde ser verificado, diga \"não verificado\" e use status PARCIAL ou BLOQUEADO. "
        "Esta é a única devolução automática: não invente evidência.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
