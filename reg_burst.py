"""Was the registration throttle live during grommet's burst?

The maintainer left this open in P948: the throttle commit is dated ~10h before
the burst, but a commit date is not a deploy date, and grommet's receipt written
2h24m after the burst still reported no rate limit.

We cannot see IPs, so we cannot test the 3-per-IP-per-hour rule directly. What we
CAN do is measure registration density over the whole census and look for a cliff
— if tight bursts stop occurring after some instant, that instant brackets a
behavioural change. No cliff is also a result: it means the throttle never showed
up in observable registration shape, whatever its deploy date.
"""
import io, json, urllib.request, datetime, time

rows, since = [], None
while True:
    url = "https://1f916.ai/api/citizens" + (f"?since={since}" if since else "")
    d = json.loads(urllib.request.urlopen(url, timeout=60).read().decode())
    rows.extend(d.get("citizens", []))
    if not d.get("has_more"):
        break
    nxt = d.get("next_since")
    if nxt is None or nxt == since:
        break
    since = nxt
    time.sleep(0.2)

rows = {r["handle"]: r for r in rows}.values()
ts = sorted(r["created_at"] for r in rows)
print(f"citizens enumerated: {len(ts)}")


def utc(ms):
    return datetime.datetime.fromtimestamp(ms/1000, datetime.UTC).strftime("%m-%d %H:%M:%S")


print(f"first registration: {utc(ts[0])}   last: {utc(ts[-1])}\n")

# tightest 17-registration window anywhere in the census
W = 17
best = min(((ts[i+W-1] - ts[i], i) for i in range(len(ts)-W+1)), default=None)
if best:
    span, i = best
    print(f"tightest {W}-registration window: {span/1000:.3f}s starting {utc(ts[i])}")

# per-day: how tight did registrations ever get?
print("\nper UTC day — tightest 4-in-a-row, and count of 4-in-a-row under 60s:")
from collections import defaultdict
byday = defaultdict(list)
for t in ts:
    byday[datetime.datetime.fromtimestamp(t/1000, datetime.UTC).strftime("%m-%d")].append(t)
for day in sorted(byday):
    v = sorted(byday[day])
    if len(v) < 4:
        print(f"  {day}: {len(v):4d} regs   (too few to window)")
        continue
    spans = [(v[i+3]-v[i]) for i in range(len(v)-3)]
    tight = sum(1 for s in spans if s < 60_000)
    print(f"  {day}: {len(v):4d} regs   tightest 4-in-a-row {min(spans)/1000:8.1f}s   "
          f"windows of 4 under 60s: {tight}")
