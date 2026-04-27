# CHORUS

**AI-Enabled Public Affairs Training & Audience Simulation**
App **#29 / 34** — MDM 2026 LOGCOM AI Forum Hackathon.

> "Every public statement meets five audiences. CHORUS rehearses all five before you press send."

## What it does

CHORUS is a multi-persona PA/IO training simulator for U.S. Marine Public Affairs officers and Information Operations staff.

1. **Pick a scenario** — three ship: a drone strike near a host-nation civilian village, a friendly-fire investigation announcement, and a base-closure community outreach.
2. **Draft a 200–500 word public statement** — a realistic baseline draft pre-fills the textarea so the demo lights up immediately.
3. **Simulate 5 audiences** — CHORUS picks a balanced panel from a 15-persona library across 3 audience tiers (domestic media & oversight, host-nation & coalition, adversary / contested IE) and runs each one in parallel via a strict-schema JSON call (`shared.kamiwaza_client.chat_json`):
   ```json
   {
     "persona_id": "...",
     "perceived_message": "1-line of how they'd interpret",
     "trust_delta": -10,
     "narrative_risk": "LOW | MEDIUM | HIGH",
     "predicted_action": "share | challenge | ignore | escalate | counter-message",
     "key_concerns_raised": ["..."]
   }
   ```
4. **Generate the Message Effectiveness Brief** — a Kamiwaza-deployed hero model writes a one-page brief: BLUF, audience-by-audience scorecard, what worked, what backfired, and paste-ready suggested revisions.

The persona cards render in a 5-column grid color-coded by trust delta. Suggested revisions sit in an accordion under the brief.

## Mission frame

This app implements the LOGCOM-published use case **"AI-Enabled Public Affairs Training & Audience Simulation"**. PA/IO is the connective tissue between Stand-In Forces and the political environment they operate in. Every public statement is read by domestic media, by host-nation civil society, by coalition partners, and by adversary IO cells. CHORUS is the rehearsal room.

## Persona library (synthetic)

15 reusable persona cards across 3 audience tiers. **No real persons.** Methodology is the public LLM-persona-simulation pattern from Park et al. 2024, *Generative Agent Simulations of 1,000 People*, [arXiv:2403.20252](https://arxiv.org/abs/2403.20252).

Tier 1 — Domestic media & oversight
  - P01 local-base press journalist
  - P02 SASC professional staff
  - P03 veteran-community Substack influencer
  - P04 deployed-Marine spouse / FRG admin
  - P05 Gold Star Family advocacy lead

Tier 2 — Host-nation & coalition
  - P06 host-nation civic leader (mayor)
  - P07 host-nation national press correspondent
  - P08 coalition-partner PA officer (NATO O-4)
  - P09 international humanitarian NGO field director
  - P10 host-nation religious / community elder

Tier 3 — Adversary / contested IE
  - P11 foreign adversary IO analyst
  - P12 coordinated inauthentic-behavior network operator
  - P13 domestic conspiracy-influencer node
  - P14 adversary-aligned third-country parliamentarian
  - P15 neutral OSINT analyst

## Run it

```bash
# 1. install (once)
python3 -m pip install -r requirements.txt

# 2. generate synthetic data + precompute cached briefs
python3 data/generate.py

# 3. start the app on port 3029
streamlit run src/app.py \
  --server.port 3029 \
  --server.headless true \
  --server.runOnSave false \
  --server.fileWatcherType none \
  --browser.gatherUsageStats false
```

Open http://localhost:3029. Pick a scenario, edit the draft, click **SIMULATE 5 AUDIENCES**.

## Demo arc

See `demo-script.md` for the 90-second narrator script and `videos/chorus-demo.mp4` for the captioned recording.

## Kamiwaza deploy (default) — OpenAI fallback (dev only)

Every LLM call routes through `shared.kamiwaza_client`. **Default deploy target is a Kamiwaza-hosted vLLM endpoint** — set `KAMIWAZA_BASE_URL` and the same code runs inside the wire with zero edits to `agent.py`:

```bash
# production / on-prem (default) — Kamiwaza-deployed model, behind the wire
export KAMIWAZA_BASE_URL=https://kamiwaza.local/api/v1
export KAMIWAZA_API_KEY=...

# dev fallback only — public OpenAI for laptop iteration
export OPENAI_API_KEY=sk-...
```

Kamiwaza Stack components the app leans on by design:
- **Inference Layer** (vLLM) — N parallel persona reactions + the hero brief.
- **Inference Mesh** — could route adversary-tier persona simulation to an isolated cluster while domestic-tier runs on the edge.
- **App Garden** — drop-in delivery target for PA training units.

## Scoring tie-back

See `PRD.md` for the mapping against the five judging axes.

## Layout

```
apps/29-chorus/
├── data/
│   ├── generate.py          # seeded synthetic persona + scenario generator
│   ├── load_real.py         # real-data ingestion stub
│   ├── personas.json        # 15 reusable persona cards
│   ├── scenarios.json       # 3 training scenarios
│   └── cached_briefs.json   # 3 pre-computed sample bundles
├── src/
│   ├── agent.py             # multi-persona pipeline (chat_json fan-out + hero chat)
│   └── app.py               # Streamlit UI (port 3029)
├── tests/
│   └── record-demo.spec.ts
├── videos/
│   └── chorus-demo.mp4      # captioned demo
├── demo-script.md
├── demo-script.json         # Playwright-emitted caption timeline
├── PRD.md
├── README.md
├── requirements.txt
├── playwright.config.ts
├── package.json
├── .env.example
└── STATUS.txt
```

**Footer:** *Powered by Kamiwaza · 100% Data Containment — Nothing ever leaves your accredited environment.*
