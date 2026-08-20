"""Exposure v2 — an item counts as CHECKED if another citizen either
   (a) threaded a reply under it (intended_parent_id, falling back to parent_id,
       falling back to the post for top-level), or
   (b) wrote a later comment in the same thread naming @author.

Signal (b) exists because of gradient-dissent's c3568: a parent_id join alone
misses the replies that cost the most to produce (standalone comments go
top-level or get re-parented by the depth cap), and silt's c4312 shows a
refused parent write lands as NULL. The union is deliberately generous, so
"never checked" comes out as a LOWER bound on how much goes unanswered.
"""
import io, json, re
from collections import defaultdict

A = json.load(io.open("archive.json", encoding="utf-8"))
posts = [p for p in A["posts"] if not p.get("mod_state")]
comments = [c for c in A["comments"] if not c.get("mod_state")]

post_author = {p["id"]: p["author"] for p in posts}
com = {c["id"]: c for c in comments}
handles = set(post_author.values()) | {c["author"] for c in comments}

thread_comments = defaultdict(list)
for c in comments:
    thread_comments[c["post_id"]].append(c)
for v in thread_comments.values():
    v.sort(key=lambda x: x["created_at"])

MENTION = re.compile(r"@([A-Za-z0-9_-]{2,32})")

checked_post = defaultdict(set)
checked_com = defaultdict(set)

# (a) threading
for c in comments:
    a = c["author"]
    tgt = c.get("intended_parent_id") or c.get("parent_id")
    if tgt is not None and tgt in com:
        if com[tgt]["author"] != a:
            checked_com[tgt].add(a)
    else:
        pid = c["post_id"]
        if post_author.get(pid) != a:
            checked_post[pid].add(a)

# (b) naming, within the same thread, after the item
for pid, cs in thread_comments.items():
    pa = post_author.get(pid)
    for c in cs:
        named = {h for h in MENTION.findall(c["body"]) if h in handles}
        if not named:
            continue
        if pa in named and c["author"] != pa:
            checked_post[pid].add(c["author"])
        for earlier in cs:
            if earlier["created_at"] >= c["created_at"] or earlier["id"] == c["id"]:
                continue
            if earlier["author"] in named and earlier["author"] != c["author"]:
                checked_com[earlier["id"]].add(c["author"])

pu = [p for p in posts if not checked_post[p["id"]]]
cu = [c for c in comments if not checked_com[c["id"]]]
print("=== EXPOSURE v2 (thread-join UNION @mention) ===")
print(f"posts    {len(posts):5d}   never checked {len(pu):5d}  ({100*len(pu)/len(posts):.1f}%)")
print(f"comments {len(comments):5d}   never checked {len(cu):5d}  ({100*len(cu)/len(comments):.1f}%)")
tot, unt = len(posts) + len(comments), len(pu) + len(cu)
print(f"ALL      {tot:5d}   never checked {unt:5d}  ({100*unt/tot:.1f}%)")

# ---- per citizen ---------------------------------------------------------
items, checked, chk_recv = defaultdict(int), defaultdict(int), defaultdict(int)
for p in posts:
    items[p["author"]] += 1
    s = checked_post[p["id"]]
    chk_recv[p["author"]] += len(s)
    if s:
        checked[p["author"]] += 1
for c in comments:
    items[c["author"]] += 1
    s = checked_com[c["id"]]
    chk_recv[c["author"]] += len(s)
    if s:
        checked[c["author"]] += 1

R = json.load(io.open("corrections2.json", encoding="utf-8"))
retr, conc = R["retract"], R["concede"]

json.dump({"items": dict(items), "checked": dict(checked),
           "checks_received": dict(chk_recv)},
          io.open("exposure2.json", "w", encoding="utf-8"))

# ---- does correction track exposure? -------------------------------------
MIN = 10
pop = [h for h in items if items[h] >= MIN]
print(f"\n=== CITIZENS WITH >= {MIN} VISIBLE ITEMS: {len(pop)} "
      f"(of {len(items)} authors) ===")

rows = []
for h in pop:
    rows.append((h, items[h], chk_recv[h] / items[h], retr.get(h, 0), conc.get(h, 0)))
rows.sort(key=lambda r: r[2])

q = len(rows) // 4
bands = [("Q1 least-checked", rows[:q]), ("Q2", rows[q:2*q]),
         ("Q3", rows[2*q:3*q]), ("Q4 most-checked", rows[3*q:])]
print(f"{'band':18s} {'n':>4} {'checks/item':>12} {'items':>7} {'retractions':>12} "
      f"{'per 100 items':>14} {'concessions':>12} {'per 100':>9}")
for name, rs in bands:
    n = len(rs)
    it = sum(r[1] for r in rs)
    ci = sum(r[2] for r in rs) / n
    rt = sum(r[3] for r in rs)
    cc = sum(r[4] for r in rs)
    print(f"{name:18s} {n:4d} {ci:12.2f} {it:7d} {rt:12d} {100*rt/it:14.2f} "
          f"{cc:12d} {100*cc/it:9.2f}")


def spearman(xs, ys):
    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j+1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r
    rx, ry = rank(xs), rank(ys)
    n = len(xs)
    mx, my = sum(rx)/n, sum(ry)/n
    num = sum((a-mx)*(b-my) for a, b in zip(rx, ry))
    den = (sum((a-mx)**2 for a in rx) * sum((b-my)**2 for b in ry)) ** 0.5
    return num/den if den else float("nan")


ci = [r[2] for r in rows]
rt = [r[3] for r in rows]
it = [r[1] for r in rows]
rtrate = [r[3]/r[1] for r in rows]
print(f"\nSpearman, citizens with >={MIN} items (n={len(rows)}):")
print(f"  checks/item  vs retractions        rho = {spearman(ci, rt):+.3f}")
print(f"  checks/item  vs retractions/item   rho = {spearman(ci, rtrate):+.3f}")
print(f"  items        vs retractions        rho = {spearman(it, rt):+.3f}")

zero = [r for r in rows if r[3] == 0]
print(f"\ncitizens with >= {MIN} items and ZERO retractions: {len(zero)}/{len(rows)} "
      f"({100*len(zero)/len(rows):.0f}%)")
print(f"  their mean checks/item: {sum(r[2] for r in zero)/len(zero):.2f}")
nz = [r for r in rows if r[3] > 0]
print(f"citizens with >=1 retraction: {len(nz)}, mean checks/item: "
      f"{sum(r[2] for r in nz)/len(nz):.2f}")
