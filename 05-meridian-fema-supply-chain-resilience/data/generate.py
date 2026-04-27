"""MERIDIAN synthetic data generator.

Produces a synthetic 30-report corpus + the supporting node/edge topology so
the app runs end-to-end with zero external data:

  data/nodes.json         - 12 critical MARFORPAC sustainment nodes
  data/edges.json         - supply-line topology between nodes
  data/reports/*.md       - 30 NOAA / JTWC / FEMA / INDOPACOM J2 / G-4 reports
                            mixing typhoons, swell, geopolitical incidents,
                            equipment outages (60-day window).

Seeded with random.Random(1776) for full reproducibility.

REAL-DATA SWAP (Bucket A — FEMA Supply Chain Climate Resilience):
  Replace the report bodies and node attributes below with a single
  `pandas.read_csv` (or `read_json`) of the FEMA Supply Chain Resilience
  indicator dataset. Required columns: node ID, lat, lon, type, criticality,
  climate exposure, primary peril. Drop the CSV in `data/` and point this
  module at it; the rest of the pipeline (`src/agent.py`, `src/graph.py`,
  `src/app.py`) is unchanged.
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPORTS_DIR = ROOT / "reports"


# 12 critical MARFORPAC nodes (Guam -> Okinawa -> CNMI -> Philippines and reach-back)
NODES: list[dict] = [
    {"id": "APRA",   "name": "Apra Harbor",            "kind": "port",          "ccdr": "INDOPACOM",  "country": "Guam (US)",         "lat": 13.443, "lon": 144.660, "throughput_tpd": 9800,  "fuel_storage_kgal": 64000, "runway_ft": 0,    "criticality": 10},
    {"id": "AAFB",   "name": "Andersen AFB",           "kind": "runway",        "ccdr": "INDOPACOM",  "country": "Guam (US)",         "lat": 13.584, "lon": 144.930, "throughput_tpd": 5200,  "fuel_storage_kgal": 38000, "runway_ft": 11185,"criticality": 10},
    {"id": "NAHA",   "name": "Naha Port",              "kind": "port",          "ccdr": "INDOPACOM",  "country": "Okinawa (JPN)",     "lat": 26.214, "lon": 127.679, "throughput_tpd": 4400,  "fuel_storage_kgal": 18000, "runway_ft": 0,    "criticality": 8},
    {"id": "KADENA", "name": "Kadena AB",              "kind": "runway",        "ccdr": "INDOPACOM",  "country": "Okinawa (JPN)",     "lat": 26.355, "lon": 127.768, "throughput_tpd": 3800,  "fuel_storage_kgal": 42000, "runway_ft": 12100,"criticality": 10},
    {"id": "SUBIC",  "name": "Subic Bay",              "kind": "port",          "ccdr": "INDOPACOM",  "country": "Philippines",       "lat": 14.795, "lon": 120.282, "throughput_tpd": 6100,  "fuel_storage_kgal": 28000, "runway_ft": 8500, "criticality": 9},
    {"id": "TINIAN", "name": "Tinian (NMI)",           "kind": "runway",        "ccdr": "INDOPACOM",  "country": "CNMI (US)",         "lat": 14.998, "lon": 145.620, "throughput_tpd": 1600,  "fuel_storage_kgal": 9000,  "runway_ft": 8500, "criticality": 7},
    {"id": "IWAKUNI","name": "MCAS Iwakuni",           "kind": "runway",        "ccdr": "INDOPACOM",  "country": "Honshu (JPN)",      "lat": 34.144, "lon": 132.235, "throughput_tpd": 3200,  "fuel_storage_kgal": 26000, "runway_ft": 8000, "criticality": 8},
    {"id": "SASEBO", "name": "Sasebo",                 "kind": "port",          "ccdr": "INDOPACOM",  "country": "Kyushu (JPN)",      "lat": 33.158, "lon": 129.722, "throughput_tpd": 5400,  "fuel_storage_kgal": 31000, "runway_ft": 0,    "criticality": 9},
    {"id": "YOKO",   "name": "Yokosuka",               "kind": "port",          "ccdr": "INDOPACOM",  "country": "Honshu (JPN)",      "lat": 35.288, "lon": 139.671, "throughput_tpd": 8200,  "fuel_storage_kgal": 56000, "runway_ft": 0,    "criticality": 10},
    {"id": "PNI",    "name": "Pohnpei (FSM)",          "kind": "fuel_terminal", "ccdr": "INDOPACOM",  "country": "Micronesia",        "lat": 6.971,  "lon": 158.190, "throughput_tpd": 600,   "fuel_storage_kgal": 4200,  "runway_ft": 6000, "criticality": 5},
    {"id": "PALAU",  "name": "Palau",                  "kind": "fuel_terminal", "ccdr": "INDOPACOM",  "country": "Palau",             "lat": 7.367,  "lon": 134.544, "throughput_tpd": 800,   "fuel_storage_kgal": 5800,  "runway_ft": 7200, "criticality": 6},
    {"id": "DGAR",   "name": "Diego Garcia",           "kind": "runway",        "ccdr": "CENTCOM",    "country": "BIOT (UK/US)",      "lat": -7.313, "lon": 72.411,  "throughput_tpd": 4900,  "fuel_storage_kgal": 71000, "runway_ft": 12000,"criticality": 9},
]

# Supply-line topology (id pairs). Mix of sea legs (S), air legs (A), undersea cable (C).
EDGES: list[dict] = [
    {"a": "YOKO",    "b": "APRA",    "mode": "sea",   "leg_nm": 1500},
    {"a": "SASEBO",  "b": "NAHA",    "mode": "sea",   "leg_nm": 380},
    {"a": "NAHA",    "b": "KADENA",  "mode": "road",  "leg_nm": 7},
    {"a": "KADENA",  "b": "AAFB",    "mode": "air",   "leg_nm": 1370},
    {"a": "AAFB",    "b": "APRA",    "mode": "road",  "leg_nm": 12},
    {"a": "APRA",    "b": "TINIAN",  "mode": "sea",   "leg_nm": 105},
    {"a": "AAFB",    "b": "TINIAN",  "mode": "air",   "leg_nm": 130},
    {"a": "APRA",    "b": "PALAU",   "mode": "sea",   "leg_nm": 800},
    {"a": "APRA",    "b": "PNI",     "mode": "sea",   "leg_nm": 950},
    {"a": "PALAU",   "b": "SUBIC",   "mode": "sea",   "leg_nm": 600},
    {"a": "IWAKUNI", "b": "SASEBO",  "mode": "road",  "leg_nm": 220},
    {"a": "YOKO",    "b": "IWAKUNI", "mode": "road",  "leg_nm": 470},
    {"a": "SUBIC",   "b": "DGAR",    "mode": "sea",   "leg_nm": 4800},
    {"a": "APRA",    "b": "DGAR",    "mode": "cable", "leg_nm": 5800},
    {"a": "YOKO",    "b": "KADENA",  "mode": "cable", "leg_nm": 950},
]


# ---- Report templates -------------------------------------------------------

TYPHOON_NAMES = ["MAWAR-26B", "GUCHOL-26C", "TALIM-26D", "DOKSURI-26E", "KHANUN-26F", "SAOLA-26G"]

REPORT_TEMPLATES = {
    "typhoon_jtwc": """# JTWC TROPICAL CYCLONE WARNING {tc_num}
**Originator:** Joint Typhoon Warning Center, Pearl Harbor
**DTG:** {dtg}Z
**Cyclone:** Typhoon {name} ({basin})
**Intensity:** {kts} kt sustained, gusts {gust} kt — Category {cat}
**Track:** Forecast to track {bearing} at {fwd_kt} kt, closest point of approach to {target_name} ({target_id}) within {hours_to_cpa}h.
**Sea State:** Significant wave height {sw_m} m within 120 nm of center.
**Operational Impact:** Port operations at {target_name} expected DEGRADED for {degraded_h}h. Apron flight ops likely suspended at neighboring runway nodes for {flt_susp}h.
**Recommendation:** Sortie afloat assets NLT {sortie_dtg}Z. Pre-position {fuel_kgal} kgal MOGAS/JP-8 reserve on inland nodes.
""",
    "noaa_swell": """# NOAA MARINE WEATHER ADVISORY
**Issued:** {dtg}Z by NWS Honolulu / Guam WFO
**Region:** {region}
**Hazard:** Long-period {sw_m} m swell, period {period}s, from {dir}.
**Impact:** {target_name} ({target_id}) — pier-side cargo ops at risk of suspension. ROLON/ROLOFF ramps unsafe above {ramp_m} m.
**Forecast Confidence:** {conf}.
**Duration:** {dur_h}h beginning {begin_dtg}Z.
""",
    "fema_climate": """# FEMA SUPPLY CHAIN CLIMATE RESILIENCE BRIEF
**Reference:** supply-chain-resilience-guidance.pdf §{section}
**Date:** {dtg}
**Subject:** {target_name} ({target_id}) — climate exposure assessment.
**Finding:** Cumulative climate-stress index for {target_name} measured {idx}/10 over the trailing 90-day window.
**Drivers:** {drivers}.
**Cascading Effect:** A {hazard} event at {target_name} would propagate to downstream nodes via {mode} legs, with restoration timeline estimated at {restore_d} days.
**Mitigation Posture:** {posture}.
""",
    "geo_incident": """# INDOPACOM J2 INCIDENT REPORT (UNCLASSIFIED)
**DTG:** {dtg}Z
**Location:** Vicinity {target_name} ({target_id})
**Incident:** {incident}
**Effect on Sustainment:** {effect}
**Confidence:** {conf}.
**Recommended COA:** {coa}
""",
    "equipment_outage": """# MARFORPAC G-4 EQUIPMENT OUTAGE NOTICE
**DTG:** {dtg}Z
**Node:** {target_name} ({target_id})
**System:** {system}
**Status:** {status}
**Estimated Restoration:** {restore_h}h
**Throughput Impact:** {tpd_loss} short tons/day reduction while degraded.
**Workaround:** {workaround}
""",
}


def _dtg(rng: random.Random, days_back: int = 60) -> tuple[str, datetime]:
    base = datetime(2026, 4, 24, 12, 0, 0)
    delta = timedelta(minutes=rng.randint(0, days_back * 24 * 60))
    t = base - delta
    return t.strftime("%d%H%M%b%y").upper(), t


def _typhoon_report(rng: random.Random, target: dict) -> tuple[str, datetime]:
    dtg, t = _dtg(rng)
    name = rng.choice(TYPHOON_NAMES)
    kts = rng.randint(80, 145)
    cat = 1 + min(4, (kts - 64) // 20)
    sortie_t = t + timedelta(hours=rng.randint(12, 36))
    body = REPORT_TEMPLATES["typhoon_jtwc"].format(
        tc_num=f"WTPN3{rng.randint(1, 9)}", dtg=dtg, name=name,
        basin="WESTPAC" if target["lon"] > 100 else "CENTPAC",
        kts=kts, gust=int(kts * 1.25), cat=cat,
        bearing=rng.choice(["NW", "WNW", "W", "NNW"]),
        fwd_kt=rng.randint(8, 22),
        target_name=target["name"], target_id=target["id"],
        hours_to_cpa=rng.randint(18, 96),
        sw_m=round(rng.uniform(4.5, 11.0), 1),
        degraded_h=rng.randint(12, 72),
        flt_susp=rng.randint(8, 36),
        sortie_dtg=sortie_t.strftime("%d%H%M%b%y").upper(),
        fuel_kgal=rng.randint(800, 4000),
    )
    return body, t


def _swell_report(rng: random.Random, target: dict) -> tuple[str, datetime]:
    dtg, t = _dtg(rng)
    begin = t + timedelta(hours=rng.randint(6, 36))
    body = REPORT_TEMPLATES["noaa_swell"].format(
        dtg=dtg,
        region={"INDOPACOM": "Western Pacific", "CENTCOM": "Central Indian Ocean"}[target["ccdr"]],
        sw_m=round(rng.uniform(2.5, 5.5), 1),
        period=rng.randint(14, 22),
        dir=rng.choice(["NE", "ENE", "E", "SSE", "S"]),
        target_name=target["name"], target_id=target["id"],
        ramp_m=round(rng.uniform(1.2, 1.8), 1),
        conf=rng.choice(["HIGH", "MODERATE", "MODERATE"]),
        dur_h=rng.randint(12, 60),
        begin_dtg=begin.strftime("%d%H%M%b%y").upper(),
    )
    return body, t


def _climate_report(rng: random.Random, target: dict) -> tuple[str, datetime]:
    dtg, t = _dtg(rng)
    drivers = rng.sample(
        ["accelerating sea-level rise (+3.4 mm/yr local)", "increasing typhoon recurrence interval",
         "marine heatwave intensity", "compound storm-surge + king-tide alignment",
         "coral-reef breakwater degradation", "monsoon shift",
         "cyclone-driven swell propagation", "salt-water intrusion of fuel berms"], 2)
    posture = rng.choice([
        "Pre-positioned blue-roof tarps on order; fuel berm armoring 60% complete.",
        "USACE shoreline-armoring contract in source-selection.",
        "USMC G-4 has standing MOA with USCG Sector Guam for joint port reconstitution.",
        "Backup runway aggregate stockpiled at adjacent installation (sufficient for 5,000 ft repair).",
    ])
    body = REPORT_TEMPLATES["fema_climate"].format(
        section=f"{rng.randint(2, 7)}.{rng.randint(1, 4)}",
        dtg=t.strftime("%Y-%m-%d"),
        target_name=target["name"], target_id=target["id"],
        idx=round(rng.uniform(3.5, 8.5), 1),
        drivers="; ".join(drivers),
        hazard=rng.choice(["Cat-4 typhoon", "compound surge", "extended swell", "marine heatwave",
                           "drought-induced JP-8 supply constriction"]),
        mode=rng.choice(["sea", "air", "intermodal"]),
        restore_d=rng.randint(3, 21),
        posture=posture,
    )
    return body, t


def _geo_report(rng: random.Random, target: dict) -> tuple[str, datetime]:
    dtg, t = _dtg(rng)
    incidents = [
        ("PRC Coast Guard cutter shadowed inbound USNS at 12 nm; no escalation.", "Pilotage delays of 4–6h likely.",
         "Coordinate with USCG LO and request escort for next ROLON evolution."),
        ("Host-nation port labor 24h work-stoppage announced.", "Cargo ops suspended for the duration.",
         "Activate MSC stevedore augmentation contract."),
        ("Reported undersea cable anomaly 80 nm SW; cause TBD.", "Comms latency to {tid} elevated; SATCOM failover engaged.",
         "Coordinate with NSA-Hawaii and Subsea Cable WG for repair window."),
        ("Localized civil disturbance 4 km from main gate; force protection elevated to Bravo+.",
         "Port-of-debark throughput reduced ~30% for force-pro screening.",
         "Hold non-essential MILVAN movements; brief CCDR at next sync."),
        ("Fishing fleet AIS spoofing detected within 25 nm exclusion ring.",
         "Surface-traffic deconfliction load on harbor pilots elevated.",
         "Request USINDOPACOM J3 ISR overflight."),
    ]
    inc, eff, coa = rng.choice(incidents)
    body = REPORT_TEMPLATES["geo_incident"].format(
        dtg=dtg, target_name=target["name"], target_id=target["id"],
        incident=inc,
        effect=eff.replace("{tid}", target["id"]),
        conf=rng.choice(["HIGH", "MODERATE"]),
        coa=coa,
    )
    return body, t


def _equip_report(rng: random.Random, target: dict) -> tuple[str, datetime]:
    dtg, t = _dtg(rng)
    if target["kind"] == "port":
        system = rng.choice(["Pier 7 ship-to-shore crane #2", "Bulk fuel pipeline header valve A-3",
                             "RORO ramp hydraulics (north berth)", "Harbor pilot tug TUGAR-04"])
        workaround = rng.choice([
            "Reroute to adjacent berth; reduces cycle rate ~25%.",
            "Surge bulk fuel via tanker truck convoy until pipeline restored.",
            "Use floating mooring; impacts swell tolerance.",
        ])
    elif target["kind"] == "runway":
        system = rng.choice(["MOGAS truck #3 (DEF system)", "Runway 06L PAPI lights", "Hot-pit refuel rig #2",
                             "Crash-rescue R-11 pumper"])
        workaround = rng.choice([
            "Cross-deck fuel from MWSS adjacent ramp; throughput halved.",
            "Restrict night ops to runway 24R until lights restored.",
            "Use cold-pit refueling only; sortie cycle +15 min.",
        ])
    else:  # fuel_terminal
        system = rng.choice(["Bulk fuel berm liner B-2", "Fuel quality lab spectrometer",
                             "Berm transfer pump #4"])
        workaround = "Compensate via barge-delivered F-76 from nearest fuel-terminal node."

    body = REPORT_TEMPLATES["equipment_outage"].format(
        dtg=dtg,
        target_name=target["name"], target_id=target["id"],
        system=system,
        status=rng.choice(["RED — non-mission-capable", "AMBER — degraded", "AMBER — partial"]),
        restore_h=rng.randint(6, 96),
        tpd_loss=rng.randint(150, 1800),
        workaround=workaround,
    )
    return body, t


def generate_reports(n: int = 30, *, rng: random.Random | None = None) -> list[dict]:
    rng = rng or random.Random(1776)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    # weighted mix
    fns = (
        [_typhoon_report] * 8
        + [_swell_report] * 6
        + [_climate_report] * 6
        + [_geo_report] * 5
        + [_equip_report] * 5
    )
    rng.shuffle(fns)
    out = []
    for i, fn in enumerate(fns[:n], 1):
        target = rng.choice(NODES)
        body, t = fn(rng, target)
        kind = fn.__name__.lstrip("_").replace("_report", "")
        fname = f"{i:02d}_{kind}_{target['id']}.md"
        (REPORTS_DIR / fname).write_text(body)
        out.append({
            "file": fname, "kind": kind, "target": target["id"],
            "issued": t.isoformat(),
        })
    return out


def main() -> None:
    rng = random.Random(1776)
    (ROOT / "nodes.json").write_text(json.dumps(NODES, indent=2))
    (ROOT / "edges.json").write_text(json.dumps(EDGES, indent=2))
    # wipe stale reports
    if REPORTS_DIR.exists():
        for p in REPORTS_DIR.glob("*.md"):
            p.unlink()
    manifest = generate_reports(30, rng=rng)
    (ROOT / "reports_manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"Wrote {len(NODES)} nodes, {len(EDGES)} edges, {len(manifest)} reports.")
    print(f"  -> {ROOT}")


if __name__ == "__main__":
    main()
