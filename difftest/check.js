// Node side of the differential JSON checker. Reads the candidate document as
// RAW BYTES on stdin -- not text -- because a large share of the interesting
// inputs are invalid UTF-8, BOM-prefixed, or contain unpaired surrogates, and a
// text-oriented harness cannot even express those.
const chunks = [];
process.stdin.on("data", d => chunks.push(d));
process.stdin.on("end", () => {
  const buf = Buffer.concat(chunks);
  const text = buf.toString("utf8");
  // Did decoding lose information? Buffer.toString substitutes U+FFFD silently.
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
  if (typeof v === "number") return Number.isFinite(v) ? num(v) : "NONFINITE";
  if (typeof v === "string") return "s:" + cps(v);
  if (Array.isArray(v)) return "[" + v.map(canon).join(",") + "]";
  const ks = Object.keys(v).sort();
  return "{" + ks.map(k => cps(k) + ":" + canon(v[k])).join(",") + "}";
}
// Compare strings as code point sequences. Serialising them instead makes the
// checker fire on ensure_ascii differences, which is agreement dressed as a find.
function cps(s) { return [...s].map(c => c.codePointAt(0)).join("."); }
function num(v) { return Number.isInteger(v) && Math.abs(v) < 1e21 ? v.toFixed(0) : String(v); }
