# EMBODIED

**Egocentric multimodal Marine training simulator.** The trainee sees a
helmet-cam still — a doorway, a vehicle checkpoint, a downed Marine, an IED
indicator, a night perimeter — and answers "what would you do?". A
multimodal AI coach evaluates their action against doctrine and writes a
one-page after-action brief.

> *Egocentric reps, instrumented at the point of decision.*

## Run

```bash
# from repo root
python apps/27-embodied/data/generate.py     # one-time: synthesize 8 frames + scenarios + cache
streamlit run apps/27-embodied/src/app.py \
  --server.port 3027 \
  --server.headless true \
  --server.runOnSave false \
  --server.fileWatcherType none \
  --browser.gatherUsageStats false
```

Open http://localhost:3027

## Hero AI move

A vision-capable model reads the **same egocentric frame the trainee saw**
plus their typed action plus the scenario's doctrinal context (MCWP / MCRP /
TM citations + canonical correct actions + canonical common failures) and
returns structured JSON:

```json
{
  "action_classified_as": "tactical | hesitation | risky | doctrinally_correct",
  "score": 0,
  "doctrine_reference": "MCWP X-Y para Z",
  "consequences_simulated": "...",
  "coaching_feedback": "...",
  "next_scenario_suggestion": "..."
}
```

A second hero call writes a 1-page **Egocentric Decision Brief** across the
session.

Both calls are wrapped in `ThreadPoolExecutor` timeouts with a deterministic
keyword-overlap baseline as fallback (per `AGENT_BRIEF_V2` §B). The demo path
reads pre-computed evaluations from `data/cached_briefs.json` so the
recording is snappy (cache-first per §A); the live path fires when the
trainee enters a custom response.

## Real-data plug-in

```python
# data/load_real.py — point REAL_DATA_PATH at a curated Xperience-10M subset
# with the same {scenarios.json, frames/<id>.png} shape; everything else
# (rendering, evaluation, AAR, theming) is unchanged.
```

Source: **Xperience-10M** — large-scale egocentric multimodal dataset of human
experience for embodied AI / robot learning / world models.

## On-prem posture

```
$ export KAMIWAZA_BASE_URL=https://kamiwaza.local/api/v1
$ export KAMIWAZA_API_KEY=$(cat /run/secrets/kw)
# same code path. trainee video stays inside the wire. SIPR / JWICS ready.
```

Powered by Kamiwaza.
