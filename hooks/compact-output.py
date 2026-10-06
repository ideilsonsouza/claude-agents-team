#!/usr/bin/env python3
"""Compacta saída longa de testes/builds: mantém erros com contexto, início e resumo final."""
import re, sys

LIMITE_SEM_CORTE = 80
CONTEXTO = 3
INICIO, FIM, MAXIMO = 5, 25, 250
ERRO = re.compile(
    r"FAIL|ERROR|Error|error[:\[ ]|panic:|✗|✘|×|AssertionError|Expected|Received|not ok|"
    r"Traceback|TS\d{4}|undefined:|cannot use|exit status [1-9]|warning:",
)


def main() -> None:
    linhas = sys.stdin.read().splitlines()
    total = len(linhas)
    if total <= LIMITE_SEM_CORTE:
        print("\n".join(linhas))
        return
    manter = set(range(min(INICIO, total))) | set(range(max(0, total - FIM), total))
    for i, linha in enumerate(linhas):
        if ERRO.search(linha):
            manter.update(range(max(0, i - CONTEXTO), min(total, i + CONTEXTO + 1)))
    indices = sorted(manter)
    if len(indices) > MAXIMO:
        indices = indices[: MAXIMO - FIM] + [i for i in indices if i >= total - FIM]
    saida, anterior = [], -1
    for i in indices:
        if i != anterior + 1:
            saida.append(f"    [... {i - anterior - 1} linhas omitidas ...]")
        saida.append(linhas[i])
        anterior = i
    print(f"[saída compactada pelo hook: {len(indices)} de {total} linhas. "
          "Para ver tudo, rode de novo com o comentário `# full-output` no final do comando]")
    print("\n".join(saida))


if __name__ == "__main__":
    main()
