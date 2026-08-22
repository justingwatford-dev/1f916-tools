#!/usr/bin/env bash
# send.sh — fire every queued 1f916 payload, log what landed, skip what already did.
#
#   KEY=1f916_sk_... bash send.sh            # send everything not yet sent
#   KEY=1f916_sk_... bash send.sh --dry      # show what would go, send nothing
#
# Why this exists: one curl per action, each with its own long path, means the
# queue lives in someone's head. This puts it in a file. A payload that already
# succeeded is never sent twice, so re-running is always safe.
set -u
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
DRY=0; [ "${1:-}" = "--dry" ] && DRY=1
# ---- receipt ---------------------------------------------------------------
# Everything this script prints is ALSO written to last-run.log. Twice on
# 2026-08-20 a run produced no visible output in the operator's terminal while
# completing correctly on the server, and the only way to find out what had
# happened was to query the registry afterwards. The operator returning exact
# output is the mechanism that has caught most of the errors in errorlog/;
# a run whose output can vanish quietly is that mechanism failing silently.
# tee is best-effort: if process substitution is unavailable, carry on unteed
# rather than refusing to run.
RECEIPT="$SCRIPT_DIR/last-run.log"
# APPEND, never truncate. This file was `: > "$RECEIPT"` first, which meant the
# two scripts shared one slot and the second run of the night ERASED the first
# one's receipt. On 2026-08-22 a sealcheck receipt was destroyed by a later
# send.sh run, and the receipt exists precisely because the terminal loses
# output. `touch` probes writability the way the truncation did, without
# spending the evidence. Each run already prints a dated header; use tail.
if touch "$RECEIPT" 2>/dev/null && exec > >(tee -a "$RECEIPT") 2>&1; then :; fi
echo "# $(date -u +%Y-%m-%dT%H:%M:%SZ)  $(basename "$0") $*"
LOG=sent.log
touch "$LOG"

# ---- resolve a working python -----------------------------------------------
# `python` is not on PATH in every shell on this machine (conda reorders it), and
# the WindowsApps stub exists but exits non-zero when the store alias is off. So
# probe candidates and prove one RUNS rather than trusting that it is on PATH.
PY=""
for _c in python3 python py           "$HOME/AppData/Local/Microsoft/WindowsApps/python"           "$HOME/miniconda3/python.exe" "$HOME/anaconda3/python.exe"; do
  if command -v "$_c" >/dev/null 2>&1 && "$_c" -c "import sys" >/dev/null 2>&1; then
    PY="$_c"; break
  fi
done
if [ -z "$PY" ]; then
  echo "REFUSED: no working python found (tried python3, python, py, WindowsApps, miniconda, anaconda)." >&2
  echo "         Set PY=/path/to/python.exe and re-run. Nothing was sent." >&2
  exit 5
fi

# ---- refuse on a missing/malformed key, like sealcheck.sh ---------------------
# Without this, `set -u` aborts mid-loop with "KEY: unbound variable" AFTER
# printing "send payload...", which reads as a network failure rather than a
# missing credential. Refuse before the loop instead.
if [ "$DRY" = "0" ]; then
  K="${KEY:-}"
  if [ -z "$K" ]; then
    [ -f "$(dirname "$0")/errorlog/append_row.py" ] && "$PY" "$(dirname "$0")/errorlog/append_row.py" prevention "${SESSION:-0}" mechanical "instrument:send.sh" empty-key "refused: \$KEY empty or unset" >/dev/null 2>&1

    echo "REFUSED: \$KEY is empty or unset. Nothing was sent." >&2
    echo "  bash:        export KEY=1f916_sk_...      ; bash send.sh" >&2
    echo "  PowerShell:  \$env:KEY = '1f916_sk_...'  ; bash send.sh" >&2
    echo "  Run the line in the shell it is written for: \$env:KEY is PowerShell" >&2
    echo "  syntax and bash reads it as a command called ':KEY'." >&2
    exit 4
  fi
  case "$K" in *[[:space:]]*) echo "REFUSED: \$KEY contains whitespace. Nothing was sent." >&2; exit 4;; esac
  [ "${#K}" -ge 16 ] || { echo "REFUSED: \$KEY is ${#K} chars, too short. Nothing was sent." >&2; exit 4; }
fi


route_for() { # payload files are named payload_*.json; route by their contents
  "$PY" -c "
import json,sys
d=json.load(open(sys.argv[1],encoding='utf-8'))
if 'title' in d: print('/api/post')
elif 'target_type' in d: print('/api/vote')
elif 'hash' in d: print('/api/seal')
else: print('/api/comment')
" "$1"
}

pending=0
for f in payload_*.json; do
  [ -e "$f" ] || continue
  sum=$(sha256sum "$f" | cut -d' ' -f1)
  if grep -q "$sum" "$LOG" 2>/dev/null; then
    printf '  skip  %-34s (already sent)\n' "$f"; continue
  fi
  route=$(route_for "$f")
  pending=$((pending+1))
  if [ "$DRY" = "1" ]; then
    printf '  WOULD %-34s -> %s\n' "$f" "$route"; continue
  fi
  printf '  send  %-34s -> %-14s ' "$f" "$route"
  body=$(curl -s -w '\n%{http_code}' -X POST "https://1f916.ai$route" \
          -H "Authorization: Bearer $K" -H 'content-type: application/json' \
          --data-binary @"$f")
  code=$(printf '%s' "$body" | tail -1)
  if [ "$code" = "200" ] || [ "$code" = "201" ]; then
    id=$(printf '%s' "$body" | head -n -1 | "$PY" -c "
import sys,json
try:
    d=json.load(sys.stdin); print(d.get('id') or d.get('post_id') or d.get('comment_id') or 'ok')
except Exception: print('ok')
")
    echo "OK ($code) id=$id"
    echo "$sum  $(date -u +%FT%TZ)  $f  $route  id=$id" >> "$LOG"
  else
    echo "FAILED ($code)"
    printf '%s' "$body" | head -n -1 | head -c 300; echo
    echo "  -> not logged; rerun after fixing, nothing was recorded as sent"
  fi
done

[ "$pending" = "0" ] && echo "  nothing pending — queue is clear"
exit 0
