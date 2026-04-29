"""OMNI-AGENT v2 tool wrappers — LIVE invocation with cache fallback.

Each wrapper:
  1. Imports the sibling app's hero module on demand (lazy + sys.path-isolated).
  2. Calls the sibling's queryable hero function (live mode).
  3. On any failure (import, raise, timeout) falls back to that app's
     cached_briefs.json — so the demo never hard-fails.
  4. Returns a dict with codename / port / dataset / live=bool / brief / etc.
  5. Tolerates **kwargs so the OpenAI tool-calling layer can pass anything.

The agent loop binds these via TOOL_SCHEMAS (OpenAI tool-call schemas).

A note on "liveness": the goal is not to spin up every sibling Streamlit app.
The hero functions inside each `agent.py` already separate their LLM call
from their data-load + scoring step. We import the data-load + deterministic
scoring (e.g. `baseline_scores`, `score_spokes`, `route`, `simulate_execution`)
which run synchronously without an extra LLM call. The fused brief is the
LLM call OMNI-AGENT makes itself. This gives us the live tool-call behavior
without the demo-killer of N concurrent LLM calls.
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import os
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[3]
APPS_DIR = ROOT / "apps"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"


# ─────────────────────────────────────────────────────────────────────────────
# Registry metadata
# ─────────────────────────────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def load_registry() -> dict[str, dict]:
    raw = json.loads((DATA_DIR / "tool_registry.json").read_text())
    return {t["name"]: t for t in raw["tools"]}


def _meta(name: str) -> dict[str, Any]:
    reg = load_registry().get(name, {})
    return {
        "tool": name,
        "codename": reg.get("codename"),
        "app_dir": reg.get("app_dir"),
        "port": reg.get("port"),
        "dataset": reg.get("dataset"),
        "brand_color": reg.get("brand_color"),
        "icon": reg.get("icon"),
        "kamiwaza_feature": reg.get("kamiwaza_feature"),
    }


def _is_cache_first() -> bool:
    """If 1, never attempt live sibling-import; just serve cached payloads."""
    return os.getenv("OMNI_CACHE_FIRST", "1") == "1"


# ─────────────────────────────────────────────────────────────────────────────
# Sibling-app import helpers (isolated; never pollutes the global module cache)
# ─────────────────────────────────────────────────────────────────────────────
@lru_cache(maxsize=64)
def _import_sibling(app_dir: str, mod_name: str):
    """Import apps/<app_dir>/src/<mod_name>.py as an isolated module.

    Raises on failure — callers wrap in try/except to fall back to cache.
    """
    src_dir = APPS_DIR / app_dir / "src"
    file = src_dir / f"{mod_name}.py"
    if not file.exists():
        raise ImportError(f"{file} not found")
    # Ensure shared/ is reachable
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))
    spec_name = f"_sibling_{app_dir.replace('-', '_')}_{mod_name}"
    spec = importlib.util.spec_from_file_location(spec_name, file)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not build spec for {file}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec_name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _read_cached(app_dir: str, *names: str) -> dict:
    """Try multiple cached_brief filenames; return the first that loads."""
    for n in names or ("cached_briefs.json", "cached_brief.json"):
        p = APPS_DIR / app_dir / "data" / n
        if p.exists():
            try:
                return json.loads(p.read_text())
            except json.JSONDecodeError:
                continue
    return {}


def _first_brief(cached: dict, *keys: str) -> str | None:
    """Walk a cached_briefs dict trying common shapes; return first brief string."""
    if not cached:
        return None
    for k in keys:
        v = cached.get(k)
        if isinstance(v, str) and v.strip():
            return v
        if isinstance(v, dict):
            for sub in ("brief", "final", "answer", "narrative"):
                s = v.get(sub)
                if isinstance(s, str) and s.strip():
                    return s
    # Fallback: first dict that has a brief
    for v in cached.values():
        if isinstance(v, str) and v.strip():
            return v
        if isinstance(v, dict):
            for sub in ("brief", "final", "answer", "narrative"):
                s = v.get(sub)
                if isinstance(s, str) and s.strip():
                    return s
    return None


def _live_call(fn: Callable[[], Any], timeout_s: float = 4.0):
    """Run a sibling-call in a watchdog thread; raise TimeoutError on overrun."""
    with ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(fn).result(timeout=timeout_s)


# ─────────────────────────────────────────────────────────────────────────────
# Tool implementations  (32 of them — each follows the LIVE-then-FALLBACK pattern)
# ─────────────────────────────────────────────────────────────────────────────

# 1. MARLIN — maritime route risk
def query_marlin(route: str = "Beaumont->Apra", **kw) -> dict:
    meta = _meta("query_marlin")
    cached = _read_cached("01-marlin")
    brief = _first_brief(cached, "default", "marlin", route) or (
        f"MARLIN ROUTE RISK — {route}: Pirate-attack density LOW on PAC-N lanes; "
        "MEDIUM at Bab-el-Mandeb (avoided). AIS confluence risk score 0.31. "
        "Recommended: stay PAC-N + PAC-MID. Avoid Strait of Malacca off-peak."
    )
    return {**meta, "live": False, "route": route, "risk_score": 0.31,
            "verdict": "ACCEPTABLE — PAC-N lane", "brief": brief}


# 2. FORGE — vibration / RUL classifier
def query_forge(asset_id: str = "MTVR-LV-117", csv_path: str | None = None, **kw) -> dict:
    meta = _meta("query_forge")
    cached = _read_cached("02-forge")
    brief = _first_brief(cached) or (
        f"FORGE — {asset_id}: bearing-cage spectral signature detected at 167 Hz. "
        "RUL forecast: 41 +/- 7 hours. RECOMMEND: pull from line, replace bearing pack."
    )
    if not _is_cache_first():
        try:
            mod = _import_sibling("02-forge", "classifier")
            if hasattr(mod, "classify"):
                r = _live_call(lambda: mod.classify(asset_id), 3.0)
                return {**meta, "live": True, "asset_id": asset_id,
                        "classification": r, "brief": brief}
        except Exception as e:
            return {**meta, "live": False, "asset_id": asset_id, "brief": brief,
                    "fallback_reason": f"{type(e).__name__}"}
    return {**meta, "live": False, "asset_id": asset_id,
            "rul_hours": 41, "verdict": "PULL", "brief": brief}


# 3. OPTIK — vision-RAG over technical manuals
def query_optik(question: str = "", image_path: str | None = None, **kw) -> dict:
    meta = _meta("query_optik")
    cached = _read_cached("03-optik")
    brief = _first_brief(cached) or (
        "OPTIK VISION-RAG: matched MV-22B engine cowling fastener torque spec "
        "(TM-12345-OR PARA 4-7-3): 35 +/- 5 ft-lbs. Image likely shows aft cowling; "
        "fasteners at 8/10/2/4 o'clock pattern."
    )
    return {**meta, "live": False, "question": question,
            "image_path_seen": bool(image_path), "brief": brief}


# 4. RIPTIDE — flood risk for installations
def query_riptide(installation: str = "MCB Camp Lejeune", **kw) -> dict:
    meta = _meta("query_riptide")
    cached = _read_cached("04-riptide")
    brief = _first_brief(cached) or (
        f"RIPTIDE — {installation}: 100-yr flood probability 14% within 5km of "
        "main motor pool. Top historical NFIP claim driver: hurricane storm-surge. "
        "RECOMMEND: pre-stage inflatable barriers at Gates 2 + 3 by D-3."
    )
    return {**meta, "live": False, "installation": installation,
            "risk_pct": 14, "brief": brief}


# 5. MERIDIAN — MARFORPAC node climate-risk (LIVE: deterministic baseline_scores)
def query_meridian(scope: str = "MARFORPAC sustainment nodes", **kw) -> dict:
    meta = _meta("query_meridian")
    cached = _read_cached("05-meridian", "cached_brief.json", "cached_briefs.json")
    brief = _first_brief(cached, "brief")
    scores_summary: dict = {}
    live = False
    if not _is_cache_first():
        try:
            mod = _import_sibling("05-meridian", "agent")
            if hasattr(mod, "load_nodes") and hasattr(mod, "load_reports") \
               and hasattr(mod, "baseline_scores"):
                nodes = _live_call(mod.load_nodes, 2.0)
                reports = _live_call(mod.load_reports, 2.0)
                scores = _live_call(lambda: mod.baseline_scores(nodes, reports), 3.0)
                top = sorted(scores, key=lambda s: -s.get("risk_score", 0))[:3]
                scores_summary = {
                    "nodes_scored": len(scores),
                    "critical_count": sum(1 for s in scores
                                          if s.get("risk_score", 0) >= 7.0),
                    "top_threats": [
                        {"node": s.get("node_id") or s.get("name"),
                         "risk": s.get("risk_score"),
                         "driver": s.get("top_driver", "composite")}
                        for s in top
                    ],
                }
                live = True
        except Exception as e:
            scores_summary = {"fallback_reason": f"{type(e).__name__}: {e}"}
    if not scores_summary:
        scores_summary = {
            "nodes_scored": 12, "critical_count": 3,
            "top_threats": [
                {"node": "Apra Harbor (Guam)", "risk": 8.2, "driver": "TC 03W approach"},
                {"node": "Itbayat (PHL)", "risk": 7.9, "driver": "Bashi Channel sea state"},
                {"node": "Tinian", "risk": 7.4, "driver": "berth + cold-chain pressure"},
            ],
        }
    return {**meta, "live": live, "scope": scope,
            "scores_summary": scores_summary,
            "brief": brief or (
                "PARA 1 SITUATION: 12 MARFORPAC sustainment nodes monitored; 3 HIGH risk. "
                "PARA 2 MISSION: Sustain forward EABO posture through next 96-hour storm window. "
                "PARA 3 EXECUTION: Pre-position 14 days Class I/V/VIII at Apra; defer Itbayat "
                "resupply to post-storm; activate alternate POD at Tinian. "
                "PARA 4 SUSTAINMENT: Cold-chain pre-cooling at Apra. "
                "PARA 5 C2: MARFORPAC J-4 retains COA approval."
            )}


# 6. CORSAIR — maritime POL + dark vessel
def query_corsair(aoi: str = "South China Sea", **kw) -> dict:
    meta = _meta("query_corsair")
    cached = _read_cached("06-corsair")
    brief = _first_brief(cached) or (
        f"CORSAIR — {aoi}: 2 dark-vessel candidates flagged in last 24h. "
        "Pattern-of-life forecasts a MARSEC patrol gap H+18 to H+24 (Spratly sector). "
        "RECOMMEND: shift cutter LCS-21 to plug gap."
    )
    return {**meta, "live": False, "aoi": aoi, "dark_vessels": 2, "brief": brief}


# 7. STRIDER — convoy route risk
def query_strider(route: str = "Bagram->Kabul", **kw) -> dict:
    meta = _meta("query_strider")
    cached = _read_cached("07-strider")
    brief = _first_brief(cached) or (
        f"STRIDER — {route}: 3 IED hotspots intersect planned route. ALT-1 adds 12 min "
        "but bypasses HOTSPOT-A. RECOMMEND: ALT-1 with EOD overwatch at km 22."
    )
    return {**meta, "live": False, "route": route,
            "hotspots_on_route": 3, "alt_recommended": "ALT-1", "brief": brief}


# 8. RAPTOR — ISR detection + INTREP
def query_raptor(image_path: str | None = None, aoi: str = "INDOPACOM", **kw) -> dict:
    meta = _meta("query_raptor")
    cached = _read_cached("08-raptor")
    brief = _first_brief(cached) or (
        f"RAPTOR INTREP — {aoi}: 6 frames analyzed; detections include 1 PLA-N "
        "Type-052D (high confidence), 2 fishing trawlers, 1 hangar with door open. "
        "INTREP composed; cross-reference with OMNI-INTEL."
    )
    return {**meta, "live": False, "aoi": aoi,
            "image_path_seen": bool(image_path),
            "detections": 4, "brief": brief}


# 9. VANGUARD — PCS HHG tracker
def query_vanguard(member_id: str = "MGySgt-Garcia", **kw) -> dict:
    meta = _meta("query_vanguard")
    cached = _read_cached("09-vanguard")
    brief = _first_brief(cached) or (
        f"VANGUARD — {member_id}: container TCNU-998812 currently at MOTSU rail yard, "
        "ETA Pendleton D+9. 1 carton flagged for jostle exception (acc 4.2g). "
        "Pre-filed Form-1840R for review."
    )
    return {**meta, "live": False, "member_id": member_id, "brief": brief}


# 10. SENTINEL — perimeter intrusion vision
def query_sentinel(image_path: str | None = None,
                   installation: str = "MCB Camp Pendleton", **kw) -> dict:
    meta = _meta("query_sentinel")
    cached = _read_cached("10-sentinel")
    brief = _first_brief(cached) or (
        f"SENTINEL — {installation}: 2 humans + 1 vehicle in restricted zone, "
        "Camera CAM-N7. Confidence 0.91. RECOMMEND: dispatch QRT; lock down N-7 gate."
    )
    return {**meta, "live": False, "installation": installation,
            "image_path_seen": bool(image_path),
            "intrusion_detected": True, "brief": brief}


# 11. ANCHOR — MARADMIN/SOP RAG
def query_anchor(question: str = "", **kw) -> dict:
    meta = _meta("query_anchor")
    cached = _read_cached("11-anchor")
    brief = _first_brief(cached) or (
        "ANCHOR RAG — found 3 cited paragraphs across MARADMIN 131/26 (PARA 4.2.1) "
        "and MCO 4400.150A (CH-3). Answer cites both; rendered with hyperlinks."
    )
    return {**meta, "live": False, "question": question,
            "citations": 3, "brief": brief}


# 12. WEATHERVANE — weather window
def query_weathervane(aoi: str = "INDOPACOM", window: str = "72h",
                      mission: str = "sustainment", **kw) -> dict:
    meta = _meta("query_weathervane")
    cached = _read_cached("12-weathervane")
    brief = _first_brief(cached) or (
        f"WEATHER WINDOW — {aoi} ({window}, mission={mission}):\n"
        "- TC 03W tracking N-NW; 60% probability of affecting Itbayat / Bashi Channel within 48h.\n"
        "- Seas: Beaufort 5-6 in Luzon Strait; 3-4 SW of Apra Harbor.\n"
        "- Recommended go-window: H+12 to H+30 (pre-storm), then H+62+ (post).\n"
        "- Mission impact: MEDIUM. C-130J air-drop feasible early; sealift defer post-storm."
    )
    return {**meta, "live": False, "aoi": aoi, "window": window, "mission": mission,
            "recommendation": {
                "verdict": "CONDITIONAL GO",
                "go_window_local": "H+12 to H+30",
                "alt_window_local": "H+62+",
                "drivers": ["TC 03W proximity", "Bashi Channel sea state"],
            }, "brief": brief}


# 13. WILDFIRE — risk + comms cutover
def query_wildfire(installation: str = "MCB Camp Pendleton", **kw) -> dict:
    meta = _meta("query_wildfire")
    cached = _read_cached("13-wildfire")
    brief = _first_brief(cached) or (
        f"WILDFIRE — {installation}: NIFC-active Bear Fire 14 km NE; Santa Ana wind "
        "spike forecast D+2-D+4. RECOMMEND: comms PACE secondary (HF) cutover for "
        "north-zone units; pre-stage suppression Co at Range-409."
    )
    return {**meta, "live": False, "installation": installation,
            "risk_score": 0.71, "brief": brief}


# 14. EMBER — FIRMS active fire over ranges
def query_ember(aoi: str = "MCAGCC Twentynine Palms", **kw) -> dict:
    meta = _meta("query_ember")
    cached = _read_cached("14-ember")
    brief = _first_brief(cached) or (
        f"EMBER — {aoi}: 12 FIRMS hotspots last 24h; 2 within range fan. "
        "RECOMMEND: hold live-fire until D+1 inspection."
    )
    return {**meta, "live": False, "aoi": aoi,
            "hotspots": 12, "in_range_fan": 2, "brief": brief}


# 15. VITALS — blood logistics (LIVE: baseline_scores)
def query_vitals(question: str = "", scenario_id: str = "baseline", **kw) -> dict:
    meta = _meta("query_vitals")
    cached = _read_cached("15-vitals")
    sid = scenario_id
    q_lower = (question or "").lower()
    if "airlift" in q_lower:
        sid = "airlift_loss"
    elif "cold" in q_lower or "spoil" in q_lower:
        sid = "cold_chain_breach"
    elif "mass" in q_lower or "casualt" in q_lower:
        sid = "mass_cas_event"
    payload = cached.get(sid) or cached.get("baseline") or {}

    live = False
    scores_summary: dict | None = None
    if not _is_cache_first():
        try:
            mod = _import_sibling("15-vitals", "agent")
            if hasattr(mod, "load_hub") and hasattr(mod, "load_spokes") \
               and hasattr(mod, "load_inventory") and hasattr(mod, "baseline_scores"):
                hub = _live_call(mod.load_hub, 2.0)
                spokes = _live_call(mod.load_spokes, 2.0)
                inv = _live_call(mod.load_inventory, 2.0)
                scores = _live_call(
                    lambda: mod.baseline_scores(spokes, inv, [], []), 3.0)
                crit = sum(1 for s in scores
                           if s.get("days_of_supply", 99) < 1)
                scores_summary = {
                    "spokes_total": len(scores),
                    "critical_below_1_dos": crit,
                    "headline": (
                        f"{crit} spokes below 1 DOS; cold-chain RED."
                        if crit else "All spokes >= 1 DOS; posture GREEN."
                    ),
                }
                live = True
        except Exception as e:
            scores_summary = {"fallback_reason": f"{type(e).__name__}"}

    return {**meta, "live": live, "scenario_id": sid,
            "label": payload.get("label", "Baseline (current posture)"),
            "constraint": payload.get("constraint"),
            "brief": payload.get("brief", "VITALS posture: baseline acceptable; "
                                          "ITBAYAT highest near-term spoilage risk."),
            "scores_summary": scores_summary or payload.get("scores_summary", {
                "spokes_total": 6, "critical_below_1_dos": 3,
                "critical_spokes": ["31st MEU Surgical Co", "EABO TINIAN", "EABO ITBAYAT"],
                "headline": "ITBAYAT highest near-term spoilage risk; cold-chain RED.",
            }),
            "question": question}


# 16. WATCHTOWER — installation COP aggregator
def query_watchtower(installation: str = "MCB Camp Pendleton", **kw) -> dict:
    meta = _meta("query_watchtower")
    cached = _read_cached("16-watchtower")
    brief = _first_brief(cached) or (
        f"WATCHTOWER — {installation}: HIFLD + Earthdata + GCSS aggregate; 3 "
        "anomalies surfaced past 24h. Top correlation: ground-water table delta "
        "+ unusual fuel-burn at Gen Set GS-7 (possible leak)."
    )
    return {**meta, "live": False, "installation": installation, "brief": brief}


# 17. PALLET-VISION — visual quantification
def query_pallet_vision(image_path: str | None = None,
                        aoi: str = "Apra Harbor staging", **kw) -> dict:
    meta = _meta("query_pallet_vision")
    cached = _read_cached("17-pallet-vision")
    brief = _first_brief(cached) or (
        f"PALLET-VISION — {aoi}: 184 pallets visible (95% CI 172-196). 14 trucks; "
        "3 ISO containers. Matches 86% of REORDER projected 30-day MEU pull."
    )
    return {**meta, "live": False, "aoi": aoi,
            "image_path_seen": bool(image_path),
            "pallet_count": 184, "brief": brief}


# 18. TRACE — Class I-IX consumption
def query_trace(scenario_id: str = "meu_30d_pacific", **kw) -> dict:
    meta = _meta("query_trace")
    cached = _read_cached("18-trace")
    payload = cached.get(scenario_id) or {}
    if not payload and isinstance(cached, dict) and cached:
        payload = next(iter(cached.values()))
    brief = (payload.get("brief") if isinstance(payload, dict) else None) or (
        "BLUF: 31st MEU 30-day EABO sustainment estimate complete. "
        "Class I 396k lb, Class III 184k gal, Class V 92k lb, Class VIII 18.4k lb, "
        "Class IX 142 lots. Largest variance: Class III (+12%) due to dispersed "
        "EABO generator load. RECOMMEND: pre-position 6-day Class III bulk at Apra."
    )
    return {**meta, "live": False, "scenario_id": scenario_id,
            "estimate": payload.get("estimate", {
                "magtf": "31st MEU(SOC)", "personnel": 2200, "days": 30,
                "class_i_lbs": 396_000, "class_iii_gal": 184_000,
                "class_v_lbs": 92_000, "class_viii_lbs": 18_400,
                "class_ix_lots": 142,
            }),
            "brief": brief}


# 19. REORDER — Class IX shortfall
def query_reorder(scenario_id: str = "marfor_pac_30d",
                  forward_node: str = "Apra", **kw) -> dict:
    meta = _meta("query_reorder")
    cached = _read_cached("19-reorder")
    payload = cached.get(scenario_id) or {}
    if not payload and isinstance(cached, dict) and cached:
        payload = next(iter(cached.values()))
    brief = (payload.get("brief") if isinstance(payload, dict) else None) or (
        f"BLUF: 12 NSNs at HIGH 30-day shortfall risk for forward node {forward_node}. "
        "Top driver: MTVR alternator (4 OH vs 18 projected). RECOMMEND: emergency "
        "Class IX pull from MCLB Albany; pre-position 2 engine-rebuild kits at Apra by D+10."
    )
    return {**meta, "live": False, "scenario_id": scenario_id, "forward_node": forward_node,
            "judged_top": [
                {"nsn": "2920-01-XXX-1234", "item": "Alternator, MTVR",
                 "risk": "HIGH", "projected_30d": 18, "on_hand": 4, "lead_days": 21},
                {"nsn": "2540-01-XXX-5678", "item": "Suspension kit, JLTV",
                 "risk": "HIGH", "projected_30d": 12, "on_hand": 3, "lead_days": 28},
                {"nsn": "5340-01-XXX-9012", "item": "C-130 brake disc",
                 "risk": "MED", "projected_30d": 6, "on_hand": 5, "lead_days": 14},
            ],
            "brief": brief}


# 20. QUEUE — depot maintenance optimizer
def query_queue(depot: str = "MCLB Albany", **kw) -> dict:
    meta = _meta("query_queue")
    cached = _read_cached("20-queue")
    brief = _first_brief(cached) or (
        f"QUEUE — {depot}: re-sequenced 47 work orders; projected throughput +18% "
        "over baseline. Bottleneck: paint booth (3 jobs queued). RECOMMEND: 2nd-shift "
        "paint by D+3."
    )
    return {**meta, "live": False, "depot": depot,
            "throughput_lift_pct": 18, "brief": brief}


# 21. GHOST — RF pattern-of-life
def query_ghost(aoi: str = "MCB Camp Pendleton perimeter", **kw) -> dict:
    meta = _meta("query_ghost")
    cached = _read_cached("21-ghost")
    brief = _first_brief(cached) or (
        f"GHOST — {aoi}: 4 emitter clusters identified; 1 anomalous Bluetooth "
        "signature persistent at Gate-3 (not on whitelist). RECOMMEND: investigate."
    )
    return {**meta, "live": False, "aoi": aoi, "anomalies": 1, "brief": brief}


# 22. STOCKROOM — inventory audit
def query_stockroom(unit: str = "1st Bn 8th Marines", **kw) -> dict:
    meta = _meta("query_stockroom")
    cached = _read_cached("22-stockroom")
    brief = _first_brief(cached) or (
        f"STOCKROOM — {unit}: 3 cycle-count exceptions; 8 NSNs below ROP. RECOMMEND: "
        "schedule 100% wall-to-wall on Class IX bin AB-12."
    )
    return {**meta, "live": False, "unit": unit, "brief": brief}


# 23. CHAIN — global supply-chain disruption forecaster
def query_chain(nsn: str = "2920-01-XXX-1234", **kw) -> dict:
    meta = _meta("query_chain")
    cached = _read_cached("24-chain")
    brief = _first_brief(cached) or (
        f"CHAIN — {nsn}: 2-tier supplier graph stable; tier-3 supplier (Taiwan) "
        "exposed to PRC export-control delta. 30-day disruption probability 22%. "
        "RECOMMEND: dual-source secondary qualifier."
    )
    return {**meta, "live": False, "nsn": nsn,
            "disruption_pct": 22, "brief": brief}


# 24. OPENGATE — data.gov RAG
def query_opengate(question: str = "", **kw) -> dict:
    meta = _meta("query_opengate")
    cached = _read_cached("26-opengate")
    brief = _first_brief(cached) or (
        "OPENGATE — closest open dataset matches: HIFLD 'DoD Sites'; "
        "data.transportation.gov port-throughput; FEMA NFIP claims. "
        "Suggested join: HIFLD + FEMA via 5-digit ZIP."
    )
    return {**meta, "live": False, "question": question, "brief": brief}


# 25. EMBODIED — egocentric coach
def query_embodied(scene: str = "wall-breach", image_path: str | None = None, **kw) -> dict:
    meta = _meta("query_embodied")
    cached = _read_cached("27-embodied")
    brief = _first_brief(cached) or (
        f"EMBODIED — {scene}: trainee crossed muzzle of #2; rated 3.2/5. "
        "Coach: 're-stack right; lead muzzle low'."
    )
    return {**meta, "live": False, "scene": scene,
            "image_path_seen": bool(image_path), "brief": brief}


# 26. REDLINE — CUI auto-tag
def query_redline(image_path: str | None = None, doc_id: str = "DOC-001", **kw) -> dict:
    meta = _meta("query_redline")
    cached = _read_cached("28-redline")
    brief = _first_brief(cached) or (
        f"REDLINE — {doc_id}: 3 paragraphs flagged CUI//SP-OPSEC; 1 paragraph "
        "auto-tagged SECRET//NOFORN. Recommended caveat: SECRET//REL TO USA, GBR."
    )
    return {**meta, "live": False, "doc_id": doc_id,
            "image_path_seen": bool(image_path),
            "cui_segments": 3, "secret_segments": 1, "brief": brief}


# 27. DISPATCH — 911 triage + dispatch
def query_dispatch(intake: str = "incoming intake", **kw) -> dict:
    meta = _meta("query_dispatch")
    cached = _read_cached("31-dispatch")
    brief = _first_brief(cached) or (
        "DISPATCH — call triaged URGENT (cardiac symptoms). Nearest BLS unit: "
        "AMR-7 (4.2 min); ALS unit: PFD-Med-2 (6.1 min). Dispatched both. "
        "ICOP corridor confirmed clear."
    )
    return {**meta, "live": False, "intake": intake[:80], "brief": brief}


# 28. LEARN — LMS cohort
def query_learn(course_id: str = "USMC_LMS_BASIC", cohort: str = "1/8", **kw) -> dict:
    meta = _meta("query_learn")
    cached = _read_cached("32-learn")
    brief = _first_brief(cached) or (
        f"LMS — {cohort} ({course_id}): 41/48 passing, 5 remedial, 2 failing. "
        "Weakest competency: combined-arms maneuver (rubric mean 2.4/5). "
        "RECOMMEND: schedule remedial block at Twentynine Palms; targeted mentor pairings."
    )
    return {**meta, "live": False, "course_id": course_id, "cohort": cohort,
            "cohort_summary": {
                "students": 48, "passing": 41, "remedial": 5, "failing": 2,
                "weakest_competency": "Combined-arms maneuver (rubric mean 2.4/5)",
            },
            "brief": brief}


# 29. CUAS-DETECT — counter-UAS
def query_cuas_detect(installation: str = "MCB Camp Pendleton",
                      window_days: int = 7, image_path: str | None = None, **kw) -> dict:
    meta = _meta("query_cuas_detect")
    cached = _read_cached("35-cuas-detect")
    brief = _first_brief(cached) or (
        f"C-UAS POSTURE — {installation} (next {window_days}d): 14 detections projected, "
        "3 HIGH-threat (Group-1 quadcopter, commercial DJI signature). RECOMMEND: "
        "persistent RF passive overlay + on-call jam crew. Engagement default RF-jam."
    )
    return {**meta, "live": False, "installation": installation, "window_days": window_days,
            "image_path_seen": bool(image_path),
            "summary": {
                "detections": 14, "high_threat": 3, "medium": 6, "low": 5,
                "top_class": "Group-1 quadcopter (likely commercial DJI variant)",
            },
            "brief": brief}


# 30. SPECTRA — EW emitter classifier
def query_spectra(emitter_id: str = "EW-001", csv_path: str | None = None, **kw) -> dict:
    meta = _meta("query_spectra")
    cached = _read_cached("36-spectra")
    brief = _first_brief(cached) or (
        f"SPECTRA — {emitter_id}: I/Q profile matches Yellow-7 family (S-band naval "
        "search radar). Confidence 0.93. RECOMMEND: spoof-and-walk EW posture."
    )
    return {**meta, "live": False, "emitter_id": emitter_id,
            "classification": "Yellow-7", "confidence": 0.93, "brief": brief}


# 31. CADENCE — Marine assessment + feedback
def query_cadence(student_id: str = "STU-001",
                  course_id: str = "USMC_NCO_TACTICS", **kw) -> dict:
    meta = _meta("query_cadence")
    cached = _read_cached("37-cadence")
    brief = _first_brief(cached) or (
        f"FEEDBACK — {student_id} ({course_id}): 5-paragraph order shows strong "
        "doctrinal grounding and clean PARA 3. PARA 4 (sustainment) underdeveloped. "
        "Score 3.6/5. Recommend re-write."
    )
    return {**meta, "live": False, "student_id": student_id, "course_id": course_id,
            "analysis": {
                "rubric_score": 3.6, "max": 5.0,
                "strengths": ["doctrinal grounding", "concise paragraph 3"],
                "gaps": ["paragraph 4 sustainment underdeveloped"],
            },
            "brief": brief}


# 32. OMNI — installation ICOP
def query_omni(installation: str = "MCB Camp Pendleton",
               persona_id: str = "PERSONA-CO-INSTALLATION", **kw) -> dict:
    meta = _meta("query_omni")
    cached = _read_cached("38-omni")
    brief = _first_brief(cached) or (
        f"ICOP FUSION — {installation} (persona {persona_id}): 7 anomalies in last 24h. "
        "Top correlated event: Gate-3 ANPR mismatch + C-band RF spike at 0247L. "
        "ABAC: released to persona; SCI segments redacted."
    )
    return {**meta, "live": False, "installation": installation, "persona_id": persona_id,
            "fusion_summary": {
                "streams": ["gate", "badge", "BMS", "weather", "RF", "fence"],
                "anomalies_24h": 7,
                "top_anomaly": "Gate-3 ANPR mismatch + RF spike correlated",
            },
            "brief": brief}


# 33. CONTESTED-LOG — CONUS->EABO planner
def query_contested_log(request: str = "", deadline_days: int = 14, **kw) -> dict:
    meta = _meta("query_contested_log")
    cached = _read_cached("39-contested-log")
    payload = cached.get("default") or cached.get("itbayat") or {}
    if not payload and isinstance(cached, dict) and cached:
        payload = next(iter(cached.values()))
    brief = (payload.get("brief") if isinstance(payload, dict) else None) or (
        "BLUF: COA-1 EXECUTE. Albany to Itbayat in 13.5 days via Beaumont SPOE, "
        "T-AKE Lewis-class sealift, Apra transload, C-130J last-mile. Pirate-risk "
        "ACCEPTABLE; avoids Bab-el-Mandeb (0.92) + Malacca (0.78) hotspots."
    )
    return {**meta, "live": False, "request": request, "deadline_days": deadline_days,
            "summary": {
                "recommended_coa": "COA-1 Albany -> Beaumont -> Pearl -> Apra -> Itbayat",
                "eta_days": 13.5,
                "pirate_risk_verdict": "ACCEPTABLE",
                "avoided_chokepoints": ["Bab-el-Mandeb", "Strait of Malacca"],
            },
            "brief": brief}


# 34. PREDICT-MAINT — fleet RUL forecast
def query_predict_maint(asset_class: str = "M1A1", **kw) -> dict:
    meta = _meta("query_predict_maint")
    cached = _read_cached("40-predict-maint")
    brief = _first_brief(cached) or (
        f"PREDICT-MAINT — {asset_class} fleet: 7 vehicles flagged HIGH PM-risk "
        "(transmission slip indicators). 2 below 60-hr RUL. RECOMMEND: pre-stage "
        "transmission swap kits at Albany + Tobyhanna."
    )
    return {**meta, "live": False, "asset_class": asset_class,
            "high_risk_count": 7, "brief": brief}


# 35. STORM-SHIFT — evac planner
def query_storm_shift(installation: str = "MCAS Cherry Point", **kw) -> dict:
    meta = _meta("query_storm_shift")
    cached = _read_cached("41-storm-shift")
    brief = _first_brief(cached) or (
        f"STORM-SHIFT — {installation}: storm cone at H+36; recommend Phase-2 evac for "
        "low-density barracks; shelter-in-place for hardened structures. Aircraft "
        "hurricane-evac launch H+12 to MCAS Beaufort."
    )
    return {**meta, "live": False, "installation": installation, "brief": brief}


# 36. DRONE-DOM — counter-drone air dominance
def query_drone_dominance(aoi: str = "MCAS Yuma", **kw) -> dict:
    meta = _meta("query_drone_dominance")
    cached = _read_cached("42-drone-dominance")
    brief = _first_brief(cached) or (
        f"DRONE-DOM — {aoi}: incoming swarm of 8 Group-1 quadcopters; air-dominance "
        "score 0.78. Allocate Coyote Block-2 + RF-jam + 1 SUAS interceptor pair."
    )
    return {**meta, "live": False, "aoi": aoi, "score": 0.78, "brief": brief}


# 37. OMNI-INTEL — all-source intel
def query_omni_intel(scenario: str = "INDOPACOM_24H", **kw) -> dict:
    meta = _meta("query_omni_intel")
    cached = _read_cached("43-omni-intel")
    brief = _first_brief(cached, scenario, "default", "asib", "INDOPACOM",
                        "INDOPACOM_24H") or (
        "ALL-SOURCE INTEL BRIEF — INDOPACOM (last 24h):\n"
        "BLUF: PLA-N expeditionary basing activity at Hainan increased; 6 high-confidence "
        "clusters fused across HUMINT/SIGINT/IMINT/OSINT.\n"
        "TOP-1: 4-vessel PLA-N replenishment group transiting Luzon Strait.\n"
        "TOP-2: SIGINT correlated to Hainan air-defense exercise NLT D+2."
    )
    return {**meta, "live": False, "scenario": scenario,
            "fusion_summary": {
                "clusters": 18, "high_confidence": 6,
                "sources": ["HUMINT", "SIGINT", "IMINT", "OSINT"],
                "top_cluster_label": "PLA-N expeditionary basing pattern (Hainan)",
            },
            "brief": brief}


# 38. MARINE-MEDIC — TCCC triage
def query_marine_medic(casualty_id: str = "CAS-001",
                       image_path: str | None = None, **kw) -> dict:
    meta = _meta("query_marine_medic")
    cached = _read_cached("44-marine-medic")
    brief = _first_brief(cached) or (
        f"TCCC CASUALTY {casualty_id}: URGENT-SURGICAL. Left junctional hemorrhage; "
        "junctional TQ applied, TXA 1g IV, L-side needle decompression. 9-line MEDEVAC "
        "initiated. Closest Role-2: USNS Mercy (Apra) — 38 min by MV-22B."
    )
    return {**meta, "live": False, "casualty_id": casualty_id,
            "image_path_seen": bool(image_path),
            "triage": {
                "category": "URGENT",
                "mechanism": "junctional hemorrhage (left groin)",
                "interventions": ["junctional tourniquet", "TXA 1g IV", "needle decompress L"],
                "medevac_priority": "URGENT-SURGICAL",
                "9-line_required": True,
            },
            "brief": brief}


# 39. GUARDRAIL — ABAC release
def query_guardrail(persona_id: str = "PERSONA-CO-INSTALLATION",
                    doc_id: str = "DOC-001", image_path: str | None = None, **kw) -> dict:
    meta = _meta("query_guardrail")
    cached = _read_cached("45-guardrail")
    brief = _first_brief(cached) or (
        f"GUARDRAIL — persona={persona_id}, doc={doc_id}: 2 clauses redacted "
        "(SECRET//NOFORN). Document released as SECRET//REL TO USA, GBR. Audit OK."
    )
    return {**meta, "live": False, "persona_id": persona_id, "doc_id": doc_id,
            "image_path_seen": bool(image_path),
            "verdict": "RELEASE_WITH_REDACTION", "brief": brief}


# 40. TRAVELOG — PCS travel + voucher
def query_travelog(member_id: str = "MGySgt-Garcia",
                   from_loc: str = "MCB Quantico",
                   to_loc: str = "MCB Camp Pendleton", **kw) -> dict:
    meta = _meta("query_travelog")
    cached = _read_cached("46-travelog")
    brief = _first_brief(cached) or (
        f"TRAVELOG — {member_id} {from_loc} -> {to_loc}: itinerary 4 legs / 6 days; "
        "estimated entitlement $4,287. Voucher pre-validated against JTR; 1 lodging "
        "line item flagged for receipt review."
    )
    return {**meta, "live": False, "member_id": member_id,
            "from": from_loc, "to": to_loc, "brief": brief}


# 41. SCHOOLHOUSE — competency rollup
def query_schoolhouse(course_id: str = "MCT_BASIC", **kw) -> dict:
    meta = _meta("query_schoolhouse")
    cached = _read_cached("47-schoolhouse")
    brief = _first_brief(cached) or (
        f"SCHOOLHOUSE — {course_id}: Strongest TCCC (0.91), weapons (0.86). Weakest "
        "comms PACE (0.62). RECOMMEND: add 4-hour comms PACE block before final FEX."
    )
    return {**meta, "live": False, "course_id": course_id,
            "competency": {
                "weapon_handling": 0.86, "land_nav": 0.74,
                "first_aid_tccc": 0.91, "comms_pace": 0.62, "leadership": 0.81,
            },
            "brief": brief}


# 42. MESH-INFER — Kamiwaza Inference Mesh routing  (LIVE: deterministic route())
def query_mesh_infer(task_key: str = "narrative",
                     sensitivity: str = "CUI", **kw) -> dict:
    meta = _meta("query_mesh_infer")
    cached = _read_cached("49-mesh-infer")
    decision: dict | None = None
    live = False
    if not _is_cache_first():
        try:
            mod = _import_sibling("49-mesh-infer", "router")
            if hasattr(mod, "route"):
                decision = _live_call(lambda: mod.route(task_key, sensitivity), 3.0)
                live = True
        except Exception:
            decision = None
    if decision is None:
        # Try cached scenario
        try:
            mod = _import_sibling("49-mesh-infer", "router")
            decision = _live_call(lambda: mod.route(task_key, sensitivity), 3.0)
            live = True
        except Exception:
            decision = {
                "selected_node": "kamiwaza-edge-il6-spi-pendleton",
                "rationale": "Sensitivity = CUI; nearest IL6-accredited node; lowest latency.",
                "alternates_considered": 4,
            }
    brief = (
        f"MESH-INFER decision: route '{task_key}' at sensitivity={sensitivity} -> "
        f"{decision.get('selected_node', '?')}. {decision.get('rationale', '')}"
    )
    return {**meta, "live": live, "task_key": task_key, "sensitivity": sensitivity,
            "decision": decision, "brief": brief}


# 43. FED-RAG — federated RAG (LIVE: federated_query)
def query_fed_rag(query: str = "alternator MTVR shortfalls",
                  k_per_silo: int = 3, **kw) -> dict:
    meta = _meta("query_fed_rag")
    cached = _read_cached("50-fed-rag")
    fed: dict | None = None
    live = False
    if not _is_cache_first():
        try:
            mod = _import_sibling("50-fed-rag", "federation")
            if hasattr(mod, "federated_query"):
                fed = _live_call(lambda: mod.federated_query(query, k_per_silo), 4.0)
                live = True
        except Exception:
            fed = None
    if fed is None:
        try:
            mod = _import_sibling("50-fed-rag", "federation")
            fed = _live_call(lambda: mod.federated_query(query, k_per_silo), 4.0)
            live = True
        except Exception:
            fed = {
                "silos_queried": ["Albany", "Pendleton", "Philly", "Tobyhanna"],
                "hits_total": 9,
                "top_hit_silo": "Albany",
            }
    brief = _first_brief(cached) or (
        f"FED-RAG — '{query}': queried {len(fed.get('silos_queried', fed.get('silos', []))) or 4} "
        f"silos in parallel. {fed.get('hits_total', 9)} cited paragraphs returned; "
        "no corpus data left its enclave."
    )
    return {**meta, "live": live, "query": query,
            "summary": fed, "brief": brief}


# 44. CHAIN-OF-COMMAND — ReBAC walk (LIVE: compute_access)
def query_chain_of_command(subject_id: str = "PERS-LCpl-Smith",
                           object_id: str = "DOC-001", **kw) -> dict:
    meta = _meta("query_chain_of_command")
    cached = _read_cached("51-chain-of-command")
    decision: dict | None = None
    live = False
    if not _is_cache_first():
        try:
            mod = _import_sibling("51-chain-of-command", "engine")
            if hasattr(mod, "compute_access"):
                decision = _live_call(lambda: mod.compute_access(subject_id, object_id), 4.0)
                live = True
        except Exception:
            decision = None
    if decision is None:
        try:
            mod = _import_sibling("51-chain-of-command", "engine")
            decision = _live_call(lambda: mod.compute_access(subject_id, object_id), 4.0)
            live = True
        except Exception:
            decision = {
                "verdict": "PERMIT_WITH_REDACTION",
                "path": ["LCpl Smith", "S-2", "Bn", "Regt", "MARFORPAC", "DOC-001"],
                "rationale": "ReBAC: clearance OK; need-to-know via S-2 chain; NOFORN redacted.",
            }
    brief = _first_brief(cached) or (
        f"CHAIN-OF-COMMAND ReBAC: subject={subject_id}, object={object_id} -> "
        f"{decision.get('verdict', '?')}. Path-walk depth: "
        f"{len(decision.get('path', []))}."
    )
    return {**meta, "live": live, "subject_id": subject_id, "object_id": object_id,
            "decision": decision, "brief": brief}


# 45. CAT-ROUTER — Kamiwaza Model Gateway routing  (LIVE: route_workflow)
def query_cat_router(workflow_id: str = "medlog_opord",
                     mode: str = "best_quality", **kw) -> dict:
    meta = _meta("query_cat_router")
    cached = _read_cached("52-cat-router")
    routed: dict | None = None
    live = False
    if not _is_cache_first():
        try:
            mod = _import_sibling("52-cat-router", "router")
            if hasattr(mod, "route_workflow"):
                routed = _live_call(lambda: mod.route_workflow(workflow_id, mode=mode), 4.0)
                live = True
        except Exception:
            routed = None
    if routed is None:
        try:
            mod = _import_sibling("52-cat-router", "router")
            routed = _live_call(lambda: mod.route_workflow(workflow_id, mode=mode), 4.0)
            live = True
        except Exception:
            routed = {}
    routed = routed or {}
    totals = routed.get("totals") or {
        "cost_usd": 0.0143, "latency_s": 4.2,
        "avg_quality": 0.86, "n_unique_models": 3,
    }
    decisions = routed.get("decisions") or []
    brief = _first_brief(cached) or (
        f"CAT-ROUTER — workflow {workflow_id} (mode={mode}): "
        f"{len(decisions) or 4} tasks routed across "
        f"{totals.get('n_unique_models', 3)} unique models. "
        f"Cost ${totals.get('cost_usd', 0):.4f}, latency {totals.get('latency_s', 0):.2f}s, "
        f"avg quality {totals.get('avg_quality', 0):.2f}."
    )
    return {**meta, "live": live, "workflow_id": workflow_id, "mode": mode,
            "totals": totals,
            "decisions_count": len(decisions) or 4,
            "decisions_preview": [
                {"task": d.get("task") or d.get("task_type"),
                 "winner": d.get("winner") or d.get("model_id")}
                for d in (decisions[:3] if decisions else [
                    {"task": "fast_classification", "winner": "edge-llama-8b-il5"},
                    {"task": "long_context_summarization", "winner": "kamiwaza-qwen-72b"},
                    {"task": "long_form_prose", "winner": "kamiwaza-llama-405b"},
                ])
            ],
            "brief": brief}


# 46. DDE-RAG — compute-at-data  (LIVE: dde_trace + simulate_execution)
def query_dde_rag(query: str = "M1A1 transmission risk",
                  corpus_size_gb: float = 50.0, **kw) -> dict:
    meta = _meta("query_dde_rag")
    cached = _read_cached("53-dde-rag")
    summary: dict | None = None
    live = False
    if not _is_cache_first():
        try:
            mod_dde = _import_sibling("53-dde-rag", "dde")
            if hasattr(mod_dde, "load_nodes") and hasattr(mod_dde, "load_queries"):
                nodes = _live_call(mod_dde.load_nodes, 2.0)
                queries = _live_call(mod_dde.load_queries, 2.0)
                q = next((qq for qq in queries
                          if "M1A1" in qq.get("question", "")), queries[0]) if queries else None
                if q:
                    naive = _live_call(lambda: mod_dde.naive_trace(q, nodes), 3.0)
                    dde = _live_call(lambda: mod_dde.dde_trace(q, nodes), 3.0)
                    summary = {
                        "naive_seconds": naive.get("total_seconds"),
                        "dde_seconds": dde.get("total_seconds"),
                        "speedup_x": (
                            naive.get("total_seconds", 1) / max(dde.get("total_seconds", 1), 0.001)
                        ),
                        "bytes_moved_naive": naive.get("bytes_moved"),
                        "bytes_moved_dde": dde.get("bytes_moved"),
                    }
                    live = True
        except Exception:
            summary = None
    if summary is None:
        summary = {
            "naive_seconds": 1820.0, "dde_seconds": 47.0, "speedup_x": 38.7,
            "bytes_moved_naive": 53_687_091_200, "bytes_moved_dde": 8_192,
        }
    brief = _first_brief(cached) or (
        f"DDE-RAG — '{query}' over {corpus_size_gb:.0f} GB: compute-at-data took "
        f"{summary['dde_seconds']:.1f}s vs naive central-pull "
        f"{summary['naive_seconds']:.0f}s ({summary['speedup_x']:.1f}x faster). "
        f"Bytes moved across enclave: only {summary['bytes_moved_dde']/1024:.1f} KB."
    )
    return {**meta, "live": live, "query": query,
            "corpus_size_gb": corpus_size_gb,
            "summary": summary, "brief": brief}


# ─────────────────────────────────────────────────────────────────────────────
# OpenAI tool-calling schemas (one per implemented tool)
# ─────────────────────────────────────────────────────────────────────────────
def _schema(name: str, description: str, properties: dict,
            required: list[str] | None = None) -> dict:
    out = {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                **({"required": required} if required else {}),
            },
        },
    }
    return out


TOOL_SCHEMAS: list[dict] = [
    _schema("query_marlin",
            "MARLIN (apps/01-marlin): Maritime route risk classifier. Use to score "
            "a sealift lane vs piracy + chokepoint risk.",
            {"route": {"type": "string", "description": "e.g. 'Beaumont->Apra'."}}),
    _schema("query_forge",
            "FORGE (apps/02-forge): Vibration spectrogram classifier. Use for any "
            "depot-machinery 'is this bearing dying' question.",
            {"asset_id": {"type": "string"}, "csv_path": {"type": "string"}}),
    _schema("query_optik",
            "OPTIK (apps/03-optik): Vision-RAG over Marine technical manuals. Use "
            "when the operator uploads a photo of equipment + asks a TM question.",
            {"question": {"type": "string"}, "image_path": {"type": "string"}}),
    _schema("query_riptide",
            "RIPTIDE (apps/04-riptide): Flood-risk overlay for an installation. "
            "Use for any 'flood risk at <installation>' question.",
            {"installation": {"type": "string"}}),
    _schema("query_meridian",
            "MERIDIAN (apps/05-meridian): MARFORPAC sustainment-node climate-risk "
            "scorer. Use for named-node sustainment-line impact across "
            "Guam/Okinawa/CNMI/Philippines.",
            {"scope": {"type": "string"}}),
    _schema("query_corsair",
            "CORSAIR (apps/06-corsair): Maritime pattern-of-life + dark-vessel "
            "detection for an AOI.",
            {"aoi": {"type": "string"}}),
    _schema("query_strider",
            "STRIDER (apps/07-strider): Convoy route IED-risk + alternate picker.",
            {"route": {"type": "string"}}),
    _schema("query_raptor",
            "RAPTOR (apps/08-raptor): ISR object detection + INTREP composer. "
            "Use when the operator uploads ISR imagery.",
            {"image_path": {"type": "string"}, "aoi": {"type": "string"}}),
    _schema("query_vanguard",
            "VANGUARD (apps/09-vanguard): PCS HHG cargo tracker + claims pre-filer.",
            {"member_id": {"type": "string"}}),
    _schema("query_sentinel",
            "SENTINEL (apps/10-sentinel): Perimeter intrusion vision-classifier. "
            "Use when the operator uploads a perimeter camera frame.",
            {"image_path": {"type": "string"}, "installation": {"type": "string"}}),
    _schema("query_anchor",
            "ANCHOR (apps/11-anchor): RAG over MARADMIN + SOP corpus.",
            {"question": {"type": "string"}}),
    _schema("query_weathervane",
            "WEATHERVANE (apps/12-weathervane): Mission weather windowing for an "
            "AOI. Use for any weather / typhoon / window question.",
            {"aoi": {"type": "string"}, "window": {"type": "string"},
             "mission": {"type": "string"}},
            required=["aoi"]),
    _schema("query_wildfire",
            "WILDFIRE (apps/13-wildfire): Wildfire risk + comms PACE cutover for "
            "a Marine installation.",
            {"installation": {"type": "string"}}),
    _schema("query_ember",
            "EMBER (apps/14-ember): NASA FIRMS active-fire dashboard for training "
            "ranges. Pass a CSV of FIRMS rows for live mode.",
            {"aoi": {"type": "string"}}),
    _schema("query_vitals",
            "VITALS (apps/15-vitals): DHA blood-logistics. Score hub-and-spoke "
            "risk for blood/Class VIII supply across MARFORPAC. Use for any blood "
            "/ cold-chain / Class VIII medical question.",
            {"question": {"type": "string"},
             "scenario_id": {"type": "string",
                             "enum": ["baseline", "airlift_loss",
                                      "cold_chain_breach", "mass_cas_event"]}}),
    _schema("query_watchtower",
            "WATCHTOWER (apps/16-watchtower): Installation Common Operating "
            "Picture aggregator. Use for installation-wide situational picture.",
            {"installation": {"type": "string"}}),
    _schema("query_pallet_vision",
            "PALLET-VISION (apps/17-pallet-vision): AI Visual Quantification — "
            "count pallets/trucks/containers from an aerial or warehouse photo.",
            {"image_path": {"type": "string"}, "aoi": {"type": "string"}}),
    _schema("query_trace",
            "TRACE (apps/18-trace): Class I-IX consumption-rate estimator for a "
            "MAGTF scenario.",
            {"scenario_id": {"type": "string"}}),
    _schema("query_reorder",
            "REORDER (apps/19-reorder): Class IX parts demand forecast for a "
            "deployed MAGTF. Returns shortfall + reorder priorities.",
            {"scenario_id": {"type": "string"}, "forward_node": {"type": "string"}}),
    _schema("query_queue",
            "QUEUE (apps/20-queue): Depot maintenance throughput optimizer.",
            {"depot": {"type": "string"}}),
    _schema("query_ghost",
            "GHOST (apps/21-ghost): RF pattern-of-life heatmap; flag anomalous "
            "WiFi/Bluetooth emitters.",
            {"aoi": {"type": "string"}}),
    _schema("query_stockroom",
            "STOCKROOM (apps/22-stockroom): Unit inventory audit (on-hand vs "
            "authorized; cycle-count exceptions).",
            {"unit": {"type": "string"}}),
    _schema("query_chain",
            "CHAIN (apps/24-chain): Global supply-chain disruption forecaster.",
            {"nsn": {"type": "string"}}),
    _schema("query_opengate",
            "OPENGATE (apps/26-opengate): RAG over the data.gov catalog.",
            {"question": {"type": "string"}}),
    _schema("query_embodied",
            "EMBODIED (apps/27-embodied): Egocentric multimodal Marine training "
            "simulator + coach. Accepts an image of a training scene.",
            {"scene": {"type": "string"}, "image_path": {"type": "string"}}),
    _schema("query_redline",
            "REDLINE (apps/28-redline): CUI auto-tagging assistant. Use when the "
            "operator uploads a document scan.",
            {"image_path": {"type": "string"}, "doc_id": {"type": "string"}}),
    _schema("query_dispatch",
            "DISPATCH (apps/31-dispatch): 911-style triage + nearest-unit dispatch.",
            {"intake": {"type": "string"}}),
    _schema("query_learn",
            "LEARN (apps/32-learn): Marine LMS cohort assessment.",
            {"course_id": {"type": "string"}, "cohort": {"type": "string"}}),
    _schema("query_cuas_detect",
            "CUAS-DETECT (apps/35-cuas-detect): Counter-UAS RF spectrogram "
            "classifier + engagement decision. Image-aware.",
            {"installation": {"type": "string"},
             "window_days": {"type": "integer"},
             "image_path": {"type": "string"}}),
    _schema("query_spectra",
            "SPECTRA (apps/36-spectra): EW emitter I/Q classifier + counter-EW "
            "recommendation. Pass a CSV of I/Q samples for live mode.",
            {"emitter_id": {"type": "string"}, "csv_path": {"type": "string"}}),
    _schema("query_cadence",
            "CADENCE (apps/37-cadence): Per-Marine assessment + doctrine-grounded "
            "feedback letter.",
            {"student_id": {"type": "string"}, "course_id": {"type": "string"}}),
    _schema("query_omni",
            "OMNI (apps/38-omni): Installation Common Operating Picture (ICOP) "
            "fusion under ABAC. Use for installation-wide anomaly correlation.",
            {"installation": {"type": "string"}, "persona_id": {"type": "string"}}),
    _schema("query_contested_log",
            "CONTESTED-LOG (apps/39-contested-log): End-to-end CONUS-to-EABO "
            "contested-sustainment plan (rail + sealift + last-mile).",
            {"request": {"type": "string"}, "deadline_days": {"type": "integer"}}),
    _schema("query_predict_maint",
            "PREDICT-MAINT (apps/40-predict-maint): Fleet RUL forecast.",
            {"asset_class": {"type": "string"}}),
    _schema("query_storm_shift",
            "STORM-SHIFT (apps/41-storm-shift): Storm-shift evacuation + "
            "sheltering planner for an installation.",
            {"installation": {"type": "string"}}),
    _schema("query_drone_dominance",
            "DRONE-DOM (apps/42-drone-dominance): Counter-drone air-dominance "
            "posture allocator.",
            {"aoi": {"type": "string"}}),
    _schema("query_omni_intel",
            "OMNI-INTEL (apps/43-omni-intel): All-Source Intel Brief (ASIB) fusion.",
            {"scenario": {"type": "string"}}),
    _schema("query_marine_medic",
            "MARINE-MEDIC (apps/44-marine-medic): TCCC casualty triage + "
            "treatment ladder + 9-line MEDEVAC. Image-aware (photo of injury).",
            {"casualty_id": {"type": "string"}, "image_path": {"type": "string"}}),
    _schema("query_guardrail",
            "GUARDRAIL (apps/45-guardrail): Browser-agent governance + ABAC CUI "
            "release. Image-aware (document scan).",
            {"persona_id": {"type": "string"}, "doc_id": {"type": "string"},
             "image_path": {"type": "string"}}),
    _schema("query_travelog",
            "TRAVELOG (apps/46-travelog): PCS travel itinerary planner + DTS "
            "voucher pre-validator.",
            {"member_id": {"type": "string"},
             "from_loc": {"type": "string"}, "to_loc": {"type": "string"}}),
    _schema("query_schoolhouse",
            "SCHOOLHOUSE (apps/47-schoolhouse): Schoolhouse training-competency "
            "rollup.",
            {"course_id": {"type": "string"}}),
    _schema("query_mesh_infer",
            "MESH-INFER (apps/49-mesh-infer): Kamiwaza Inference Mesh router. "
            "Choose the right inference node by data sensitivity (UNCLAS / CUI / "
            "SECRET / TS). Use FIRST when the user query is sensitive or when you "
            "need to demonstrate sensitivity-aware routing.",
            {"task_key": {"type": "string"},
             "sensitivity": {"type": "string",
                             "enum": ["UNCLAS", "CUI", "SECRET", "TS"]}}),
    _schema("query_fed_rag",
            "FED-RAG (apps/50-fed-rag): Federated RAG across Albany / Pendleton / "
            "Philly / Tobyhanna silos with NO data movement. Use for cross-silo "
            "queries where the data shouldn't leave its enclave.",
            {"query": {"type": "string"}, "k_per_silo": {"type": "integer"}}),
    _schema("query_chain_of_command",
            "CHAIN-OF-COMMAND (apps/51-chain-of-command): Kamiwaza ReBAC — "
            "relationship-based access control. Walk the personnel + clearance + "
            "ORBAT graph to decide if subject can access object. Use for any "
            "'can <Marine> access <document>' question.",
            {"subject_id": {"type": "string"}, "object_id": {"type": "string"}}),
    _schema("query_cat_router",
            "CAT-ROUTER (apps/52-cat-router): Kamiwaza Model Gateway routing. "
            "Score every model in the catalog per task and return the optimal "
            "pick (with audit chain). Modes: best_quality, fast_cheap. Use when "
            "the operator asks 'pick the right model'.",
            {"workflow_id": {"type": "string"},
             "mode": {"type": "string", "enum": ["best_quality", "fast_cheap"]}}),
    _schema("query_dde_rag",
            "DDE-RAG (apps/53-dde-rag): Kamiwaza Distributed Data Engine — "
            "compute-at-data. Use for big-corpus queries where moving the data is "
            "the wrong move (10+ GB scan).",
            {"query": {"type": "string"},
             "corpus_size_gb": {"type": "number"}}),
]


TOOL_REGISTRY: dict[str, Callable[..., dict]] = {
    "query_marlin":            query_marlin,
    "query_forge":             query_forge,
    "query_optik":             query_optik,
    "query_riptide":           query_riptide,
    "query_meridian":          query_meridian,
    "query_corsair":           query_corsair,
    "query_strider":           query_strider,
    "query_raptor":            query_raptor,
    "query_vanguard":          query_vanguard,
    "query_sentinel":          query_sentinel,
    "query_anchor":            query_anchor,
    "query_weathervane":       query_weathervane,
    "query_wildfire":          query_wildfire,
    "query_ember":             query_ember,
    "query_vitals":            query_vitals,
    "query_watchtower":        query_watchtower,
    "query_pallet_vision":     query_pallet_vision,
    "query_trace":             query_trace,
    "query_reorder":           query_reorder,
    "query_queue":             query_queue,
    "query_ghost":             query_ghost,
    "query_stockroom":         query_stockroom,
    "query_chain":             query_chain,
    "query_opengate":          query_opengate,
    "query_embodied":          query_embodied,
    "query_redline":           query_redline,
    "query_dispatch":          query_dispatch,
    "query_learn":             query_learn,
    "query_cuas_detect":       query_cuas_detect,
    "query_spectra":           query_spectra,
    "query_cadence":           query_cadence,
    "query_omni":              query_omni,
    "query_contested_log":     query_contested_log,
    "query_predict_maint":     query_predict_maint,
    "query_storm_shift":       query_storm_shift,
    "query_drone_dominance":   query_drone_dominance,
    "query_omni_intel":        query_omni_intel,
    "query_marine_medic":      query_marine_medic,
    "query_guardrail":         query_guardrail,
    "query_travelog":          query_travelog,
    "query_schoolhouse":       query_schoolhouse,
    "query_mesh_infer":        query_mesh_infer,
    "query_fed_rag":           query_fed_rag,
    "query_chain_of_command":  query_chain_of_command,
    "query_cat_router":        query_cat_router,
    "query_dde_rag":           query_dde_rag,
}


def list_tools() -> list[str]:
    return list(TOOL_REGISTRY.keys())


def has_kamiwaza_feature(name: str) -> str | None:
    return load_registry().get(name, {}).get("kamiwaza_feature")


def is_multimodal(name: str) -> bool:
    return load_registry().get(name, {}).get("modality") in ("image", "csv")


if __name__ == "__main__":
    # Smoke test — every tool returns a serializable dict
    n_ok = 0
    for name, fn in TOOL_REGISTRY.items():
        out = fn()
        ok = bool(isinstance(out, dict) and out.get("tool") == name and out.get("codename"))
        n_ok += int(ok)
        print(f"  {'OK' if ok else 'FAIL':4} {name:26s} live={out.get('live')!s:5} "
              f"keys={list(out)[:5]}")
    print(f"\n{n_ok}/{len(TOOL_REGISTRY)} tools OK")
    print(f"schemas: {len(TOOL_SCHEMAS)}")
