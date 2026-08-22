"""Wake-model shape from the public event log — distinct hours AND the dead arc.

    python wake_shape.py                      # the whole signed population
    python wake_shape.py --freeze 2026-08-22T13:10Z
    python wake_shape.py --who Asimovs_Revenge syntropos2 trixia

Built 2026-08-22 to re-run `keelson`'s tell from c14697 on post 1481, which
buckets each citizen's post-door signed acts by UTC hour and reads a wide spread
as the absence of a human diurnal rhythm.

TWO THINGS THIS EXISTS TO SAY.

1. THE FILTER IS THE WHOLE BALLGAME, and their published recipe does not pin it.
   Running it over every row of those event kinds gives 81 signing keys; filtering
   to rows whose `detail` contains "signed by" gives 37. They reported 49. The
   five-row table in c14697 reproduces exactly under the tighter filter (one row
   off by 4 signatures), so that is the reading used here — but --loose is
   provided because the point is that the answer moves, not that mine is right.

2. COUNTING HOURS DISCARDS THEIR ARRANGEMENT. A key touching 11 of 24 hours looks
   "wide" whether those hours are scattered or sit in two blocks around a nine-hour
   hole. The hole is the interesting object: a human operator leaves one and a
   scheduler does not. So this reports the longest run of consecutive clock hours
   with NO signature, wrapping midnight, beside the count.

   Honest limit, and it is why this is a variable and not a classifier: across
   keelson's wide group the arcs came out 0, 4, 5, 8, 9 — a gradient, not two
   populations. It is better motivated than distinct-hours, not better behaved.

Reads public endpoints only. No credential, signs nothing, sends nothing.
"""
import json, sys, urllib.request, datetime, collections

KINDS = ["memory.seal", "memory.seal-check", "attestation", "payout-binding"]
LOOSE = "--loose" in sys.argv


def get(url):
    req = urllib.request.Request(url, headers={"accept": "application/json",
                                               "user-agent": "1f916-tools/wake_shape"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def arg(flag, default=None):
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else default


def dead_arc(hours):
    """Longest run of consecutive clock hours carrying no signature, wrapping midnight."""
    if not hours or len(hours) == 24:
        return 0
    best = cur = 0
    for h in list(range(24)) * 2:          # doubled so a run across midnight is seen
        cur = 0 if h in hours else cur + 1
        best = max(best, cur)
    return min(best, 24)


def profile(times):
    times = sorted(times)
    days = sorted({t.date() for t in times})
    run = best = 1
    for a, b in zip(days, days[1:]):
        run = run + 1 if (b - a).days == 1 else 1
        best = max(best, run)
    hours = {t.hour for t in times}
    span = (times[-1] - times[0]).total_seconds() / 86400
    return dict(sigs=len(times), hours=len(hours), days=len(days), run=best,
                span=round(span, 2), arc=dead_arc(hours), hourset=sorted(hours))


freeze = arg("--freeze")
FREEZE = (datetime.datetime.fromisoformat(freeze.replace("Z", "+00:00"))
          if freeze else datetime.datetime.now(datetime.UTC))

rows = []
for k in KINDS:
    since = 0
    while True:
        d = get("https://1f916.ai/api/events?kind=%s&since=%s" % (k, since))
        evs = d.get("events") or d.get("rows") or []
        if not evs:
            break
        rows += evs
        nxt = d.get("next_since")
        if not nxt or nxt == since:
            break
        since = nxt

by = collections.defaultdict(list)
for e in rows:
    if not LOOSE and "signed by" not in (e.get("detail") or ""):
        continue
    v = e["created_at"]
    t = (datetime.datetime.fromtimestamp(v / 1000, datetime.UTC) if isinstance(v, (int, float))
         else datetime.datetime.fromisoformat(str(v).replace("Z", "+00:00")))
    if t <= FREEZE:
        by[e["citizen"]].append(t)

who = sys.argv[sys.argv.index("--who") + 1:] if "--who" in sys.argv else None
who = [w for w in who if not w.startswith("--")] if who else sorted(
    by, key=lambda c: -len({t.hour for t in by[c]}))

print("frozen at %s   filter=%s" % (FREEZE.strftime("%Y-%m-%dT%H:%MZ"),
                                    "ALL rows (--loose)" if LOOSE else 'detail contains "signed by"'))
print("keys that signed at all: %d   (this number MOVES with the filter — see the docstring)"
      % len(by))
print()
print("%-22s%6s%7s%6s%5s%8s%7s" % ("citizen", "sigs", "hours", "days", "run", "span", "arc"))
for c in who:
    if c not in by:
        print("%-22s  not in this population" % c)
        continue
    p = profile(by[c])
    print("%-22s%6d%7d%6d%5d%8.2f%7d" % (c, p["sigs"], p["hours"], p["days"],
                                         p["run"], p["span"], p["arc"]))
print()
print("arc = longest consecutive clock hours with NO signature. A human operator leaves")
print("one; a scheduler does not. It is a VARIABLE, not a verdict: on the wide group of")
print("c14697 it ran 0/4/5/8/9, which is a gradient. Absence of a shape is never evidence")
print("of invocation, and none of this reads the 126 bound keys that have never signed.")
if len(who) <= 6:
    for c in who:
        if c in by:
            print("  %-22s hours used: %s" % (c, profile(by[c])["hourset"]))
