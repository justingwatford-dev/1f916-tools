// Node side of the differential JSON checker. Reads the candidate as RAW BYTES
// on stdin, because many interesting inputs are invalid UTF-8, BOM-prefixed, or
// carry unpaired surrogates, and a text-oriented harness cannot express those.
const chunks = [];
process.stdin.on("data", d => chunks.push(d));
process.stdin.on("end", () => {
  const buf = Buffer.concat(chunks);
  const text = buf.toString("utf8");
  const lossy = !Buffer.from(text, "utf8").equals(buf);
  let out;
  try {
    out = { accepted: true, lossy, canon: canon(JSON.parse(text)) };
  } catch (e) {
    out = { accepted: false, lossy, error: String(e.name) };
  }
  process.stdout.write(JSON.stringify(out));
});
function canon(v) {
  if (v === null) return "null";
  if (typeof v === "boolean") return v ? "true" : "false";
  if (typeof v === "number") return "d:" + bits(v);
  if (typeof v === "string") return "s:" + cps(v);
  if (Array.isArray(v)) return "[" + v.map(canon).join(",") + "]";
  const ks = Object.keys(v).sort();
  return "{" + ks.map(k => cps(k) + ":" + canon(v[k])).join(",") + "}";
}
// A double's canonical form is its 64 IEEE754 bits, never its decimal spelling.
// Comparing spellings made 1e-7 read as a divergence: CPython repr gives 1e-07
// and JS String gives 1e-7 for the same value. Found by margin-lantern, c51001.
// Signed zero is kept DISTINCT here, matching Object.is(-0, 0) === false; the
// other side documents the same policy as an explicit constant.
function bits(x) {
  const b = Buffer.alloc(8);
  b.writeDoubleBE(x, 0);
  return b.toString("hex");
}
// Strings compare as code point sequences. Serialising them instead makes the
// checker fire on ensure_ascii differences, which is agreement dressed as a find.
function cps(s) { return [...s].map(c => c.codePointAt(0)).join("."); }
