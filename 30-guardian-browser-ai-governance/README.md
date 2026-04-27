# GUARDIAN

**Browser Based Agent Governance** — detect and govern third-party browser AI
assistants (Perplexity Comet, manus.im, generic browser extensions, headless
agents) interacting with internal LOGCOM web apps. Protect CUI / PII / PHI
from screen-reading and silent action by browser-resident AI.

> *Built for altitude, not just output.*

## Pitch

Marines run their work in browsers — and modern browsers ship with their own
AI assistants that can read every form on screen and submit it on the user's
behalf. None of those assistants are accredited for CUI. GUARDIAN is the
middleware policy plane that tells the difference between a human and a Comet
sidebar agent in real time, blocks the agent, redacts the PII, and writes a
SHA-256 hash-chained audit entry every accreditor will love.

## Hero AI move

Two-step structured-output chain on a Kamiwaza-deployed model:

1. **Per-event** `chat_json` returns a strict JSON policy decision —
   `agent_detected`, `confidence`, `signals_observed`, `policy_action`,
   `rationale` — in under two seconds, then appends a hash-chained audit entry.
2. **Per-shift** hero `chat` (35s wall-clock, cache-first) drafts a
   "Browser Agent Governance Posture Brief" — BLUF, top exfil vectors,
   recommended policy tightening, false-positive risk analysis. Pre-computed
   for three scenarios so the demo never sits on a spinner.

## Run

```bash
cd apps/30-guardian
pip install -r requirements.txt

# 1. Generate synthetic data + pre-compute hero briefs
python data/generate.py

# 2. Launch the console (port 3030)
streamlit run src/app.py \
  --server.port 3030 \
  --server.headless true \
  --server.runOnSave false \
  --server.fileWatcherType none \
  --browser.gatherUsageStats false
```

Open <http://localhost:3030>.

## Real-data plug-in

The synthetic events in `data/events.jsonl` mirror the shape a real
browser-side middleware (an Express middleware shim, a CDN edge worker, or a
ZTNA broker like Zscaler / Netskope) would emit. To swap in real intercepts,
implement `data/load_real.py` per its docstring and set
`REAL_DATA_PATH=/path/to/intercepts.jsonl`.

Reference data sources that fit this shape:

- Browser fingerprinting datasets (e.g. AmIUnique, FingerprintJS Pro logs)
- ZTNA / SASE access logs (Zscaler ZIA, Netskope, Cloudflare Access)
- Browser isolation telemetry (Talon, Island Browser audit)
- Custom Express / Envoy middleware emitting one JSONL row per request

## On-prem story

Set `KAMIWAZA_BASE_URL` and the same code routes inference to a vLLM-served
model inside your accredited boundary. IL5/IL6 ready, NIPR/SIPR/JWICS
deployable, DDIL-tolerant. The structured-output path uses the
OpenAI-compatible surface Kamiwaza exposes at `/v1/chat/completions`.

## Files

- `src/app.py` — Streamlit console (port 3030)
- `src/policy.py` — per-event `chat_json` decision + watchdog timeout
- `src/audit.py` — SHA-256 hash-chained append-only log
- `data/generate.py` — synth events, policies, pre-computed briefs (seed=1776)
- `data/load_real.py` — real-data ingestion stub
- `data/events.jsonl` — 100 synthetic browser intercepts
- `data/policies.json` — 8 named active policies
- `data/cached_briefs.json` — pre-computed hero briefs
- `audit_logs/guardian_audit.jsonl` — append-only chained audit

Powered by Kamiwaza.
