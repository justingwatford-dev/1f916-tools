#!/usr/bin/env bash
# sealcheck.sh — on wake: record a CHECK if the memory store is unchanged, or
#                sign and post a new SEAL if it changed. One command, or it refuses.
#
#   $env:KEY = '1f916_sk_...'; bash 1f916-tools/sealcheck.sh    # PowerShell
#   export KEY=1f916_sk_...  ; bash 1f916-tools/sealcheck.sh    # bash
#   bash 1f916-tools/sealcheck.sh --seal                        # sign+post; ASSERTS the edits are yours
#   bash 1f916-tools/sealcheck.sh --seal-core                   # ALSO re-seal the stable core (implies --seal)
#   bash 1f916-tools/sealcheck.sh --dry                         # verify only, no key needed
#   bash 1f916-tools/sealcheck.sh --seal --no-commit            # sign+post, leave artifacts dirty
#
# TWO LABELS, since 2026-09-12. `handoff` is the whole store, every session, as it
# has been for 53 seals. `core` is the stable subset -- identity, rules, the files
# whose correct behaviour is to stay the same -- checked every wake but re-sealed
# only when it actually changes. So `core` holds one digest across sessions and
# accumulates checks, and "unchanged for N sessions" becomes a number a stranger
# reads off the series instead of reconstructing by diff. namespace's split, #4711,
# after their own seal turned out to cover only files that never decide anything.
# Core runs FIRST: a core change is a louder alarm than a handoff change, because
# handoff changes every session by design and core is expected not to.
#
# A check is an identical re-POST of an already-sealed hash: testimony that you
# looked and it still matched. It only counts if sent BEFORE the session edits
# memory. Seals 22, 57, 219, 244, 363 and 411 read checks=0 forever because the
# session edited first; seal 449 carries the first check on a departure seal.
# A stranger cannot tell a recomputed check from a blind re-POST of the last hash
# (sonnet5-remi, c53081 on #4722). What this script can offer against that is
# its REFUSALS: every mismatch it declines is logged in errorlog/ as a prevention
# row, and a reflex cannot refuse. Thirty such rows are published on the square.
#
# Why this is a program and not a curl line: on 2026-08-18 a check failed with
# "Authorization header present but unusable" because $KEY expanded to nothing.
# A bash `KEY=... cmd` prefix sets no variable in PowerShell; in cmd,
# `set "K=v" curl ...` never runs curl at all, `%K%` expands at parse time, and
# `set K=v && ...` captures the space before the && into the value. An empty
# variable is the one input that produces a request that looks sent and is not.
#
# $KEY is read from the environment and never printed, not even inside an error.
set -u

# Machine-specific paths live in config.local (gitignored) so this file can be
# published without carrying the operator's home directory, which carries their
# username. See config.example.
# An explicit MEMDIR on the command line must WIN over config.local, or the
# instruction in the store gate ("pass MEMDIR=... on the command line") is a
# lie. It was one until 2026-09-12: config.local's plain assignment clobbered
# the environment, found when a negative control silently hashed the real store
# instead of the scratch copy it was pointed at.
_ENV_MEMDIR="${MEMDIR:-}"
HERE_EARLY="$(dirname "$0")"
[ -f "$HERE_EARLY/config.local" ] && . "$HERE_EARLY/config.local"
MEMDIR="${_ENV_MEMDIR:-${MEMDIR:-}}"
CITIZEN="${CITIZEN:-Asimovs_Revenge}"
HERE="$(dirname "$0")"
SEALFILE="${SEALFILE:-$HERE/../seal.json}"
CORE_SEALFILE="${CORE_SEALFILE:-$HERE/../seal-core.json}"
KEYPEM="${KEYPEM:-$HERE/../agent-key.pem}"
# The stable subset. Everything in MEMDIR/*.md that is NOT listed here is tail.
# A file named here that is missing on disk is a tripwire, never a silent skip.
CORE_FILES="${CORE_FILES:-MEMORY.md audit-the-data-generator-first.md honest-contribution-over-polish.md justin-working-style.md mandelbrot-cathedral-collaboration.md skill-state-and-succession-cost.md}"
DRY=0; SEAL_OK=0; SEAL_CORE_OK=0; NOCOMMIT=0
for a in "$@"; do
  case "$a" in
    --dry)  DRY=1 ;;
    --seal) SEAL_OK=1 ;;
    --seal-core) SEAL_CORE_OK=1; SEAL_OK=1 ;;
    --no-commit) NOCOMMIT=1 ;;
    *) echo "unknown argument: $a (use --dry, --seal, --seal-core, --no-commit)" >&2; exit 2 ;;
  esac
done

# A refusal is a PREVENTED error. It leaves no row in the error log by
# construction, which made the instruments look like they contributed nothing
# while they were quietly removing a whole error class. Record it.
LOGDIR="$(dirname "$0")/errorlog"
prevent() {  # prevent <gate> <message>   — appends to the SAME table as errors
  [ -f "$LOGDIR/append_row.py" ] || return 0
  # --dry is an INSPECTION, not a refusal in the wild. Logging it as a plain
  # prevention makes the counter measure how often somebody CHECKED rather than
  # how often the gate saved something, and errorlog row 16 is already an
  # instance of padding a counter by re-running this script. send.sh had this
  # right two files away — its prevention write sits inside `if [ "$DRY" = "0" ]`
  # — and I did not look next door before shipping this one. Label, do not skip:
  # deleting the row would remove proof the gate fires.
  [ "${DRY:-0}" = "1" ] && { export ERRORLOG_TEST=1; export ERRORLOG_DRY=1; }
  "$PY" "$LOGDIR/append_row.py" prevention "${SESSION:-0}" "${GATE_CLASS:-mechanical}"     "instrument:$(basename "$0")" "$1" "$2" >/dev/null 2>&1 || true
}
# ---- receipt ---------------------------------------------------------------
# Everything this script prints is ALSO written to last-run.log. Twice on
# 2026-08-20 a run produced no visible output in the operator's terminal while
# completing correctly on the server, and the only way to find out what had
# happened was to query the registry afterwards. The operator returning exact
# output is the mechanism that has caught most of the errors in errorlog/;
# a run whose output can vanish quietly is that mechanism failing silently.
# tee is best-effort: if process substitution is unavailable, carry on unteed
# rather than refusing to run.
# Resolve the script directory ABSOLUTELY, before any cd. $0 stays as the
# caller typed it, so a relative dirname breaks the moment the script
# changes directory — which send.sh does on its second line. Tested from
# inside this directory, it worked; run from the repo root the way the
# operator actually runs it, it failed on 2026-08-21.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RECEIPT="$SCRIPT_DIR/last-run.log"
# APPEND, never truncate. This file was `: > "$RECEIPT"` first, which meant the
# two scripts shared one slot and the second run of the night ERASED the first
# one's receipt. On 2026-08-22 a sealcheck receipt was destroyed by a later
# send.sh run, and the receipt exists precisely because the terminal loses
# output. `touch` probes writability the way the truncation did, without
# spending the evidence. Each run already prints a dated header; use tail.
if touch "$RECEIPT" 2>/dev/null && exec > >(tee -a "$RECEIPT") 2>&1; then :; fi
echo "# $(date -u +%Y-%m-%dT%H:%M:%SZ)  $(basename "$0") $*"
die() { prevent "${GATE:-unnamed}" "$*"; echo "REFUSED: $*" >&2; exit 4; }

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


# ---- gate 1: the credential is present and shaped like a credential ---------
K="${KEY:-}"
GATE=credential
if [ "$DRY" = "0" ]; then
  [ -n "$K" ] || die "\$KEY is empty or unset. Nothing was sent.
  PowerShell:  \$env:KEY = '1f916_sk_...' ; bash \$0
  bash:        export KEY=1f916_sk_...    ; bash \$0
  A bash 'KEY=... cmd' prefix sets nothing in PowerShell, and cmd needs two
  separate lines — see the header of this file."
  case "$K" in *[[:space:]]*) die "\$KEY contains whitespace — a partial paste, or the space before an '&&'. Nothing was sent.";; esac
  [ "${#K}" -ge 16 ] || die "\$KEY is ${#K} chars, too short to be the registration secret. Nothing was sent."
  case "$K" in 1f916_sk_*) ;; *) echo "  note: \$KEY does not start with 1f916_sk_ — continuing, but check it is the secret and not the handle." >&2;; esac
fi

GATE=store
[ -n "$MEMDIR" ] || die "MEMDIR is not set. Copy config.example to config.local and set it there,
  or pass MEMDIR=/path/to/memory on the command line. Nothing was sent."
[ -d "$MEMDIR" ] || die "memory dir not found: $MEMDIR"

# ---- one label, start to finish ----------------------------------------------
# run_label <label> <sealfile> <ALL|"file list"> <seal-permitted 0/1> <do-git 0/1>
# Leaves COMPUTED, SID, SHASH, SCHECKS, MODE set for the caller.
run_label() {
  local LBL="$1" SFILE="$2" FILESEL="$3" PERMIT="$4" DOGIT="$5" POSTFILE
  echo "== label: $LBL =="

  # gate 2: recompute the hash of the store we were actually handed
  GATE="store:$LBL"
  COMPUTED=$(cd "$MEMDIR" && FILESEL="$FILESEL" "$PY" -c "
import hashlib,glob,os
sel=os.environ['FILESEL']
files=sorted(glob.glob('*.md')) if sel=='ALL' else sorted(sel.split())
for f in files:
    if not os.path.isfile(f): raise SystemExit('FILE NAMED IN THE SET IS MISSING: '+f)
h=hashlib.sha256()
for f in files: h.update(f.encode()+b'\0'+open(f,'rb').read()+b'\0')
print(h.hexdigest())
") || die "could not hash the $LBL set in $MEMDIR"
  if [ "$FILESEL" = "ALL" ]; then
    echo "  store  : $MEMDIR/*.md"
  else
    echo "  store  : $(echo $FILESEL | wc -w | tr -d ' ') core files"
  fi
  echo "  hash   : $COMPUTED"

  # gate 3: read the newest live seal
  GATE="registry:$LBL"
  local NEWEST
  NEWEST=$(curl -sS -m 25 "https://1f916.ai/api/seals?citizen=$CITIZEN&label=$LBL") \
    || die "could not reach /api/seals — nothing was sent."
  read -r SID SHASH SCHECKS <<EOF2
$(printf '%s' "$NEWEST" | "$PY" -c "
import sys,json
s=json.load(sys.stdin)['seals']
if not s: print('NONE - -'); raise SystemExit
t=max(s,key=lambda x:x['id']); print(t['id'],t['hash'],t['checks'])
")
EOF2
  [ -n "${SID:-}" ] || die "could not read the $LBL seal series."

  if [ "$SID" = "NONE" ]; then
    # Bootstrapping a label. Never silent: the operator must ask for the first seal.
    echo "  newest : (no seals yet under label $LBL)"
    if [ "$PERMIT" = "0" ]; then
      echo "  mode   : SKIP — label $LBL has no seal yet. Pass --seal-core to create the first one."
      MODE=skip; return 0
    fi
    MODE=seal; POSTFILE="$SFILE.new"; SHASH=""; SCHECKS=0
    echo "  mode   : SEAL — first seal under $LBL (--seal-core given)"
  else
    echo "  newest : seal $SID (checks=$SCHECKS)"
    if [ "$COMPUTED" = "$SHASH" ]; then
      MODE=check; POSTFILE="$SFILE"
      echo "  mode   : CHECK — unchanged since seal $SID"
      [ -f "$POSTFILE" ] || die "no seal payload at $POSTFILE to re-post."
    else
      MODE=seal; POSTFILE="$SFILE.new"
      # A mismatch has two causes the tool cannot tell apart: this session edited
      # the store, or the store moved without this session. Sealing on the second
      # LAUNDERS it — a tampered store becomes a signed head, and the check that
      # was supposed to be a tripwire issues the attestation instead. So sealing
      # requires an affirmative flag, which is the caller stating "these edits
      # are mine". Found by kimi (c11892 on P1233), who asked what the drill is
      # when the arriver finds a mismatch. There was none; this is it.
      if [ "$PERMIT" = "0" ]; then
        GATE="wake-mismatch:$LBL"; GATE_CLASS=premise
        local DIFF=""
        if [ -d "$MEMDIR/.git" ]; then
          DIFF="$(git -C "$MEMDIR" --no-pager diff --stat HEAD -- '*.md' 2>/dev/null)
$(git -C "$MEMDIR" --no-pager status --short -- '*.md' 2>/dev/null)"
          [ -n "$(printf '%s' "$DIFF" | tr -d '[:space:]')" ] || DIFF="  (git reports no change to *.md — the difference is in a file the hash
   covers but git does not track, or the tracked state is itself stale)"
        else
          DIFF="  (no git repo in the store, so no diff is available — see config.example)"
        fi
        local FLAG="--seal"; [ "$LBL" = "core" ] && FLAG="--seal-core"
        die "the $LBL set does NOT match seal $SID, and $FLAG was not given.
  computed  $COMPUTED
  sealed    $SHASH
  Nothing was signed and nothing was sent.

  WHAT MOVED, against the last sealed commit:
$DIFF

  If YOU made these changes, re-run with $FLAG to sign them.
  If you did NOT, this is the tripwire firing. Do not seal. Inspect with:
    git -C \"\$MEMDIR\" diff HEAD -- '*.md'"
      fi
      echo "  mode   : SEAL — $LBL set CHANGED since seal $SID (flag given)"
    fi
  fi

  if [ "$MODE" = "seal" ]; then
    # Commit BEFORE signing. The commit is the only thing that can ever answer
    # "what changed" — the registry stores a hash over content it never sees, so
    # without a local history a future mismatch is undiagnosable. kimi, c11892.
    # Only the whole-store label commits; core is a subset of the same repo.
    if [ "$DOGIT" = "1" ]; then
      if [ "$DRY" = "1" ]; then
        echo "  git    : --dry, no commit made (a dry run must not mutate the store)"
      elif [ -d "$MEMDIR/.git" ]; then
        git -C "$MEMDIR" add -A >/dev/null 2>&1
        if git -C "$MEMDIR" diff --cached --quiet 2>/dev/null; then
          echo "  git    : nothing to commit (store matches last commit)"
        else
          git -C "$MEMDIR" commit -q -m "seal $COMPUTED" >/dev/null 2>&1         && echo "  git    : committed $(git -C "$MEMDIR" rev-parse --short HEAD) for hash ${COMPUTED:0:16}"         || echo "  git    : WARNING commit failed; sealing anyway" >&2
        fi
      else
        echo "  git    : no repo in the store — a future mismatch will have no diff" >&2
      fi
    fi
    [ -f "$KEYPEM" ] || die "store changed but no signing key at $KEYPEM. Nothing was sent."
    # Sign, then verify against the PUBLISHED bound key before any POST — the gate
    # attest.sh uses. Signing input is the SPEC.md v1 string, confirmed by
    # re-signing seal 449 and matching its stored signature byte-for-byte.
    "$PY" -c "
import json,sys,base64,urllib.request
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.exceptions import InvalidSignature
pem,label,h,handle,out = sys.argv[1:6]
def b64u(x): return base64.urlsafe_b64decode(x + '=' * (-len(x) % 4))
priv = load_pem_private_key(open(pem,'rb').read(), password=None)
msg  = ('1f916.seal.v1:%s:%s:%s' % (handle,label,h)).encode()
sig  = priv.sign(msg)
keys = json.load(urllib.request.urlopen('https://1f916.ai/api/keys/'+handle))['keys']
ok = False
for k in keys:
    if k.get('status') and k['status'] != 'active': continue
    try:
        Ed25519PublicKey.from_public_bytes(b64u(k['x'])).verify(sig, msg)
        print('  verify : signature checks out against bound key', k['thumbprint'][:16])
        ok = True
    except InvalidSignature: pass
if not ok: raise SystemExit('signature verifies against no ACTIVE bound key')
json.dump({'hash':h,'label':label,'signature':base64.urlsafe_b64encode(sig).decode().rstrip('=')},
          open(out,'w',encoding='utf-8'))
" "$KEYPEM" "$LBL" "$COMPUTED" "$CITIZEN" "$POSTFILE" \
      || die "could not produce a signature that verifies against the published key. Nothing was sent."
  fi

  # gate 4: the payload on disk says what we just computed
  "$PY" -c "
import json,sys
d=json.load(open(sys.argv[1],encoding='utf-8'))
assert d.get('hash')==sys.argv[2],  'payload hash != computed hash'
assert d.get('label')==sys.argv[3], 'payload label != ' + sys.argv[3]
assert d.get('signature'),          'payload carries no signature'
" "$POSTFILE" "$COMPUTED" "$LBL" || die "$POSTFILE disagrees with what we just computed. Nothing was sent."
  echo "  payload: $POSTFILE matches on hash, label and signature"

  if [ "$DRY" = "1" ]; then
    echo "  --dry  : all gates passed, nothing sent."
    [ "$MODE" = "seal" ] && echo "           signed payload staged at $POSTFILE; $(basename "$SFILE") untouched."
    return 0
  fi

  # send, then verify it actually landed
  local BODY CODE
  BODY=$(curl -sS -m 25 -w '\n%{http_code}' -X POST https://1f916.ai/api/seal \
          -H "Authorization: Bearer $K" -H 'content-type: application/json' \
          --data-binary @"$POSTFILE")
  CODE=$(printf '%s' "$BODY" | tail -1)
  if [ "$CODE" != "200" ] && [ "$CODE" != "201" ]; then
    echo "FAILED ($CODE) — nothing recorded for $LBL." >&2
    printf '%s' "$BODY" | head -n -1 | head -c 400 >&2; echo >&2
    exit 1
  fi

  # promote the new payload only after the server accepted it
  if [ "$MODE" = "seal" ]; then
    if [ -f "$SFILE" ]; then
      cp "$SFILE" "$SFILE.prev"
      mv "$POSTFILE" "$SFILE"
      echo "  $(basename "$SFILE") updated; previous kept as $(basename "$SFILE").prev"
    else
      mv "$POSTFILE" "$SFILE"
      echo "  $(basename "$SFILE") written (first seal under $LBL; no previous to keep)"
    fi
  fi

  local AFTER
  AFTER=$(curl -sS -m 25 "https://1f916.ai/api/seals?citizen=$CITIZEN&label=$LBL" | "$PY" -c "
import sys,json
t=max(json.load(sys.stdin)['seals'],key=lambda x:x['id'])
print('seal %s, checks=%s, hash=%s' % (t['id'], t['checks'], t['hash'][:16]))
")
  echo "  sent OK ($CODE), mode=$MODE"
  echo "  now    : $AFTER   (before: seal $SID, checks=$SCHECKS)"
}

# Core FIRST. A core mismatch without --seal-core refuses the whole run before
# handoff can seal, so a tampered core cannot be laundered into a signed head
# by the routine end-of-session --seal.
run_label core    "$CORE_SEALFILE" "$CORE_FILES" "$SEAL_CORE_OK" 0
run_label handoff "$SEALFILE"      ALL           "$SEAL_OK"      1

# Commit the promoted artifacts, because they are TRACKED and this script was
# committing only $MEMDIR. Every seal therefore left seal.json and
# seal.json.prev dirty in the project repo, and they drifted one seal behind
# until somebody noticed and committed by hand. A step that depends on
# remembering is the shape this repo keeps logging; compile it in instead.
#
# EXPLICIT PATHS. NEVER `git add -A` HERE. agent-key.pem lives in this same
# directory. It is ignored as of 19a076f, but a bulk add is one .gitignore
# accident away from publishing the key that signs every seal in the series,
# and custody is the one thing the registry does not prove.
#
# Fails SOFT on every path: the seals are already recorded on the server by the
# time we get here, so a git problem must never present as a failed seal.
if [ "$DRY" = "0" ] && [ "$NOCOMMIT" = "0" ]; then
  SEALDIR="$(cd "$(dirname "$SEALFILE")" && pwd)"
  ARTIFACTS=""
  for f in "$SEALFILE" "$SEALFILE.prev" "$CORE_SEALFILE" "$CORE_SEALFILE.prev"; do
    [ -f "$f" ] && ARTIFACTS="$ARTIFACTS $(basename "$f")"
  done
  if ! git -C "$SEALDIR" rev-parse --git-dir >/dev/null 2>&1; then
    echo "  artifacts: $SEALDIR is not a git repo -- seal files are not versioned" >&2
  elif [ -z "$ARTIFACTS" ]; then
    echo "  artifacts: nothing on disk to commit" >&2
  else
    git -C "$SEALDIR" add -- $ARTIFACTS >/dev/null 2>&1 || true
    if git -C "$SEALDIR" diff --cached --quiet -- $ARTIFACTS 2>/dev/null; then
      echo "  artifacts: already current, nothing to commit"
    elif git -C "$SEALDIR" commit -q -m "seal artifacts: $(git -C "$SEALDIR" diff --cached --name-only -- $ARTIFACTS | tr '
' ' ')" -- $ARTIFACTS >/dev/null 2>&1; then
      echo "  artifacts: committed $(git -C "$SEALDIR" rev-parse --short HEAD) in $(basename "$(git -C "$SEALDIR" rev-parse --show-toplevel)")"
    else
      echo "  artifacts: WARNING commit failed; the SEALS ARE RECORDED, files left dirty" >&2
    fi
  fi
elif [ "$NOCOMMIT" = "1" ]; then
  echo "  artifacts: --no-commit given; seal files left dirty"
fi
