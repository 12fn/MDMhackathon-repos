# REDLINE — CUI Auto-Tagging and Classification Assistant

> *AI Inside Your Security Boundary.*

REDLINE is a draft-document marking assistant for USMC LOGCOM. Operators
paste or upload a draft; REDLINE returns per-paragraph CUI markings,
recommended caveats, an overall Document Marking Brief, and a
SHA-256 hash-chained audit trail of every analyst decision.

Built for the **published LOGCOM use case** *"CUI Auto-Tagging and
Classification Assistant"*: an LLM-based tool that reads draft documents,
briefings, or datasets and recommends CUI markings, classification levels,
and handling caveats per **DoDM 5200.01**. Direct upstream complement to
the seeded Data Sanitization use case.

## Hero AI move

1. Per-paragraph structured-JSON marking call (`chat_json`) — each paragraph
   gets `recommended_marking`, `rationale`, `trigger_phrases`,
   `caveats_recommended`, and `confidence`.
2. Document-level **hero** call (`chat`, ~35 s budget) writes a Marking
   Brief covering the recommended overall marking, releasability call
   (NOFORN vs REL TO partners), and the explicit risk tradeoff between
   over-marking (slows coalition data sharing) and under-marking
   (compromise + spillage). **Cache-first** — pre-computed for all 4
   sample drafts, so the demo never blocks on a long LLM call.
3. **SHA-256 hash-chained** audit log of every marking decision and
   analyst CONCUR / NON-CONCUR action. Tamper-evident: every entry
   references `prev_hash`, so any alteration breaks the chain.

## Run

```bash
# 1. install (the shared kamiwaza_client picks up your provider from .env)
cd apps/28-redline
pip install -r requirements.txt

# 2. (optional) regenerate cached briefs against a real provider
python data/generate.py

# 3. start the Streamlit app on port 3028
streamlit run src/app.py \
  --server.port 3028 \
  --server.headless true \
  --server.runOnSave false \
  --server.fileWatcherType none \
  --browser.gatherUsageStats false
```

Open <http://localhost:3028>.

## Real-data plug-in

The 4 sample drafts in `sample_docs/` are **synthetic** — no real CUI/PII.
To point REDLINE at a real corpus (SharePoint export, EDMS dump, .docx
folder, DoDM 5200.01 reg corpus, etc.) implement `data/load_real.py` and
re-run `python data/generate.py` to refresh `cached_briefs.json`.

## Files

```
apps/28-redline/
├── README.md                       # this file
├── PRD.md                          # product spec + scoring tie-back
├── data/
│   ├── generate.py                 # synth data + cache builder
│   ├── load_real.py                # real-data ingestion stub
│   ├── markings_taxonomy.json      # synthetic DoDM 5200.01 categories
│   └── cached_briefs.json          # pre-analyzed for all 4 sample drafts
├── sample_docs/                    # 4 synthetic demo drafts
├── audit_logs/redline_audit.jsonl  # append-only hash-chained log
├── src/
│   ├── app.py                      # Streamlit UI (port 3028)
│   ├── audit.py                    # SHA-256 chain
│   └── marker.py                   # paragraph + document brief LLM calls
├── tests/record-demo.spec.ts       # Playwright recorder
├── playwright.config.ts
├── demo-script.md / .json
├── videos/redline-demo.mp4         # final captioned 90-s demo
├── requirements.txt
├── .env.example
└── STATUS.txt
```

## Scoring tie-back

See `PRD.md` for the per-axis breakdown.

---

**Powered by Kamiwaza** &middot; on-prem, IL5/IL6 ready, NIPR/SIPR/JWICS deployable.
