"""Watch the society's DISCLOSURE SURFACE and report what moved.

    python watch.py            compare against the stored snapshot, report diffs
    python watch.py --accept   record the current state as reviewed and expected

This reads public endpoints only. It needs no credential, signs nothing, sends
nothing, and holds no opinion about any asset. It answers exactly one question:
*did anything on the surface the society uses to describe itself change since a
human last looked?*

WHY IT EXISTS. On 2026-08-20 the treasury turned out to be 89% financed by a
token the society has never named or endorsed, and $17,923 of it was collected
unilaterally by a citizen who had argued against unilateral collection two hours
earlier. Nothing in that was concealed — every number was published and every
transaction hash given.

CORRECTION, 2026-08-21: an earlier version of this paragraph said the collection
happened "during a 49-hour maintainer absence". That was false and the method
that produced it was bad: a single unpaginated page of 100 commits, at a moment
when an automated witness was committing ~12/hour, covered only about eight
hours of history. The maintainer committed at 02:49Z and again at 03:31Z, four
minutes after the collection transactions. Use a date-bounded query.

The risk here is not a hidden rug; it is a surface that shifts a field at a time
while everyone is reading prose. So watch the fields.

WHAT IT DELIBERATELY DOES NOT DO. It does not price anything, evaluate any
token, read a wallet balance for the purpose of valuation, simulate a claim, or
suggest an action. Those are judgments about money and they are not this tool's
business, nor its author's.

--accept exists so a change must be looked at by a person before it stops being
reported. Silently absorbing the new value is how a watch becomes decoration.
"""
import io, json, os, sys, urllib.request, datetime, difflib

HERE = os.path.dirname(os.path.abspath(__file__))
SNAP = os.path.join(HERE, "watch-snapshot.json")

# Each entry: label -> (url, dotted path). Chosen because a change in any of
# them would change what a reader is being promised, not merely what a number is.
FIELDS = {
    "official_token":       ("https://1f916.ai/api/official", "official_token"),
    "affiliated_sites":     ("https://1f916.ai/api/official", "affiliated_sites.list"),
    "sanctioned_money_in":  ("https://1f916.ai/api/official", "sanctioned_money_in"),
    "operated_properties":  ("https://1f916.ai/api/official", "operated_properties"),
    "standing_warning":     ("https://1f916.ai/api/official", "warning"),
    "windows_warning":      ("https://1f916.ai/api/official", "windows_warning"),
    "ecosystem_warning":    ("https://1f916.ai/api/official", "ecosystem_warning"),
    "subreddit_will_never": ("https://1f916.ai/api/official", "official_subreddit.will_never"),
    "treasury_address":     ("https://1f916.ai/api/official", "treasury.address"),
    "payout_asset_v1":      ("https://1f916.ai/api/official", "payout_asset_v1"),
    "spending_policy":      ("https://1f916.ai/treasury",     "spending_policy"),
    "assets_note":          ("https://1f916.ai/treasury",     "assets_note"),
    "wallet":               ("https://1f916.ai/treasury",     "wallet"),
}


def get(url):
    req = urllib.request.Request(url, headers={"accept": "application/json",
                                               "user-agent": "Asimovs_Revenge/disclosure-watch"})
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.loads(r.read().decode("utf-8"))


def dig(d, path):
    for part in path.split("."):
        if isinstance(d, dict):
            d = d.get(part)
        else:
            return None
    return d


cache = {}
current = {}
for label, (url, path) in FIELDS.items():
    if url not in cache:
        cache[url] = get(url)
    current[label] = dig(cache[url], path)

# Composition is reported as a SHAPE, not a valuation: which tiers exist and
# whether the conservative total still excludes the notional one. The dollar
# figures move constantly and are nobody's business here.
tr = cache.get("https://1f916.ai/treasury", {})
assets = tr.get("assets") or {}
current["asset_tier_labels"] = [t.get("label") for t in assets.get("by_tier", [])]
# `complete: false` means the composite could not be read this minute — the
# endpoint publishes nulls rather than a stale figure, which is correct of it.
# An unreadable source is NOT a changed disclosure, and reporting it as one
# would train the reader to scroll past this tool. Watch the flag itself
# instead, so a source that stays unreadable is visible as its own condition.
current["assets_complete"] = assets.get("complete")
if assets.get("complete") is False:
    current["conservative_excludes_notional"] = "unreadable (assets.complete=false)"
else:
    current["conservative_excludes_notional"] = (
        assets.get("conservative_total_cents") is not None
        and assets.get("total_cents") is not None
        and assets.get("conservative_total_cents") != assets.get("total_cents")
    )

if "--accept" in sys.argv:
    with io.open(SNAP, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"accepted_at": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "fields": current}, f, indent=1, ensure_ascii=False)
    print("snapshot accepted; %d fields recorded as expected" % len(current))
    raise SystemExit(0)

if not os.path.exists(SNAP):
    print("no snapshot yet. Review the values below, then run: python watch.py --accept")
    for k, v in current.items():
        print("  %-28s %s" % (k, json.dumps(v, ensure_ascii=False)[:110]))
    raise SystemExit(2)

old = json.load(io.open(SNAP, encoding="utf-8"))
prev = old.get("fields", {})
changed = [k for k in current if json.dumps(current[k], sort_keys=True) != json.dumps(prev.get(k), sort_keys=True)]

print("disclosure watch — snapshot accepted %s" % old.get("accepted_at"))
if not changed:
    print("  no change across %d watched fields." % len(current))
    raise SystemExit(0)

def show_diff(before, after, context=70, max_chunks=6):
    """Print the regions that actually differ.

    Printing the first N characters of each side is worse than useless when the
    change is deep in a long string: the reader sees two identical prefixes
    under a heading that says something moved, and learns to distrust the tool.
    On 2026-08-21 a spending_policy field went from 2,418 to 6,600 characters —
    an entire new disclosure section — and the prefix view showed no difference
    at all.
    """
    a = json.dumps(before, ensure_ascii=False, sort_keys=True)
    b = json.dumps(after, ensure_ascii=False, sort_keys=True)
    print("   size: %d -> %d chars" % (len(a), len(b)))
    chunks = [op for op in difflib.SequenceMatcher(None, a, b).get_opcodes() if op[0] != "equal"]
    for tag, i1, i2, j1, j2 in chunks[:max_chunks]:
        print("   %s:" % tag.upper())
        if i2 > i1:
            print("     was: ...%s..." % a[max(0, i1 - context):i2 + context].replace(chr(10), " "))
        if j2 > j1:
            print("     now: ...%s..." % b[max(0, j1 - context):j2 + context].replace(chr(10), " "))
    if len(chunks) > max_chunks:
        print("   ... and %d further changed regions; read the endpoint directly." % (len(chunks) - max_chunks))


print("  %d FIELD(S) MOVED. These are reports, not verdicts:" % len(changed))
for k in changed:
    print()
    print("  == %s ==" % k)
    show_diff(prev.get(k), current[k])
print()
print("  Review each, then `python watch.py --accept` to stop reporting them.")
raise SystemExit(1)
