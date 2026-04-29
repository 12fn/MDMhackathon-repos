# CHAIN-OF-COMMAND

> **Relationship-Based Access Control modeled as the actual Marine ORBAT.**
> Authorization is a graph walk over OPCON / TACON / attached / detached edges — exactly how Marines task-organize.

The sister app **AGORA** (apps/33-agora) implements ABAC RAG (role + attribute filter). **CHAIN-OF-COMMAND** is the ReBAC sibling: same threat model, but the math is graph-walk over relation tuples (Google Zanzibar / OpenFGA pattern), and the graph is the literal Marine ORBAT.

## Hero AI move
For the same query (LCpl Smith → INDOPACOM Posture Brief Q3):
- **RBAC** says DENY (his role isn't on the staff ACL).
- **ABAC** says DENY (his unit attribute doesn't equal a need-to-know unit).
- **ReBAC** says **ALLOW via OPCON path**: Smith → 3rd Sqd → 1st Plt → A Co 1/8 → ATTACHED 2/2 → DETACHED 24th MEU → OPCON USINDOPACOM → HAS_NEED_TO_KNOW(DOC_008). The path lights up on the ORBAT graph.

Operator changes 24th MEU's OPCON edge to USCENTCOM live → access flips to DENY in real time. RBAC and ABAC verdicts don't change because they never looked at OPCON.

## Run
```bash
cd apps/51-chain-of-command
pip install -r requirements.txt

# 1) Generate the synthetic ORBAT + pre-warm cached briefs
python data/generate.py

# 2) Launch the Streamlit app on port 3051
streamlit run src/app.py \
    --server.port 3051 --server.headless true \
    --server.runOnSave false --server.fileWatcherType none \
    --browser.gatherUsageStats false
```

Open http://localhost:3051. The sidebar lets you pick any (Marine, document) pair and dial the 24th MEU's OPCON relationship live.

## Architecture
- **`data/generate.py`** — synthetic ORBAT (60 nodes), 7 relationship types, 30 personnel, 20 documents, 6 demo queries, cache-first scenario briefs.
- **`src/engine.py`** — ReBAC engine. NetworkX MultiDiGraph + BFS over command edges. Three checks (CLEARANCE / RELEASABILITY / NEED_TO_KNOW) AND together. Returns the minimal authorizing path so the UI can light it up.
- **`src/llm.py`** — LLM operator narration over the deterministic verdict. Cache-first; live call gated by Refresh button. Watchdog timeout + deterministic fallback.
- **`src/audit.py`** — SHA-256 hash-chained append-only verdict log.
- **`src/app.py`** — Streamlit UI: subject/object pickers, three-way RBAC/ABAC/ReBAC verdict cards, authorizing-path edge sequence, Folium geo-overlay with the path highlighted in neon, hash-chain inspector, OPCON live-flip dial.

## Real-data plug-in
Three sources unlock real ORBAT (see `data/load_real.py` for the env-var contract):
1. **DEERS / MOL** — personnel + UIC parent chain → MEMBER_OF edges.
2. **GCSS-MC unit table** — OPCON / TACON / ATTACHED / DETACHED rows → dynamic command edges.
3. **Keycloak realm export** — clearance + nationality + caveats → HAS_CLEARANCE pseudo-edges.

Set `REAL_ORBAT_DIR`, `REAL_KEYCLOAK_EXPORT`, `REAL_GCSS_TASK_ORG` and re-run `python data/generate.py`.

## Citations
- **DoDM 5200.02** — DoD Personnel Security Program (clearance ranks).
- **MCO 1500.61** — USMC PME (rank ↔ clearance binding).
- **JP 3-0** — Joint Operations (command relationships taxonomy).
- **Google Zanzibar** — Pang et al., USENIX ATC '19 (relation tuples).
- **NIST SP 800-178** — comparison of ABAC standards (motivates ReBAC).

## Powered by Kamiwaza
Set `KAMIWAZA_BASE_URL` to route inference inside the SCIF. The ReBAC engine itself is pure local Python (NetworkX) — no external dependency for the verdict, only for narration.
