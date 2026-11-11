#!/usr/bin/env bash
# Limpeza de disco das sessões de agentes. Padrão: --dry-run (só lista e estima).
# Uso: limpeza-agentes.sh [--dry-run | --apply]
#
# Limpa: cache de build do Docker (> 7 dias), cache do Go (> 10G), cache do npm (> 5G),
#        temporários do usuário em /tmp (> 3 dias e sem processo usando) e bancos test_% antigos.
# Só relata: worktrees candidatas à remoção (nunca apaga).
# Raízes de busca de worktrees: WORKSPACE_ROOTS (lista separada por ':'), lida do ambiente ou de
#             ~/.config/agent-team/env; sem nenhum dos dois, usa $HOME.
# Nunca toca: dados dos serviços locais compartilhados, volumes Docker, ~/.orca, ~/.claude, ~/.cache/ms-playwright,
#             ~/.cache/qmd e a pasta principal dos repositórios.
# Proibido aqui: docker system prune, docker volume prune, docker image prune -a.
set -euo pipefail

MODO=dry-run
case "${1:-}" in
  "" | --dry-run) MODO=dry-run ;;
  --apply) MODO=apply ;;
  -h | --help) sed -n 2,12p "$0"; exit 0 ;;
  *) echo "Uso: $0 [--dry-run | --apply]" >&2; exit 64 ;;
esac

LIMITE_GO=$((10 * 1024 * 1024 * 1024))
LIMITE_NPM=$((5 * 1024 * 1024 * 1024))
DIAS_TMP=3
DIAS_WORKTREE=14
DIAS_BANCO=1
DOCKER_IDADE=168h
UID_ATUAL=$(id -u)
HOMEDIR=${HOME:?}
CRED="$HOMEDIR/.config/agent-db/credentials.env"
# WORKSPACE_ROOTS: ambiente > ~/.config/agent-team/env > $HOME
if [ -z "${WORKSPACE_ROOTS:-}" ] && [ -f "$HOMEDIR/.config/agent-team/env" ]; then
  # shellcheck disable=SC1091
  . "$HOMEDIR/.config/agent-team/env"
fi
WORKSPACE_ROOTS=${WORKSPACE_ROOTS:-$HOMEDIR}
IFS=: read -r -a RAIZES <<<"$WORKSPACE_ROOTS"
TMPDIR_LIMPEZA=$(mktemp -d)
trap 'rm -rf "$TMPDIR_LIMPEZA"' EXIT

TOTAL=0 # bytes liberados, medidos antes/depois (apply), ou estimados (dry-run)

humano() { numfmt --to=iec --suffix=B "${1:-0}" 2>/dev/null || echo "${1:-0}B"; }
titulo() { printf '\n== %s ==\n' "$1"; }
somar() { TOTAL=$((TOTAL + ${1:-0})); }
tam() { local r; r=$(du -sb -- "$1" 2>/dev/null | cut -f1) || r=""; echo "${r:-0}"; }
# Processo do usuário que pode estar usando os caches (só leitura).
proc_ativo() {
  local n
  for n in go npm pnpm node; do
    if pgrep -u "$UID_ATUAL" -x "$n" >/dev/null 2>&1; then echo "$n"; return 0; fi
  done
  return 1
}
BLOQUEADO=0 # bytes que não puderam ser limpos agora por haver processo ativo
disco_livre() { df -B1 --output=avail / | tail -1 | tr -d ' '; }
uso_disco() { df -h --output=pcent,avail / | tail -1 | awk '{print $1" usado, "$2" livre"}'; }
aplicando() { [ "$MODO" = apply ]; }

echo "Modo: $MODO"
echo "Disco /: $(uso_disco)"
LIVRE_ANTES=$(disco_livre)

# ---------------------------------------------------------------- Docker
titulo "Docker: build cache com mais de $DOCKER_IDADE"
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  # O "buildx du --filter until=" IGNORA o filtro (testado: until=1h e until=168h devolvem o
  # mesmo total), enquanto o "builder prune --filter until=" o respeita. Por isso a estimativa
  # é calculada aqui, pela idade (LastUsedAt, relativo) de cada entrada reclamável.
  HORAS_MIN=${DOCKER_IDADE%h}
  docker_bytes() { # $1 = idade mínima em horas (0 = tudo que é reclamável)
    docker buildx du --format '{{json .}}' 2>/dev/null | jq -r '
      select(.Reclaimable)
      | (.LastUsedAt | capture("(?<n>[0-9]+) (?<u>second|minute|hour|day|week|month|year)") // {n:"0",u:"second"}) as $a
      | ($a.n|tonumber) * ({second:0.0003,minute:0.017,hour:1,day:24,week:168,month:720,year:8760}[$a.u]) as $h
      | "\($h) \(.Size)"' | awk -v min="$1" '
      $1>=min { v=$2; u=v; gsub(/[0-9.]/,"",u); gsub(/[A-Za-z]/,"",v);
        m=(u=="GB")?1e9:(u=="MB")?1e6:(u=="kB"||u=="KB")?1e3:(u=="TB")?1e12:1; s+=v*m }
      END { printf "%.0f", s+0 }'
  }
  EST=$(docker_bytes "$HORAS_MIN"); EST=${EST:-0}
  echo "Reclamável estimado (>${DOCKER_IDADE}): $(humano "$EST") de $(humano "$(docker_bytes 0)") de cache total"
  if aplicando; then
    ANTES_D=$(docker_bytes 0)
    docker builder prune -f --filter "until=$DOCKER_IDADE" | tail -1
    DEPOIS_D=$(docker_bytes 0)
    REAL_D=$((ANTES_D - DEPOIS_D)); [ "$REAL_D" -lt 0 ] && REAL_D=0
    echo "Liberado (medido): $(humano "$REAL_D")"
    somar "$REAL_D"
  else
    somar "$EST"
  fi
else
  echo "Docker indisponível: pulado."
fi

# ---------------------------------------------------------------- Go
titulo "Go: cache de build (limite $(humano $LIMITE_GO))"
GOCACHE_DIR=$(go env GOCACHE 2>/dev/null || echo "$HOMEDIR/.cache/go-build")
if [ -d "$GOCACHE_DIR" ]; then
  T=$(tam "$GOCACHE_DIR")
  echo "$GOCACHE_DIR: $(humano "$T")"
  if [ "$T" -gt "$LIMITE_GO" ]; then
    echo "Acima do limite: go clean -cache"
    if P=$(proc_ativo); then
      echo "AVISO: processo '$P' do usuário em execução; seção pulada. Rode com as sessões paradas."
      BLOQUEADO=$((BLOQUEADO + T))
    else
      if aplicando; then go clean -cache; somar "$((T - $(tam "$GOCACHE_DIR")))"; else somar "$T"; fi
    fi
  else
    echo "Abaixo do limite: nada a fazer."
  fi
else
  echo "Sem cache do Go."
fi

# ---------------------------------------------------------------- npm
titulo "npm: cache (limite $(humano $LIMITE_NPM))"
NPMCACHE=$(npm config get cache 2>/dev/null || echo "$HOMEDIR/.npm")
if [ -d "$NPMCACHE" ]; then
  T=$(tam "$NPMCACHE")
  echo "$NPMCACHE: $(humano "$T")"
  if [ "$T" -gt "$LIMITE_NPM" ]; then
    # clean --force em vez de verify: o verify só remove o que nenhum índice referencia e
    # costuma liberar pouco; o cache é regenerável (custo: o próximo npm install baixa de novo).
    echo "Acima do limite: npm cache clean --force"
    if P=$(proc_ativo); then
      echo "AVISO: processo '$P' do usuário em execução; seção pulada. Rode com as sessões paradas."
      BLOQUEADO=$((BLOQUEADO + T))
    else
      if aplicando; then npm cache clean --force 2>&1 | tail -1; somar "$((T - $(tam "$NPMCACHE")))"; else somar "$T"; fi
    fi
  else
    echo "Abaixo do limite: nada a fazer."
  fi
else
  echo "Sem cache do npm."
fi

# ---------------------------------------------------------------- /tmp
titulo "/tmp: itens do usuário com mais de $DIAS_TMP dias e sem processo usando"
SESSOES_DIR="$HOMEDIR/.claude/sessions"
USO="$TMPDIR_LIMPEZA/em-uso.txt"
VIVAS="$TMPDIR_LIMPEZA/sessoes-vivas.txt"
TMP_OK=1
# Sessões vivas: ~/.claude/sessions/<pid>.json com sessionId e /proc/<pid> existente.
if [ -d "$SESSOES_DIR" ] && [ -r "$SESSOES_DIR" ]; then
  python3 -I - "$SESSOES_DIR" >"$VIVAS" <<'PY' || TMP_OK=0
import json, os, sys
d = sys.argv[1]
for nome in os.listdir(d):
    if not nome.endswith(".json"):
        continue
    try:
        j = json.load(open(os.path.join(d, nome), encoding="utf-8"))
        if os.path.isdir(f"/proc/{int(j['pid'])}") and j.get("sessionId"):
            print(j["sessionId"])
    except FileNotFoundError:
        continue  # sessão encerrou entre a listagem e a leitura
    except Exception:
        sys.exit(1)  # arquivo ilegível ou sendo reescrito: não adivinha, pula a seção
PY
else
  TMP_OK=0
fi
# Arquivos abertos e cwd do usuário (varredura única). lsof ausente ou com erro: pula a seção.
if ! command -v lsof >/dev/null 2>&1; then
  TMP_OK=0
else
  LSOF_RC=0
  lsof -nP -w -u "$UID_ATUAL" -Fn >"$TMPDIR_LIMPEZA/lsof.raw" 2>/dev/null || LSOF_RC=$?
  if [ "$LSOF_RC" -gt 1 ]; then TMP_OK=0; fi
  sed -n 's/^n//p' "$TMPDIR_LIMPEZA/lsof.raw" | sort -u >"$USO" || true
fi

if [ "$TMP_OK" != 1 ]; then
  echo "AVISO: sem ~/.claude/sessions legível ou sem lsof funcional; seção do /tmp pulada."
else
  CAND="$TMPDIR_LIMPEZA/cand.bin"
  {
    # claude-<uid>/<projeto>/<sessão>: cada sessão é julgada sozinha; arquivos soltos também.
    find "/tmp/claude-$UID_ATUAL" -mindepth 2 -maxdepth 2 -user "$UID_ATUAL" -print0 2>/dev/null || true
    find "/tmp/claude-$UID_ATUAL" -mindepth 1 -maxdepth 1 -type f -user "$UID_ATUAL" -print0 2>/dev/null || true
    find /tmp -maxdepth 1 -mindepth 1 -user "$UID_ATUAL" \( -name 'go-build*' -o -name 'electron-download-*' -o -name '*.log' \) -print0 2>/dev/null || true
  } | sort -z -u >"$CAND"

  LIMITE_SEG=$(($(date +%s) - DIAS_TMP * 86400))
  TMP_TOTAL=0
  N_TMP=0
  while IFS= read -r -d '' item; do
    [ -e "$item" ] || continue
    # Só dentro dos padrões esperados, sem ".." e sem symlink na raiz do item.
    case "$item" in
      *"/../"* | *$'\n'*) continue ;;
      "/tmp/claude-$UID_ATUAL/"?* | /tmp/go-build* | /tmp/electron-download-* | /tmp/*.log) ;;
      *) continue ;;
    esac
    [ ! -L "$item" ] || continue
    # Nunca uma sessão viva (o nome da pasta é o sessionId).
    if grep -qxF -- "$(basename -- "$item")" "$VIVAS"; then
      echo "pulado (sessão viva): $item"
      continue
    fi
    # Qualquer arquivo ou pasta modificado dentro do prazo mantém o item inteiro.
    if [ -n "$(find "$item" -newermt "@$LIMITE_SEG" -print -quit 2>/dev/null)" ]; then
      continue
    fi
    # Em uso: algum caminho aberto ou cwd igual ao item ou dentro dele.
    if grep -qxF -- "$item" "$USO" || grep -qF -- "$item/" "$USO"; then
      echo "pulado (em uso): $item"
      continue
    fi
    T=$(tam "$item")
    echo "$(humano "$T")  $item"
    TMP_TOTAL=$((TMP_TOTAL + T))
    N_TMP=$((N_TMP + 1))
    if aplicando; then rm -rf -- "$item"; fi
  done <"$CAND"
  echo "Subtotal /tmp: $N_TMP item(ns), $(humano "$TMP_TOTAL")"
  somar "$TMP_TOTAL"
fi

# ---------------------------------------------------------------- Bancos de teste
titulo "Bancos test_% com mais de $DIAS_BANCO dia(s)"
# Lê só as variáveis necessárias do arquivo de credenciais (sem `source`); nunca imprime.
le_cred() { grep -m1 "^$1=" "$CRED" 2>/dev/null | cut -d= -f2- | sed -e "s/^['\"]//" -e "s/['\"]$//" || true; }
nome_valido() { [[ "$1" =~ ^test_[A-Za-z0-9_-]+$ ]]; }
if [ -r "$CRED" ] && command -v docker >/dev/null 2>&1; then
  AGENT_PG_PASSWORD=$(le_cred AGENT_PG_PASSWORD)
  AGENT_MARIADB_PASSWORD=$(le_cred AGENT_MARIADB_PASSWORD)
  AGORA=$(date +%s)
  N_BD=0
  # A senha vai por variável de ambiente (-e NOME, sem valor no argv).
  pg() { PGPASSWORD="$AGENT_PG_PASSWORD" docker exec -i -e PGPASSWORD postgres psql -U agent_test -h 127.0.0.1 -d postgres "$@"; }
  my() { MYSQL_PWD="$AGENT_MARIADB_PASSWORD" docker exec -i -e MYSQL_PWD mariadb mariadb -u agent_test "$@"; }
  # PostgreSQL: não há data de criação no catálogo; usa o mtime do PG_VERSION do banco no disco.
  if docker exec postgres true 2>/dev/null; then
    PGDATA_DIR=$(docker exec postgres sh -c 'echo "$PGDATA"')
    while IFS='|' read -r -u 3 oid nome; do
      [ -n "${nome:-}" ] || continue
      case "$nome" in test_*) ;; *) continue ;; esac
      nome_valido "$nome" || { echo "postgres: nome ignorado por caracteres inválidos"; continue; }
      [[ "$oid" =~ ^[0-9]+$ ]] || continue
      ts=$(docker exec postgres stat -c %Y "$PGDATA_DIR/base/$oid/PG_VERSION" 2>/dev/null || echo "$AGORA")
      if [ $((AGORA - ts)) -gt $((DIAS_BANCO * 86400)) ]; then
        echo "postgres: $nome (criado em $(date -d "@$ts" +%F))"
        N_BD=$((N_BD + 1))
        if aplicando; then
          # :"n" aplica quote_ident no psql.
          printf 'DROP DATABASE IF EXISTS :"n" WITH (FORCE)\n' | pg -q -v n="$nome"
        fi
      fi
    done 3< <(pg -Atc "select oid||'|'||datname from pg_database where datname like 'test\_%'" 2>/dev/null </dev/null || true)
  else
    echo "postgres: container parado, pulado."
  fi
  # MariaDB: idade = menor create_time das tabelas. Schema sem tabelas não tem data: é ignorado.
  if docker exec mariadb true 2>/dev/null; then
    # Laço lê pelo descritor 3: o docker exec -i do DROP não pode consumir a lista.
    while IFS=$'\t' read -r -u 3 nome idade; do
      [ -n "${nome:-}" ] || continue
      case "$nome" in test_*) ;; *) continue ;; esac
      nome_valido "$nome" || { echo "mariadb: nome ignorado por caracteres inválidos"; continue; }
      if [ "${idade:-0}" -gt $((DIAS_BANCO * 86400)) ]; then
        echo "mariadb: $nome (idade $((idade / 3600))h)"
        N_BD=$((N_BD + 1))
        if aplicando; then
          q=${nome//\`/\`\`}
          my -e "DROP DATABASE \`$q\`" </dev/null
        fi
      fi
    done 3< <(my -Nse "select table_schema, timestampdiff(SECOND, min(create_time), now()) from information_schema.tables where table_schema like 'test\_%' group by 1" 2>/dev/null </dev/null || true)
  else
    echo "mariadb: container parado, pulado."
  fi
  unset AGENT_PG_PASSWORD AGENT_MARIADB_PASSWORD
  echo "Bancos antigos encontrados: $N_BD"
else
  echo "Sem credenciais ($CRED) ou sem docker: pulado."
fi

# ---------------------------------------------------------------- Worktrees (só relata)
titulo "Worktrees candidatas a remoção (somente relatório, nada é apagado)"
PASTAS="$TMPDIR_LIMPEZA/pastas.txt"
find "${RAIZES[@]}" -maxdepth 5 \( -name node_modules -o -name .git -o -name .cache -o -name .npm -o -name .orca -o -name .claude \) -prune \
  -o -type d \( -name .worktree -o -name .worktrees \) -print 2>/dev/null | sort -u >"$PASTAS" || true
CORTE_WT=$(($(date +%s) - DIAS_WORKTREE * 86400))
HA_GH=0
if command -v gh >/dev/null 2>&1; then HA_GH=1; fi
N_CAND=0
N_TOT=0
WT_BYTES=0
while IFS= read -r pasta; do
  for wt in "$pasta"/*/; do
    wt=${wt%/}
    # Só worktrees de verdade: a pasta principal de um repositório tem .git como diretório.
    [ -f "$wt/.git" ] || continue
    N_TOT=$((N_TOT + 1))
    branch=$(git -C "$wt" symbolic-ref --quiet --short HEAD 2>/dev/null || true)
    if [ -z "$branch" ]; then echo "ignorada (HEAD destacado): $wt"; continue; fi
    # Mudança pendente (inclui não rastreados) descarta a candidata.
    [ -z "$(git --no-optional-locks -C "$wt" status --porcelain 2>/dev/null)" ] || continue
    # Idade: o mais recente entre o último commit e o mtime da pasta.
    ts_c=$(git -C "$wt" log -1 --format=%ct 2>/dev/null || echo 0)
    ts_d=$(stat -c %Y "$wt")
    ts=$((ts_c > ts_d ? ts_c : ts_d))
    [ "$ts" -lt "$CORTE_WT" ] || continue
    # Mergeada: na branch padrão do repositório, ou PR mergeado/fechado (cobre squash).
    padrao=$(git -C "$wt" symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null || true)
    padrao=${padrao:-origin/main}
    motivo=""
    if git -C "$wt" merge-base --is-ancestor "$branch" "$padrao" 2>/dev/null; then
      motivo="branch mergeada em $padrao"
    elif [ "$HA_GH" = 1 ]; then
      estado=$(cd "$wt" && timeout 25 gh pr list --state all --head "$branch" --json state --jq '.[].state' 2>/dev/null | sort -u | tr '\n' ' ' || true)
      case "$estado" in
        *OPEN*) ;;
        *MERGED* | *CLOSED*) motivo="PR ${estado% }" ;;
      esac
    fi
    [ -n "$motivo" ] || continue
    T=$(tam "$wt")
    N_CAND=$((N_CAND + 1))
    WT_BYTES=$((WT_BYTES + T))
    echo "$(humano "$T")  $wt  [$branch; $motivo; $((($(date +%s) - ts) / 86400)) dias]"
  done
done <"$PASTAS"
echo "$N_CAND candidata(s) de $N_TOT worktree(s); ocupam $(humano "$WT_BYTES") (não entram no total)."
if [ "$HA_GH" != 1 ]; then echo "Aviso: gh ausente; merge por squash não é detectado."; fi
if [ "$N_CAND" -gt 0 ]; then echo "Remoção é decisão do dono: git worktree remove <caminho>."; fi

# ---------------------------------------------------------------- Resumo
titulo "Resumo"
if aplicando; then
  LIVRE_DEPOIS=$(disco_livre)
  echo "Liberado (soma medida por item, antes/depois): $(humano "$TOTAL")"
  echo "Liberado (variação de espaço livre em /; Docker, Go e npm ficam em /home): $(humano $((LIVRE_DEPOIS - LIVRE_ANTES)))"
else
  echo "DRY-RUN: liberaria cerca de $(humano "$TOTAL") (sem contar worktrees nem bancos)."
  if [ "$BLOQUEADO" -gt 0 ]; then echo "Fora do total, bloqueado por processo ativo: $(humano "$BLOQUEADO") (rode com as sessões paradas)."; fi
  echo "Para executar: $0 --apply"
fi
echo "Disco /: $(uso_disco)"
