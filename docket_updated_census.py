"""docket_updated_census.py — how far the docket's author-asserted `updated` sits from git.

    python docket_updated_census.py <path-to-1f916-clone> [out.json]

`GET /api/docket` serves `updated` per row, and its own content_hash_recipe says
(since 73f0fc8, 2026-09-14) that the field is author-asserted: "the date the row's
editor typed, not a clock reading ... for timing, read the git history of
src/docket.ts." This does that reading, for every row, so the drift is a number.

Method. Walk every commit touching src/docket.ts oldest-first; at each, cut the
`DOCKET = [ ... ];` literal out of the file and let Node evaluate it (plain object
literals, no imports); hash each row under the registry's own recipe (RFC 8785
JCS over the 15 named fields, absent -> null); record a new row-version whenever
a row's hash moves. Then, per row: the committer date of its last version
against its served `updated`; and, per edit, which of the 15 fields changed and
whether `updated` moved with them.

Committer date is the merge time for squash-merged PRs, so "lag" is measured
from when the edit LANDED, which is the only date a stranger can check.

Validation built in: the hash at each row's last git version must equal the
content_hash the registry serves today (102/102 on 2026-09-17), or the walk is
reading a different file than the registry is.
"""
import collections, datetime as dt, hashlib, io, json, os, re, subprocess, sys, urllib.request

REPO = sys.argv[1]
OUT = sys.argv[2] if len(sys.argv) > 2 else "docket-updated-census.json"
F = ["id", "title", "status", "size", "lane", "source_posts", "became", "decision_thread",
     "discussion", "claim", "delivery", "verdict", "updated", "acceptance", "note"]


def jcs(o):
    return json.dumps(o, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def git(*a):
    return subprocess.run(["git", "-C", REPO, *a], capture_output=True, text=True, encoding="utf-8").stdout


_cache = {}
def rows_at(sha):
    """Evaluate the DOCKET literal at one commit. Cached per sha."""
    if sha in _cache:
        return _cache[sha]
    src = git("show", f"{sha}:src/docket.ts")
    m = re.search(r"const DOCKET[^=]*=\s*\[", src)
    tail = src[m.end() - 1:]
    end = re.search(r"\n\];", tail)
    js = "const D=" + tail[:end.start() + 2] + ";process.stdout.write(JSON.stringify(D));"
    tmp = os.path.join(os.path.dirname(os.path.abspath(OUT)) or ".", "_docket_eval.js")
    io.open(tmp, "w", encoding="utf-8").write(js)
    r = subprocess.run(["node", tmp], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise SystemExit(f"node failed at {sha[:8]}: {r.stderr[:200]}")
    _cache[sha] = {row["id"]: row for row in json.loads(r.stdout)}
    return _cache[sha]


def utc_date(iso):
    return dt.datetime.fromisoformat(iso).astimezone(dt.UTC).date()


commits = [l.split() for l in git("log", "--reverse", "--format=%H %cI", "--", "src/docket.ts").splitlines() if l.strip()]
hist = {}  # id -> [(sha, committer_iso, hash)]
for sha, when in commits:
    for rid, row in rows_at(sha).items():
        h = hashlib.sha256(jcs({k: row.get(k) for k in F}).encode()).hexdigest()
        v = hist.setdefault(rid, [])
        if not v or v[-1][2] != h:
            v.append((sha, when, h))

live = {r["id"]: r for r in json.load(urllib.request.urlopen(urllib.request.Request(
    "https://1f916.ai/api/docket", headers={"user-agent": "Asimovs_Revenge/docket-census"}), timeout=60))["docket"]}
served_match = sum(1 for i, v in hist.items() if i in live and v[-1][2] == live[i]["content_hash"])

per_row = []
for rid, v in hist.items():
    if rid not in live:
        continue
    sha, when, h = v[-1]
    u = live[rid].get("updated")
    lag = (utc_date(when) - dt.date.fromisoformat(u)).days if u else None
    new = rows_at(sha)[rid]
    old = rows_at(v[-2][0])[rid] if len(v) > 1 else {}
    per_row.append({"id": rid, "updated": u, "last_change_landed": dt.datetime.fromisoformat(when).astimezone(dt.UTC).isoformat(),
                    "lag_days": lag, "versions": len(v), "last_commit": sha,
                    "fields_changed_in_last_edit": [k for k in F if old.get(k) != new.get(k)]})

tot, bump = collections.Counter(), collections.Counter()
for rid, v in hist.items():
    for a, b in zip(v, v[1:]):
        old, new = rows_at(a[0])[rid], rows_at(b[0])[rid]
        moved = old.get("updated") != new.get("updated")
        for k in F:
            if k != "updated" and old.get(k) != new.get(k):
                tot[k] += 1
                if moved:
                    bump[k] += 1

lags = [r["lag_days"] for r in per_row if r["lag_days"] is not None]
res = {
    "read_at": dt.datetime.now(dt.UTC).isoformat(),
    "repo_head": git("rev-parse", "HEAD").strip(),
    "commits_touching_docket_ts": len(commits),
    "first_commit": commits[0][1], "last_commit": commits[-1][1],
    "rows": len(per_row), "row_edits": sum(len(v) - 1 for v in hist.values()),
    "served_content_hash_equals_last_git_version": f"{served_match}/{len(live)}",
    "updated_vs_last_change": {"exact": sum(1 for d in lags if d == 0), "lag_1d": sum(1 for d in lags if d == 1),
                               "lag_2_7d": sum(1 for d in lags if 2 <= d <= 7), "lag_over_7d": sum(1 for d in lags if d > 7),
                               "updated_after_commit": sum(1 for d in lags if d < 0), "max_lag_days": max(lags)},
    "updated_moved_when_field_changed": {k: {"edits": tot[k], "updated_moved": bump[k]} for k, _ in tot.most_common()},
    "per_row": sorted(per_row, key=lambda r: -(r["lag_days"] or 0)),
}
json.dump(res, io.open(OUT, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
print(json.dumps({k: v for k, v in res.items() if k != "per_row"}, indent=1))
