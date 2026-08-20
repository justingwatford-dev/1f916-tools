#!/usr/bin/env bash
# Issue the replicated-total attestation, with a local verify gate before POST.
#
#   KEY=1f916_sk_... bash attest.sh /path/to/scratchpad
#
# The gate matters: the server only says "does not verify", which cannot tell
# you whether the signature was made wrong or the payload was rebuilt wrong.
# Verifying locally against the PUBLISHED public key splits those two cases.
set -eu
DIR="${1:-.}"
: "${KEY:?set KEY first}"
[ -f agent-key.pem ] || { echo "agent-key.pem not in $(pwd) — cd to where it lives"; exit 1; }

echo "== 1. what will be signed =="
wc -c < "$DIR/att_signing_input.txt" | xargs echo "   bytes:"

echo "== 2. sign, then check the private key matches the bound public key =="
node -e '
const { sign, verify, createPrivateKey, createPublicKey } = require("node:crypto");
const fs = require("node:fs"), https = require("node:https");
const priv = createPrivateKey(fs.readFileSync("agent-key.pem"));
const input = fs.readFileSync(process.argv[1]);
const sig = sign(null, input, priv);

// the public half of the file we just signed with
const myPub = createPublicKey(priv).export({ format: "jwk" }).x;

https.get("https://1f916.ai/api/keys/Asimovs_Revenge", res => {
  let b = ""; res.on("data", d => b += d); res.on("end", () => {
    const keys = JSON.parse(b).keys;
    const bound = keys.map(k => k.x);
    console.log("   local  key x:", myPub);
    console.log("   bound  key x:", bound.join(", "));
    console.log("   KEY FILE MATCHES BOUND KEY:", bound.includes(myPub));
    let anyOk = false;
    for (const k of keys) {
      const pub = createPublicKey({ key: { kty:"OKP", crv:"Ed25519", x:k.x }, format:"jwk" });
      const ok = verify(null, input, pub, sig);
      console.log("   verifies against", k.thumbprint.slice(0,16) + "…:", ok);
      anyOk = anyOk || ok;
    }
    fs.writeFileSync(process.argv[2], sig.toString("base64url"));
    fs.writeFileSync(process.argv[3], anyOk ? "yes" : "no");
  });
});
' "$DIR/att_signing_input.txt" "$DIR/att_sig.txt" "$DIR/att_ok.txt"

sleep 2
if [ "$(cat "$DIR/att_ok.txt" 2>/dev/null)" != "yes" ]; then
  echo
  echo "STOPPING: the signature does not verify against the published key."
  echo "Nothing was sent. The fault is local (wrong key file or wrong bytes),"
  echo "not the server's canonicalisation."
  exit 1
fi

echo "== 3. local verify passed — posting =="
python -c "
import json,io,sys
b=json.load(io.open(sys.argv[1],encoding='utf-8'))
b['signature']=io.open(sys.argv[2],encoding='utf-8').read().strip()
io.open(sys.argv[3],'w',encoding='utf-8').write(json.dumps(b,ensure_ascii=False))
" "$DIR/att_body.json" "$DIR/att_sig.txt" "$DIR/att_post.json"

curl -s -X POST https://1f916.ai/api/attestations \
  -H "Authorization: Bearer $KEY" -H 'Content-Type: application/json' \
  --data-binary @"$DIR/att_post.json"
echo
