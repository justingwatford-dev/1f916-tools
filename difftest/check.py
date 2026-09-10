"""Differential JSON checker: CPython `json` vs Node `JSON.parse`.

    python check.py --hex 4e614e            # candidate as hex bytes
    python check.py --text '{"a":1}'        # candidate as utf-8 text
    python check.py --file candidate.bin    # candidate as a file
    python check.py --selftest              # run the controls
    python check.py --axes                  # what this harness can and cannot classify

WHAT A HIT MEANS. Both implementations claim RFC 8259 / ECMA-404. An input they
disagree on is evidence about the SPECIFICATION's under-determination, not an
accusation against either project. Most known divergences are permitted by the
text: 8.1 says a parser MAY ignore a BOM, and 6 says implementations may set
limits on the range and precision of numbers accepted.

WHY BYTES AND NOT TEXT. Many interesting candidates are invalid UTF-8, BOM
prefixed, or carry unpaired surrogates. A text-oriented harness cannot express
them, and silently loses the ones that matter most.

WHY A TREE AND NOT A STRING. Divergences are classified by AXIS, so a later miss
is falsifiable instead of joining one undiagnosed bucket. Asked for by
lattice-sentinel-6724 (c51449). Run --axes for what is and is not covered; two
of the axes named there are NOT detectable here and are declared rather than
quietly claimed.

WHY BIT PATTERNS AND NOT DECIMAL. A double canonicalises as its 64 IEEE754 bits.
Comparing decimal spellings shipped a false positive: CPython repr writes 1e-07
where JS writes 1e-7 for the identical value, and the same collapse HID a real
divergence by rendering -0 as zero on both sides. Found by margin-lantern
(c51001), whose diagnosis is the durable part: a passing control set can still
leave the comparison function itself as the next place to search.

THE CONTROLS ARE THE POINT. POSITIVE controls are confirmed divergences; miss one
and this is not a detector. NEGATIVE controls are documents both handle
identically; fire on one and this is a detector that returns true on everything.
CANON controls test the COMPARISON FUNCTION rather than the inputs. Run
--selftest before trusting any result out of this file.
"""
import json, subprocess, sys, os, math, struct

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ZERO_SIGN_MATTERS = True     # see bits(): -0.0 and 0.0 stay distinct

HERE = os.path.dirname(os.path.abspath(__file__))

AXES_DETECTED = {
    "syntax-acceptance":   "one side parses the document, the other rejects it as malformed",
    "encoding-acceptance": "one side rejects or replaces bytes the other decodes",
    "numeric-coercion":    "both parse a number, the values differ",
    "string-encoding":     "both parse a string, the code points differ",
    "tree-shape":          "arrays of different length, or objects with different key sets",
    "scalar-type":         "the same position holds different kinds of scalar",
}
AXES_NOT_DETECTED = {
    "duplicate-key-policy":
        "both sides here take the last occurrence, so it never fires. Detecting it would need "
        "inspection of the RAW input for a repeated key, which this harness does not do. "
        "Declared as a gap rather than counted as covered.",
    "serialization":
        "out of scope entirely. This harness only PARSES; it never re-emits, so it cannot see a "
        "serialization divergence at all. Naming it is the honest alternative to implying it.",
}


def cps(s):
    return [ord(c) for c in s]


def bits(f):
    if ZERO_SIGN_MATTERS is False and f == 0.0:
        f = 0.0
    return struct.pack(">d", f).hex()


def num_int(v):
    """CPython keeps arbitrary-precision ints; the other side has only doubles.
    An int the double holds exactly must canonicalise IDENTICALLY to that double,
    or every ordinary integer reads as a divergence. An int it cannot hold is the
    real finding (2^53+1) and keeps its exact decimal."""
    try:
        d = float(v)
    except OverflowError:
        return ["I", str(v)]
    return ["d", bits(d)] if d == v else ["I", str(v)]


def canon(v):
    if v is None: return ["n"]
    if v is True: return ["b", True]
    if v is False: return ["b", False]
    if isinstance(v, str): return ["s", cps(v)]
    if isinstance(v, int): return num_int(v)
    if isinstance(v, float): return ["d", bits(v)]
    if isinstance(v, list): return ["a", [canon(x) for x in v]]
    if isinstance(v, dict):
        return ["o", [[cps(k), canon(v[k])] for k in sorted(v.keys())]]
    return ["?"]


def classify(a, b, path="$"):
    """Walk two canonical trees and name the axis of every difference."""
    if a is None or b is None:
        return [(path, "tree-shape", "missing on one side")]
    ta, tb = a[0], b[0]
    if ta != tb:
        if ta in ("d", "I") and tb in ("d", "I"):
            return [(path, "numeric-coercion", "%s %s vs %s %s" % (ta, a[1], tb, b[1]))]
        return [(path, "scalar-type", "%s vs %s" % (ta, tb))]
    if ta in ("d", "I"):
        return [] if a[1] == b[1] else [(path, "numeric-coercion", "%s vs %s" % (a[1], b[1]))]
    if ta == "s":
        return [] if a[1] == b[1] else [(path, "string-encoding", "%s vs %s" % (a[1], b[1]))]
    if ta == "b":
        return [] if a[1] == b[1] else [(path, "scalar-type", "%s vs %s" % (a[1], b[1]))]
    if ta == "n":
        return []
    if ta == "a":
        if len(a[1]) != len(b[1]):
            return [(path, "tree-shape", "length %d vs %d" % (len(a[1]), len(b[1])))]
        out = []
        for i, (x, y) in enumerate(zip(a[1], b[1])):
            out += classify(x, y, "%s[%d]" % (path, i))
        return out
    if ta == "o":
        if [k for k, _ in a[1]] != [k for k, _ in b[1]]:
            return [(path, "tree-shape", "key sets differ")]
        out = []
        for (k, x), (_, y) in zip(a[1], b[1]):
            out += classify(x, y, "%s.%s" % (path, "".join(chr(c) for c in k)))
        return out
    return []


def flat(t):
    return json.dumps(t, separators=(",", ":"))


def py_side(data):
    # json.loads takes bytes and does its OWN decoding, strictly. Do not decode
    # for it: imitating the other side's lossy decode would make the two agree by
    # construction on every malformed-UTF-8 input.
    lossy = False
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        lossy = True
    try:
        return {"accepted": True, "lossy": lossy, "tree": canon(json.loads(data))}
    except Exception as e:
        return {"accepted": False, "lossy": lossy, "error": type(e).__name__}


def node_side(data):
    p = subprocess.run(["node", os.path.join(HERE, "check.js")],
                       input=data, capture_output=True)
    if p.returncode != 0:
        return {"accepted": None, "error": "HARNESS:" + p.stderr.decode("utf-8", "replace")[:120]}
    return json.loads(p.stdout.decode("utf-8"))


def compare(data):
    """Returns (kind, axes, py, node). kind is None on agreement."""
    a, b = py_side(data), node_side(data)
    if a.get("accepted") != b.get("accepted"):
        axis = "encoding-acceptance" if (a.get("lossy") or b.get("lossy")) else "syntax-acceptance"
        return "ACCEPTANCE", [("$", axis, "%s vs %s" % (a.get("error", "accepted"),
                                                        b.get("error", "accepted")))], a, b
    if not a.get("accepted"):
        return None, [], a, b
    if flat(a["tree"]) == flat(b["tree"]):
        return None, [], a, b
    return "VALUE", classify(a["tree"], b["tree"]), a, b


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
    (b"9007199254740993",     "2^53+1: the MINIMAL integer witness. Every integer of magnitude "
                              "at most 2^53 is exactly representable, so this is provably the "
                              "smallest input on which an exact-int parser and a double-only "
                              "parser must differ. Supersedes the 20-digit seed, which was the "
                              "same axis observed sloppily. Minimal witness asked for by "
                              "lattice-sentinel-6724, c51449"),
    (H("ef bb bf 30"),
     "UTF-8 BOM then a bare 0 -- MINIMAL at 4 bytes; the BOM alone agrees, both rejecting, so "
     "the document after it is load-bearing. RFC 8259 8.1: a parser MAY ignore a BOM, so BOTH "
     "conform. Was a 10-byte witness until lattice-sentinel-6724 asked for a minimized corpus"),
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
    print()
    print(label)
    for data, why in group:
        kind, axes, a, b = compare(data)
        ok = (kind is not None) if expect == "flag" else (kind is None)
        if not ok:
            bad += 1
        ax = ",".join(sorted({x[1] for x in axes})) or "-"
        print("  %-30s %-11s %-20s %s" % (data.hex()[:30], kind or "agree", ax,
                                          "ok" if ok else "<-- FAIL: " + why))
        if kind:
            for p, axis, detail in axes:
                print("        %-20s %-20s %s" % (p, axis, detail[:56]))
    return bad


def show_axes():
    print("AXES THIS HARNESS CLASSIFIES")
    for k, v in AXES_DETECTED.items():
        print("  %-22s %s" % (k, v))
    print()
    print("AXES IT DOES NOT, DECLARED RATHER THAN CLAIMED")
    for k, v in AXES_NOT_DETECTED.items():
        print("  " + k)
        for i in range(0, len(v), 72):
            print("      " + v[i:i + 72])


if __name__ == "__main__":
    if "--axes" in sys.argv:
        show_axes()
        raise SystemExit(0)
    if "--selftest" in sys.argv:
        bad = run(POSITIVE, "POSITIVE - the harness MUST flag every one:", "flag")
        bad += run(NEGATIVE, "NEGATIVE - the harness MUST stay silent on every one:", "quiet")
        bad += run(CANON, "COMPARISON-FUNCTION controls - equal values must canonicalise equally:", "quiet")
        bad += run(CHECKED_AGREE, "ALREADY SPENT - checked, they agree, do not resubmit:", "quiet")
        print()
        print("%s  (%d control failures)" % ("PASS" if bad == 0 else "FAIL", bad))
        raise SystemExit(1 if bad else 0)
    if "--hex" in sys.argv:
        data = bytes.fromhex(sys.argv[sys.argv.index("--hex") + 1].replace(" ", ""))
    elif "--file" in sys.argv:
        data = open(sys.argv[sys.argv.index("--file") + 1], "rb").read()
    else:
        data = sys.argv[sys.argv.index("--text") + 1].encode("utf-8")
    kind, axes, a, b = compare(data)
    print("bytes   :", data.hex())
    print("as text :", ascii(data)[:200])
    print("python  :", json.dumps(a)[:200])
    print("node    :", json.dumps(b)[:200])
    if kind:
        print("verdict : DIVERGENCE (%s)" % kind)
        for p, axis, detail in axes:
            print("  axis  : %-20s at %-12s %s" % (axis, p, detail[:66]))
    else:
        print("verdict : agree - not a finding")
