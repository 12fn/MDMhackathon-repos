# DDE-RAG — Compute-at-Data RAG on the Kamiwaza Distributed Data Engine

> **Don't move the data. Move the compute.**

DDE-RAG demonstrates the architectural pattern that separates Kamiwaza from
every other RAG vendor: instead of pulling 70 GB of GCSS-MC + ICM + Technical
Manual data into a central embedding store (slow, bandwidth-killing, ICD-503
spillage risk), Kamiwaza spawns inference containers AT each data node and
ships only megabytes of model weights + query. Only the answers come home.

## The hero question

> "Which serial-number M1A1s are at risk for transmission failure based on the
> last 90 days of work orders?"

The answer needs cross-installation joins:

| Node | Data | Size | Bandwidth class | Posture |
|---|---|---|---|---|
| MCLB Albany | GCSS-MC work orders | 50 GB | 50 Mbps backhaul | UNCLASS, but volume-prohibitive |
| MCB Lejeune | ICM lateral-transfer + parts | 8 GB | 25 Mbps deployable | DDIL/EMCON sensitive |
| MCB Quantico | NSN-tagged technical manuals | 12 GB | 100 Mbps | CUI/FOUO — ICD 503 enclave |

The traditional "central RAG" path: pull all 70 GB to the central embedder,
hours of transit, DCSA spillage risk on the Quantico CUI corpus.

The DDE path: ~10 MB of model weights + query into each node, compute fires
locally, only ~50 KB of answer text returns. Seconds, not hours. Zero data
movement. Zero spillage risk.

## Run it

```bash
cd apps/53-dde-rag
pip install -r requirements.txt

# 1) Generate synthetic 3-node corpus + pre-warm 5 cached briefs
python data/generate.py

# 2) Launch the app
streamlit run src/app.py \
  --server.port 3053 \
  --server.headless true \
  --server.runOnSave false \
  --server.fileWatcherType none \
  --browser.gatherUsageStats false
```

Open <http://localhost:3053>. Pick one of 5 cold-start queries and watch both
execution paths animate side-by-side.

## What you see

1. **3-node DDE map** — Albany / Lejeune / Quantico, sized to data volume,
   colored by security posture.
2. **Side-by-side execution race** — top half is naive central RAG, bottom
   half is Kamiwaza DDE. Bytes-transferred counters tick up; arrows animate
   in proportion to the volume of data crossing the wire.
3. **Bandwidth + compliance panel** — wall-clock time, total bytes
   transferred, DCSA spillage class per path. The naive path lights up red on
   the Quantico CUI lane.
4. **Composed answer** — assembled from the per-node DDE responses by the
   Kamiwaza Model Gateway.
5. **Hash-chained audit log** — every dispatch decision (which node ran which
   compute, with which model weights checksum) appended to
   `data/audit_logs/dde_audit.jsonl` with SHA-256 chaining.

## Real-data plug-in

See `data/load_real.py`. Document a real Kamiwaza Inference Mesh deployment:
spawn one inference container per data locality, register them through the
mesh, set `KAMIWAZA_DDE_NODES=<node1>:8443,<node2>:8443,<node3>:8443`, and
this app routes against them with no other code changes.

## Cited authorities

- **DCSA Industrial Security Policy** — data spillage handling for CUI / FOUO.
- **ICD 503** — Risk Management Framework for IC enclaves (per-node accreditation).
- **DDIL / EMCON** — denied/disrupted/intermittent/limited operating realities
  (deployable Marines do not get 1 Gbps backhaul).
- **MARADMIN 131/26** — LOGCOM AI Forum hackathon mission frame.

## Status

Built for the LOGCOM AI Forum 2026 Hackathon (MARADMIN 131/26).
Powered by Kamiwaza.
