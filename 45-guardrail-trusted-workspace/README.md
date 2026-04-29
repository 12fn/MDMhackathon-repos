# GUARDRAIL — Trusted Marine Workspace

**Tier-A app. Three "Other"-category LOGCOM use cases fused into one shell.**
Port: **3045**. Stack: Streamlit mono-page.

GUARDRAIL is the workspace a Marine opens when handling a draft document
that *might* be CUI. Four governance layers run in parallel:

1. **CUI Auto-Tagging** — every paragraph is marked under DoDM 5200.01 Vol 2
   (REDLINE pattern).
2. **ABAC Enforcement** — the active persona's clearance, role, caveats, and
   contractor flag determine which paragraphs render or come back as
   `REDACTED — INSUFFICIENT CLEARANCE [marking]` (NIST SP 800-162 / AGORA pattern).
3. **Browser AI Governance** — every workspace request is screened against
   known browser-AI fingerprints (Perplexity Comet, manus.im, Skyvern,
   generic AI sidekicks). Blocks fire at the workspace boundary
   (GUARDIAN pattern).
4. **Hash-chained Audit** — every event from layers 1–3 + every AI query
   is appended to a single SHA-256 hash chain. One verifiable chain across
   all four layers.

Hero AI move: a "Workspace Governance Posture Brief" written by the
Kamiwaza-deployed hero model. Cache-first per `AGENT_BRIEF_V2.md`.

## Run

```bash
cd apps/45-guardrail
pip install -r requirements.txt
python data/generate.py                       # synth + cache hero briefs
streamlit run src/app.py \
  --server.port 3045 \
  --server.headless true \
  --server.runOnSave false \
  --server.fileWatcherType none \
  --browser.gatherUsageStats false
# open http://localhost:3045
```

## Demo arc

1. Cold open — "GUARDRAIL. Four layers, one chain."
2. Switch personas and watch the same intel summary re-redact in real time.
3. Stream the browser intercept feed — watch Comet and manus.im get blocked.
4. Ask the workspace AI a question — only authorized paragraphs are cited.
5. Open the audit chain — every layer's events live in one chain.
6. Posture brief streams (cache-first, hero output).
7. Closer — `KAMIWAZA_BASE_URL` keeps the whole workspace inside the SCIF.

## Personas

| Persona | Clearance | Highlights |
|---|---|---|
| Pvt Joe Mason | SECRET | No NOFORN, no procurement role, no need-to-know on FP |
| Sgt Jane Reyes | SECRET-NF | Holds NOFORN; intel S-2; force_protection NTK |
| Capt Avery Doe | TS-SCI | OCA-equivalent reviewer; procurement role; NOFORN + FVEY |
| Quinn Park (Contractor) | SECRET (need-to-know) | TECOM SETA — clamped to CUI; no NOFORN; no FED ONLY |

## Real-data plug-in

`data/load_real.py` documents five real-data hooks:

- `REAL_CUI_DIR` — directory of `.txt`/`.docx`/`.pdf` (SharePoint export of a
  III MEF / LOGCOM working drafts library).
- `REAL_DTS_PATH` — DTS-shape voucher records (CSV).
- `REAL_LMS_PATH` — MarineNet / Moodle export of courses + transcripts (JSONL).
- `REAL_BROWSER_EVENTS` — Splunk / Sentinel export of intercepted browser
  activity (JSONL — same shape as `data/browser_events.jsonl`).
- `REAL_KEYCLOAK_REALM` — Keycloak realm-export JSON (users + role mappings).

Drop a path, re-run `python data/generate.py`, and the workspace picks up
real markings, real personas, real intercepts.

## Authority anchors

- **DoDM 5200.01 Vol 2** — CUI marking (per-paragraph banners + caveats)
- **32 CFR Part 2002** — CUI Program
- **NIST SP 800-162** — Attribute-Based Access Control
- **DoDD 5230.24** — Distribution / CTI handling
- **DoDD 5205.02E** — OPSEC indicators (FPCON, vulnerability, manning)
- **FAR 3.104** — Procurement / source-selection sensitive information
- **Privacy Act of 1974 / DoD 5400.11-R** — PII handling
- **Real browser-AI products tracked** — Perplexity Comet, manus.im,
  Skyvern (and generic `X-AI-Assistant` / extension markers)

## On-prem story

Set `KAMIWAZA_BASE_URL` (and `KAMIWAZA_API_KEY`) and the same code routes
through a vLLM-served model inside your accredited boundary. IL5/IL6 ready,
NIPR / SIPR / JWICS deployable, DDIL-tolerant, multi-provider via the shared
client. Powered by Kamiwaza.
