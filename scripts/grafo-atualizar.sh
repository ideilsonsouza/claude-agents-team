#!/usr/bin/env bash
# Atualiza o grafo central do graphify (só código, sem LLM) quando a main avançou.
# Uso: grafo-atualizar.sh [<cwd>]
# Só age em projetos que já têm ~/.claude/graphs/<slug>/ (piloto). Nunca usa `graphify update <path>`
# nem `graphify hook install`. Slug calculado como em ~/.claude/hooks/team_base.py.
set -u
cwd="${1:-$PWD}"

common=$(git -C "$cwd" rev-parse --path-format=absolute --git-common-dir 2>/dev/null) || exit 0
raiz=$(dirname "$common")
nome=$(basename "$raiz" | tr 'A-Z' 'a-z' | sed -E 's/[^a-z0-9]+/-/g; s/^-+|-+$//g')
[ -n "$nome" ] || nome=projeto
slug="$nome-$(printf %s "$raiz" | sha1sum | cut -c1-6)"
dest="$HOME/.claude/graphs/$slug"
[ -d "$dest" ] || exit 0   # projeto fora do piloto

log="$dest/update.log"
msg() { printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >>"$log"; }
aparar() { [ -f "$log" ] && tail -n 200 "$log" >"$log.tmp" && mv "$log.tmp" "$log"; }
trap aparar EXIT

exec 9>"$dest/.lock"
flock -n 9 || { msg "Outra atualização em andamento; saindo."; exit 0; }

atual=$(git -C "$raiz" rev-parse HEAD 2>/dev/null) || { msg "Não consegui ler o HEAD de $raiz."; exit 0; }
gravado=$(cat "$dest/.main_commit" 2>/dev/null || true)
if [ "$atual" = "$gravado" ]; then
  msg "Grafo já está na main (${atual:0:9}); nada a fazer."
  exit 0
fi

msg "Main mudou (${gravado:0:9} -> ${atual:0:9}); atualizando o grafo."
cd "$dest" || exit 0
inicio=$SECONDS
if timeout 60 graphify extract "$raiz" --code-only --out "$dest" --no-viz >>"$log" 2>&1 \
   && timeout 60 graphify cluster-only "$dest" --no-label --no-viz >>"$log" 2>&1; then
  printf '%s\n' "$atual" >"$dest/.main_commit"
  msg "Grafo atualizado em $((SECONDS - inicio))s."
else
  msg "Falha ou timeout (60s) ao atualizar o grafo; .main_commit não alterado."
fi
exit 0
