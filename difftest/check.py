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
import json, subprocess, sys, os, math, struct

# See bits(): -0.0 and 0.0 are kept distinct by default.
ZERO_SIGN_MATTERS = True

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
    if isinstance(v, bool): return "true" if v else "false"
    if isinstance(v, int): return num_int(v)
    if isinstance(v, float): return "d:" + bits(v)
    if isinstance(v, list): return "[" + ",".join(canon(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{" + ",".join(cps(k) + ":" + canon(v[k]) for k in sorted(v.keys())) + "}"
    return "UNKNOWN"


def bits(f):
    """A double's canonical form is its 64 IEEE754 bits, never its decimal
    spelling. Comparing spellings is what made 1e-7 read as a divergence:
    CPython's repr emits 1e-07 and JS emits 1e-7 for the SAME binary64 value,
    0x1.ad7f29abcaf48p-24. Found by margin-lantern (c51001), who packed both
    sides big-endian and showed identical bytes 3e7ad7f29abcaf48.

    SIGNED ZERO POLICY, stated because it is a real choice and not an accident:
    -0.0 and 0.0 have DIFFERENT bit patterns and this function keeps them
    distinct. JS agrees that Object.is(-0, 0) is false. Set ZERO_SIGN_MATTERS
    False to fold them together; the constant exists so the policy is visible
    rather than buried in a comparison."""
    if ZERO_SIGN_MATTERS is False and f == 0.0:
        f = 0.0
    return struct.pack(">d", f).hex()


def num_int(v):
    """CPython keeps arbitrary-precision ints; the other side has only doubles.
    An int the double can hold exactly must canonicalise IDENTICALLY to that
    double, or every ordinary integer reads as a divergence. An int it cannot
    hold is the real finding (2^53+1) and keeps its exact decimal."""
    try:
        d = float(v)
    except OverflowError:
        return "I:" + str(v)
    return "d:" + bits(d) if d == v else "I:" + str(v)


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
    (b"-0",
     "signed zero: CPython yields int 0 (bits 0000...), the other side -0.0 (bits 8000...). "
     "Object.is(-0,0) is false and 1/-0 is -Infinity, so the sign is observable. Found only "
     "AFTER the canonicaliser was fixed -- the old one spelled both '0' and called it agreement"),
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
    (b"1.0",                          "integral float"),
    (b"[1e-400]",                     "underflow to zero"),
    (('"' + BS + '/"').encode(),      "escaped solidus"),
]


# CONTROLS ON THE COMPARISON FUNCTION ITSELF, not on JSON. Every group above
# samples interesting INPUTS; none of them tested whether canon() renders equal
# values equally. That gap shipped a false positive on 1e-7, where CPython repr
# gives 1e-07 and JS String gives 1e-7 for identical bits. Named by
# margin-lantern in c51001: "a passing control set can still leave the
# comparison function itself as the next place to search."
#
# Each of these is a value the two languages SPELL differently and must still
# canonicalise identically. They must all agree.
CANON = [
    (b"1e-7",                    "the shipped false positive: repr 1e-07 vs String 1e-7"),
    (b"-1e-7",                   "same, negative"),
    (b"1e-5",                    "repr 1e-05 vs String 0.00001 -- different NOTATION, not just width"),
    (b"1e16",                    "CPython switches to exponential here, JS does not until 1e21"),
    (b"1e17",                    "still decimal in JS, exponential in CPython"),
    (b"1e21",                    "both exponential, but only by coincidence of thresholds"),
    (b"1.5e300",                 "large finite"),
    (b"5e-324",                  "smallest denormal"),
    (b"1.7976931348623157e308",  "largest finite double"),
    (b"0.1",                     "not exactly representable"),
    (b"-0.1",                    "negative, not exactly representable"),
    (b"123456789.123456789",     "precision loss on both sides, identically"),
    (b"1.0",                     "integral float must match the integer path"),
    (b"9007199254740992",        "2^53: exactly representable, must canonicalise AS the double"),
    (b"[1e-7,1e-5,1e16]",        "array branch"),
    (b'{"a":1e-7,"b":1e21}',     "object branch"),
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
        bad += run(CANON, "COMPARISON-FUNCTION controls - equal values must canonicalise equally:", "quiet")
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
