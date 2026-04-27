# STOCKROOM — Inventory Control Management

> **AI-augmented relational inventory for the USMC supply NCO.**
> Replaces the LOGCOM "5,000 items across disconnected Excel docs" problem
> with a single filterable table, natural-language query, and a one-page
> Readiness & Lateral Transfer Brief.

App `22-stockroom` of the LOGCOM MDM 2026 hackathon portfolio.
**Port: 3022 (Streamlit mono).**

## Mission frame

Verbatim from the LOGCOM published use case:

> "Current inventory management procedures lack a centralized, relational
> database, forcing personnel to manually track over 5,000 items daily across
> disconnected Excel documents. Looking for an interactive application."

STOCKROOM **is** that interactive application.

## Hero AI move

1. **NL → filter spec.** A user types *"show me all sensitive items not
   lateral-transferred in 60 days"*. STOCKROOM uses `chat_json` (structured
   output) to translate that into a JSON filter spec, runs it against the
   5,000-item DataFrame, and renders the matched rows. The parsed spec is
   visible to the user — no opaque magic.
2. **Hero brief.** The **Readiness & Lateral Transfer Brief** is a polished
   BLUF / overdue / NMC / lateral-transfer / recommended-actions document
   drafted by the hero `gpt-5.4` model. Three pre-cached scenarios (routine,
   pre-deploy, post-IG) load instantly; "Regenerate" fires the live hero
   call under a 35s wall-clock timeout with a deterministic fallback.
3. **Audit log.** Every interaction lands in an append-only
   `data/transactions.jsonl`. Production-grade pattern; ReBAC-ready.

## Run

```bash
cd apps/22-stockroom
pip install -r requirements.txt
python data/generate.py        # seed synth + precompute hero briefs
streamlit run src/app.py \
  --server.port 3022 \
  --server.headless true \
  --server.runOnSave false \
  --server.fileWatcherType none \
  --browser.gatherUsageStats false
```

Visit **http://localhost:3022**.

## Real-data plug-in

The synthetic dataset mirrors the column shape of the LOGCOM ICM workbook.
To plug in real data:

```bash
export REAL_DATA_PATH=/abs/path/to/icm-workbook.xlsx
```

`data/load_real.py` does the case-insensitive column rename and the
derived-column math. The Streamlit app picks it up automatically.

Required columns (case-insensitive):
- NSN, Nomenclature, Quantity / OnHand, Required (optional)
- Location / Bin, Responsible Marine
- Sensitivity (ROUTINE/SENSITIVE/CCI/ARMS/HAZMAT)
- Last Inventoried, Last Lateral Transfer, Condition Code

## Stack

- Python 3.10+, Streamlit 1.30+
- pandas + openpyxl for Excel ingest
- `shared/kamiwaza_client` (`chat`, `chat_json`) — multi-provider
  (Kamiwaza / OpenAI / OpenRouter / Anthropic / OpenAI-compat)
- Cache-first hero pattern with `concurrent.futures` watchdog (35s timeout
  + deterministic fallback)

## On-prem story

Set `KAMIWAZA_BASE_URL=https://kamiwaza.local/api/v1` and the same code
points at on-prem inference. **100% data containment.** Air-gapped, IL5/IL6
ready, NIPR / SIPR / JWICS compatible.

## Powered by Kamiwaza
