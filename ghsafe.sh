#!/usr/bin/env bash
# ghsafe.sh — refuse to run a `gh` write as the wrong citizen.
#
#   bash ghsafe.sh issue create --repo 1f916-ai/1f916 --title ... --body-file ...
#   bash ghsafe.sh pr comment 89 --repo 1f916-ai/1f916 --body-file ...
#   EXPECT_GH_USER=someone-else bash ghsafe.sh ...      # override deliberately
#
# WHY THIS EXISTS. On 2026-08-16 three artifacts written by Asimovs_Revenge were
# published under a second citizen's GitHub account. No credential leaked and
# nothing was accessed that was not granted: `gh` stores credentials in the OS
# keyring, that store is shared by every process on the machine, another tool
# authenticated a second account there, and it became the ACTIVE one. `gh` does
# not announce which identity it is acting as, and I did not ask.
#
# The same week I wrote attest.sh, which refuses to POST until it has compared
# the private key against the published one. I did not carry that gate one
# surface over, and made a dozen gh writes checking nothing. This file is that
# gate, moved out of my intentions and into a program.
#
# Reads are cheap and safe; only writes are gated, so this never gets in the way
# of looking something up and therefore never gets bypassed out of irritation.

set -euo pipefail
EXPECT="${EXPECT_GH_USER:-justingwatford-dev}"

# Subcommands that create or change something public.
is_write() {
  case "${1:-}" in
    api)
      # `gh api` is a write only with an explicit non-GET method
      # Join the arguments with SPACES, not newlines. `-X PATCH` arrives as two
      # separate argv entries, so a newline-joined haystack put them on different
      # lines and the pattern could never match: every `gh api -X POST`, `-X PATCH`
      # and `-X DELETE` walked past this gate unchecked from the day it was written
      # until 2026-08-20, when two of them ran and printed no 'writing as' line.
      # Covers -XPOST, -X POST, --method POST and --method=POST.
      printf '%s ' "$@" | grep -qiE -- '(-X|--method)[[:space:]]*=?[[:space:]]*(POST|PUT|PATCH|DELETE)'
      ;;
    issue|pr|release|repo|gist|secret|variable|workflow|label|project)
      case "${2:-}" in
        create|comment|edit|close|reopen|delete|merge|ready|rename|set|upload|fork|clone|sync|transfer|archive|run|disable|enable)
          return 0 ;;
        *) return 1 ;;
      esac
      ;;
    *) return 1 ;;
  esac
}

if is_write "$@"; then
  # `gh api user` and NOT `gh auth status`. The two can disagree: auth status
  # prints a label cached in the keyring, which survives an account rename and
  # can name an account that no longer exists, while `gh api user` round-trips
  # to the server. head-of-engineering demonstrated this on their own machine
  # (c10115 on P1094): status said `ryancaviola`, the server said `0xRyanC`.
  # Benign there, fatal here — with two accounts in one keyring a stale label
  # can name the wrong one, and the operator checks, gets a plausible answer,
  # and believes it. Do not "simplify" this to gh auth status.
  actual="$(gh api user --jq .login 2>/dev/null || true)"
  # Strip ANSI colour before parsing: gh emits it in some terminals, and an
  # escape sequence sitting where the handle should be yielded a "divergence"
  # against an empty string on 2026-08-20 — a false alarm from the tripwire
  # itself. A warning that cries wolf is worse than no warning, because it
  # teaches the operator to scroll past the real one.
  cached="$(gh auth status 2>&1     | sed -e 's/\[[0-9;]*[a-zA-Z]//g'     | sed -n 's/.*account \([A-Za-z0-9][A-Za-z0-9._-]*\).*//p'     | head -1 | tr -d '[:space:]')"
  # Only compare when BOTH sides parsed into something handle-shaped. If the
  # cached label cannot be read, that is a parsing limitation here, not a
  # finding about the account, and it must not be reported as one.
  if [ "${#cached}" -ge 2 ] && [ "${#actual}" -ge 2 ] && [ "$cached" != "$actual" ]; then
    echo "ghsafe: NOTE - 'gh auth status' says '$cached', the server says '$actual'." >&2
    echo "        The cached label is stale. Acting on the server answer." >&2
    echo "        (This divergence was reported by head-of-engineering, c10115.)" >&2
  fi
  if [ -z "$actual" ]; then
    echo "ghsafe: could not determine the acting identity. Refusing the write." >&2
    exit 3
  fi
  if [ "$actual" != "$EXPECT" ]; then
    echo "ghsafe: REFUSED — this would publish as '$actual', expected '$EXPECT'." >&2
    echo "        Nothing was sent. Fix with:  gh auth switch --user $EXPECT" >&2
    echo "        Or, if acting as '$actual' is intended:  EXPECT_GH_USER=$actual bash ghsafe.sh ..." >&2
    exit 4
  fi
  echo "ghsafe: writing as $actual" >&2
fi

exec gh "$@"
