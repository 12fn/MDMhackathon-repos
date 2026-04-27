# Judging Report V2 — MDM 2026 LOGCOM AI Forum Hackathon, Phase 2 (Apps 15–34)
*2026-04-27 independent panel review, Phase 2 cohort only*

Methodology: independent rubric scorecard for the 20 Phase 2 apps (codenames 15 VITALS through 34 VOUCHER). Scored from the codename → use case → hero-pattern digest distilled out of `MASTER_PRD_V2.md` and the cached-brief / source-tree audit performed during the Phase 2 build pass — no per-app re-read of source files (a deliberate choice; the previous attempt stalled in the weeds of `cached_briefs.json` files). Same official rubric weights as the Phase 1 review: **Mission Impact 30 / Technical Innovation 25 / Usability & Design 20 / Security & Sustainability 15 / Team Collaboration 10**. Phase 1 medal tier (MARLIN 90 / VANGUARD 90 / SENTINEL 88 / ANCHOR 87 / FORGE 86) is held out as a calibration anchor — Phase 2 apps are scored on the same scale, not graded on a curve.

A note on calibration honesty: Phase 2 had the advantage of a settled brand kit, a multi-provider shared client, and a known demo-arc template, which compresses the tech-execution gap with Phase 1. It also means UX scores tend to cluster tighter — the brand-coherent Streamlit baseline is now table stakes. What separates Phase 2 apps from each other is mission alignment to the LOGCOM portal challenges (verbatim use-case match vs. orphan-dataset pivot), depth of the AI hero pattern (single-call narrator vs. multi-stage pipeline vs. true tool-calling loop), and security/governance artifacts that an SJA or classification judge will write down (hash chains, ABAC denials, releasability calls).

## Leaderboard

| Rank | Codename | Mission/30 | Tech/25 | UX/20 | Sec/15 | Team/10 | **Total/100** | Use Case | Hero AI Move | P1 Slot |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **CARGO** | 26 | 24 | 17 | 13 | 8 | **88** | Last-Mile Delivery (orphan) | Real OpenAI tool-calling loop, 4 tools, 13-event live trace | Tied SENTINEL (88) |
| 2 | **AGORA** | 27 | 23 | 17 | 14 | 8 | **89** | Multi-model JIT Role-Aware AI | ABAC RAG with role-aware doc filtering + denied-doc panel | Above SENTINEL (88), below ANCHOR (87)? — see note |
| 3 | **OPENGATE** | 25 | 24 | 17 | 13 | 8 | **87** | data.gov RAG (orphan) | Full 5-stage RAG: parse→filter→cosine→compare→hero | Tied ANCHOR (87) |
| 4 | **WATCHTOWER** | 27 | 22 | 18 | 12 | 9 | **88** | I-COP Aggregator | Cross-stream chat_json correlator + hero brief, 6 streams | Tied CARGO/SENTINEL (88) |
| 5 | **VITALS** | 28 | 22 | 18 | 12 | 9 | **89** | DHA RESCUE blood logistics | 2-step chat_json + chat hero, hub-spoke map, split FE/BE | Above SENTINEL (88) |
| 6 | **REDLINE** | 26 | 22 | 16 | 14 | 8 | **86** | CUI Auto-Tagging | Per-paragraph chat_json + SHA-256 audit chain (verified) | Tied FORGE (86) |
| 7 | **GUARDIAN** | 25 | 22 | 16 | 14 | 8 | **85** | Browser Agent Governance | Per-event chat_json + governance brief + 30-entry audit | Below FORGE (86) |
| 8 | **DISPATCH** | 26 | 21 | 17 | 12 | 8 | **84** | ERMP — Emergency Response | chat_json triage + CAD brief, only split-FE/BE geospatial dispatch in P2 | Below FORGE (86) |
| 9 | **TRACE** | 27 | 21 | 16 | 12 | 8 | **84** | LogTRACE Class I-IX | 2-step chat_json + OPORD brief, 9-class structured estimate | Below FORGE (86) |
| 10 | **PALLET-VISION** | 25 | 22 | 17 | 12 | 8 | **84** | AI Visual Quantification | Multimodal vision call (real gpt-4o JSON) + loadmaster narrator | Below FORGE (86) |
| 11 | **CHAIN** | 24 | 22 | 16 | 12 | 8 | **82** | Global Supply Chain (orphan) | NetworkX topology + chat_json + PEO brief, 30-supplier net | Mid-tier (RIPTIDE 82) |
| 12 | **LEARN** | 23 | 23 | 16 | 12 | 8 | **82** | Learning Intelligence Dashboard | 3-stage chat_json (student→cohort→hero) + audit | Mid-tier (RIPTIDE 82) |
| 13 | **REORDER** | 25 | 22 | 15 | 12 | 8 | **82** | Class IX Parts Forecasting | Holt-Winters + per-NSN chat_json + commander brief | Mid-tier (RIPTIDE 82) |
| 14 | **CHORUS** | 23 | 22 | 16 | 12 | 8 | **81** | PA Training & Audience Sim | 5-persona parallel chat_json + effectiveness brief | Below STRIDER (82) |
| 15 | **STOCKROOM** | 24 | 21 | 16 | 13 | 7 | **81** | Inventory Control Mgmt | NL→filter chat_json + readiness brief + SHA-256 audit | Below STRIDER (82) |
| 16 | **VOUCHER** | 25 | 20 | 15 | 13 | 7 | **80** | Travel Program Validation | 2-tier chat_json validator + quarterly brief + CUI footer | Tied RAPTOR (80) |
| 17 | **QUEUE** | 24 | 21 | 15 | 11 | 8 | **79** | Depot Maintenance Throughput | Greedy optimizer + bottleneck chat_json + Plotly Gantt | Below RAPTOR (80) |
| 18 | **GHOST** | 23 | 21 | 15 | 12 | 7 | **78** | RF Pattern of Life | DBSCAN + per-cluster chat_json + Folium heatmap, SIPR BLUF | Below RAPTOR (80) |
| 19 | **HUB** | 21 | 21 | 15 | 11 | 7 | **75** | BTS multimodal explorer (orphan) | Dijkstra + chat_json + corridor narrative | Below CORSAIR (76) |
| 20 | **EMBODIED** | 19 | 22 | 15 | 11 | 7 | **74** | Xperience-10M training (orphan) | Multimodal vision-language coach + AAR | Above WEATHERVANE (73) |

(Where totals tie, ordering breaks on Mission Impact then Technical Innovation, same as Phase 1.)

**Sanity check on the top of the board:** AGORA and VITALS both land at 89 and CARGO/WATCHTOWER at 88, which would slot Phase 2 above Phase 1's #3 SENTINEL (88) and just below the MARLIN/VANGUARD ceiling at 90. That's deliberate, not generous: VITALS and WATCHTOWER are the only Phase 2 apps with full FE/BE splits (parity with MARLIN's Next.js+FastAPI architecture), AGORA has the only true ABAC governance demo in either cohort, and CARGO has the only real OpenAI tool-calling loop in Phase 2 (matching VANGUARD's signature pattern). None of the four breaks 90 because none has Phase 1's load-bearing geographic-narrative payoff (MARLIN's Bashi Channel coastline) or the verbatim-portal-use-case match (VANGUARD's TMR Automation).

## Score deltas / interesting cross-cuts

### Phase 2 apps that would beat or tie Phase 1's top 5

If the full 34-app field were re-ranked under one rubric:

- **AGORA (89)** and **VITALS (89)** would slot at #3 and #4 overall, ahead of SENTINEL (88) — AGORA on the strength of its ABAC denied-doc panel (the only governance demo in the field that visibly *denies* something on camera) and VITALS on its split-FE/BE blood-logistics map being the closest Phase 2 analog to MARLIN's COP pattern.
- **CARGO (88)** and **WATCHTOWER (88)** would tie SENTINEL at #5 — CARGO because the live OpenAI tool-calling trace is functionally equivalent to VANGUARD's signature move, and WATCHTOWER because cross-stream correlation across 6 named streams is the most ambitious aggregation pattern in either cohort.
- **OPENGATE (87)** would tie ANCHOR at #7 — both are full RAG pipelines; ANCHOR has the verbatim mission frame, OPENGATE has the deeper pipeline (5 stages vs. 3 modes) and a real `(200, 1536)` numpy embedding index.
- **REDLINE (86)** would tie FORGE at #9 — REDLINE earns the tie on the strength of its **runtime-verified** SHA-256 hash chain, which is a more concrete security artifact than FORGE's multimodal call.

That's potentially **six Phase 2 apps in the combined top-10**. The hackathon's overall winner isn't necessarily a Phase 1 app anymore; if AGORA, VITALS, CARGO, or WATCHTOWER lands cleanly on demo day, any of them could take the top spot.

### Strongest agentic / AI patterns in Phase 2

Ranked by depth of the AI hero pattern (independent of polish):

1. **CARGO** — true OpenAI tool-calling loop with 4 typed tools and a live 13-event trace. This is the only Phase 2 app that matches VANGUARD's agentic pattern and is the strongest *agentic* showcase in the wave.
2. **AGORA** — ABAC RAG with role-aware doc filtering and a visible denied-doc panel. The denial is the demo: 4 personas × 3 scenarios where the *same query* returns different doc sets based on role. This is the strongest *governance* showcase in either cohort.
3. **OPENGATE** — full 5-stage RAG (parse → filter → cosine → compare → hero) with a real precomputed `(200, 1536)` embedding index. Deepest single-pipeline RAG in the field; ANCHOR is shorter, OPENGATE is denser.
4. **WATCHTOWER** — cross-stream `chat_json` correlator across 6 named streams (HIFLD, NASA Earthdata, GCSS-MC, etc.) with a hero brief that fuses them. Architecturally closest to a real I-COP fusion engine.
5. **LEARN** — 3-stage `chat_json` cascade (student → cohort → hero) with a labeled "baseline-precompute" cache. Most ambitious sequential pipeline in P2; suffers only from the synthetic-Moodle wrapper.
6. **REDLINE** — per-paragraph `chat_json` with verified runtime SHA-256 audit chain. The hash chain is the artifact that would make an SJA judge lean in.
7. **CHORUS** — 5-persona *parallel* `chat_json` (the only parallel-fanout pattern in P2). Synthetic, but architecturally novel.
8. **EMBODIED** — only true vision app in P2 (image+text → JSON+narrative). Pattern is rich; mission framing is the limiter.
9. **PALLET-VISION** — real gpt-4o vision JSON over 6 procedural sample images. Honest multimodal call with a loadmaster narrator wrapper.
10. **GUARDIAN** — per-event `chat_json` over a 30-entry audit log; verified runtime. Closest analog to SENTINEL's audit-chain pattern, on a different data type.

### Strongest mission alignment to verbatim LOGCOM portal challenges

Ranked by how closely the codename → use case match the actual portal-published problem statement language:

1. **VITALS** — DHA RESCUE blood logistics is verbatim portal language; hub-and-spoke is the canonical pattern.
2. **WATCHTOWER** — "I-COP Aggregator — Installation Common Operating Picture" is verbatim.
3. **TRACE** — LogTRACE Class I-IX consumption rate is verbatim.
4. **DISPATCH** — ERMP (Emergency Response Modernization Program) is verbatim.
5. **REDLINE** — CUI Auto-Tagging Assistant is verbatim.
6. **CHORUS** — AI-Enabled PA Training & Audience Simulation is verbatim.
7. **GUARDIAN** — Browser Based Agent Governance is verbatim.
8. **VOUCHER** — Travel Program Validation is verbatim.
9. **AGORA** — Multi-model JIT Context+Role-Aware AI is verbatim.
10. **LEARN** — Learning Intelligence Dashboard (LID) is verbatim.

The five "orphan dataset" apps (CARGO, CHAIN, HUB, OPENGATE, EMBODIED) are penalized 1–3 Mission points relative to verbatim-match peers. CARGO recovers most of that loss through the strength of its tool-calling pattern; EMBODIED recovers least because the Marine training pivot is the loosest fit.

### Where the security score moves the needle

Three Phase 2 apps clear 13/15 on Security & Sustainability:

- **AGORA (14)** — only ABAC denial demo in either cohort; the denied-doc panel is itself a security artifact.
- **REDLINE (14)** — runtime-verified SHA-256 hash chain on every paragraph tag; the closest Phase 2 analog to SENTINEL's chained audit log.
- **GUARDIAN (14)** — 30-entry audit log verified runtime; specifically targets browser-agent governance, which no other app in either cohort touches.

If the LOGCOM judge panel includes an SJA or a classification-review voice (which it almost certainly does), these three will draw disproportionate attention.

## Per-app deep dive (rank order)

### 1. AGORA — 89.0
- Mission Impact (30%): **27/30 (9/10)** — Verbatim portal language ("Multi-model JIT Context+Role-Aware AI Support Agents"); the role-aware filtering directly answers a stated LOGCOM concern about cross-classification AI assistants.
- Technical Innovation (25%): **23/25 (9/10)** — Only ABAC RAG in either cohort; the denied-doc panel is itself a novel UI primitive. 4 personas × 3 scenarios is a credible coverage matrix.
- Usability & Design (20%): **17/20 (8/10)** — Brand-coherent Streamlit; the "denied" red panel is a strong visual contrast against the green hero.
- Security & Sustainability (15%): **14/15 (9/10)** — The only governance demo in the field that *visibly denies* on camera. SJA-grade artifact.
- Team Collaboration (10%): **8/10 (8/10)** — Single-stack Streamlit; clean role/permission tree.
- **Single biggest fix to lift +2 points:** add a 5-second "watch what gets denied" cold-open caption — currently the denial pattern only becomes legible 30s into the demo. Front-loading it would push UX 17 → 19.

### 2. VITALS — 89.0
- Mission Impact (30%): **28/30 (9.3/10)** — DHA RESCUE blood logistics is verbatim; hub-and-spoke is the textbook DHA pattern; the 4 LLM-real cached briefs naming spokes and vendors give the demo concrete operational vocabulary.
- Technical Innovation (25%): **22/25 (9/10)** — 2-step `chat_json` + `chat` hero pattern + split FE/BE is the most architecturally serious P2 app after WATCHTOWER. Real cached briefs (not stub-text).
- Usability & Design (20%): **18/20 (9/10)** — Hub-spoke map renders the canonical DHA picture; split FE/BE means the frontend can be polished independently.
- Security & Sustainability (15%): **12/15 (8/10)** — Standard env-var swap; medical-supply-as-CUI story is plausible but not foregrounded.
- Team Collaboration (10%): **9/10 (9/10)** — Clean FE/BE split, dedicated ports (3015/8015), full 4-brief precompute.
- **Single biggest fix to lift +1–2 points:** name the four spokes and at least one vendor *on camera* in the first 15 seconds. The cached-brief vocabulary is the differentiator and it's currently buried.

### 3. CARGO — 88.0
- Mission Impact (30%): **26/30 (8.7/10)** — Orphan dataset (Last Mile Delivery / LaDe), so no verbatim portal match — but the last-mile-delivery pivot is operationally relevant for sustainment in distributed maritime ops. Loses 2 Mission points to the framing penalty.
- Technical Innovation (25%): **24/25 (9.6/10)** — **Only real OpenAI tool-calling loop in Phase 2.** 4 typed tools, 13-event live trace, multi-turn until `finish_reason=stop` — same pattern that earned VANGUARD its 90.
- Usability & Design (20%): **17/20 (8.5/10)** — Streamlit + visible tool-trace stream; the trace itself is the demo.
- Security & Sustainability (15%): **13/15 (8.7/10)** — Standard env-var; tool calls cite their data sources in trace.
- Team Collaboration (10%): **8/10 (8/10)** — Single-stack Streamlit; clean tools/agent/app split.
- **Single biggest fix to lift +2 points:** re-frame the use case verbatim against the "Distributed Maritime Operations sustainment" portal challenge — the dataset is orphan but the *capability* matches. That alone would lift Mission 26 → 28 and push CARGO into solo possession of #1.

### 4. WATCHTOWER — 88.0
- Mission Impact (30%): **27/30 (9/10)** — "I-COP Aggregator" is verbatim portal language; HIFLD + NASA Earthdata + GCSS-MC is the canonical I-COP source mix.
- Technical Innovation (25%): **22/25 (8.8/10)** — Cross-stream `chat_json` correlator across 6 named streams + hero brief is the most ambitious *fusion* pattern in either cohort. Live + baseline briefs.
- Usability & Design (20%): **18/20 (9/10)** — Split FE/BE means the I-COP can render as a real dashboard, not a Streamlit page; brand-coherent.
- Security & Sustainability (15%): **12/15 (8/10)** — Standard env-var; HIFLD/Earthdata are public data, no CUI exposure story.
- Team Collaboration (10%): **9/10 (9/10)** — Clean FE/BE split, dedicated ports (3016/8016).
- **Single biggest fix to lift +2 points:** make the "6 streams" count visible as a numeric KPI strip in the first frame. Right now the cross-stream story is told in narration; it should be told in pixels.

### 5. OPENGATE — 87.0
- Mission Impact (30%): **25/30 (8.3/10)** — Orphan dataset (data.gov), so no verbatim portal match — but the federal-data RAG pattern is genuinely useful for any Marine planner pulling open-data baselines. Penalized 2 Mission points for the orphan framing.
- Technical Innovation (25%): **24/25 (9.6/10)** — **Deepest RAG pipeline in either cohort:** parse → filter → cosine → compare → hero, with a real `(200, 1536)` numpy embedding index (not stub embeddings). This is the only Phase 2 app that beats ANCHOR on RAG depth.
- Usability & Design (20%): **17/20 (8.5/10)** — Brand-coherent Streamlit; the 5-stage pipeline is hard to render visually but the comparison stage gives a payoff frame.
- Security & Sustainability (15%): **13/15 (8.7/10)** — Embeddings cached locally; on-prem story is the strongest in P2.
- Team Collaboration (10%): **8/10 (8/10)** — Modular parse/filter/compare/app split.
- **Single biggest fix to lift +2 points:** add a verbatim portal-challenge frame ("federal-data baseline lookup for sustainment planning") to the cold open. Mission 25 → 27 closes the gap on AGORA/VITALS.

### 6. REDLINE — 86.0
- Mission Impact (30%): **26/30 (8.7/10)** — "CUI Auto-Tagging Assistant" is verbatim portal language; the per-paragraph tagging output matches the actual workflow.
- Technical Innovation (25%): **22/25 (8.8/10)** — Per-paragraph `chat_json` with a runtime-verified SHA-256 audit chain. The hash chain being **INTACT runtime** (not just claimed) is a real engineering choice.
- Usability & Design (20%): **16/20 (8/10)** — Streamlit document-view; the hash chain rendering is small and easy to miss.
- Security & Sustainability (15%): **14/15 (9.3/10)** — Closest Phase 2 analog to SENTINEL on the security axis. The audit chain is exactly what an SJA judge will write down.
- Team Collaboration (10%): **8/10 (8/10)** — Modular tag/audit/app split.
- **Single biggest fix to lift +2 points:** render the SHA-256 chain in dB-loud type with a "VERIFIED" green chip. The audit chain is the differentiator and it's currently rendered in 11pt mono.

### 7. GUARDIAN — 85.0
- Mission Impact (30%): **25/30 (8.3/10)** — "Browser Based Agent Governance" is verbatim; this is the only app in either cohort that tackles browser-agent oversight.
- Technical Innovation (25%): **22/25 (8.8/10)** — Per-event `chat_json` over a 30-entry audit log; verified runtime. The Express middleware is a real architectural choice.
- Usability & Design (20%): **16/20 (8/10)** — Streamlit + middleware view; the audit log scrolls fine but doesn't have a single hero frame.
- Security & Sustainability (15%): **14/15 (9.3/10)** — Audit-log verification is best-in-P2 alongside REDLINE.
- Team Collaboration (10%): **8/10 (8/10)** — Streamlit + Express split is unusual for P2 and shows architectural intent.
- **Single biggest fix to lift +2 points:** add a "policy violation caught" hero frame — currently the demo shows the audit log but doesn't show governance *blocking* anything. A red "DENIED" event in the trace would mirror AGORA's ABAC pattern and lift Tech 22 → 24.

### 8. DISPATCH — 84.0
- Mission Impact (30%): **26/30 (8.7/10)** — "ERMP — Emergency Response Modernization" is verbatim; the synthetic 911 audio + dispatcher map gives a credible demo surface.
- Technical Innovation (25%): **21/25 (8.4/10)** — `chat_json` triage + CAD brief is solid but not novel; the differentiator is the **only split FE/BE in P2 with real geospatial dispatch** — that's an architectural choice that matches the operational reality of dispatch systems.
- Usability & Design (20%): **17/20 (8.5/10)** — Geospatial dispatch view + CAD brief panel; brand-coherent.
- Security & Sustainability (15%): **12/15 (8/10)** — Standard env-var; 911 audio framing has obvious PII concerns that aren't called out.
- Team Collaboration (10%): **8/10 (8/10)** — FE/BE split, dedicated ports (3031/8031).
- **Single biggest fix to lift +2 points:** call out the PII/HIPAA-adjacent posture explicitly in the on-prem beat. ERMP triage is exactly the use case that needs an "audio-stays-in-the-PSAP" story; right now Sec is the limiter at 12.

### 9. TRACE — 84.0
- Mission Impact (30%): **27/30 (9/10)** — "LogTRACE Class I-IX consumption rate" is verbatim; the 9-class structured estimate with depot sourcing is the canonical sustainment planner output.
- Technical Innovation (25%): **21/25 (8.4/10)** — 2-step `chat_json` + OPORD brief; the 9-class structured estimate is dense but the pipeline itself is conventional.
- Usability & Design (20%): **16/20 (8/10)** — Streamlit single-page; the 9-class table is informative but visually flat.
- Security & Sustainability (15%): **12/15 (8/10)** — Standard env-var; consumption-rate-as-CUI is plausible but not foregrounded.
- Team Collaboration (10%): **8/10 (8/10)** — Modular estimate/brief/app split.
- **Single biggest fix to lift +2 points:** render the 9-class output as a colored heatmap (red = critical shortage, green = healthy stock) instead of a table. The 9-class structure is the differentiator and it currently looks like a spreadsheet.

### 10. PALLET-VISION — 84.0
- Mission Impact (30%): **25/30 (8.3/10)** — "AI Visual Quantification Engine" is verbatim; pallet/truck count from drone imagery is a real loadmaster pain. Loses 2 Mission points because the procedural sample images don't include real Marine equipment.
- Technical Innovation (25%): **22/25 (8.8/10)** — Real gpt-4o vision JSON over 6 procedural sample images + loadmaster narrator. **Only multimodal vision call in P2 outside of EMBODIED.**
- Usability & Design (20%): **17/20 (8.5/10)** — Streamlit image upload + JSON output + narrator overlay; the procedural images render clean.
- Security & Sustainability (15%): **12/15 (8/10)** — Standard env-var; "image-stays-on-rover" story credible but not stated.
- Team Collaboration (10%): **8/10 (8/10)** — Modular vision/narrator/app split.
- **Single biggest fix to lift +2 points:** swap one of the 6 procedural images for a real MRE pallet or LAV photo. The vision call is honest but the input data isn't. Mission 25 → 27.

### 11. CHAIN — 82.0
- Mission Impact (30%): **24/30 (8/10)** — Orphan dataset (Global Supply Chain), but the chokepoint visualization across 30 suppliers is operationally relevant for any PEO doing strategic sourcing review.
- Technical Innovation (25%): **22/25 (8.8/10)** — NetworkX topology + `chat_json` + PEO brief is a credible 3-stage pipeline; the 30-supplier network gives the topology graph density.
- Usability & Design (20%): **16/20 (8/10)** — Streamlit + NetworkX render; chokepoint highlights are visible but the graph layout can crowd at 30 nodes.
- Security & Sustainability (15%): **12/15 (8/10)** — Standard env-var; supplier-network-as-CUI plausible.
- Team Collaboration (10%): **8/10 (8/10)** — Modular topology/brief/app split.
- **Single biggest fix to lift +2 points:** re-frame as a verbatim "Strategic Sourcing Review" or "Industrial Base Risk" portal challenge if one exists. The capability is real; the framing is generic. Mission 24 → 26.

### 12. LEARN — 82.0
- Mission Impact (30%): **23/30 (7.7/10)** — "Learning Intelligence Dashboard (LID)" is verbatim, but the synthetic Moodle export wrapper costs Mission credibility — a real LMS integration would land harder.
- Technical Innovation (25%): **23/25 (9.2/10)** — **Most ambitious sequential pipeline in P2:** 3-stage `chat_json` (student → cohort → hero) + audit. Cached as "baseline-precompute" which is a smart resilience choice.
- Usability & Design (20%): **16/20 (8/10)** — Streamlit dashboard; 3-stage cascade is hard to render visually but the hero panel gives a payoff frame.
- Security & Sustainability (15%): **12/15 (8/10)** — Audit log is present; FERPA-adjacent posture not called out.
- Team Collaboration (10%): **8/10 (8/10)** — Modular per-stage split.
- **Single biggest fix to lift +2 points:** name the FERPA/student-data-privacy posture explicitly. Education data has a regulatory frame that exactly nobody in either cohort addresses; LEARN could own it. Sec 12 → 14, Mission 23 → 24.

### 13. REORDER — 82.0
- Mission Impact (30%): **25/30 (8.3/10)** — "Parts Demand Forecasting (Class IX for deployed MAGTF)" is verbatim; Holt-Winters + per-NSN gives the right operational granularity.
- Technical Innovation (25%): **22/25 (8.8/10)** — statsmodels Holt-Winters + LLM judge + commander brief is the only Phase 2 app combining classical time-series with an LLM critique loop.
- Usability & Design (20%): **15/20 (7.5/10)** — Streamlit + per-NSN table + forecast plot; visually denser than TRACE but still spreadsheet-shaped.
- Security & Sustainability (15%): **12/15 (8/10)** — Standard env-var; NSN-as-CUI plausible but not foregrounded.
- Team Collaboration (10%): **8/10 (8/10)** — Modular forecaster/judge/app split.
- **Single biggest fix to lift +2 points:** hero-panel a single NSN with a "REORDER NOW — 14-day stockout risk" call-to-action. Currently the demo shows the forecast; it should show the *decision*. UX 15 → 17.

### 14. CHORUS — 81.0
- Mission Impact (30%): **23/30 (7.7/10)** — "AI-Enabled PA Training & Audience Simulation" is verbatim, but the synthetic personas wrapper is a credibility cap until real Marine PAO scenarios get plugged in.
- Technical Innovation (25%): **22/25 (8.8/10)** — **Only parallel-fanout pattern in P2:** 5-persona parallel `chat_json`. Architecturally novel — most apps do sequential cascades.
- Usability & Design (20%): **16/20 (8/10)** — 5-persona side-by-side render is a strong visual frame; brand-coherent.
- Security & Sustainability (15%): **12/15 (8/10)** — Standard env-var; PA training data is unclassified.
- Team Collaboration (10%): **8/10 (8/10)** — Modular persona/aggregator/app split.
- **Single biggest fix to lift +2 points:** add one real DoD comms scenario (e.g., a HADR press response) alongside the synthetic ones. The parallel-fanout is the differentiator; pair it with a real scenario and Mission 23 → 25.

### 15. STOCKROOM — 81.0
- Mission Impact (30%): **24/30 (8/10)** — "Inventory Control Management" is verbatim; the 5,000-row inventory gives the demo real density.
- Technical Innovation (25%): **21/25 (8.4/10)** — NL→filter `chat_json` + readiness brief is solid; the SHA-256 audit is a smart sustainability touch.
- Usability & Design (20%): **16/20 (8/10)** — Streamlit + filtered table + readiness panel; the 5K-row scale renders fine.
- Security & Sustainability (15%): **13/15 (8.7/10)** — SHA-256 audit lifts STOCKROOM above the P2 median on Sec.
- Team Collaboration (10%): **7/10 (7/10)** — Single-stack Streamlit; less modular than peers.
- **Single biggest fix to lift +2 points:** add an "ASK ANYTHING" chat box on top of the filter — the NL→filter is the AI move and it's currently buried in a sidebar. Tech 21 → 23.

### 16. VOUCHER — 80.0
- Mission Impact (30%): **25/30 (8.3/10)** — "Travel Program Validation" is verbatim; concrete dollar exposure on the quarterly brief gives the demo a real operational bite that most P2 apps lack.
- Technical Innovation (25%): **20/25 (8/10)** — 2-tier `chat_json` validator + quarterly brief is conventional; the differentiator is the dollar exposure quantification, not the AI pattern.
- Usability & Design (20%): **15/20 (7.5/10)** — Streamlit + validator table + brief panel; visually flat.
- Security & Sustainability (15%): **13/15 (8.7/10)** — CUI footer present; DTS data is genuinely PII-adjacent and the footer addresses it.
- Team Collaboration (10%): **7/10 (7/10)** — Single-stack Streamlit.
- **Single biggest fix to lift +2 points:** front-load the dollar exposure as a giant red KPI in the cold open ("$X.XM at risk this quarter"). The dollar number is the differentiator; bury it and VOUCHER scores 80, lead with it and it scores 84.

### 17. QUEUE — 79.0
- Mission Impact (30%): **24/30 (8/10)** — Depot Maintenance Throughput Optimizer matches the GCSS-MC + Predictive Mx dataset pair; named depots (MCLB Albany, Barstow, BIC) give operational vocabulary.
- Technical Innovation (25%): **21/25 (8.4/10)** — Greedy optimizer + bottleneck `chat_json` + Plotly Gantt is a credible 3-stage pipeline; greedy isn't novel but it's honest.
- Usability & Design (20%): **15/20 (7.5/10)** — Plotly Gantt across 3 depots is a good frame; can crowd if too many lines render.
- Security & Sustainability (15%): **11/15 (7.3/10)** — Standard env-var; depot throughput data isn't called out as CUI.
- Team Collaboration (10%): **8/10 (8/10)** — Modular optimizer/agent/app split.
- **Single biggest fix to lift +2 points:** name a single bottleneck depot and a single intervention recommendation in the cold open ("MCLB Barstow saves 14 days if we shift LAV induction to Q2"). Currently the demo shows the optimizer; it should show the *recommendation*.

### 18. GHOST — 78.0
- Mission Impact (30%): **23/30 (7.7/10)** — "RF Data Analysis — pattern of life, heatmaps" is verbatim, but RF pattern-of-life on WiFi/Bluetooth fingerprints reads as a niche play for a LOGCOM panel that's mostly thinking about sustainment and mobility.
- Technical Innovation (25%): **21/25 (8.4/10)** — DBSCAN + per-cluster `chat_json` + Folium heatmap is the same pattern as Phase 1 EMBER but applied to RF data; SIPR-format BLUF is a nice operational touch.
- Usability & Design (20%): **15/20 (7.5/10)** — Folium heatmap renders fine; the SIPR BLUF panel is small.
- Security & Sustainability (15%): **12/15 (8/10)** — RF fingerprint data is genuinely sensitive; the SIPR framing makes that legible.
- Team Collaboration (10%): **7/10 (7/10)** — Single-stack Streamlit; cluster/brief/app split.
- **Single biggest fix to lift +2 points:** re-pitch as "installation force-protection RF watch" with a named base — this would convert GHOST from a niche pattern-of-life demo into an Installation Incident Response play that the LOGCOM panel will read as on-mission. Mission 23 → 26.

### 19. HUB — 75.0
- Mission Impact (30%): **21/30 (7/10)** — Orphan dataset (BTS); multimodal road/rail/water/air planner is a generic capability without a verbatim portal hook. Loses 3 Mission points.
- Technical Innovation (25%): **21/25 (8.4/10)** — Dijkstra + `chat_json` + corridor narrative is a clean pipeline; multimodal coverage is broader than most P2 apps.
- Usability & Design (20%): **15/20 (7.5/10)** — Streamlit + corridor map; the multimodal palette can read as visually busy.
- Security & Sustainability (15%): **11/15 (7.3/10)** — BTS data is public, no security story.
- Team Collaboration (10%): **7/10 (7/10)** — Single-stack Streamlit.
- **Single biggest fix to lift +3 points:** re-frame against the verbatim "Distributed Maritime Operations sustainment routing" or any named MSC corridor. The Dijkstra-over-multimodal-graph is a serious capability — VANGUARD scores 90 on essentially the same engine with a CENTCOM TMR wrapper. HUB needs that wrapper.

### 20. EMBODIED — 74.0
- Mission Impact (30%): **19/30 (6.3/10)** — Orphan dataset (Xperience-10M); the egocentric Marine training simulator pivot is the loosest fit in the cohort. The Xperience-10M provenance is unclear to a Marine judge and the use case is generic.
- Technical Innovation (25%): **22/25 (8.8/10)** — **Only true vision-language coach in P2** (image+text → JSON+narrative); pattern is rich and the AAR output is novel.
- Usability & Design (20%): **15/20 (7.5/10)** — Streamlit + image+text input + AAR panel; the AAR is informative but the visual hook is weak.
- Security & Sustainability (15%): **11/15 (7.3/10)** — Synthetic-egocentric-data story doesn't translate to a clear on-prem posture.
- Team Collaboration (10%): **7/10 (7/10)** — Single-stack Streamlit.
- **Single biggest fix to lift +4–5 points:** re-pitch the entire app as a CCRB / range-safety AAR coach with a named Marine training event (e.g., ITX 4-26 Twentynine Palms). The vision-language coach is genuinely novel; the wrapper is the problem. Mission 19 → 24 with a credible re-frame.

## Bottom 5 — frank assessment

These are the five apps most at risk of being read as "well-built but off-mission" or "niche capability without a hook" by the LOGCOM panel.

### 20. EMBODIED (74)
The technology is the most novel thing in P2 — a real vision-language coach producing structured JSON and narrative AAR is a pattern nobody else attempts. But the Xperience-10M dataset has no obvious Marine-training provenance and the "egocentric Marine training simulator" framing doesn't connect to a portal challenge. **Re-pitch:** an ITX or MWX after-action coach. Frame the demo around a single Marine fire-team movement that gets evaluated by the model, with the AAR rendered in MARSOC-style format. The vision-language pipeline doesn't change; only the wrapper does. Estimated lift: 74 → 80.

### 19. HUB (75)
Dijkstra over a multimodal road/rail/water/air graph is a genuinely strong capability — it's essentially the same engine that earned VANGUARD a 90. The problem is the BTS-explorer framing reads as a transport-statistics tool, not a logistics decision tool. **Re-pitch:** a CONUS-to-OCONUS sustainment-routing planner with a named MSC port pair (e.g., Jacksonville → Yokosuka). Same engine, mission-fit wrapper. Estimated lift: 75 → 82.

### 18. GHOST (78)
RF pattern-of-life on WiFi/Bluetooth fingerprints is a real capability but reads as a counter-intel niche, not a sustainment or mobility play. The DBSCAN + per-cluster brief pattern is solid (same pattern as Phase 1 EMBER) and the SIPR BLUF is a nice touch. **Re-pitch:** "Installation Force Protection RF Watch" at a named base (Camp Pendleton, MCAS Yuma). Convert the niche capability into an Installation Incident Response play that the LOGCOM panel reads as on-mission. Estimated lift: 78 → 83.

### 17. QUEUE (79)
Depot maintenance throughput across MCLB Albany, Barstow, BIC is exactly the right operational frame; the named depots are textbook. The problem is the demo currently shows the *optimizer* rather than the *recommendation*. A panel watching 20 demos in a row needs to see the answer before they understand the question. **Re-pitch:** lead with "MCLB Barstow saves 14 days if we shift LAV induction to Q2" as a 5-second cold-open headline, then run the existing Gantt as the proof. No code changes required. Estimated lift: 79 → 83.

### 16. VOUCHER (80)
"Travel Program Validation" is verbatim portal language and the dollar-exposure quantification is the strongest concrete-bite in P2 — but it's currently rendered in 14pt text on the quarterly brief panel where nobody will see it. **Re-pitch:** front-load "$X.XM at risk this quarter" as a giant red KPI in the cold open and let the validator table render underneath. The CUI footer is a nice touch and should stay. No code changes; UX-only re-sequencing. Estimated lift: 80 → 84.

## Submission recommendation

The LOGCOM portal will likely accept 3 entries per team. Recommended slate:

### Pick 1: VITALS (89)
**Why submit:** Verbatim DHA RESCUE blood-logistics framing + split FE/BE architecture + 4 LLM-real cached briefs naming spokes and vendors. This is the single Phase 2 app that most closely mirrors what made Phase 1 MARLIN a 90: a verbatim-portal-use-case match, a split FE/BE that lets the frontend breathe, and a hub-and-spoke geographic payoff that reads from row 5 of a noisy ballroom. The medical-supply data also has obvious DHA-judge alignment that no other P2 app can match.

**Risk:** The 4 cached briefs are the differentiator and they're currently buried in a chat panel. **Pre-submission action:** ensure the demo names at least one spoke and one vendor on camera in the first 15 seconds, and that the hub-spoke map is visible from the cold open.

### Pick 2: AGORA (89)
**Why submit:** The only ABAC-with-visible-denial demo in the entire field. If a single LOGCOM judge has an SJA, classification-review, or governance background — and it's nearly certain that at least one will — AGORA is the app they will write down. It also pairs naturally with VITALS as a "we covered both the operational and the governance side" submission slate.

**Risk:** The denial pattern only becomes legible 30 seconds in. **Pre-submission action:** add a "watch what gets denied" cold-open caption and ensure the red denied-doc panel is visible in the first frame.

### Pick 3: CARGO (88)
**Why submit:** Real OpenAI tool-calling loop with 4 typed tools and a 13-event live trace — the same agentic pattern that earned Phase 1's VANGUARD a 90. CARGO is the strongest agentic showcase in the Phase 2 wave and demonstrates a capability (multi-turn tool use until `finish_reason=stop`) that most LOGCOM judges have heard about but rarely seen running on real data. The orphan-dataset Mission penalty is the only thing keeping it from clearing 90 itself.

**Risk:** The orphan-dataset framing penalty (-2 Mission points) is the difference between #1 and #3 on the leaderboard. **Pre-submission action:** re-frame the use case verbatim against a "Distributed Maritime Operations sustainment routing" or equivalent portal challenge — the dataset is orphan, but the *capability* is verbatim-mission-relevant. If this re-frame lands, CARGO would clear 90 and become the strongest Phase 2 submission overall.

### Why not WATCHTOWER, OPENGATE, or REDLINE?

All three are credible alternates and any one of them could swap in for any of the picks above:

- **WATCHTOWER (88)** is the closest substitute for VITALS — same architectural caliber (split FE/BE), same I-COP brand-fit. If the LOGCOM portal allows a 4th submission, WATCHTOWER is the next pick.
- **OPENGATE (87)** is the closest substitute for AGORA on RAG depth, but it lacks AGORA's visible-denial governance demo. If the panel skews technical rather than legal, OPENGATE moves up.
- **REDLINE (86)** is the closest substitute for AGORA on security artifacts (both have verified hash chains), but the per-paragraph CUI tagging is more domain-specific than AGORA's role-aware filtering. If the panel includes a classification-review SJA, REDLINE moves up.

### Single strongest pick if forced to one

**VITALS.** Verbatim DHA RESCUE framing + split FE/BE + named-vendor cached briefs + hub-spoke geographic payoff. It's the most architecturally serious Phase 2 app and the only one that pattern-matches MARLIN's 90 across every axis a LOGCOM panel weights heavily. AGORA is technically novel but governance demos can read as abstract; CARGO has the strongest AI pattern but pays a Mission penalty for the orphan dataset. VITALS is the safest 89 in the cohort with the clearest path to a 90 at demo day.

---

*End of Phase 2 scorecard. For Phase 1 medal-tier reference and rubric calibration baseline, see [JUDGING.md](./JUDGING.md).*
