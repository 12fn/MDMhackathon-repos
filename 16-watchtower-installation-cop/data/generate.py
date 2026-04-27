"""WATCHTOWER — synthetic data generator for the I-COP Aggregator demo.

Generates a single Marine Corps installation (MCB Camp Pendleton) and a
24-hour fused stream of seven operational data feeds patterned after the
real datasets that would plug in:

    - HIFLD (Datasets for Infrastructure Identification) — critical
      infrastructure assets (water tower, fuel depot, magazines, power
      substation, comms tower, gates).
    - NASA Earthdata — hourly weather (wind, precip, temp).
    - GCSS-MC Supply & Maintenance — maintenance status (a few critical
      assets in NMC state during the demo window).
    - Synthetic gate ingress/egress, utility readings, fire/EMS dispatches,
      mass-notification events (these would come from the installation's
      DPW / PMO / Mass Notification System).

Outputs (under data/):
    installations.json   1 base + named gates, utility nodes, fire/EMS units,
                         critical infrastructure (HIFLD-shape).
    weather.json         24h hourly weather (NASA Earthdata-shape).
    maintenance.json     GCSS-MC-shape maintenance status for ~12 critical assets.
    gate_events.json     ~120 ingress/egress events with planted spike anomaly.
    utility_events.json  ~96 utility readings (water/power) with planted dip.
    ems_events.json      ~24 fire/EMS dispatches incl. correlated incident.
    massnotify_events.json ~6 mass-notification events incl. the active incident.
    fused_timeline.json  All events merged + sorted by timestamp (canonical view).
    cached_briefs.json   Pre-computed hero outputs (cross-stream correlation +
                         Commander's I-COP Brief). Cache-first pattern.

Re-run any time with the SAME seed (1776) to reproduce.
"""
from __future__ import annotations

import json
import math
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

SEED = 1776
OUT = Path(__file__).parent

# Anchor "now" so the demo is reproducible.
T_NOW = datetime(2026, 4, 27, 18, 0, tzinfo=timezone.utc)
T_START = T_NOW - timedelta(hours=24)

# Center of the planted incident window (~hours T-3..T-1).
T_INCIDENT = T_NOW - timedelta(hours=2, minutes=30)

# ---------------------------------------------------------------------------
# Installation: MCB Camp Pendleton, with named gates / nodes / units / assets.
# ---------------------------------------------------------------------------
INSTALLATION = {
    "id": "pendleton",
    "name": "MCB Camp Pendleton",
    "state": "CA",
    "centroid": [33.3858, -117.5631],
    "polygon": [
        [33.55, -117.71],
        [33.55, -117.32],
        [33.21, -117.32],
        [33.21, -117.71],
    ],
    "personnel": 70000,
    "commander": "MajGen Marine, CG MCIWEST-MCB CamPen",
    "gates": [
        {"id": "GATE-MAIN", "name": "Main Gate (Vandegrift)", "lat": 33.2284, "lon": -117.3893,
         "expected_throughput_per_hr": [40, 220]},
        {"id": "GATE-SAN-LUIS-REY", "name": "San Luis Rey Gate", "lat": 33.2400, "lon": -117.4192,
         "expected_throughput_per_hr": [20, 140]},
        {"id": "GATE-LAS-PULGAS", "name": "Las Pulgas Gate", "lat": 33.3470, "lon": -117.5030,
         "expected_throughput_per_hr": [15, 90]},
        {"id": "GATE-DEL-MAR", "name": "Del Mar Gate", "lat": 33.2503, "lon": -117.4350,
         "expected_throughput_per_hr": [10, 70]},
        {"id": "GATE-CRISTIANITOS", "name": "Cristianitos Gate", "lat": 33.4622, "lon": -117.5917,
         "expected_throughput_per_hr": [5, 60]},
    ],
    "utility_nodes": [
        {"id": "WATER-TOWER-MAINSIDE", "kind": "water", "name": "Mainside Water Tower",
         "lat": 33.3850, "lon": -117.5640,
         "expected_psi": [62.0, 78.0], "capacity_gal": 1_500_000},
        {"id": "WATER-TOWER-SAN-MATEO", "kind": "water", "name": "San Mateo Water Tower",
         "lat": 33.4555, "lon": -117.6150,
         "expected_psi": [58.0, 74.0], "capacity_gal": 800_000},
        {"id": "POWER-SUBSTATION-22", "kind": "power", "name": "22-Area Substation",
         "lat": 33.3712, "lon": -117.5310,
         "expected_load_mw": [4.5, 9.2], "feeder": "SDG&E Tap 12kV"},
        {"id": "POWER-SUBSTATION-43", "kind": "power", "name": "43-Area Substation",
         "lat": 33.3010, "lon": -117.4480,
         "expected_load_mw": [2.0, 5.5], "feeder": "SDG&E Tap 12kV"},
        {"id": "FUEL-DEPOT-NFTI", "kind": "fuel", "name": "NFTI Fuel Depot",
         "lat": 33.2450, "lon": -117.4140,
         "expected_inventory_gal": [180_000, 240_000], "capacity_gal": 320_000},
    ],
    "ems_units": [
        {"id": "ENGINE-CO-1", "name": "Engine Company 1 (Mainside)", "lat": 33.3855, "lon": -117.5625,
         "type": "fire"},
        {"id": "ENGINE-CO-3", "name": "Engine Company 3 (San Mateo)", "lat": 33.4540, "lon": -117.6160,
         "type": "fire"},
        {"id": "MEDIC-2", "name": "Medic 2 (Naval Hospital)", "lat": 33.3720, "lon": -117.5410,
         "type": "ems"},
        {"id": "MEDIC-5", "name": "Medic 5 (43 Area)", "lat": 33.3015, "lon": -117.4490,
         "type": "ems"},
        {"id": "PMO-PATROL-7", "name": "PMO Patrol 7", "lat": 33.2600, "lon": -117.4250,
         "type": "police"},
    ],
    "critical_infrastructure": [
        # HIFLD-shape: kind, name, lat, lon, owner, fips_state, fips_county, status.
        {"id": "HIFLD-WT-001", "kind": "water_tower", "name": "Mainside Water Tower",
         "lat": 33.3850, "lon": -117.5640, "owner": "MCIWEST-DPW",
         "fips_state": "06", "fips_county": "073", "status": "operational"},
        {"id": "HIFLD-WT-002", "kind": "water_tower", "name": "San Mateo Water Tower",
         "lat": 33.4555, "lon": -117.6150, "owner": "MCIWEST-DPW",
         "fips_state": "06", "fips_county": "073", "status": "operational"},
        {"id": "HIFLD-FD-001", "kind": "fuel_depot", "name": "NFTI Fuel Depot",
         "lat": 33.2450, "lon": -117.4140, "owner": "DLA Energy",
         "fips_state": "06", "fips_county": "073", "status": "operational"},
        {"id": "HIFLD-MAG-001", "kind": "magazine", "name": "Las Pulgas Ammo Magazine 14",
         "lat": 33.3450, "lon": -117.5050, "owner": "MCIWEST-Ord",
         "fips_state": "06", "fips_county": "073", "status": "operational"},
        {"id": "HIFLD-MAG-002", "kind": "magazine", "name": "Camp Horno Magazine 7",
         "lat": 33.4100, "lon": -117.5550, "owner": "MCIWEST-Ord",
         "fips_state": "06", "fips_county": "073", "status": "operational"},
        {"id": "HIFLD-PS-001", "kind": "power_substation", "name": "22-Area Substation",
         "lat": 33.3712, "lon": -117.5310, "owner": "SDG&E / MCIWEST",
         "fips_state": "06", "fips_county": "073", "status": "operational"},
        {"id": "HIFLD-PS-002", "kind": "power_substation", "name": "43-Area Substation",
         "lat": 33.3010, "lon": -117.4480, "owner": "SDG&E / MCIWEST",
         "fips_state": "06", "fips_county": "073", "status": "operational"},
        {"id": "HIFLD-CT-001", "kind": "comms_tower", "name": "MCB Mainside Trunked Radio Tower",
         "lat": 33.3870, "lon": -117.5660, "owner": "MCEN-USMC G6",
         "fips_state": "06", "fips_county": "073", "status": "operational"},
        {"id": "HIFLD-HOSP-001", "kind": "hospital", "name": "Naval Hospital Camp Pendleton",
         "lat": 33.3720, "lon": -117.5410, "owner": "Navy BUMED",
         "fips_state": "06", "fips_county": "073", "status": "operational"},
    ],
}

# ---------------------------------------------------------------------------
# GCSS-MC maintenance — ~12 critical assets. Plant 3 in NMC state during the demo.
# ---------------------------------------------------------------------------
MAINTENANCE_ASSETS = [
    # (eic, nomenclature, serial, unit, location, status, defect, est_repair_hr)
    ("MTVR", "Truck, Cargo MTVR MK23", "MTVR-12491", "1st CEB", "Mainside Motor Pool", "FMC", None, 0),
    ("MTVR", "Truck, Cargo MTVR MK23", "MTVR-12502", "1st CEB", "Mainside Motor Pool", "FMC", None, 0),
    ("LVSR", "Logistics Vehicle System Replacement", "LVSR-08812", "CLB-1", "43-Area Motor Pool", "PMC",
     "Right rear hub bearing rumble — TM 11-2320 maint pending", 8),
    ("LVSR", "Logistics Vehicle System Replacement", "LVSR-08840", "CLB-1", "43-Area Motor Pool", "FMC", None, 0),
    ("HMMWV", "M1165A1 Up-Armored HMMWV", "HMMWV-44102", "1st Recon Bn", "Camp Horno Motor Pool", "NMC",
     "Engine fuel injector bank #2 failed — parts on backorder NSN 2910-01-573-9442", 36),
    ("HMMWV", "M1165A1 Up-Armored HMMWV", "HMMWV-44119", "1st Recon Bn", "Camp Horno Motor Pool", "FMC", None, 0),
    ("HMMWV", "M1165A1 Up-Armored HMMWV", "HMMWV-44123", "1st Recon Bn", "Camp Horno Motor Pool", "FMC", None, 0),
    ("AAV", "Amphibious Assault Vehicle AAV-7A1", "AAV-09921", "3rd AABn", "Del Mar Boat Basin", "NMC",
     "Hydraulic ramp actuator leak — induct depot Dec 2026", 240),
    ("M1A1", "M1A1 Tank, FEP", "M1A1-66103", "1st Tank Bn (cadre)", "Las Pulgas", "PMC",
     "Sponson box rust mitigation pending", 24),
    ("FIRETRUCK", "Pierce Fire Engine, Type-1", "ENG-CO1-PUMPER", "MCFD-Pendleton", "Mainside Fire Sta 1", "FMC", None, 0),
    ("AMBULANCE", "Type-3 Ambulance, MCFD", "AMB-MED2", "MCFD-Pendleton", "Naval Hospital", "FMC", None, 0),
    ("GENSET", "MEP-806B 60kW Tactical Quiet Generator", "GENSET-MCFD-AUX-3", "MCFD-Pendleton",
     "Mainside Fire Sta 1", "NMC",
     "Voltage regulator failure during last weekly load-bank — replacement on order", 12),
]


def _gcss_maintenance(rng: random.Random) -> list[dict]:
    out = []
    for eic, nomen, serial, unit, loc, status, defect, hrs in MAINTENANCE_ASSETS:
        last_pmcs = T_NOW - timedelta(hours=rng.randint(2, 168))
        out.append({
            "eic": eic,
            "nomenclature": nomen,
            "serial": serial,
            "unit": unit,
            "location": loc,
            "status": status,                       # FMC / PMC / NMC
            "defect_summary": defect,
            "est_repair_hours": hrs,
            "last_pmcs_iso": last_pmcs.isoformat(),
            "source_system": "GCSS-MC",
        })
    return out


# ---------------------------------------------------------------------------
# Weather — NASA Earthdata-shape hourly. Plant a wind shift around T_INCIDENT.
# ---------------------------------------------------------------------------
def _weather(rng: random.Random) -> list[dict]:
    out = []
    base_temp_c = 18.0
    for h in range(25):
        t = T_START + timedelta(hours=h)
        # Diurnal temp wave
        hr_local = (t.hour - 8) % 24  # PDT proxy (UTC-8)
        temp = base_temp_c + 6.0 * math.sin(math.pi * (hr_local - 6) / 12.0) \
               + rng.uniform(-1.0, 1.0)
        # Wind: routine 4-8 m/s southerly, then a Santa Ana spike near incident.
        delta_h = (t - T_INCIDENT).total_seconds() / 3600.0
        santa_ana = 14.0 * math.exp(-((delta_h) ** 2) / 2.0)  # gaussian peak at incident
        wind_speed = max(0.5, rng.uniform(3.5, 7.0) + santa_ana)
        # Direction shifts from S (180) to E (90) during Santa Ana.
        from_dir = 180 - min(90.0, santa_ana * 6.5)
        precip_mm = max(0.0, rng.gauss(0.0, 0.2))
        out.append({
            "valid_iso": t.isoformat(),
            "source": "NASA Earthdata (MERRA-2 shape)",
            "lat": INSTALLATION["centroid"][0],
            "lon": INSTALLATION["centroid"][1],
            "temp_c": round(temp, 2),
            "wind_speed_mps": round(wind_speed, 2),
            "wind_from_dir_deg": round(from_dir, 1),
            "precip_mm_hr": round(precip_mm, 3),
            "rh_pct": round(max(8.0, 50.0 - santa_ana * 2.5 + rng.uniform(-3, 3)), 1),
        })
    return out


# ---------------------------------------------------------------------------
# Gate ingress/egress events. Plant a spike of POV ingress at GATE-LAS-PULGAS
# in the 30-min window centered at T_INCIDENT.
# ---------------------------------------------------------------------------
def _gate_events(rng: random.Random) -> list[dict]:
    out = []
    eid = 0
    for hr in range(24):
        t_hr = T_START + timedelta(hours=hr)
        for gate in INSTALLATION["gates"]:
            lo, hi = gate["expected_throughput_per_hr"]
            # Diurnal: morning rush 0600-0800 PDT (~T+13..15), evening 1530-1730 PDT
            local_hr = (t_hr.hour - 8) % 24
            rush = 1.0
            if 6 <= local_hr <= 8:
                rush = 1.7
            elif 15 <= local_hr <= 17:
                rush = 1.5
            elif 22 <= local_hr or local_hr <= 4:
                rush = 0.35
            base = int(rng.uniform(lo, hi) * rush)

            # PLANTED: gate spike at LAS-PULGAS during incident window
            spike = 0
            if gate["id"] == "GATE-LAS-PULGAS":
                delta_h = (t_hr + timedelta(minutes=30) - T_INCIDENT).total_seconds() / 3600.0
                if -0.6 < delta_h < 0.6:
                    spike = int(110 * math.exp(-(delta_h ** 2) / 0.05))

            n_in = base + spike
            n_out = max(2, int(base * rng.uniform(0.7, 1.1)))
            out.append({
                "id": f"GATE-{eid:05d}",
                "stream": "gate",
                "gate_id": gate["id"],
                "gate_name": gate["name"],
                "lat": gate["lat"],
                "lon": gate["lon"],
                "ts_iso": t_hr.isoformat(),
                "ingress_count": n_in,
                "egress_count": n_out,
                "is_anomaly": bool(spike > 30),
                "anomaly_note": (
                    "POV ingress spike — possible incident-driven family arrival surge."
                    if spike > 30 else None
                ),
            })
            eid += 1
    return out


# ---------------------------------------------------------------------------
# Utility readings. Plant a water-pressure dip at WATER-TOWER-MAINSIDE
# centered at T_INCIDENT, plus a power load surge at PS-22.
# ---------------------------------------------------------------------------
def _utility_events(rng: random.Random) -> list[dict]:
    out = []
    eid = 0
    # 15-min readings for 24h (96 per node; 5 nodes = 480, trim to ~96 by hr+node).
    # Use hourly per node to keep dataset compact (~120 records).
    for hr in range(24):
        t_hr = T_START + timedelta(hours=hr)
        delta_h = (t_hr - T_INCIDENT).total_seconds() / 3600.0
        for node in INSTALLATION["utility_nodes"]:
            rec = {
                "id": f"UTIL-{eid:05d}",
                "stream": "utility",
                "node_id": node["id"],
                "node_kind": node["kind"],
                "node_name": node["name"],
                "lat": node["lat"],
                "lon": node["lon"],
                "ts_iso": t_hr.isoformat(),
                "is_anomaly": False,
                "anomaly_note": None,
            }
            if node["kind"] == "water":
                lo, hi = node["expected_psi"]
                psi = rng.uniform(lo, hi)
                if node["id"] == "WATER-TOWER-MAINSIDE" and -1.2 < delta_h < 1.2:
                    dip = 22.0 * math.exp(-(delta_h ** 2) / 0.6)
                    psi -= dip
                    if dip > 6.0:
                        rec["is_anomaly"] = True
                        rec["anomaly_note"] = (
                            "Water pressure dip — possible main break or hydrant draw."
                        )
                rec["pressure_psi"] = round(psi, 2)
                rec["flow_gpm"] = round(rng.uniform(800, 1400), 1)
            elif node["kind"] == "power":
                lo, hi = node["expected_load_mw"]
                load = rng.uniform(lo, hi)
                if node["id"] == "POWER-SUBSTATION-22" and -1.0 < delta_h < 1.0:
                    surge = 2.6 * math.exp(-(delta_h ** 2) / 0.5)
                    load += surge
                    if surge > 1.0:
                        rec["is_anomaly"] = True
                        rec["anomaly_note"] = (
                            "Power load surge — emergency systems engaged."
                        )
                rec["load_mw"] = round(load, 3)
                rec["voltage_kv"] = round(rng.uniform(11.7, 12.3), 2)
            elif node["kind"] == "fuel":
                lo, hi = node["expected_inventory_gal"]
                inv = rng.uniform(lo, hi)
                rec["inventory_gal"] = int(inv)
                rec["temp_f"] = round(rng.uniform(58, 72), 1)
            out.append(rec)
            eid += 1
    return out


# ---------------------------------------------------------------------------
# Fire/EMS dispatches — routine traffic + planted incident.
# ---------------------------------------------------------------------------
ROUTINE_DISPATCHES = [
    ("ems", "Chest pain", "Mainside Family Housing"),
    ("ems", "Sports injury — ankle fx", "Camp Horno PT field"),
    ("fire", "Brush fire — small, suppressed by Engine Co 3", "San Mateo training area"),
    ("ems", "Diabetic emergency", "23-Area Barracks"),
    ("ems", "Slip-fall", "BX Parking lot"),
    ("fire", "Cooking fire — false alarm", "Bachelor Officer Quarters"),
    ("police", "Traffic stop — admin", "Vandegrift / Stuart Mesa"),
    ("ems", "Migraine", "1st Recon S-1 office"),
    ("fire", "Smoke alarm — burnt toast", "Family Housing San Onofre"),
    ("police", "Suspicious vehicle", "Las Pulgas Range Rd"),
    ("ems", "Heat exhaustion", "Range 116"),
    ("fire", "Vehicle fire (POV) — extinguished", "I-5 NB Onramp"),
    ("ems", "Lift-assist", "Naval Hospital Pendleton"),
    ("police", "Domestic — verbal", "Family Housing Wire Mountain"),
    ("ems", "Allergic reaction", "Camp Horno chow hall"),
    ("fire", "Range fire — suppressed", "Range 410"),
    ("ems", "Pediatric fever", "Family Housing Stuart Mesa"),
    ("police", "Lost child reunited", "Mainside BX"),
]


def _ems_events(rng: random.Random) -> list[dict]:
    out = []
    eid = 0
    # Routine traffic — scattered through the 24h window.
    for d_type, narrative, location in ROUTINE_DISPATCHES:
        t = T_START + timedelta(hours=rng.uniform(0.5, 23.0))
        unit = next(u for u in INSTALLATION["ems_units"]
                    if u["type"] == d_type or (d_type == "police" and u["type"] == "police"))
        out.append({
            "id": f"EMS-{eid:05d}",
            "stream": "ems",
            "type": d_type,
            "ts_iso": t.isoformat(),
            "unit_id": unit["id"],
            "unit_name": unit["name"],
            "lat": unit["lat"] + rng.uniform(-0.01, 0.01),
            "lon": unit["lon"] + rng.uniform(-0.01, 0.01),
            "narrative": narrative,
            "location": location,
            "priority": rng.choice(["P3", "P3", "P2"]),
            "is_anomaly": False,
            "anomaly_note": None,
        })
        eid += 1
    # PLANTED incident: structure fire near Las Pulgas magazines, multi-unit.
    incident_units = [
        ("ENGINE-CO-1", "Engine Company 1 (Mainside)", "fire", "P1"),
        ("ENGINE-CO-3", "Engine Company 3 (San Mateo)", "fire", "P1"),
        ("MEDIC-2", "Medic 2 (Naval Hospital)", "ems", "P1"),
        ("PMO-PATROL-7", "PMO Patrol 7", "police", "P1"),
    ]
    for i, (uid, uname, utype, pri) in enumerate(incident_units):
        t = T_INCIDENT + timedelta(minutes=2 + i * 3)
        out.append({
            "id": f"EMS-{eid:05d}",
            "stream": "ems",
            "type": utype,
            "ts_iso": t.isoformat(),
            "unit_id": uid,
            "unit_name": uname,
            "lat": 33.3460 + rng.uniform(-0.005, 0.005),
            "lon": -117.5040 + rng.uniform(-0.005, 0.005),
            "narrative": (
                "STRUCTURE FIRE — Magazine 14 perimeter, smoke visible from adjacent "
                "magazine. All response. Mutual aid CDF requested."
            ),
            "location": "Las Pulgas Magazine 14 perimeter",
            "priority": pri,
            "is_anomaly": True,
            "anomaly_note": "Critical incident response — structure fire near magazine.",
        })
        eid += 1
    out.sort(key=lambda r: r["ts_iso"])
    return out


# ---------------------------------------------------------------------------
# Mass-notification events.
# ---------------------------------------------------------------------------
def _massnotify_events(rng: random.Random) -> list[dict]:
    routine = [
        (T_START + timedelta(hours=2),
         "TEST", "Daily AtHoc test broadcast — no action required."),
        (T_START + timedelta(hours=8),
         "ADVISORY", "Family housing area water-system flushing 0900-1100; brief discoloration possible."),
        (T_START + timedelta(hours=14),
         "ADVISORY", "Las Pulgas range complex live-fire 1300-1700; expect blast noise on Basilone Rd."),
        (T_START + timedelta(hours=20),
         "INFO", "Commissary closes at 2000 today; reopens 0900 tomorrow."),
    ]
    incident = [
        (T_INCIDENT + timedelta(minutes=6),
         "EMERGENCY",
         "ATTENTION ALL HANDS: Active incident vicinity Las Pulgas Magazine 14. "
         "All non-essential personnel shelter in place. Avoid Basilone Rd north of "
         "Stuart Mesa. EOC activated."),
        (T_INCIDENT + timedelta(minutes=22),
         "UPDATE",
         "Las Pulgas incident: structure fire contained to magazine perimeter. "
         "No munitions detonation. Family housing in San Onofre placed on "
         "voluntary evacuation. Continue to avoid Basilone Rd."),
    ]
    out = []
    for i, (t, sev, msg) in enumerate(routine + incident):
        out.append({
            "id": f"MASS-{i:04d}",
            "stream": "massnotify",
            "ts_iso": t.isoformat(),
            "severity": sev,
            "message": msg,
            "system": "AtHoc / Giant Voice",
            "is_anomaly": sev in ("EMERGENCY", "UPDATE"),
            "anomaly_note": (
                "Active emergency mass-notification" if sev == "EMERGENCY" else None
            ),
        })
    out.sort(key=lambda r: r["ts_iso"])
    return out


# ---------------------------------------------------------------------------
# Fused timeline — every event normalized to {stream, ts_iso, label, severity?}
# ---------------------------------------------------------------------------
def _fuse(gates, utils, ems, massnotify, weather, maint) -> list[dict]:
    fused = []
    for g in gates:
        fused.append({
            "stream": "gate", "ts_iso": g["ts_iso"], "id": g["id"],
            "label": f"{g['gate_name']} ingress {g['ingress_count']} / egress {g['egress_count']}",
            "is_anomaly": g["is_anomaly"], "anomaly_note": g["anomaly_note"],
            "lat": g["lat"], "lon": g["lon"],
        })
    for u in utils:
        if u["node_kind"] == "water":
            lab = f"{u['node_name']} {u.get('pressure_psi','?')} psi @ {u.get('flow_gpm','?')} gpm"
        elif u["node_kind"] == "power":
            lab = f"{u['node_name']} {u.get('load_mw','?')} MW @ {u.get('voltage_kv','?')} kV"
        else:
            lab = f"{u['node_name']} inv {u.get('inventory_gal','?')} gal"
        fused.append({
            "stream": "utility", "ts_iso": u["ts_iso"], "id": u["id"], "label": lab,
            "is_anomaly": u["is_anomaly"], "anomaly_note": u["anomaly_note"],
            "lat": u["lat"], "lon": u["lon"],
        })
    for e in ems:
        fused.append({
            "stream": "ems", "ts_iso": e["ts_iso"], "id": e["id"],
            "label": f"{e['unit_name']} :: {e['priority']} :: {e['narrative'][:90]}",
            "is_anomaly": e["is_anomaly"], "anomaly_note": e["anomaly_note"],
            "lat": e["lat"], "lon": e["lon"],
        })
    for m in massnotify:
        fused.append({
            "stream": "massnotify", "ts_iso": m["ts_iso"], "id": m["id"],
            "label": f"[{m['severity']}] {m['message'][:90]}",
            "is_anomaly": m["is_anomaly"], "anomaly_note": m["anomaly_note"],
            "lat": INSTALLATION["centroid"][0], "lon": INSTALLATION["centroid"][1],
        })
    for w in weather:
        fused.append({
            "stream": "weather", "ts_iso": w["valid_iso"], "id": f"WX-{w['valid_iso']}",
            "label": (
                f"Wind {w['wind_speed_mps']} m/s from {w['wind_from_dir_deg']} deg, "
                f"{w['temp_c']} C, RH {w['rh_pct']}%, precip {w['precip_mm_hr']} mm/h"
            ),
            "is_anomaly": w["wind_speed_mps"] > 13.0,
            "anomaly_note": ("High wind / Santa Ana flow" if w["wind_speed_mps"] > 13.0 else None),
            "lat": w["lat"], "lon": w["lon"],
        })
    # Maintenance is point-in-time, not a stream of events; append one summary record.
    nmc = [m for m in maint if m["status"] == "NMC"]
    pmc = [m for m in maint if m["status"] == "PMC"]
    fused.append({
        "stream": "maintenance", "ts_iso": T_NOW.isoformat(), "id": "GCSS-MC-SNAPSHOT",
        "label": (
            f"GCSS-MC snapshot: {len(nmc)} NMC / {len(pmc)} PMC of {len(maint)} critical assets"
        ),
        "is_anomaly": len(nmc) >= 2,
        "anomaly_note": (
            "Multiple critical assets NMC during incident window."
            if len(nmc) >= 2 else None
        ),
        "lat": INSTALLATION["centroid"][0], "lon": INSTALLATION["centroid"][1],
    })

    fused.sort(key=lambda r: r["ts_iso"])
    return fused


# ---------------------------------------------------------------------------
# Pre-compute hero LLM outputs (cache-first pattern).
# ---------------------------------------------------------------------------
def _baseline_correlation(fused: list[dict]) -> dict:
    """Deterministic fallback correlator. Used both as a backup and to seed
    the cached_briefs.json so the demo never sits idle."""
    anomalies = [f for f in fused if f.get("is_anomaly")]
    streams = sorted(set(a["stream"] for a in anomalies))
    by_stream = {s: [a["label"] for a in anomalies if a["stream"] == s][:3] for s in streams}
    return {
        "anomalies": [
            {
                "anomaly_id": "COP-001",
                "severity": "HIGH",
                "contributing_streams": ["ems", "massnotify", "utility", "gate"],
                "hypothesis": (
                    "Cross-stream correlation indicates an active structure-fire incident "
                    "vicinity Las Pulgas Magazine 14: P1 multi-unit dispatch (Engine 1, Engine 3, "
                    "Medic 2, PMO 7) coincides with a 22 psi water-pressure dip at the Mainside "
                    "Water Tower (consistent with hydrant draw), a load surge at 22-Area "
                    "Substation (emergency systems engaged), an EMERGENCY AtHoc broadcast, and "
                    "an unusual POV ingress spike at Las Pulgas Gate (family-driven response "
                    "to the AtHoc message)."
                ),
                "recommended_action": (
                    "Activate Installation EOC at COG; pre-position MEDIC-5 to 43-Area as "
                    "backfill; verify Magazine 14 cooling-spray loop pressure; issue "
                    "shelter-in-place reaffirmation through AtHoc; coordinate with CDF "
                    "for structural collapse contingency."
                ),
            },
            {
                "anomaly_id": "COP-002",
                "severity": "MEDIUM",
                "contributing_streams": ["weather", "ems"],
                "hypothesis": (
                    "Santa Ana wind shift to ~14 m/s easterly is concurrent with the magazine "
                    "structure fire — wind alignment is pushing smoke and embers toward "
                    "San Onofre family housing."
                ),
                "recommended_action": (
                    "Pre-stage Engine Co 1 reserves at San Onofre; coordinate with PWD for "
                    "downwind air-quality monitoring; place housing on voluntary evacuation."
                ),
            },
            {
                "anomaly_id": "COP-003",
                "severity": "MEDIUM",
                "contributing_streams": ["maintenance"],
                "hypothesis": (
                    "Three critical assets are NMC during the incident window: HMMWV-44102 "
                    "(1st Recon), AAV-09921 (3rd AABn), and GENSET-MCFD-AUX-3 (MCFD aux power). "
                    "The MCFD genset NMC reduces backup power resilience for Mainside Fire Sta 1 "
                    "exactly when an incident is consuming primary capacity."
                ),
                "recommended_action": (
                    "Direct CLB-1 to expedite voltage-regulator swap on GENSET-MCFD-AUX-3; "
                    "stage HMMWV-44119 / 44123 as Recon backfill; confirm AAV-09921 depot "
                    "induct date does not slip into the next exercise window."
                ),
            },
        ],
        "_source": "deterministic_baseline",
    }


def _baseline_brief(fused: list[dict], correlation: dict) -> str:
    """Deterministic Commander's I-COP Brief used to seed the cache and as
    a watchdog fallback if the hero call times out."""
    anomalies = correlation.get("anomalies", [])
    bullets = "\n".join(
        f"  - [{a['severity']}] {a['anomaly_id']}: {a['hypothesis']}" for a in anomalies[:3]
    )
    actions = "\n".join(
        f"  - {a['recommended_action']}" for a in anomalies[:3]
    )
    return (
        f"COMMANDER'S I-COP BRIEF — {INSTALLATION['name']}\n"
        f"AS OF: {T_NOW.isoformat()}\n\n"
        f"BLUF: Active structure-fire incident at Las Pulgas Magazine 14 with cross-stream "
        f"corroboration across EMS, mass-notification, utility, and gate streams. EOC activation "
        f"recommended. Three critical assets NMC during the incident window degrades resilience.\n\n"
        f"TOP 3 CROSS-STREAM ANOMALIES:\n{bullets}\n\n"
        f"PREDICTIVE RISK — NEXT 12H:\n"
        f"  - Santa Ana wind shift (~14 m/s easterly) sustains 6-8h; ember risk to San Onofre "
        f"family housing is the dominant hazard until winds abate ~T+8h.\n"
        f"  - Mainside water pressure expected to recover to baseline (62-78 psi) within 90 min "
        f"of incident-fire suppression.\n"
        f"  - Gate ingress at Las Pulgas should normalize within 60 min of AtHoc UPDATE; if it "
        f"does not, escalate to PMO traffic-control plan.\n\n"
        f"RECOMMENDED PRE-POSITIONING:\n{actions}\n\n"
        f"//SIGNED// I-COP Aggregator (WATCHTOWER) — Powered by Kamiwaza"
    )


def _precompute_briefs(fused: list[dict]) -> dict:
    """Pre-compute the hero outputs at synth time. Cache-first pattern:
    the app reads from this on startup; the live call only fires when the
    user clicks Regenerate.

    We try the live LLM (with a strict timeout) and ALWAYS fall back to the
    deterministic baseline so the cache is guaranteed to be populated.
    """
    correlation = _baseline_correlation(fused)
    brief = _baseline_brief(fused, correlation)

    # Try a live LLM precompute, time-bounded. Never let it block synth.
    live_correlation = None
    live_brief = None
    try:
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout
        from shared.kamiwaza_client import chat, chat_json  # noqa: WPS433

        def _live_correlator():
            anomaly_window = [f for f in fused if f.get("is_anomaly")]
            sys = (
                "You are a USMC LOGCOM Installation Common Operating Picture (I-COP) "
                "cross-stream correlator. You consume fused multi-source events from gate "
                "access, utility readings, fire/EMS dispatches, mass-notification, weather, "
                "and GCSS-MC maintenance. You output strict JSON identifying anomalies that "
                "are corroborated ACROSS MULTIPLE STREAMS in the same time window."
            )
            usr = (
                f"Installation: {INSTALLATION['name']}\n"
                f"As of: {T_NOW.isoformat()}\n\n"
                f"Anomalous fused events (last 24h):\n"
                f"{json.dumps(anomaly_window, indent=2)}\n\n"
                "Return JSON: {\"anomalies\": [{\"anomaly_id\": str, "
                "\"severity\": \"LOW|MEDIUM|HIGH\", \"contributing_streams\": [str], "
                "\"hypothesis\": str, \"recommended_action\": str}]} -- 2 to 4 anomalies."
            )
            return chat_json(
                [{"role": "system", "content": sys},
                 {"role": "user", "content": usr}],
                schema_hint="anomalies[] with anomaly_id, severity, contributing_streams, hypothesis, recommended_action",
                temperature=0.25,
                max_tokens=900,
            )

        def _live_brief(corr):
            sys_msg = (
                "You are the senior watch officer's AI battle-buddy in the MCB Camp Pendleton "
                "Installation EOC. Draft a Commander's I-COP Brief in plain text. Use Marine "
                "register: BLUF, then top 3 cross-stream anomalies, then predictive risk for "
                "the next 12 hours, then recommended pre-positioning actions. End with "
                "'//SIGNED// I-COP Aggregator (WATCHTOWER)'. Do not exceed 320 words."
            )
            usr = (
                f"INSTALLATION: {INSTALLATION['name']}\n"
                f"AS OF: {T_NOW.isoformat()}\n\n"
                f"CORRELATION JSON:\n{json.dumps(corr, indent=2)}\n\n"
                "Draft the Commander's I-COP Brief now."
            )
            messages = [
                {"role": "system", "content": sys_msg},
                {"role": "user", "content": usr},
            ]
            # Hero model uses max_completion_tokens; fall back to mini chain on error.
            try:
                from shared.kamiwaza_client import get_client  # noqa: WPS433
                client = get_client()
                resp = client.chat.completions.create(
                    model="gpt-5.4",
                    messages=messages,
                    max_completion_tokens=900,
                )
                return resp.choices[0].message.content or ""
            except Exception:
                return chat(messages, temperature=0.35, max_tokens=900)

        with ThreadPoolExecutor(max_workers=1) as ex:
            try:
                live_correlation = ex.submit(_live_correlator).result(timeout=25)
            except Exception:
                live_correlation = None
        if live_correlation and "anomalies" in live_correlation:
            with ThreadPoolExecutor(max_workers=1) as ex:
                try:
                    live_brief = ex.submit(lambda: _live_brief(live_correlation)).result(timeout=35)
                except Exception:
                    live_brief = None
    except Exception:
        live_correlation = None
        live_brief = None

    out = {
        "as_of_iso": T_NOW.isoformat(),
        "installation": {
            "id": INSTALLATION["id"],
            "name": INSTALLATION["name"],
            "centroid": INSTALLATION["centroid"],
        },
        "baseline_correlation": correlation,
        "baseline_brief": brief,
        "live_correlation": live_correlation,
        "live_brief": live_brief,
    }
    return out


# ---------------------------------------------------------------------------
def main() -> None:
    rng = random.Random(SEED)

    weather = _weather(rng)
    maint = _gcss_maintenance(rng)
    gates = _gate_events(rng)
    utils = _utility_events(rng)
    ems = _ems_events(rng)
    mn = _massnotify_events(rng)
    fused = _fuse(gates, utils, ems, mn, weather, maint)

    (OUT / "installations.json").write_text(json.dumps([INSTALLATION], indent=2))
    (OUT / "weather.json").write_text(json.dumps(weather, indent=2))
    (OUT / "maintenance.json").write_text(json.dumps(maint, indent=2))
    (OUT / "gate_events.json").write_text(json.dumps(gates, indent=2))
    (OUT / "utility_events.json").write_text(json.dumps(utils, indent=2))
    (OUT / "ems_events.json").write_text(json.dumps(ems, indent=2))
    (OUT / "massnotify_events.json").write_text(json.dumps(mn, indent=2))
    (OUT / "fused_timeline.json").write_text(json.dumps(fused, indent=2))

    # Cache-first hero outputs (always populated, even if LLM is offline).
    do_llm = os.getenv("WATCHTOWER_PRECOMPUTE_LIVE", "1") != "0"
    if do_llm:
        cached = _precompute_briefs(fused)
    else:
        corr = _baseline_correlation(fused)
        cached = {
            "as_of_iso": T_NOW.isoformat(),
            "installation": {
                "id": INSTALLATION["id"],
                "name": INSTALLATION["name"],
                "centroid": INSTALLATION["centroid"],
            },
            "baseline_correlation": corr,
            "baseline_brief": _baseline_brief(fused, corr),
            "live_correlation": None,
            "live_brief": None,
        }
    (OUT / "cached_briefs.json").write_text(json.dumps(cached, indent=2))

    # Summary
    print("WATCHTOWER synthetic data:")
    print(f"  installations.json       1 base  ({INSTALLATION['name']})")
    print(f"  weather.json             {len(weather)} hourly readings (NASA Earthdata-shape)")
    print(f"  maintenance.json         {len(maint)} GCSS-MC asset records")
    print(f"  gate_events.json         {len(gates)} ingress/egress records")
    print(f"  utility_events.json      {len(utils)} utility readings")
    print(f"  ems_events.json          {len(ems)} fire/EMS dispatches")
    print(f"  massnotify_events.json   {len(mn)} mass-notification events")
    print(f"  fused_timeline.json      {len(fused)} fused records (sorted)")
    print(f"  cached_briefs.json       baseline + (live if reachable) hero outputs")
    print(f"\nIncident anchored at: {T_INCIDENT.isoformat()}")
    n_anom = sum(1 for f in fused if f.get("is_anomaly"))
    print(f"Total flagged anomalies in fused timeline: {n_anom}")


if __name__ == "__main__":
    main()
