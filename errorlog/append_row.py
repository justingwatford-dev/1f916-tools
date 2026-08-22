"""Append one row to log.jsonl with the next id. Used by humans and by the gates.

  python append_row.py prevention <session> <class> <caught_by> <gate> <message>

Preventions and errors live in ONE table on purpose. A refusal that stops a
`mechanical` failure and a `mechanical` failure that got through are the same
event with different endings; splitting them across two files makes the only
question worth asking unanswerable — which classes do the gates actually cover.
"""
import io, json, os, sys, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "log.jsonl")

rows = [json.loads(l) for l in io.open(LOG, encoding="utf-8") if l.strip()]
nxt = max((r["id"] for r in rows), default=0) + 1

kind = sys.argv[1]
if kind != "prevention":
    raise SystemExit("only 'prevention' is written programmatically; errors are written by hand")

session, cls, caught_by, gate, message = sys.argv[2:7]
row = {
    "id": nxt,
    "session": int(session),
    "at": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "prevented": True,
    "class": cls,
    "caught_by": caught_by,
    "gate": gate,
    "message": message[:200],
    # The gate wrote this row AS it fired, so the detector path is known with
    # certainty and observed rather than reconstructed. Stamping it here rather
    # than leaving it for a later backfill is the point: rows 44-47 had to be
    # completed by hand because this writer predated the fields, and a hand
    # completion is exactly the weaker provenance the field exists to mark.
    "control_id": gate,
    "control_executed": True,
    "control_result": "fail",
    "control_provenance": "observed",
    # Not inferable by the gate: whether a stranger could replay the claim from
    # recorded state. Left null rather than guessed.
    "replayable": None,
}
# A gate exercised deliberately is evidence the gate works, and it is not a
# prevention that happened in the wild. Label it rather than delete it:
# deleting test rows removes proof the instrument fires, and three times this
# week I cleared one instead of marking it.
if os.environ.get("ERRORLOG_TEST"):
    row["test"] = True
with io.open(LOG, "a", encoding="utf-8", newline="\n") as f:
    f.write(json.dumps(row, ensure_ascii=False) + "\n")
print("logged prevention id=%d gate=%s" % (nxt, gate))
