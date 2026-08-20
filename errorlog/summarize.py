"""Summarise the prospective error log.

Refuses to print a single headline ratio, on purpose. The whole point of the log
is that "caught by another party vs caught by myself" is three numbers, not one,
and collapsing them is how the flattering version gets published.

    python summarize.py [log.jsonl]
"""
import json, io, sys, os
from collections import Counter

path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "log.jsonl")
all_rows = [json.loads(l) for l in io.open(path, encoding="utf-8") if l.strip()]
live = [r for r in all_rows if not r.get("test")]
tests = [r for r in all_rows if r.get("test")]
prevented = [r for r in live if r.get("prevented")]
rows = [r for r in live if not r.get("prevented")]   # errors only, for the catch split

EXTERNAL = lambda c: c not in ("self-pre", "self-post") and not c.startswith("instrument:")

print(f"errors: {len(rows)}   preventions: {len(prevented)}   test rows excluded: {len(tests)}")
print(f"sessions: {sorted({r['session'] for r in all_rows})}")
if prevented:
    from collections import Counter as _C
    print()
    print("PREVENTIONS (gates firing — same class vocabulary, so coverage is cross-tabbable)")
    for cls, n in sorted(_C(r["class"] for r in prevented).items()):
        got = sum(1 for r in rows if r["class"] == cls)
        print(f"  {cls:<12} prevented {n:<3} | errors of that class that still got through: {got}")
print()

# --- the catch split, which is the number that was promised ------------------
pre  = [r for r in rows if r["caught_by"] == "self-pre"]
post = [r for r in rows if r["caught_by"] == "self-post"]
ext  = [r for r in rows if EXTERNAL(r["caught_by"])]
inst = [r for r in rows if r["caught_by"].startswith("instrument:")]

print("CATCH SPLIT (the honest comparison is self-post vs external:")
print("             self-pre never reached anyone, so counting it with the others")
print("             inflates the self-caught column)")
print(f"  external            {len(ext):3d}   {sorted({r['caught_by'] for r in ext})}")
print(f"  self, post-statement{len(post):3d}")
print(f"  self, pre-statement {len(pre):3d}   (reported separately, never pooled)")
print(f"  by an instrument    {len(inst):3d}")
print()

# --- by class, which is the finding the split exists to test -----------------
print("BY CLASS x CATCHER")
classes = sorted({r["class"] for r in rows})
print(f"  {'class':<12}{'external':>9}{'self-post':>10}{'self-pre':>9}{'instrument':>11}")
for c in classes:
    sub = [r for r in rows if r["class"] == c]
    print(f"  {c:<12}{sum(1 for r in sub if EXTERNAL(r['caught_by'])):>9}"
          f"{sum(1 for r in sub if r['caught_by']=='self-post'):>10}"
          f"{sum(1 for r in sub if r['caught_by']=='self-pre'):>9}"
          f"{sum(1 for r in sub if r['caught_by'].startswith('instrument:')):>11}")
print()

# --- the bound that has to travel with any ratio -----------------------------
red = sum(1 for r in rows if r.get("rederived"))
pub = [r for r in rows if r.get("reached_public")]
print("BOUNDS")
print(f"  re-derived independently: {red}/{len(rows)} rows. Ratios over the other"
      f" {len(rows)-red} are ratios over CAUGHT errors, not over errors made.")
print(f"  reached the public record: {len(pub)}  -> {[r['id'] for r in pub]}")
print(f"  errors nobody ever caught are absent from this log by construction,")
print(f"  exactly as they are absent from the archive. The log fixes the")
print(f"  numerator (catches leaving no public row), never the denominator.")
print()
print("PREMISE ERRORS, the class no instrument here has caught:")
for r in [x for x in rows if x["class"] == "premise"]:
    print(f"  #{r['id']:<3} caught_by={r['caught_by']:<22} public={str(r.get('reached_public')):<5}")
