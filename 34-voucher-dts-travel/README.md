# VOUCHER

*DTS + Citi Manager travel-program QA agent for the unit S-1.*
**Hackathon app #34 — USMC LOGCOM AI Forum @ MDM 2026.**

> **LOGCOM published use case — Travel Program Validation:**
> "DTS (or other order writing system) and Citi Manager are heavily utilized across the Marine Corps to support Travel and vary in effectiveness of management from unit to unit based on personalities. Automate the process to the greatest extent possible. Replication and user friendliness. **It must be idiot proof.**"

VOUCHER is an idiot-proof three-button S-1 desktop app. It ingests a quarter of synthetic DTS authorization+voucher pairs and Citi Manager card statements, runs a **two-tier LLM agent** over every record, and writes a polished **Travel Program Quarterly Brief** for the unit S-1.

### Governing doctrine (cited explicitly)

- **Joint Travel Regulations (JTR)** — DoD's authoritative travel manual issued by the Defense Travel Management Office (DTMO). All authorization, voucher, and per-diem rules in VOUCHER trace back to the JTR. CONUS per-diem flows from GSA *as adopted by JTR Ch 2*; OCONUS per-diem is published by DoD/DTMO under JTR Ch 3.
- **DoDFMR Volume 9** (DoD Financial Management Regulation, Vol 9) — governs **Government Travel Charge Card (GTCC)** oversight. Non-authorized merchant-category charges and other findings are surfaced as **GTCC misuse flags per DoDFMR Vol 9 Chapter 5**.
- **DoDI 5154.31** — DTMO program lead instruction. Unit-level GTCC oversight is performed by the **Agency/Organization Program Coordinator (APC)** designated under this instruction; VOUCHER's escalation actions route to the unit APC for cardholder counseling.

Real DTS field shape is preserved verbatim in `data/dts_records.csv`: `doc_number, ta_number, traveler_edipi, traveler_name, traveler_grade, ao_edipi, ao_name, trip_purpose, trip_start, trip_end, status, total_authorized, total_voucher, mode_of_travel`. Citi Manager exports preserve the real 4-digit MCCs (no invented codes).

> **AI runtime:** This app talks to `shared.kamiwaza_client.chat_json` and `shared.kamiwaza_client.chat`, configured for a Kamiwaza-deployed model endpoint. An OpenAI-compatible endpoint is supported as a transparent fallback for local development — same code path, no app changes.

## Hero AI move

A two-tier agent over heterogeneous tabular data (one record = a fused DTS row + 1..N matching Citi card rows + a GSA per-diem row):

1. **Per-record `chat_json` validator** — typed JSON verdict per record, drawn from a fixed taxonomy of seven issue tags (`amount_mismatch`, `missing_receipt`, `rate_above_per_diem`, `non_authorized_expense`, `card_charge_no_voucher`, `voucher_no_card_charge`, `duplicate_charge`). Severity, auto-correctable flag, recommended action, and a confidence score.
2. **Hero `chat` quarterly brief** — `gpt-5.4`, 35-second wall-clock timeout, **cache-first** so the demo is instant. Falls back to mini chain, then to a deterministic baseline narrative if the LLM is unreachable.

A deterministic rule-based validator backstops both tiers. The Issues table never sits empty waiting on the model.

## Real-world data provenance (cited, not used)

This demo uses **synthetic but plausible** travel records. In production it plugs into:
- **Defense Travel System (DTS) Reporting Tool** — per-unit per-quarter authorization+voucher exports.
- **Citi Manager Government Travel Card** — per-unit transaction statements (Bank of America for some Marines — same schema).
- **GSA per-diem rate tables** — CONUS via `gsa.gov/travel/plan-book/per-diem-rates`, OCONUS via DOD JTR.

Plug-in shape is documented in `data/load_real.py`.

## Run

```bash
cd apps/34-voucher
pip install -r requirements.txt
python data/generate.py     # writes 100 DTS + 100 Citi + per-diem + 3 cached briefs
streamlit run src/app.py \
  --server.port 3034 \
  --server.headless true \
  --server.runOnSave false \
  --server.fileWatcherType none \
  --browser.gatherUsageStats false
```

Then open http://localhost:3034

## Workflow

Three buttons. That's it.

1. **Run Validation** — runs the agent over the selected unit-quarter and writes a typed JSON verdict per record.
2. **View Issues** — sortable issues table (sev / record / traveler / city / dollar exposure / recommended action / confidence) with a per-record drill-down panel that surfaces the DTS voucher lines, the linked Citi charges, and the agent's rationale.
3. **Generate Brief** — instant cached quarterly brief; "Regenerate (live)" button kicks off a fresh hero call against the Kamiwaza-deployed model.

## Files

```
apps/34-voucher/
├── README.md
├── PRD.md
├── requirements.txt
├── .env.example
├── STATUS.txt
├── data/
│   ├── generate.py            # writes the 4 data artifacts + cached briefs
│   ├── load_real.py           # real-data ingestion stub (DTS + Citi + GSA)
│   ├── dts_records.csv        # 100 synthetic DTS auth+voucher pairs
│   ├── citi_statements.csv    # 100 synthetic Citi Manager transactions
│   ├── per_diem_rates.json    # 14-city GSA-style per-diem rates
│   ├── cached_briefs.json     # 3 pre-computed unit-quarter briefs
│   └── manifest.json
├── src/
│   ├── app.py                 # Streamlit UI (port 3034)
│   └── agent.py               # validator + brief generator + baseline backstop
├── tests/record-demo.spec.ts
├── playwright.config.ts
├── demo-script.md
├── demo-script.json
└── videos/voucher-demo.mp4
```

## On-prem story

Travel financial data is **CUI**. To run VOUCHER inside an accredited environment with no data movement:

```bash
export KAMIWAZA_BASE_URL=https://kamiwaza.local/api/v1
export KAMIWAZA_API_KEY=km-...
streamlit run src/app.py --server.port 3034
```

Same Python code. Same `chat_json` / `chat` calls. Same UI. Zero internet egress.

---

Built on the Kamiwaza Stack. Powered by Kamiwaza.
