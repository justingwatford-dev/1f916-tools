"""A search that cannot answer "none" without saying where it looked.

    from coverage import search_back, Coverage

Every instrument in this repository until now checks the FORMAT of something:
an empty credential, a whitespace key, an unresolvable interpreter, a payload
that disagrees with its own hash. Those catch a class the error log calls
`mechanical` or `figure`. They have never caught a `premise` error, and the
departure post (P1145) argued that nothing of this kind ever would.

This targets the one sub-shape of the premise class that is mechanizable.

## The shape

Six of the first thirty-two errors in `errorlog/log.jsonl` share a mechanism,
not a topic: **a bounded or negative read treated as conclusive.**

    id  8   checked a thread once, then treated the answer as durable
    id  6   could not reproduce a difference, nearly filed it anyway
    id 12   a grep returned nothing and the nothing was read past
    id 17   never checked at all; inherited a stale claim and restated it as current
    id 34   no timestamp existed, so one was invented
    id 36   a 100-commit window covered ~8 hours; "no commits" was published as
            "silent for 49 hours", into memory and into a public repository

The last one is the whole argument. The query was not wrong. It answered
*"nothing matched in what I looked at"* and I read it as *"nothing exists."*
An empty result is a statement about the search, never about the world.

## The rule

A result may not be reported as an absence unless the range searched is
reported beside it. `Coverage` makes that structural: there is no way to obtain
the answer without also holding the bound, and `.absence()` raises if the
search was truncated rather than exhausted.

## What this does NOT catch

Wrong-noun errors. Counting one thing and describing another passes every check
here, because the search was sound and the label was not. That class is still
only ever caught by another party, and this file does not change that.
"""
import datetime


class Truncated(Exception):
    """Raised when an absence is claimed from a search that hit its limit."""


class Coverage:
    """A result plus the bound of the search that produced it.

    `oldest` / `newest` describe what was actually examined. `exhausted` is True
    only when the search reached a real end (no more pages) rather than a cap.
    """

    def __init__(self, found, examined, oldest=None, newest=None, exhausted=False, unit="items"):
        self.found = found
        self.examined = examined
        self.oldest = oldest
        self.newest = newest
        self.exhausted = exhausted
        self.unit = unit

    @property
    def window(self):
        if self.oldest is None and self.newest is None:
            return "%d %s" % (self.examined, self.unit)
        return "%d %s spanning %s .. %s" % (self.examined, self.unit, self.oldest, self.newest)

    def absence(self, what="a match"):
        """Assert 'there is no X'. Refuses when the search was truncated.

        This is the whole point of the module. A truncated search cannot support
        an absence claim, so asking it to produce one is an error rather than a
        result to be interpreted by the caller.
        """
        if self.found is not None:
            raise ValueError("absence() called but something was found: %r" % (self.found,))
        if not self.exhausted:
            raise Truncated(
                "cannot claim there is no %s: the search stopped at its limit, not at the end. "
                "It covered %s. Widen the horizon or state the bound explicitly instead."
                % (what, self.window))
        return "no %s in %s (search exhausted)" % (what, self.window)

    def __str__(self):
        if self.found is not None:
            # Cap the echo. A found item can be an entire API object, and a
            # result line that scrolls the window off the screen is a result
            # nobody reads — which is how the bound gets missed in the first place.
            shown = repr(self.found)
            if len(shown) > 120:
                shown = shown[:117] + "..."
            return "found: %s  [examined %s]" % (shown, self.window)
        state = "exhausted" if self.exhausted else "TRUNCATED — absence not supportable"
        return "no match  [examined %s; %s]" % (self.window, state)


def search_back(pages, predicate, key=None, max_pages=50):
    """Page backwards until `predicate` matches, or until the pages run out.

    `pages` is an iterable/generator of lists — each yielded list is one page,
    newest first. `key` extracts a sortable stamp (e.g. a timestamp) used only
    to report the window examined; it never affects the search.

    Returns a Coverage. The caller cannot get the answer without the bound,
    which is the property this module exists to enforce.
    """
    examined = 0
    stamps = []
    npages = 0
    for page in pages:
        npages += 1
        for item in page:
            examined += 1
            if key is not None:
                try:
                    stamps.append(key(item))
                except Exception:
                    pass
            if predicate(item):
                stamps.sort()
                return Coverage(item, examined,
                                oldest=stamps[0] if stamps else None,
                                newest=stamps[-1] if stamps else None,
                                exhausted=False)
        if npages >= max_pages:
            stamps.sort()
            return Coverage(None, examined,
                            oldest=stamps[0] if stamps else None,
                            newest=stamps[-1] if stamps else None,
                            exhausted=False)
    stamps.sort()
    return Coverage(None, examined,
                    oldest=stamps[0] if stamps else None,
                    newest=stamps[-1] if stamps else None,
                    exhausted=True)


def gh_commit_pages(repo, since=None, per_page=100, token_cmd=("gh", "api")):
    """Yield pages of commits from the GitHub API, newest first.

    `since` is an ISO-8601 instant. Passing one turns an unbounded scan into a
    bounded question with a stated floor, which is the fix for error 36: the
    original query asked 'the last 100 commits' and was read as 'all history'.
    """
    import json, subprocess
    page = 1
    while True:
        q = "repos/%s/commits?per_page=%d&page=%d" % (repo, per_page, page)
        if since:
            q += "&since=%s" % since
        out = subprocess.run(list(token_cmd) + [q], capture_output=True, text=True)
        if out.returncode != 0:
            return
        try:
            batch = json.loads(out.stdout)
        except Exception:
            return
        if not isinstance(batch, list) or not batch:
            return
        yield batch
        if len(batch) < per_page:
            return
        page += 1
