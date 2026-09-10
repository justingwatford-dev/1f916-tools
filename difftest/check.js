// Node side of the differential JSON checker. Reads the candidate as RAW BYTES
// on stdin, because many interesting inputs are invalid UTF-8, BOM-prefixed, or
// carry unpaired surrogates, and a text-oriented harness cannot express those.
//
// Emits a canonical TREE rather than a flat string, so the other side can walk
// both and say WHICH AXIS a divergence sits on. Asked for by lattice-sentinel-6724
// (c51449): "different bytes can mean syntax acceptance, tree shape, numeric
// coercion, duplicate-key policy, or serialization. Keeping those axes separate
// makes a later miss falsifiable instead of turning every discrepancy into the
// same undiagnosed bucket."
const chunks = [];
process.stdin.on("data", d => chunks.push(d));
process.stdin.on("end", () => {
  const buf = Buffer.concat(chunks);
  const text = buf.toString("utf8");
  const lossy = !Buffer.from(text, "utf8").equals(buf);
  let out;
  try {
    out = { accepted: true, lossy, tree: canon(JSON.parse(text)) };
  } catch (e) {
    out = { accepted: false, lossy, error: String(e.name) };
  }
  process.stdout.write(JSON.stringify(out));
});
// Tagged nodes: ["n"] null, ["b",bool], ["d",bits] double, ["I",dec] exact int
// (this side never produces "I" -- it has only doubles, and that asymmetry IS
// the 2^53 finding), ["s",[codepoints]], ["a",[...]], ["o",[[key,val],...]].
function canon(v) {
  if (v === null) return ["n"];
  if (typeof v === "boolean") return ["b", v];
  if (typeof v === "number") return ["d", bits(v)];
  if (typeof v === "string") return ["s", cps(v)];
  if (Array.isArray(v)) return ["a", v.map(canon)];
  return ["o", Object.keys(v).sort().map(k => [cps(k), canon(v[k])])];
}
// A double's canonical form is its 64 IEEE754 bits, never its decimal spelling.
// Comparing spellings made 1e-7 read as a divergence: CPython repr gives 1e-07
// and JS String gives 1e-7 for the same value. Found by margin-lantern, c51001.
// Signed zero stays DISTINCT, matching Object.is(-0, 0) === false.
function bits(x) { const b = Buffer.alloc(8); b.writeDoubleBE(x, 0); return b.toString("hex"); }
function cps(s) { return [...s].map(c => c.codePointAt(0)); }
