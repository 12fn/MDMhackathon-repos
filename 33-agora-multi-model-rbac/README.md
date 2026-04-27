# AGORA — Role-Aware AI Support Agents

**App #33 / 34** for the **MARCORLOGCOM AI Forum Hackathon (MDM 2026)**
**Codename:** AGORA
**Use case (LOGCOM portal verbatim):** *Multi-Model JIT Context+Role-Aware AI Support Agents for web-based Ecosystems.*
**Dataset:** synthetic role/permission tree + 60-doc help corpus across LMS / CMS / BBB / Keycloak.

## What it does

Marines and DoD civilians use a web ecosystem with SSO across many apps. They have **different roles in different apps** — often different roles inside parts of one app. A normal AI chatbot either leaks privileged content or refuses everything. AGORA does neither.

The hero AI move:

1. **Persona switcher** in the sidebar — 4 demo personas with realistic role/ABAC trees:
   - **PvtJoe** — boot-camp LMS student (UNCLASS, MCRD-SD).
   - **SgtJane** — unit instructor / SNCO (CUI, 1st-MLG).
   - **CaptDoe** — battalion S-3 approver (CUI, 2/1, I-MEF).
   - **Civilian (Quinn)** — TECOM SETA contractor (UNCLASS, vendor realm).
2. User asks any question. AGORA:
   - `chat_json` parses intent + required role tier.
   - Authorizes every one of the 60 docs against the persona's RBAC + ABAC (role rank, classification, scope).
   - `embed()` over the corpus, **cosine retrieves top-3 from the *authorized* set only**.
   - `chat()` answers using ONLY the authorized snippets, with inline `[DOC-NNN]` citations.
3. **Live permission audit** sidebar shows exactly which docs were excluded by ABAC/RBAC and the *reason* — the explainable governance moment. Switch persona, re-ask, watch denials flip to citations.

Cache-first: 3 scenarios are pre-answered for every persona at `data/cached_briefs.json` so the demo is snappy. The "Ask AGORA" button always re-runs live.

## Run (Kamiwaza-first; OpenAI fallback)

```bash
cd apps/33-agora
pip install -r requirements.txt
cp .env.example .env  # or rely on the repo-root .env

# Primary: Kamiwaza-deployed model (vLLM behind OpenAI-compat surface)
export KAMIWAZA_BASE_URL=https://kamiwaza.local/api/v1
export KAMIWAZA_API_KEY=...

# Fallback: OpenAI direct (uses repo-root .env)

python data/generate.py            # personas + corpus + embeddings + cached briefs
streamlit run src/app.py \
  --server.port 3033 --server.headless true \
  --server.runOnSave false --server.fileWatcherType none \
  --browser.gatherUsageStats false
```

Open <http://localhost:3033>.

## Layout

```
apps/33-agora/
├── README.md
├── PRD.md
├── requirements.txt
├── .env.example
├── data/
│   ├── generate.py          # personas + corpus + embeddings + cached briefs
│   ├── load_real.py         # real-data ingestion stub
│   ├── personas.json        # 4 personas, role/ABAC trees
│   ├── corpus.jsonl         # 60 doc chunks across LMS/CMS/BBB/Keycloak
│   ├── corpus_ids.json
│   ├── embeddings.npy       # cosine-normalized
│   └── cached_briefs.json   # pre-computed scenario answers per persona
├── src/
│   ├── retrieval.py         # ABAC/RBAC authorize + intent parse + render
│   └── app.py               # Streamlit UI (persona switcher + audit panel)
├── tests/record-demo.spec.ts
├── playwright.config.ts
├── demo-script.md
├── demo-script.json         # cue timeline (Playwright-emitted)
├── videos/
│   └── agora-demo.mp4
└── STATUS.txt
```

## Real-data swap

Drop a Keycloak realm export + the four apps' help-content into a directory and point `REAL_DATA_DIR` at it. The schema each file must produce is documented in `data/load_real.py` — re-running `python data/generate.py` rebuilds the embedding cache. Zero agent code change.
