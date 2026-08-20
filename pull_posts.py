"""Fetch every post record (body + votes) and every comment's votes via
GET /api/post/:id, walking the comment pages per the has_more contract."""
import io, json, time, urllib.request

def get(url, tries=4):
    for t in range(tries):
        try:
            req = urllib.request.Request(url, headers={
                "accept": "application/json",
                "user-agent": "Asimovs_Revenge/archive-audit"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            if t == tries - 1:
                raise
            time.sleep(1.5 * (t + 1))

A = json.load(io.open("archive.json", encoding="utf-8"))
ids = [p["id"] for p in A["posts"]]

full, cvotes, failed = {}, {}, []
for n, pid in enumerate(ids, 1):
    try:
        d = get(f"https://1f916.ai/api/post/{pid}")
    except Exception as e:
        failed.append((pid, str(e)[:80]))
        continue
    p = d.get("post")
    if p:
        full[pid] = p
    for c in d.get("comments", []):
        cvotes[c["id"]] = {"votes": c.get("votes"), "author": c.get("author")}
    # page the rest of the thread if the first page did not carry it
    guard = 0
    while d.get("has_more") and guard < 40:
        nxt = d.get("next_since")
        if nxt is None:
            break
        d = get(f"https://1f916.ai/api/post/{pid}?since={nxt}")
        for c in d.get("comments", []):
            cvotes[c["id"]] = {"votes": c.get("votes"), "author": c.get("author")}
        guard += 1
    if n % 100 == 0:
        print(f"  {n}/{len(ids)} posts, {len(cvotes)} comment-votes", flush=True)
    time.sleep(0.12)

json.dump({"posts": full, "comment_votes": cvotes, "failed": failed},
          io.open("full_posts.json", "w", encoding="utf-8"))
print(f"DONE posts={len(full)} comment_votes={len(cvotes)} failed={len(failed)}")
if failed:
    print("failures:", failed[:10])
