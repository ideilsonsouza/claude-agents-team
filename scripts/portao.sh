#!/usr/bin/env bash
# Portão de qualidade determinístico: usa o portão do projeto, se houver; senão roda as
# ferramentas da stack detectada que estiverem no PATH. Saída enxuta; última linha fixa:
#   PORTÃO: VERDE | PORTÃO: VERMELHO (falhou: x, y) | PORTÃO: VAZIO (nada rodou|sem stack)
# seguida de "| ausentes: a, b" quando faltar ferramenta. Exit: 0 verde, 1 vermelho, 2 vazio.
# Não cria banco nem container; sem pkill. Atenção: o portão PRÓPRIO do projeto (ci-local.sh,
# make check...) pode usar os serviços locais (Postgres/Redis de /worksapce/opt) conforme o
# CLAUDE.md global; o script em si não sobe nada.
set -euo pipefail

uso() {
  cat <<'USO'
Uso: portao.sh <dir> [--base <rev>]
  <dir>          raiz do projeto
  --base <rev>   revisão base do golangci-lint --new-from-rev (padrão: origin/main ou main, se existirem)
Exit: 0 = VERDE, 1 = VERMELHO (alguma etapa falhou), 2 = VAZIO (nada rodou ou sem stack)
Env: PORTAO_TIMEOUT (segundos por etapa, padrão 300), PORTAO_TAIL (linhas por falha, padrão 15)
Portão próprio (para na primeira que existir): scripts/ci-local.sh, Makefile (check|gate|ci),
  justfile (check), package.json (script check|gate|ci). Ele pode usar serviços locais.
Stacks: Go, Node (pnpm/npm/yarn), Rust, Python (sem criar venv), PHP (composer).
USO
}

DIR="" BASE=""
while [ $# -gt 0 ]; do
  case "$1" in
    -h|--help) uso; exit 0 ;;
    --base) [ $# -ge 2 ] || { echo "--base exige um valor" >&2; exit 2; }; BASE="$2"; shift 2 ;;
    -*) echo "opção desconhecida: $1" >&2; uso >&2; exit 2 ;;
    *) if [ -z "$DIR" ]; then DIR="$1"; else echo "argumento extra: $1" >&2; exit 2; fi; shift ;;
  esac
done
[ -n "$DIR" ] && [ -d "$DIR" ] || { echo "diretório inválido: ${DIR:-<vazio>}" >&2; uso >&2; exit 2; }
DIR="$(cd "$DIR" && pwd)"

TMO="${PORTAO_TIMEOUT:-300}"; TAIL="${PORTAO_TAIL:-15}"
LOG="$(mktemp -d)"; CUR=""
FALHAS=(); AUSENTES=(); RODOU=0

# encerra o grupo da etapa em andamento (ela roda em sessão própria, via setsid) e limpa
abortar() { [ -n "$CUR" ] && kill -TERM -- "-$CUR" 2>/dev/null || true; exit 130; }
trap 'rm -rf "$LOG"' EXIT
trap abortar INT TERM

# no PATH e utilizável (shim do mise sem versão definida conta como ausente)
tem_mise() { command -v mise >/dev/null 2>&1 && mise which "$1" >/dev/null 2>&1; }
tem() {
  local p; p="$(command -v "$1" 2>/dev/null)" || return 1
  case "$p" in */mise/shims/*) tem_mise "$1" ;; *) return 0 ;; esac
}
ausente() { local x; for x in "${AUSENTES[@]:-}"; do [ "$x" = "$1" ] && return 0; done; AUSENTES+=("$1"); return 0; }
# exige ferramentas no PATH; registra as que faltam e devolve 1
exige() { local ok=0 t; for t in "$@"; do tem "$t" || { ausente "$t"; ok=1; }; done; return $ok; }

PRE=()
if tem timeout; then PRE=(timeout -k 10 "$TMO"); else ausente timeout; fi
SESS=(); tem setsid && SESS=(setsid)

# etapa <nome> <dir> <cmd...>: roda em <dir>, mostra só falhas (últimas linhas). Nunca aborta o script.
# ALLOW_RC=<n> (opcional, via prefixo de variável) trata esse exit code como sucesso.
etapa() {
  local nome="$1" d="$2"; shift 2
  RODOU=$((RODOU+1))
  local out="$LOG/$RODOU.log" rc=0
  "${SESS[@]}" "${PRE[@]}" bash -c 'cd "$1" && shift && exec "$@"' _ "$d" "$@" >"$out" 2>&1 </dev/null &
  CUR=$!
  wait "$CUR" || rc=$?
  CUR=""
  [ "$rc" -eq "${ALLOW_RC:--1}" ] && rc=0
  if [ "$rc" -ne 0 ]; then
    FALHAS+=("$nome")
    echo "--- FALHOU: $nome (exit $rc; $*)"
    tail -n "$TAIL" "$out"
  else
    echo "ok: $nome"
  fi
  return 0
}

juntar() { local IFS=,; echo "$*" | sed 's/,/, /g'; }
final() {
  local msg code
  if [ "${#FALHAS[@]}" -gt 0 ]; then msg="PORTÃO: VERMELHO (falhou: $(juntar "${FALHAS[@]}"))"; code=1
  elif [ "$RODOU" -eq 0 ]; then msg="PORTÃO: VAZIO (${MOTIVO_VAZIO:-nada rodou})"; code=2
  else msg="PORTÃO: VERDE"; code=0; fi
  [ "${#AUSENTES[@]}" -gt 0 ] && msg="$msg | ausentes: $(juntar "${AUSENTES[@]}")"
  echo "$msg"
  exit "$code"
}

# ---------- portão próprio ----------
proprio=""; cmd=()
if [ -x "$DIR/scripts/ci-local.sh" ]; then proprio="scripts/ci-local.sh"; cmd=(bash scripts/ci-local.sh)
elif [ -f "$DIR/Makefile" ] && tem make && alvo=$(grep -oE '^(check|gate|ci):' "$DIR/Makefile" | head -1 | tr -d ':') && [ -n "$alvo" ]; then
  proprio="make $alvo"; cmd=(make "$alvo")
elif [ -f "$DIR/justfile" ] && tem just && grep -qE '^check\b' "$DIR/justfile"; then proprio="just check"; cmd=(just check)
elif [ -f "$DIR/package.json" ] && tem python3 && alvo=$(python3 -I -c '
import json,sys
s=json.load(open(sys.argv[1])).get("scripts",{})
print(next((k for k in ("check","gate","ci") if k in s),""))' "$DIR/package.json" 2>/dev/null) && [ -n "$alvo" ]; then
  pm=npm; [ -f "$DIR/pnpm-lock.yaml" ] && pm=pnpm; [ -f "$DIR/yarn.lock" ] && pm=yarn
  if tem "$pm"; then proprio="$pm run $alvo"; cmd=("$pm" run "$alvo"); else ausente "$pm"; fi
fi
if [ -n "$proprio" ]; then
  echo "portão próprio: $proprio"
  etapa "$proprio" "$DIR" "${cmd[@]}"
  final
fi

# ---------- por stack ----------
base_rev() {
  [ -n "$BASE" ] && { echo "$BASE"; return 0; }
  local r
  for r in origin/main main; do
    if git -C "$DIR" rev-parse --verify -q "$r" >/dev/null 2>&1; then echo "$r"; return 0; fi
  done
  return 0
}

p_go() { local d="$1" p="$2"
  exige go gofmt || return 0
  local fmt; RODOU=$((RODOU+1))
  fmt=$(cd "$d" && gofmt -l . 2>/dev/null | grep -v '^vendor/' || true)
  if [ -n "$fmt" ]; then FALHAS+=("${p}gofmt"); echo "--- FALHOU: ${p}gofmt (arquivos sem formatar)"; echo "$fmt" | head -n "$TAIL"; else echo "ok: ${p}gofmt"; fi
  etapa "${p}go vet" "$d" go vet ./...
  if tem golangci-lint; then
    local b; b="$(base_rev)" || b=""
    if [ -n "$b" ]; then etapa "${p}golangci-lint" "$d" golangci-lint run --new-from-rev="$b"
    else etapa "${p}golangci-lint" "$d" golangci-lint run; fi
  else ausente golangci-lint; fi
  etapa "${p}go test" "$d" go test -race -count=1 ./...
  if tem govulncheck; then etapa "${p}govulncheck" "$d" govulncheck ./...; else ausente govulncheck; fi
  return 0
}

p_node() { local d="$1" p="$2" pm=npm
  [ -f "$d/pnpm-lock.yaml" ] && pm=pnpm
  [ -f "$d/yarn.lock" ] && pm=yarn
  exige "$pm" || return 0
  [ -d "$d/node_modules" ] || { ausente "node_modules(${p%:})"; return 0; }
  tem python3 || { ausente python3; return 0; }
  temscript() { python3 -I -c '
import json,sys
sys.exit(0 if sys.argv[2] in json.load(open(sys.argv[1])).get("scripts",{}) else 1)' "$d/package.json" "$1" 2>/dev/null; }
  if [ -f "$d/tsconfig.json" ]; then
    case "$pm" in
      pnpm) etapa "${p}tsc" "$d" pnpm exec tsc --noEmit ;;
      yarn) etapa "${p}tsc" "$d" yarn tsc --noEmit ;;
      *) etapa "${p}tsc" "$d" npx --no-install tsc --noEmit ;;
    esac
  fi
  if temscript lint; then etapa "${p}lint" "$d" "$pm" run lint; fi
  if temscript test; then etapa "${p}test" "$d" "$pm" run test; fi
  return 0
}

p_rust() { local d="$1" p="$2"
  exige cargo || return 0
  etapa "${p}cargo fmt" "$d" cargo fmt --check
  etapa "${p}clippy" "$d" cargo clippy --all-targets -- -D warnings
  etapa "${p}cargo test" "$d" cargo test
  if cargo deny --version >/dev/null 2>&1; then etapa "${p}cargo deny" "$d" cargo deny check; else ausente cargo-deny; fi
  return 0
}

# Python: nunca cria .venv nem uv.lock (sem `uv sync`). Com uv.lock + .venv existentes usa
# `uv run --no-sync`; sem venv do projeto, usa a ferramenta do PATH; senão marca ausente.
# Motivo: o portão não pode alterar o projeto nem instalar dependências sem pedido.
py_cmd() { # py_cmd <dir> <ferramenta> -> imprime o prefixo do comando, ou nada se indisponível
  local d="$1" t="$2"
  if [ -f "$d/uv.lock" ] && [ -d "$d/.venv" ] && tem uv && grep -qsiw -- "$t" "$d/pyproject.toml" "$d/uv.lock"; then
    echo "uv run --no-sync $t"
  elif tem "$t"; then echo "$t"; fi
  return 0
}
p_python() { local d="$1" p="$2" c
  c=$(py_cmd "$d" ruff)
  if [ -n "$c" ]; then etapa "${p}ruff check" "$d" $c check; etapa "${p}ruff format" "$d" $c format --check; else ausente ruff; fi
  c=$(py_cmd "$d" pyright)
  if [ -n "$c" ] && grep -qs 'pyright' "$d/pyproject.toml" "$d/pyrightconfig.json"; then etapa "${p}pyright" "$d" $c
  else
    c=$(py_cmd "$d" mypy)
    if [ -n "$c" ] && grep -qs 'mypy' "$d/pyproject.toml" "$d/mypy.ini"; then etapa "${p}mypy" "$d" $c .
    else ausente "pyright|mypy"; fi
  fi
  c=$(py_cmd "$d" pytest)
  if [ -n "$c" ]; then ALLOW_RC=5 etapa "${p}pytest" "$d" $c -q; else ausente pytest; fi  # exit 5 = sem testes
  return 0
}

p_php() { local d="$1" p="$2"
  [ -d "$d/vendor/bin" ] || { ausente "vendor(${p%:})"; return 0; }
  if [ -x "$d/vendor/bin/pint" ]; then etapa "${p}pint" "$d" vendor/bin/pint --test; else ausente pint; fi
  if [ -x "$d/vendor/bin/phpstan" ]; then etapa "${p}phpstan" "$d" vendor/bin/phpstan analyse; else ausente phpstan; fi
  if [ -x "$d/vendor/bin/pest" ]; then etapa "${p}pest" "$d" vendor/bin/pest
  elif [ -x "$d/vendor/bin/phpunit" ]; then etapa "${p}phpunit" "$d" vendor/bin/phpunit
  else ausente "pest|phpunit"; fi
  return 0
}

# diretórios candidatos: raiz, */ e apps|packages|services/*
cands=("$DIR")
ign() { case "$1" in node_modules|.git|.worktree|vendor|dist|.*) return 0 ;; esac; return 1; }
for c in "$DIR"/*/; do
  c="${c%/}"; n="${c##*/}"
  if ign "$n"; then continue; fi
  cands+=("$c")
  case "$n" in apps|packages|services)
    for s in "$c"/*/; do s="${s%/}"; if ! ign "${s##*/}"; then cands+=("$s"); fi; done ;;
  esac
done

ACHOU=0
for d in "${cands[@]}"; do
  p=""; if [ "$d" != "$DIR" ]; then p="${d#"$DIR"/}:"; fi
  if [ -f "$d/go.mod" ]; then ACHOU=1; p_go "$d" "$p"; fi
  if [ -f "$d/package.json" ]; then ACHOU=1; p_node "$d" "$p"; fi
  if [ -f "$d/Cargo.toml" ]; then ACHOU=1; p_rust "$d" "$p"; fi
  if [ -f "$d/pyproject.toml" ] || compgen -G "$d/requirements*.txt" >/dev/null; then ACHOU=1; p_python "$d" "$p"; fi
  if [ -f "$d/composer.json" ]; then ACHOU=1; p_php "$d" "$p"; fi
done
[ "$ACHOU" -eq 1 ] || MOTIVO_VAZIO="sem stack"
final
