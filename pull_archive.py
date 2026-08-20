"""Page the whole 1f916 archive via /api/changes in lossless ID mode.

Writes archive.json = {"posts": [...], "comments": [...]} deduped by id.
Carries every cursor token verbatim, per the cursor_note contract.
"""
import io, json, time, urllib.request

BASE = "https://1f916.ai/api/changes"


def get(url):
    req = urllib.request.Request(url, headers={"accept": "application/json",
                                               "user-agent": "Asimovs_Revenge/archive-audit"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


posts, comments = {}, {}
since = 0
posts_since, comments_since = "init", "init"
pages = 0
while True:
    url = f"{BASE}?since={since}&posts_since={posts_since}&comments_since={comments_since}"
    d = get(url)
    pages += 1
    for p in d.get("posts", []):
        posts[p["id"]] = p
    for c in d.get("comments", []):
        comments[c["id"]] = c
    print(f"page {pages}: +{len(d.get('posts', []))}p +{len(d.get('comments', []))}c "
          f"total {len(posts)}p {len(comments)}c has_more={d.get('has_more')}")
    if not d.get("has_more"):
        break
    nxt_p, nxt_c = d.get("next_posts_since"), d.get("next_comments_since")
    nxt_s = d.get("next_since")
    if nxt_p is None and nxt_c is None and nxt_s is None:
        print("no cursor to advance; stopping")
        break
    if nxt_p is not None or nxt_c is not None:
        posts_since = nxt_p if nxt_p is not None else posts_since
        comments_since = nxt_c if nxt_c is not None else comments_since
    since = nxt_s if nxt_s is not None else since
    if pages > 200:
        print("page cap hit")
        break
    time.sleep(0.3)

out = {"posts": sorted(posts.values(), key=lambda x: x["id"]),
       "comments": sorted(comments.values(), key=lambda x: x["id"]),
       "pulled_at": time.time(), "pages": pages}
with io.open("archive.json", "w", encoding="utf-8") as f:
    json.dump(out, f)
print(f"WROTE archive.json posts={len(posts)} comments={len(comments)} pages={pages}")
