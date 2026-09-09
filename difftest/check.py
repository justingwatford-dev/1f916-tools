"""Differential JSON checker: CPython `json` vs Node `JSON.parse`.

    python check.py --hex 4e614e            # candidate as hex bytes
    python check.py --text '{"a":1}'        # candidate as utf-8 text
    python check.py --file candidate.bin    # candidate as a file
    python check.py --selftest              # run the controls

WHAT A HIT MEANS. Both implementations claim RFC 8259 / ECMA-404. An input they
disagree on is evidence about the SPECIFICATION's under-determination, not an
accusation against either project. Most known divergences are documented and
deliberate.

WHY BYTES AND NOT TEXT. Many interesting candidates are invalid UTF-8, BOM
prefixed, or carry unpaired surrogates. A text-oriented harness cannot express
them, and silently loses the ones that matter most.

THE CONTROLS ARE THE POINT. POSITIVE controls are known real divergences: miss
one and this is not a detector. NEGATIVE controls are documents both accept
identically: fire on one and this is a detector that returns true on everything,
which passes a confirming test while failing at its job. Run --selftest before
trusting any result out of this file.
"""
import json, subprocess, sys, os, math

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))


def cps(s):
    return ".".join(str(ord(c)) for c in s)


def canon(v):
    if v is None: return "null"
    if v is True: return "true"
    if v is False: return "false"
    if isinstance(v, str): return "s:" + cps(v)
    if isinstance(v, int): return str(v)
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v): return "NONFINITE"
        return str(int(v)) if v.is_integer() and abs(v) < 1e21 else repr(v)
    if isinstance(v, list): return "[" + ",".join(canon(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{" + ",".join(cps(k) + ":" + canon(v[k]) for k in sorted(v.keys())) + "}"
    return "UNKNOWN"


def py_side(data):
    # json.loads takes bytes and does its OWN decoding, strictly. Do not decode
    # for it: imitating the other implementation's lossy decode here would make
    # the two agree by construction on every malformed-UTF-8 input.
    lossy = False
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        lossy = True
    try:
        return {"accepted": True, "lossy": lossy, "canon": canon(json.loads(data))}
    except Exception as e:
        return {"accepted": False, "lossy": lossy, "error": type(e).__name__}


def node_side(data):
    p = subprocess.run(["node", os.path.join(HERE, "check.js")],
                       input=data, capture_output=True)
    if p.returncode != 0:
        return {"accepted": None, "error": "HARNESS:" + p.stderr.decode("utf-8", "replace")[:120]}
    return json.loads(p.stdout.decode("utf-8"))


def compare(data):
    a, b = py_side(data), node_side(data)
    if a.get("accepted") != b.get("accepted"):
        return "ACCEPTANCE", a, b
    if a.get("accepted") and a.get("canon") != b.get("canon"):
        return "VALUE", a, b
    return None, a, b


# ---- controls ---------------------------------------------------------------
# Run --selftest before trusting any result out of this file.
#
# POSITIVE: divergences confirmed by hand against RFC 8259. Miss one and this is
# not a detector. NEGATIVE: documents both implementations handle identically.
# Fire on one and this is a detector that returns true on everything, which
# passes a confirming test while failing at its job. Both halves, or neither is
# evidence. Checked at CPython 3.13.14 / Node v24.19.0; a divergence is only
# meaningful against named versions.

BS = chr(92)   # a backslash. Written this way on purpose: every layer between an
               # editor and this file eats one, and a control whose bytes are not
               # what its author believes is worse than no control at all.


def H(hexstr):
    """hex -> bytes. The same format a submission uses, so the corpus below and
    an incoming candidate are the same kind of object."""
    return bytes.fromhex(hexstr.replace(" ", ""))


POSITIVE = [
    (b"NaN",                  "CPython accepts NaN; the JSON grammar has no such literal"),
    (b"Infinity",             "CPython accepts Infinity"),
    (b"-Infinity",            "CPython accepts -Infinity"),
    (b"12345678901234567890", "integer outside the IEEE754 exactly-representable range"),
    (H("ef bb bf 7b 22 61 22 3a 31 7d"),
     "UTF-8 BOM then {\"a\":1}. RFC 8259 8.1: a parser MAY ignore a BOM, so BOTH conform"),
    (H("22 ff 22"),
     "invalid UTF-8 byte in a string. RFC 8259 does not address it, so BOTH conform"),
]

NEGATIVE = [
    (b"{\"a\":1}",                        "trivial object"),
    (b"[1,2,3]",                          "trivial array"),
    (b"\"hello\"",                        "bare string"),
    (b"true",                             "bare true"),
    (b"null",                             "bare null"),
    (b"1.5",                              "bare float"),
    (b"{}",                               "empty object"),
    (b"[]",                               "empty array"),
    (b"{\"b\":2,\"a\":1}",                "key order must not matter"),
    (b"{\"nested\":{\"x\":[1,{\"y\":null}]}}", "nesting"),
    (b"[1e400]",                          "overflow: BOTH yield +inf. A find only if you compare the SPELLING of infinity"),
    (('"' + BS + 'u00e9"').encode(),      "non-ascii via escape"),
    ("\"\u00e9\"".encode("utf-8"),        "non-ascii literal"),
    ("\"\U0001f600\"".encode("utf-8"),    "astral literal"),
    (('"' + BS + 'ud83d' + BS + 'ude00"').encode(), "astral via escaped surrogate pair"),
    ("{\"\u00e9\":1}".encode("utf-8"),    "non-ascii key"),
    (b"{",                                "malformed: both reject"),
    (b"[1,",                              "malformed: both reject"),
    (b"01",                               "leading zero: both reject"),
    (b"'x'",                              "single quotes: both reject"),
]

# Checked, and they AGREE. Published because a record of what was tried and did
# NOT diverge is the more useful half of a corpus: it stops the next person
# spending an attempt on ground already covered.
CHECKED_AGREE = [
    (('"' + BS + 'ud800"').encode(),  "lone leading surrogate via escape"),
    (('"' + BS + 'udc00"').encode(),  "lone trailing surrogate via escape"),
    (b"{\"a\":1,\"a\":2}",            "duplicate key: both take the last"),
    (b"1E1",                          "capital exponent"),
    (b"-0",                           "negative zero"),
    (b"1.0",                          "integral float"),
    (b"[1e-400]",                     "underflow to zero"),
    (('"' + BS + '/"').encode(),      "escaped solidus"),
]


def run(group, label, expect):
    bad = 0
    print("\n%s" % label)
    for data, why in group:
        kind, a, b = compare(data)
        ok = (kind is not None) if expect == "flag" else (kind is None)
        if not ok:
            bad += 1
        print("  %-30s %-11s %s" % (data.hex()[:30], kind or "agree",
                                    "ok" if ok else "<-- FAIL: " + why))
        if kind:
            print("        %-14s py   %s" % (ascii(data)[:14], a))
            print("        %-14s node %s" % ("", b))
    return bad


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        bad = run(POSITIVE, "POSITIVE - the harness MUST flag every one:", "flag")
        bad += run(NEGATIVE, "NEGATIVE - the harness MUST stay silent on every one:", "quiet")
        bad += run(CHECKED_AGREE, "ALREADY SPENT - checked, they agree, do not resubmit:", "quiet")
        print("\n%s  (%d control failures)" % ("PASS" if bad == 0 else "FAIL", bad))
        raise SystemExit(1 if bad else 0)
    if "--hex" in sys.argv:
        data = bytes.fromhex(sys.argv[sys.argv.index("--hex") + 1].replace(" ", ""))
    elif "--file" in sys.argv:
        data = open(sys.argv[sys.argv.index("--file") + 1], "rb").read()
    else:
        data = sys.argv[sys.argv.index("--text") + 1].encode("utf-8")
    kind, a, b = compare(data)
    print("bytes   :", data.hex())
    print("as text :", ascii(data)[:200])
    print("python  :", a)
    print("node    :", b)
    print("verdict :", ("DIVERGENCE (%s)" % kind) if kind else "agree - not a finding")
