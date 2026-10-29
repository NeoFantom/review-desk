#!/usr/bin/env bash
# Regenerate docs/img/*.png from the synthetic example (needs Chrome/Chromium).
# Works on a temporary copy, so the example folder stays clean.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
CHROME=${CHROME:-$(command -v google-chrome || command -v chromium || command -v chromium-browser)}
TMP=$(mktemp -d)
PORT=${PORT:-8797}
trap 'kill $SRV 2>/dev/null || true; rm -rf "$TMP"' EXIT

shot() {  # lang name hash
  cp "$ROOT"/examples/synthetic/{paper.tex,reviews.md,energy_error.svg} "$TMP"/
  rm -f "$TMP"/review-state.json
  printf '{"paper":"paper.tex","reviews":"reviews.md","port":%s,"lang":"%s"}' "$PORT" "$1" > "$TMP/review-desk.json"
  (cd "$TMP" && PYTHONPATH="$ROOT" exec python3 -m review_desk serve >/dev/null 2>&1) & SRV=$!
  sleep 1.5
  B=http://127.0.0.1:$PORT
  P() { curl -s -X POST -H 'Content-Type: application/json' -d "$2" "$B$1" >/dev/null; }
  P /api/comment '{"id":"R1.1","status":"revised","root_cause":"structure","root_cause_note":"The abstract names the modified energy before the text defines it.","response":"We now define the modified energy E(t)e^{γt} in the abstract and use it consistently.","changes":"Abstract, sentence 3; Sec. 2, definition of ε(t)."}'
  P /api/comment '{"id":"R1.2","status":"analyzing","root_cause":"weak_evidence"}'
  P /api/comment '{"id":"R1.3","status":"replied","root_cause":"our_error","response":"Equal cost means equal numbers of force evaluations; the abstract now says so."}'
  P /api/notes '{"text":"Say explicitly that the half steps make the composition symmetric, hence second order.","comment":"R1.2","block":"b12"}'
  curl -s "$B/api/wait?timeout=0" >/dev/null
  P /api/propose '{"title":"Add a phase-error panel","text":"Reviewer 2 asks for evidence of the factor of three. Proposal: add an inset with the phase error of both methods to Fig. 1 and quote the fitted slopes.","quote":"the splitting scheme has a smaller slope by a factor of three","comment":"R2.2"}'
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars --window-size=1600,1000 \
    --virtual-time-budget=4000 --screenshot="$ROOT/docs/img/$2.png" "$B/#$3" 2>/dev/null
  kill $SRV 2>/dev/null || true; wait $SRV 2>/dev/null || true
}

mkdir -p "$ROOT/docs/img"
shot en desk "tab=inbox"
shot en comment "tab=comments&c=R1.1"
shot zh desk-zh "tab=comments&c=R1.2"
ls -la "$ROOT/docs/img"
