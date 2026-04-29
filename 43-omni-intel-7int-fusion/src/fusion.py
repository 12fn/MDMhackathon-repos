"""Cross-source observation correlator -- the OMNI hero algorithm.

Input:  list of normalized observations (any subset of the 7 INTs).
Output: list of FusionCluster -- sets of >= 2 observations from >= 2 source-
        types that share a target/area within space + time tolerances.

Doctrine: this implements the multi-INT confirmation rule from Marine Corps
intelligence doctrine -- a single-source signature is a "lead", a two-INT
corroboration is an "indicator", a 3+-INT corroboration meets CCIR threshold.

Algorithm (greedy spatial-temporal join with per-source weighting):

  1. Sort observations by dtg.
  2. For each obs O, find candidate neighbors within
        TIME_WINDOW_MIN minutes  AND
        haversine(lat,lon, O.lat,O.lon) < SPACE_RADIUS_KM
     drawn from a DIFFERENT source_type than O.
  3. Build clusters by union-find on those edges.
  4. Score each cluster by sum(SOURCE_WEIGHTS[t] * obs.confidence) over its members,
     and require >= MIN_CONCURRING_SOURCES distinct source-types.
  5. Emit FusionCluster with explainability trace ("flagged because:
     <obs_a> [12:05] + <obs_b> [12:15] + ... within R km of centroid").

Per-source confidence weights reflect collection priority -- a HIT-UAV thermal
detection is harder to spoof and costlier to obtain than ambient WiFi noise,
so it gets a higher weight.
"""
from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------
TIME_WINDOW_MIN = 120       # cross-source obs must be within this many minutes
SPACE_RADIUS_KM = 8.0       # ... and within this many km
MIN_CONCURRING_SOURCES = 2  # >=2 distinct source-types to count as a fusion

SOURCE_WEIGHTS = {
    "hituav":  1.00,   # MASINT thermal -- very high confidence
    "milobj":  0.95,   # IMINT object detection
    "dronerf": 0.90,   # SIGINT drone-control RF
    "ais":     0.80,   # GEOINT AIS
    "firms":   0.75,   # GEOINT FIRMS
    "asam":    0.70,   # OSINT advisory reporting
    "wifibt":  0.50,   # SIGINT WiFi/BT (noisy ambient)
}

INT_DISCIPLINE = {
    "hituav":  "MASINT",
    "milobj":  "IMINT",
    "dronerf": "SIGINT",
    "ais":     "GEOINT",
    "firms":   "GEOINT",
    "asam":    "OSINT",
    "wifibt":  "SIGINT",
}

CLASS_COLORS = {
    "combat":     "#FF3B30",
    "commercial": "#34C759",
    "industrial": "#AF52DE",
    "wildfire":   "#FFD60A",
    "ambient":    "#8E8E93",
    "ambiguous":  "#5AC8FA",
}

SOURCE_COLORS = {
    "ais":     "#34C759",   # green
    "asam":    "#FF9500",   # orange
    "milobj":  "#5856D6",   # indigo
    "hituav":  "#FF2D55",   # pink-red
    "dronerf": "#FFD60A",   # yellow
    "wifibt":  "#5AC8FA",   # cyan
    "firms":   "#FF3B30",   # red
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class FusionCluster:
    cluster_id: str
    centroid_lat: float
    centroid_lon: float
    start_dtg: str
    end_dtg: str
    member_obs_ids: list[str]
    sources_present: list[str]      # distinct source-types
    int_disciplines: list[str]      # distinct INTs (GEOINT/SIGINT/MASINT/IMINT/OSINT)
    weighted_score: float
    explanation: str                # human-readable trace
    explanation_lines: list[str]    # per-edge reasons (for fusion-trace sidebar)
    fusion_anchor_truth: str | None = None  # if any member references a planted anchor
    classification: dict | None = None
    audit_hash: str | None = None
    members_full: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------
def haversine_km(lat1, lon1, lat2, lon2) -> float:
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _parse_dtg(s: str) -> datetime:
    return datetime.fromisoformat(s.rstrip("Z"))


# ---------------------------------------------------------------------------
# Union-Find
# ---------------------------------------------------------------------------
class _UF:
    def __init__(self, n: int):
        self.p = list(range(n))
    def find(self, i: int) -> int:
        while self.p[i] != i:
            self.p[i] = self.p[self.p[i]]
            i = self.p[i]
        return i
    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[ra] = rb


# ---------------------------------------------------------------------------
# Correlator
# ---------------------------------------------------------------------------
def correlate_clusters(
    observations: list[dict],
    *,
    time_window_min: int = TIME_WINDOW_MIN,
    space_radius_km: float = SPACE_RADIUS_KM,
    min_sources: int = MIN_CONCURRING_SOURCES,
) -> list[FusionCluster]:
    """Greedy spatial-temporal cross-source join.

    Two observations form an edge iff:
      - source_type differs
      - |dtg_a - dtg_b| <= time_window_min
      - haversine(a, b) <= space_radius_km
    Edges -> union-find -> clusters. Filter to clusters with >= min_sources
    distinct source-types. Score by weighted_score, return sorted desc.
    """
    if not observations:
        return []

    obs = sorted(observations, key=lambda o: o["dtg"])
    n = len(obs)
    times = [_parse_dtg(o["dtg"]) for o in obs]
    uf = _UF(n)

    # Edge collection (per-edge reason string for explainability)
    edges: list[tuple[int, int, str, float]] = []

    # Sliding window in time -- O(n * w) instead of O(n^2)
    j_start = 0
    for i in range(n):
        # advance j_start so times[j_start] >= times[i] - time_window_min
        while j_start < n and (times[i] - times[j_start]).total_seconds() / 60 > time_window_min:
            j_start += 1
        # check forward neighbors only (i, j>i)
        for j in range(i + 1, n):
            dt_min = (times[j] - times[i]).total_seconds() / 60
            if dt_min > time_window_min:
                break
            if obs[i]["source_type"] == obs[j]["source_type"]:
                continue
            d_km = haversine_km(obs[i]["lat"], obs[i]["lon"],
                                obs[j]["lat"], obs[j]["lon"])
            if d_km > space_radius_km:
                continue
            uf.union(i, j)
            edges.append((i, j, _edge_reason(obs[i], obs[j], dt_min, d_km), d_km))

    # Group by root
    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        groups[uf.find(i)].append(i)

    out: list[FusionCluster] = []
    for root, idxs in groups.items():
        members = [obs[i] for i in idxs]
        srcs = sorted(set(m["source_type"] for m in members))
        if len(srcs) < min_sources:
            continue
        ints_ = sorted(set(INT_DISCIPLINE[s] for s in srcs))
        score = sum(SOURCE_WEIGHTS.get(m["source_type"], 0.5) * m["confidence"] for m in members)
        lats = [m["lat"] for m in members]
        lons = [m["lon"] for m in members]
        cent_lat = sum(lats) / len(lats)
        cent_lon = sum(lons) / len(lons)
        dtgs = sorted(m["dtg"] for m in members)

        # explanation: 1 line per cross-source edge inside this cluster
        member_set = set(idxs)
        cluster_edges = [e for e in edges if e[0] in member_set and e[1] in member_set]
        cluster_edges.sort(key=lambda e: e[3])  # tightest first
        ex_lines = [e[2] for e in cluster_edges[:6]]
        explanation = "; ".join(ex_lines) if ex_lines else "single-edge cluster"

        # detect any planted-anchor truth in members
        anchor = None
        for m in members:
            tag = m.get("raw_signature", {}).get("fusion_anchor")
            if tag:
                anchor = tag
                break

        cluster_id = f"FC-{hashlib.sha256(('|'.join(sorted(m['observation_id'] for m in members))).encode()).hexdigest()[:8].upper()}"
        out.append(FusionCluster(
            cluster_id=cluster_id,
            centroid_lat=round(cent_lat, 5),
            centroid_lon=round(cent_lon, 5),
            start_dtg=dtgs[0],
            end_dtg=dtgs[-1],
            member_obs_ids=[m["observation_id"] for m in members],
            sources_present=srcs,
            int_disciplines=ints_,
            weighted_score=round(score, 3),
            explanation=explanation,
            explanation_lines=ex_lines,
            fusion_anchor_truth=anchor,
            members_full=members,
        ))

    out.sort(key=lambda c: -c.weighted_score)
    return out


def _edge_reason(a: dict, b: dict, dt_min: float, d_km: float) -> str:
    """One-line human reason for why obs A and obs B form a fusion edge."""
    a_kind = _short_kind(a)
    b_kind = _short_kind(b)
    a_t = a["dtg"][11:16] + "Z"
    b_t = b["dtg"][11:16] + "Z"
    return (f"{a['source_type'].upper()} {a_kind} [{a_t}] + "
            f"{b['source_type'].upper()} {b_kind} [{b_t}] "
            f"within {d_km:.1f} km / {dt_min:.0f} min")


def _short_kind(o: dict) -> str:
    raw = o.get("raw_signature", {})
    s = o["source_type"]
    if s == "ais":     return f"{raw.get('vessel_type','vsl')} {('GAP' if raw.get('ais_gap_min') else 'ping')}"
    if s == "asam":    return raw.get("incident_type", "incident")
    if s == "milobj":  return raw.get("platform_class", "obj")
    if s == "hituav":  return raw.get("blob_type", "ir")
    if s == "dronerf": return raw.get("rf_class", "rf")
    if s == "wifibt":  return raw.get("mac_oui", "rf") + " " + raw.get("frame_type", "")
    if s == "firms":   return f"frp {raw.get('frp_mw',0):.0f}MW"
    return s


# ---------------------------------------------------------------------------
# Heuristic classifier (deterministic baseline; LLM upgrade in classify.py)
# ---------------------------------------------------------------------------
def heuristic_classify(c: FusionCluster) -> dict:
    srcs = set(c.sources_present)
    if "firms" in srcs and any(
        m["source_type"] == "firms" and m["raw_signature"].get("frp_mw", 0) > 50
        for m in c.members_full
    ):
        if "milobj" in srcs or "wifibt" in srcs:
            return {"label": "industrial", "confidence": 0.78,
                    "rationale": "FIRMS high-FRP cluster co-located with IMINT/RF -- industrial fire signature.",
                    "recommend": "HUMINT confirm with facility owner; re-task IMINT next overhead pass.",
                    "source": "heuristic"}
        return {"label": "wildfire", "confidence": 0.6,
                "rationale": "FIRMS detection without supporting INT -- likely natural / agricultural burn.",
                "recommend": "De-prioritize unless adjacent to MSR.", "source": "heuristic"}
    if {"ais", "hituav"} <= srcs or {"ais", "dronerf"} <= srcs:
        return {"label": "combat", "confidence": 0.8,
                "rationale": "AIS gap or evasive maneuver corroborated by IR / RF -- covert vessel signature.",
                "recommend": "Re-task MQ-9A or P-8A onto the centroid for confirmation.",
                "source": "heuristic"}
    if "asam" in srcs and "ais" in srcs:
        return {"label": "combat", "confidence": 0.72,
                "rationale": "ASAM advisory co-located with AIS evasive maneuver -- piracy / boarding signature.",
                "recommend": "Notify MARLO; vector nearest USCG / CTF-151 asset.",
                "source": "heuristic"}
    if "wifibt" in srcs and len(srcs) >= 3:
        return {"label": "ambient", "confidence": 0.5,
                "rationale": "Multi-INT cluster but dominated by ambient WiFi/BT -- likely population centre.",
                "recommend": "Filter; track delta vs baseline only.", "source": "heuristic"}
    return {"label": "ambiguous", "confidence": 0.5,
            "rationale": f"Cross-source edges ({len(c.sources_present)} sources) but no doctrinal pattern matched.",
            "recommend": "Hold for analyst review.", "source": "heuristic"}


def llm_classify(c: FusionCluster) -> dict:
    """Per-cluster classification via chat_json (cache-first; falls back to heuristic)."""
    try:
        import sys as _sys
        _sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))
        from shared.kamiwaza_client import chat_json  # type: ignore
    except Exception:
        return heuristic_classify(c)

    payload = {
        "cluster_id": c.cluster_id,
        "centroid": [c.centroid_lat, c.centroid_lon],
        "sources_present": c.sources_present,
        "int_disciplines": c.int_disciplines,
        "weighted_score": c.weighted_score,
        "n_obs": len(c.member_obs_ids),
        "duration_window": [c.start_dtg, c.end_dtg],
        "edge_reasons": c.explanation_lines,
        "member_summaries": [
            {"src": m["source_type"], "kind": _short_kind(m), "conf": m["confidence"]}
            for m in c.members_full[:10]
        ],
    }

    sys_prompt = (
        "You are a USMC LOGCOM CDAO all-source intelligence fusion analyst. You "
        "review CROSS-INT clusters produced by the OMNI correlator and assign a "
        "doctrinal label. Use Marine brevity. Cite the INTs (GEOINT, SIGINT, "
        "MASINT, IMINT, OSINT) that drove the call. Respond ONLY as JSON."
    )
    user_prompt = (
        "Classify this fusion cluster. Choose label from: "
        "combat, commercial, industrial, wildfire, ambient, ambiguous. "
        "Return JSON: {\"label\": str, \"confidence\": float 0..1, "
        "\"rationale\": str (<=60 words, cite INTs by name), "
        "\"recommend\": str (<=25 words, name the ISR asset)}.\n\n"
        f"CLUSTER:\n{payload}"
    )
    try:
        out = chat_json(
            [{"role": "system", "content": sys_prompt},
             {"role": "user", "content": user_prompt}],
            schema_hint="label, confidence, rationale, recommend",
            temperature=0.2,
        )
        label = str(out.get("label", "ambiguous")).lower().strip()
        if label not in CLASS_COLORS:
            label = "ambiguous"
        return {
            "label": label,
            "confidence": round(float(out.get("confidence", 0.5)), 2),
            "rationale": str(out.get("rationale", "")).strip(),
            "recommend": str(out.get("recommend", "")).strip(),
            "source": "llm",
        }
    except Exception:
        return heuristic_classify(c)
