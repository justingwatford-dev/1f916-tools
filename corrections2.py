"""Self-correction detector, v2 — conservative, with the exclusions stated.

Two classes, kept separate on purpose:
  RETRACTION — first-person admission that something the author previously
               asserted was wrong.
  CONCESSION — granting an interlocutor's point ("you are right ...").

Excluded: conditional/hypothetical frames ("if I'm wrong", "unless I am
mistaken", "tell me I was wrong"), and matches inside quotation marks (the
square talks ABOUT retraction constantly, which is what inflated v1).
"""
import io, json, re, sys
from collections import defaultdict

A = json.load(io.open("archive.json", encoding="utf-8"))
comments = [c for c in A["comments"] if not c.get("mod_state")]

RETRACT = [
    r"\bI was wrong\b", r"\bI was mistaken\b", r"\bI withdraw\b", r"\bI retract\b",
    r"\bI overstated\b", r"\bI overclaimed\b", r"\bI misread\b",
    r"\bI got (?:that|this|it) wrong\b", r"\bI had (?:that|this|it) wrong\b",
    r"\bcorrecting myself\b", r"\bmy error\b", r"\bmy mistake\b",
    r"\bmy (?:claim|number|count|reading|argument|framing|premise|test)[^.]{0,40}\bwas wrong\b",
]
CONCEDE = [
    r"\byou(?:'re|’re| are) right\b", r"\bI concede\b", r"\bconceded\b", r"\bI grant\b",
]

COND = re.compile(
    r"\b(?:if|unless|whether|should|suppose|assuming|in case|tell me|show me|"
    r"prove|when|where|until|so that|to see (?:if|whether)|say)\b", re.I)


def framed(body, m):
    """conditional trigger in the 60 chars before the match, or inside quotes"""
    pre = body[max(0, m.start() - 60):m.start()]
    if COND.search(pre):
        return True
    # inside a quotation: odd number of quote chars before the match
    q = body[:m.start()]
    for ch in ('"', "“", "'"):
        pass
    if (q.count('"') % 2 == 1) or (q.count("“") > q.count("”")):
        return True
    return False


def classify(body):
    out = set()
    for pats, label in ((RETRACT, "retract"), (CONCEDE, "concede")):
        for p in pats:
            for m in re.finditer(p, body, re.I):
                if not framed(body, m):
                    out.add(label)
                    break
            if label in out:
                break
    return out


retr = defaultdict(int)
conc = defaultdict(int)
hits = {"retract": [], "concede": []}
for c in comments:
    cls = classify(c["body"])
    if "retract" in cls:
        retr[c["author"]] += 1
        hits["retract"].append(c)
    if "concede" in cls:
        conc[c["author"]] += 1
        hits["concede"].append(c)

print(f"comments scanned: {len(comments)}")
print(f"RETRACTION comments: {len(hits['retract'])} ({100*len(hits['retract'])/len(comments):.2f}%), "
      f"{len(retr)} distinct citizens")
print(f"CONCESSION comments: {len(hits['concede'])} ({100*len(hits['concede'])/len(comments):.2f}%), "
      f"{len(conc)} distinct citizens")

if "--sample" in sys.argv:
    import random
    random.seed(11)
    for label in ("retract", "concede"):
        print(f"\n=== SAMPLE {label.upper()} (12) ===")
        for c in random.sample(hits[label], min(12, len(hits[label]))):
            b = c["body"]
            pats = RETRACT if label == "retract" else CONCEDE
            for p in pats:
                m = re.search(p, b, re.I)
                if m and not framed(b, m):
                    break
            s = max(0, m.start() - 80)
            print(f"\n[c{c['id']} {c['author']}] ...{b[s:m.end()+80]}...")

with io.open("corrections2.json", "w", encoding="utf-8") as f:
    json.dump({"retract": dict(retr), "concede": dict(conc),
               "retract_ids": [c["id"] for c in hits["retract"]],
               "concede_ids": [c["id"] for c in hits["concede"]]}, f)
