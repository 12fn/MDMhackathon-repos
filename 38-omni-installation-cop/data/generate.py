"""OMNI — synthetic data generator for the cross-domain I-COP / ERMP / Browser-AI-Gov demo.

Generates ONE Marine Corps installation (MCB Camp Pendleton) and 24 hours of
SIX fused operational streams for ~600 events, plus the supporting layers
(HIFLD critical infra, NASA Earthdata weather, NASA FIRMS thermal, GCSS-MC
maintenance, IEEE WiFi/BT RF prints, Drone RF detections), plus 5 named
personas with role/permission JSON trees (CO / G-1 / G-2 / G-3 / G-4 / S-6).

Re-run any time with the SAME seed (1776) to reproduce.

Outputs (under data/):
    installations.json         1 base + named gates / utility nodes / EMS / comms
    weather.json               24h hourly NASA Earthdata-shape readings
    firms.json                 NASA FIRMS thermal pings (planted ones near magazine)
    maintenance.json           GCSS-MC-shape maintenance status (~12 critical assets)
    gate_events.json           ingress/egress events with planted spike
    utility_events.json        utility readings with planted dip / surge
    ems_events.json            fire/EMS dispatches w/ planted multi-unit incident
    massnotify_events.json     mass-notification events (AtHoc/Giant Voice)
    rf_events.json             IEEE WiFi/BT RF spike events (synth)
    drone_rf_events.json       Drone-RF detection events (synth)
    fused_timeline.json        all events merged + sorted by timestamp
    personas.json              5 personas + role/permission trees (ABAC)
    cached_briefs.json         pre-computed hero outputs (correlator + brief)
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
# Installation
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
         "lat": 33.3850, "lon": -117.5640, "expected_psi": [62.0, 78.0]},
        {"id": "WATER-TOWER-SAN-MATEO", "kind": "water", "name": "San Mateo Water Tower",
         "lat": 33.4555, "lon": -117.6150, "expected_psi": [58.0, 74.0]},
        {"id": "POWER-SUBSTATION-22", "kind": "power", "name": "22-Area Substation",
         "lat": 33.3712, "lon": -117.5310, "expected_load_mw": [4.5, 9.2]},
        {"id": "POWER-SUBSTATION-43", "kind": "power", "name": "43-Area Substation",
         "lat": 33.3010, "lon": -117.4480, "expected_load_mw": [2.0, 5.5]},
        {"id": "FUEL-DEPOT-NFTI", "kind": "fuel", "name": "NFTI Fuel Depot",
         "lat": 33.2450, "lon": -117.4140, "expected_inventory_gal": [180_000, 240_000]},
    ],
    "ems_units": [
        {"id": "ENGINE-CO-1", "name": "Engine Company 1 (Mainside)", "lat": 33.3855, "lon": -117.5625, "type": "fire"},
        {"id": "ENGINE-CO-3", "name": "Engine Company 3 (San Mateo)", "lat": 33.4540, "lon": -117.6160, "type": "fire"},
        {"id": "MEDIC-2", "name": "Medic 2 (Naval Hospital)", "lat": 33.3720, "lon": -117.5410, "type": "ems"},
        {"id": "MEDIC-5", "name": "Medic 5 (43 Area)", "lat": 33.3015, "lon": -117.4490, "type": "ems"},
        {"id": "PMO-PATROL-7", "name": "PMO Patrol 7", "lat": 33.2600, "lon": -117.4250, "type": "police"},
    ],
    "comm_nodes": [
        {"id": "COMM-MAINSIDE-TRR", "name": "Mainside Trunked Radio Tower",
         "lat": 33.3870, "lon": -117.5660, "kind": "trunked_radio"},
        {"id": "COMM-LASPULGAS-RPTR", "name": "Las Pulgas Repeater",
         "lat": 33.3475, "lon": -117.5025, "kind": "uhf_repeater"},
        {"id": "COMM-SANMATEO-WIFI", "name": "San Mateo Tactical WiFi",
         "lat": 33.4548, "lon": -117.6155, "kind": "wifi_5g"},
    ],
    "critical_infrastructure": [
        # HIFLD-shape: kind, name, lat, lon, owner, status.
        {"id": "HIFLD-WT-001", "kind": "water_tower", "name": "Mainside Water Tower",
         "lat": 33.3850, "lon": -117.5640, "owner": "MCIWEST-DPW", "status": "operational"},
        {"id": "HIFLD-WT-002", "kind": "water_tower", "name": "San Mateo Water Tower",
         "lat": 33.4555, "lon": -117.6150, "owner": "MCIWEST-DPW", "status": "operational"},
        {"id": "HIFLD-FD-001", "kind": "fuel_depot", "name": "NFTI Fuel Depot",
         "lat": 33.2450, "lon": -117.4140, "owner": "DLA Energy", "status": "operational"},
        {"id": "HIFLD-MAG-001", "kind": "magazine", "name": "Las Pulgas Ammo Magazine 14",
         "lat": 33.3450, "lon": -117.5050, "owner": "MCIWEST-Ord", "status": "operational"},
        {"id": "HIFLD-MAG-002", "kind": "magazine", "name": "Camp Horno Magazine 7",
         "lat": 33.4100, "lon": -117.5550, "owner": "MCIWEST-Ord", "status": "operational"},
        {"id": "HIFLD-PS-001", "kind": "power_substation", "name": "22-Area Substation",
         "lat": 33.3712, "lon": -117.5310, "owner": "SDG&E / MCIWEST", "status": "operational"},
        {"id": "HIFLD-PS-002", "kind": "power_substation", "name": "43-Area Substation",
         "lat": 33.3010, "lon": -117.4480, "owner": "SDG&E / MCIWEST", "status": "operational"},
        {"id": "HIFLD-CT-001", "kind": "comms_tower", "name": "Mainside Trunked Radio Tower",
         "lat": 33.3870, "lon": -117.5660, "owner": "MCEN-USMC G6", "status": "operational"},
        {"id": "HIFLD-HOSP-001", "kind": "hospital", "name": "Naval Hospital Camp Pendleton",
         "lat": 33.3720, "lon": -117.5410, "owner": "Navy BUMED", "status": "operational"},
    ],
}


# ---------------------------------------------------------------------------
# GCSS-MC maintenance — ~12 critical assets, with planted NMC entries.
# ---------------------------------------------------------------------------
MAINTENANCE_ASSETS = [
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
            "status": status,
            "defect_summary": defect,
            "est_repair_hours": hrs,
            "last_pmcs_iso": last_pmcs.isoformat(),
            "source_system": "GCSS-MC",
        })
    return out


# ---------------------------------------------------------------------------
# Weather (NASA Earthdata-shape).
# ---------------------------------------------------------------------------
def _weather(rng: random.Random) -> list[dict]:
    out = []
    base_temp_c = 18.0
    for h in range(25):
        t = T_START + timedelta(hours=h)
        hr_local = (t.hour - 8) % 24
        temp = base_temp_c + 6.0 * math.sin(math.pi * (hr_local - 6) / 12.0) + rng.uniform(-1.0, 1.0)
        delta_h = (t - T_INCIDENT).total_seconds() / 3600.0
        santa_ana = 14.0 * math.exp(-((delta_h) ** 2) / 2.0)
        wind_speed = max(0.5, rng.uniform(3.5, 7.0) + santa_ana)
        from_dir = 180 - min(90.0, santa_ana * 6.5)
        precip_mm = max(0.0, rng.gauss(0.0, 0.2))
        out.append({
            "id": f"WX-{h:03d}",
            "stream": "weather",
            "ts_iso": t.isoformat(),
            "valid_iso": t.isoformat(),
            "source": "NASA Earthdata (MERRA-2 shape)",
            "lat": INSTALLATION["centroid"][0],
            "lon": INSTALLATION["centroid"][1],
            "temp_c": round(temp, 2),
            "wind_speed_mps": round(wind_speed, 2),
            "wind_from_dir_deg": round(from_dir, 1),
            "precip_mm_hr": round(precip_mm, 3),
            "rh_pct": round(max(8.0, 50.0 - santa_ana * 2.5 + rng.uniform(-3, 3)), 1),
            "is_anomaly": wind_speed > 13.0,
            "anomaly_note": ("Santa Ana high wind / low RH" if wind_speed > 13.0 else None),
        })
    return out


# ---------------------------------------------------------------------------
# NASA FIRMS — synthetic thermal pings, with planted ones near magazine.
# ---------------------------------------------------------------------------
def _firms(rng: random.Random) -> list[dict]:
    out = []
    eid = 0
    # Background thermal noise
    for h in range(0, 24, 4):
        t = T_START + timedelta(hours=h)
        out.append({
            "id": f"FIRMS-{eid:04d}",
            "stream": "firms",
            "ts_iso": t.isoformat(),
            "satellite": "VIIRS-SNPP",
            "lat": INSTALLATION["centroid"][0] + rng.uniform(-0.05, 0.05),
            "lon": INSTALLATION["centroid"][1] + rng.uniform(-0.05, 0.05),
            "brightness_k": round(rng.uniform(295, 315), 1),
            "frp_mw": round(rng.uniform(0.4, 1.2), 2),
            "confidence": rng.choice(["low", "nominal"]),
            "is_anomaly": False,
            "anomaly_note": None,
        })
        eid += 1
    # PLANTED: thermal pings at Magazine 14 within incident window
    for k in range(3):
        t = T_INCIDENT + timedelta(minutes=4 + k * 12)
        out.append({
            "id": f"FIRMS-{eid:04d}",
            "stream": "firms",
            "ts_iso": t.isoformat(),
            "satellite": "VIIRS-NOAA20" if k % 2 else "VIIRS-SNPP",
            "lat": 33.3458 + rng.uniform(-0.001, 0.001),
            "lon": -117.5048 + rng.uniform(-0.001, 0.001),
            "brightness_k": round(rng.uniform(370, 410), 1),
            "frp_mw": round(rng.uniform(18.5, 32.0), 2),
            "confidence": "high",
            "is_anomaly": True,
            "anomaly_note": "FIRMS thermal anomaly vicinity Las Pulgas Magazine 14",
        })
        eid += 1
    out.sort(key=lambda r: r["ts_iso"])
    return out


# ---------------------------------------------------------------------------
# Gate events. Plant a spike of POV ingress at GATE-LAS-PULGAS in the
# 30-min window around T_INCIDENT.
# ---------------------------------------------------------------------------
def _gate_events(rng: random.Random) -> list[dict]:
    out = []
    eid = 0
    for hr in range(24):
        t_hr = T_START + timedelta(hours=hr)
        for gate in INSTALLATION["gates"]:
            lo, hi = gate["expected_throughput_per_hr"]
            local_hr = (t_hr.hour - 8) % 24
            rush = 1.0
            if 6 <= local_hr <= 8:
                rush = 1.7
            elif 15 <= local_hr <= 17:
                rush = 1.5
            elif 22 <= local_hr or local_hr <= 4:
                rush = 0.35
            base = int(rng.uniform(lo, hi) * rush)

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
                "ts_iso": t_hr.isoformat(),
                "gate_id": gate["id"],
                "gate_name": gate["name"],
                "lat": gate["lat"],
                "lon": gate["lon"],
                "ingress_count": n_in,
                "egress_count": n_out,
                "is_anomaly": bool(spike > 30),
                "anomaly_note": (
                    "POV ingress spike — incident-driven family arrival surge."
                    if spike > 30 else None
                ),
            })
            eid += 1
    return out


# ---------------------------------------------------------------------------
# Utility readings. Plant a water-pressure dip + power load surge.
# ---------------------------------------------------------------------------
def _utility_events(rng: random.Random) -> list[dict]:
    out = []
    eid = 0
    for hr in range(24):
        t_hr = T_START + timedelta(hours=hr)
        delta_h = (t_hr - T_INCIDENT).total_seconds() / 3600.0
        for node in INSTALLATION["utility_nodes"]:
            rec = {
                "id": f"UTIL-{eid:05d}",
                "stream": "utility",
                "ts_iso": t_hr.isoformat(),
                "node_id": node["id"],
                "node_kind": node["kind"],
                "node_name": node["name"],
                "lat": node["lat"],
                "lon": node["lon"],
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
                        rec["anomaly_note"] = "Water pressure dip — possible hydrant draw."
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
                        rec["anomaly_note"] = "Power load surge — emergency systems engaged."
                rec["load_mw"] = round(load, 3)
                rec["voltage_kv"] = round(rng.uniform(11.7, 12.3), 2)
            elif node["kind"] == "fuel":
                lo, hi = node["expected_inventory_gal"]
                rec["inventory_gal"] = int(rng.uniform(lo, hi))
                rec["temp_f"] = round(rng.uniform(58, 72), 1)
            out.append(rec)
            eid += 1
    return out


# ---------------------------------------------------------------------------
# Fire/EMS dispatches.
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
    for d_type, narrative, location in ROUTINE_DISPATCHES:
        t = T_START + timedelta(hours=rng.uniform(0.5, 23.0))
        unit = next(u for u in INSTALLATION["ems_units"] if u["type"] == d_type)
        out.append({
            "id": f"EMS-{eid:05d}",
            "stream": "ems",
            "ts_iso": t.isoformat(),
            "type": d_type,
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
    # PLANTED multi-unit incident
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
            "ts_iso": t.isoformat(),
            "type": utype,
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
# Mass-notification.
# ---------------------------------------------------------------------------
def _massnotify_events(rng: random.Random) -> list[dict]:
    routine = [
        (T_START + timedelta(hours=2), "TEST",
         "Daily AtHoc test broadcast — no action required."),
        (T_START + timedelta(hours=8), "ADVISORY",
         "Family housing area water-system flushing 0900-1100; brief discoloration possible."),
        (T_START + timedelta(hours=14), "ADVISORY",
         "Las Pulgas range complex live-fire 1300-1700; expect blast noise on Basilone Rd."),
        (T_START + timedelta(hours=20), "INFO",
         "Commissary closes at 2000 today; reopens 0900 tomorrow."),
    ]
    incident = [
        (T_INCIDENT + timedelta(minutes=6), "EMERGENCY",
         "ATTENTION ALL HANDS: Active incident vicinity Las Pulgas Magazine 14. "
         "All non-essential personnel shelter in place. Avoid Basilone Rd north of "
         "Stuart Mesa. EOC activated."),
        (T_INCIDENT + timedelta(minutes=22), "UPDATE",
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
            "lat": INSTALLATION["centroid"][0],
            "lon": INSTALLATION["centroid"][1],
            "is_anomaly": sev in ("EMERGENCY", "UPDATE"),
            "anomaly_note": ("Active emergency mass-notification" if sev == "EMERGENCY" else None),
        })
    out.sort(key=lambda r: r["ts_iso"])
    return out


# ---------------------------------------------------------------------------
# IEEE WiFi/BT RF fingerprinting events.
# ---------------------------------------------------------------------------
RF_DEVICE_KINDS = [
    ("wifi-ap", "WAP-MAINSIDE-001", "BSS-MAINSIDE", -52),
    ("wifi-ap", "WAP-SANMATEO-014", "BSS-SAN-MATEO", -58),
    ("bt-beacon", "BTLE-FIRESTA-1", "Engine Co 1 BLE asset tag", -68),
    ("wifi-client", "STA-44119", "1st Recon HMMWV-44119 telematics", -64),
    ("wifi-client", "STA-CO-IPHONE", "CO iPhone (corp WiFi)", -55),
]


def _rf_events(rng: random.Random) -> list[dict]:
    out = []
    eid = 0
    for hr in range(24):
        t_hr = T_START + timedelta(hours=hr)
        # Each hour, 3-4 baseline observations
        for _ in range(rng.randint(3, 5)):
            kind, devid, label, base_rssi = rng.choice(RF_DEVICE_KINDS)
            rssi = base_rssi + rng.uniform(-4, 4)
            out.append({
                "id": f"RF-{eid:05d}",
                "stream": "rf",
                "ts_iso": (t_hr + timedelta(minutes=rng.randint(0, 59))).isoformat(),
                "device_id": devid,
                "device_kind": kind,
                "label": label,
                "rssi_dbm": round(rssi, 1),
                "channel": rng.choice([1, 6, 11, 36, 149]) if "wifi" in kind else None,
                "lat": INSTALLATION["centroid"][0] + rng.uniform(-0.04, 0.04),
                "lon": INSTALLATION["centroid"][1] + rng.uniform(-0.04, 0.04),
                "is_anomaly": False,
                "anomaly_note": None,
            })
            eid += 1
    # PLANTED RF spike: unknown 2.4GHz emitter near Magazine 14 right before incident
    for k in range(3):
        t = T_INCIDENT - timedelta(minutes=8 - k * 4)
        out.append({
            "id": f"RF-{eid:05d}",
            "stream": "rf",
            "ts_iso": t.isoformat(),
            "device_id": f"UNK-EM-{k:02d}",
            "device_kind": "unknown_emitter",
            "label": "Unknown 2.4GHz emitter — no DBIDS handshake, no MCEN registration",
            "rssi_dbm": round(-45 - rng.uniform(-2, 2), 1),
            "channel": 6,
            "lat": 33.3470 + rng.uniform(-0.002, 0.002),
            "lon": -117.5040 + rng.uniform(-0.002, 0.002),
            "is_anomaly": True,
            "anomaly_note": "Unknown high-RSSI emitter inside magazine perimeter."
        })
        eid += 1
    out.sort(key=lambda r: r["ts_iso"])
    return out


# ---------------------------------------------------------------------------
# Drone RF detections.
# ---------------------------------------------------------------------------
def _drone_rf_events(rng: random.Random) -> list[dict]:
    out = []
    eid = 0
    # A few benign small-UAS detections during the day (e.g., contractor surveys)
    for hr in [4, 9, 13, 18, 22]:
        t_hr = T_START + timedelta(hours=hr, minutes=rng.randint(0, 59))
        out.append({
            "id": f"DRONE-{eid:04d}",
            "stream": "drone_rf",
            "ts_iso": t_hr.isoformat(),
            "protocol": rng.choice(["DJI-OcuSync2", "DJI-OcuSync3", "Lightbridge"]),
            "make": "DJI",
            "model": rng.choice(["Mavic 3", "Phantom 4", "Mini 3 Pro"]),
            "rid_serial": f"REG-{rng.randint(100000, 999999)}",
            "rssi_dbm": round(rng.uniform(-72, -55), 1),
            "altitude_m": round(rng.uniform(50, 110), 1),
            "lat": INSTALLATION["centroid"][0] + rng.uniform(-0.06, 0.06),
            "lon": INSTALLATION["centroid"][1] + rng.uniform(-0.06, 0.06),
            "is_anomaly": False,
            "anomaly_note": None,
        })
        eid += 1
    # PLANTED: a non-cooperative UAS (no Remote ID) loitering near magazine before fire
    for k in range(2):
        t = T_INCIDENT - timedelta(minutes=18 - k * 9)
        out.append({
            "id": f"DRONE-{eid:04d}",
            "stream": "drone_rf",
            "ts_iso": t.isoformat(),
            "protocol": "Unknown-FHSS",
            "make": "unknown",
            "model": "unknown",
            "rid_serial": None,
            "rssi_dbm": round(-48 - rng.uniform(-3, 3), 1),
            "altitude_m": round(rng.uniform(60, 90), 1),
            "lat": 33.3465 + rng.uniform(-0.003, 0.003),
            "lon": -117.5042 + rng.uniform(-0.003, 0.003),
            "is_anomaly": True,
            "anomaly_note": "Non-cooperative UAS near Magazine 14 — no Remote ID broadcast.",
        })
        eid += 1
    out.sort(key=lambda r: r["ts_iso"])
    return out


# ---------------------------------------------------------------------------
# Personas — 5 personas + role/permission JSON tree (ABAC).
# ---------------------------------------------------------------------------
PERSONAS = [
    {
        "id": "CO",
        "callsign": "ACTUAL-6",
        "name": "MajGen M. Marine",
        "role": "Commanding General, MCIWEST-MCB CamPen",
        "clearance": "TS/SCI",
        "allowed_streams": ["gate", "utility", "ems", "massnotify", "weather",
                            "maintenance", "rf", "drone_rf", "firms"],
        "allowed_anomaly_classes": ["ALL"],
        "view_brief": True,
        "view_audit": True,
        "abac_summary": "Commander — full I-COP visibility across every domain.",
    },
    {
        "id": "G-1",
        "callsign": "PERSONNEL",
        "name": "Col Davies",
        "role": "G-1 Personnel",
        "clearance": "SECRET",
        "allowed_streams": ["gate", "ems", "massnotify"],
        "allowed_anomaly_classes": ["personnel", "safety"],
        "view_brief": True,
        "view_audit": False,
        "abac_summary": "Personnel/safety only — denied intel, RF, drone, infrastructure.",
    },
    {
        "id": "G-2",
        "callsign": "INTEL",
        "name": "LtCol Kim",
        "role": "G-2 Intelligence",
        "clearance": "TS/SCI",
        "allowed_streams": ["rf", "drone_rf", "firms", "weather", "massnotify"],
        "allowed_anomaly_classes": ["intel", "force_protection"],
        "view_brief": True,
        "view_audit": True,
        "abac_summary": "Intel — RF, drone, FIRMS, weather. Denied gate/utility/EMS.",
    },
    {
        "id": "G-3",
        "callsign": "OPS",
        "name": "Col Riggs",
        "role": "G-3 Operations",
        "clearance": "SECRET",
        "allowed_streams": ["gate", "ems", "massnotify", "weather", "drone_rf", "firms"],
        "allowed_anomaly_classes": ["ops", "force_protection", "safety"],
        "view_brief": True,
        "view_audit": False,
        "abac_summary": "Ops — operational picture; denied utility SCADA + RF intel.",
    },
    {
        "id": "G-4",
        "callsign": "LOGISTICS",
        "name": "LtCol Vega",
        "role": "G-4 Logistics",
        "clearance": "SECRET",
        "allowed_streams": ["utility", "maintenance", "weather", "massnotify"],
        "allowed_anomaly_classes": ["supply", "maintenance", "safety"],
        "view_brief": True,
        "view_audit": False,
        "abac_summary": "Supply/maintenance — denied gate/EMS/RF/drone/intel.",
    },
    {
        "id": "S-6",
        "callsign": "COMMS",
        "name": "Maj Chen",
        "role": "S-6 Communications",
        "clearance": "SECRET",
        "allowed_streams": ["rf", "utility", "massnotify", "maintenance"],
        "allowed_anomaly_classes": ["comms", "infrastructure"],
        "view_brief": False,
        "view_audit": False,
        "abac_summary": "Comms — RF + infrastructure only; denied EMS/intel/drone/gate.",
    },
]


# ---------------------------------------------------------------------------
# Fused timeline.
# ---------------------------------------------------------------------------
def _fuse(gates, utils, ems, mn, weather, maint, rf, drone, firms) -> list[dict]:
    fused: list[dict] = []
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
    for m in mn:
        fused.append({
            "stream": "massnotify", "ts_iso": m["ts_iso"], "id": m["id"],
            "label": f"[{m['severity']}] {m['message'][:90]}",
            "is_anomaly": m["is_anomaly"], "anomaly_note": m["anomaly_note"],
            "lat": m["lat"], "lon": m["lon"],
        })
    for w in weather:
        fused.append({
            "stream": "weather", "ts_iso": w["ts_iso"], "id": w["id"],
            "label": (
                f"Wind {w['wind_speed_mps']} m/s from {w['wind_from_dir_deg']} deg, "
                f"{w['temp_c']} C, RH {w['rh_pct']}%, precip {w['precip_mm_hr']} mm/h"
            ),
            "is_anomaly": w["is_anomaly"],
            "anomaly_note": w["anomaly_note"],
            "lat": w["lat"], "lon": w["lon"],
        })
    for r in rf:
        fused.append({
            "stream": "rf", "ts_iso": r["ts_iso"], "id": r["id"],
            "label": f"{r['device_kind']} {r['device_id']} :: {r['rssi_dbm']} dBm :: {r['label'][:60]}",
            "is_anomaly": r["is_anomaly"], "anomaly_note": r["anomaly_note"],
            "lat": r["lat"], "lon": r["lon"],
        })
    for d in drone:
        fused.append({
            "stream": "drone_rf", "ts_iso": d["ts_iso"], "id": d["id"],
            "label": (
                f"{d['protocol']} {d['make']}/{d['model']} alt {d['altitude_m']} m "
                f"RID {d['rid_serial'] or 'NONE'}"
            ),
            "is_anomaly": d["is_anomaly"], "anomaly_note": d["anomaly_note"],
            "lat": d["lat"], "lon": d["lon"],
        })
    for f in firms:
        fused.append({
            "stream": "firms", "ts_iso": f["ts_iso"], "id": f["id"],
            "label": (
                f"{f['satellite']} thermal br {f['brightness_k']} K, FRP {f['frp_mw']} MW "
                f"({f['confidence']})"
            ),
            "is_anomaly": f["is_anomaly"], "anomaly_note": f["anomaly_note"],
            "lat": f["lat"], "lon": f["lon"],
        })
    nmc = [m for m in maint if m["status"] == "NMC"]
    pmc = [m for m in maint if m["status"] == "PMC"]
    fused.append({
        "stream": "maintenance", "ts_iso": T_NOW.isoformat(), "id": "GCSS-MC-SNAPSHOT",
        "label": f"GCSS-MC snapshot: {len(nmc)} NMC / {len(pmc)} PMC of {len(maint)} critical assets",
        "is_anomaly": len(nmc) >= 2,
        "anomaly_note": ("Multiple critical assets NMC during incident window."
                         if len(nmc) >= 2 else None),
        "lat": INSTALLATION["centroid"][0], "lon": INSTALLATION["centroid"][1],
    })
    fused.sort(key=lambda r: r["ts_iso"])
    return fused


# ---------------------------------------------------------------------------
# Cache-first hero outputs.
# ---------------------------------------------------------------------------
def _baseline_correlation(fused: list[dict]) -> dict:
    return {
        "anomalies": [
            {
                "anomaly_id": "OMNI-001",
                "severity": "HIGH",
                "domains_crossed": 5,
                "contributing_streams": ["drone_rf", "rf", "ems", "firms", "massnotify"],
                "hypothesis": (
                    "Cross-domain force-protection event at Las Pulgas Magazine 14: a "
                    "non-cooperative UAS (no Remote ID) was detected loitering 18 min "
                    "before ignition; an unknown 2.4 GHz emitter inside the magazine "
                    "perimeter persisted across 8 minutes pre-event; FIRMS thermal "
                    "anomalies (brightness 380-410 K, FRP 18-32 MW) over Magazine 14 "
                    "coincide with multi-unit P1 EMS dispatch and the EMERGENCY AtHoc "
                    "broadcast — five domains cross-corroborate within a 30-minute window."
                ),
                "recommended_action": (
                    "Activate Installation EOC at COG; cue G-2 to chain-of-custody the "
                    "drone-RF + 2.4 GHz spectrogram captures; tip MARFORPAC J-2 and CDF on "
                    "potential adversary triggering action; reaffirm shelter-in-place via "
                    "AtHoc; verify Magazine 14 cooling-spray loop pressure."
                ),
                "explainability": (
                    "Flagged because: drone-RF sighting at T-18m + RF unknown-emitter at T-8m + "
                    "FIRMS thermal at T+4m + EMS P1 dispatch at T+2m + AtHoc EMERGENCY at "
                    "T+6m — all within a 30-minute window over the same magazine."
                ),
                "confidence": 0.93,
            },
            {
                "anomaly_id": "OMNI-002",
                "severity": "HIGH",
                "domains_crossed": 4,
                "contributing_streams": ["ems", "utility", "gate", "massnotify"],
                "hypothesis": (
                    "Cross-stream installation-services event corroborates the magazine "
                    "incident: a 22 psi water-pressure dip at the Mainside Water Tower "
                    "(consistent with hydrant draw), a 2.6 MW load surge at the 22-Area "
                    "Substation (emergency systems engaged), and a POV ingress spike at "
                    "Las Pulgas Gate (family-driven response to the AtHoc EMERGENCY)."
                ),
                "recommended_action": (
                    "Pre-position MEDIC-5 at 43-Area as backfill; coordinate PMO traffic-"
                    "control plan at Las Pulgas Gate; brief PWD on residual water-pressure "
                    "recovery profile; expect 60-90 min to return to baseline."
                ),
                "explainability": (
                    "Flagged because: water dip at T+0m + power surge at T+0m + gate "
                    "spike at T+0m + AtHoc EMERGENCY at T+6m = 4 installation-services "
                    "streams corroborating the magazine incident."
                ),
                "confidence": 0.90,
            },
            {
                "anomaly_id": "OMNI-003",
                "severity": "MEDIUM",
                "domains_crossed": 2,
                "contributing_streams": ["weather", "ems"],
                "hypothesis": (
                    "Santa Ana wind shift to ~14 m/s easterly is concurrent with the "
                    "magazine structure fire — wind alignment is pushing smoke and embers "
                    "toward San Onofre family housing."
                ),
                "recommended_action": (
                    "Pre-stage Engine Co 1 reserves at San Onofre; coordinate with PWD for "
                    "downwind air-quality monitoring; place housing on voluntary evacuation."
                ),
                "explainability": (
                    "Flagged because: weather wind 14 m/s easterly at T+0m + structure-fire "
                    "EMS dispatch at T+2m, wind vector projects ember plume on housing."
                ),
                "confidence": 0.78,
            },
            {
                "anomaly_id": "OMNI-004",
                "severity": "MEDIUM",
                "domains_crossed": 2,
                "contributing_streams": ["maintenance", "ems"],
                "hypothesis": (
                    "GCSS-MC reports the MCFD GENSET-MCFD-AUX-3 NMC during the magazine "
                    "incident window — backup power resilience to Mainside Fire Sta 1 is "
                    "degraded exactly when an incident is consuming primary capacity."
                ),
                "recommended_action": (
                    "Direct CLB-1 to expedite voltage-regulator swap; confirm utility-power "
                    "redundancy is sufficient until repaired; pre-stage commercial generator "
                    "from contingency contract."
                ),
                "explainability": (
                    "Flagged because: GCSS-MC NMC GENSET-MCFD-AUX-3 + concurrent multi-unit "
                    "EMS P1 incident = degraded resilience window."
                ),
                "confidence": 0.83,
            },
        ],
        "_source": "deterministic_baseline",
    }


def _baseline_brief(fused: list[dict], correlation: dict) -> str:
    anomalies = correlation.get("anomalies", [])
    bullets = "\n".join(
        f"  - [{a['severity']}] {a['anomaly_id']} (domains crossed: {a['domains_crossed']}): "
        f"{a['hypothesis']}"
        for a in anomalies[:3]
    )
    actions = "\n".join(f"  - {a['recommended_action']}" for a in anomalies[:3])
    return (
        f"COMMANDER'S I-COP BRIEF — {INSTALLATION['name']}\n"
        f"AS OF: {T_NOW.isoformat()}\n\n"
        f"BLUF: Active cross-domain force-protection event at Las Pulgas Magazine 14. "
        f"Five domains corroborate within a 30-minute window — non-cooperative UAS "
        f"loiter, unknown 2.4 GHz emitter inside the perimeter, FIRMS thermal "
        f"anomaly, multi-unit P1 EMS dispatch, EMERGENCY AtHoc broadcast. EOC "
        f"activation recommended. G-2 to take custody of RF / drone evidence. "
        f"Two critical assets NMC (GENSET-MCFD-AUX-3, HMMWV-44102) degrade "
        f"resilience during the incident window.\n\n"
        f"TOP 3 CROSS-DOMAIN ANOMALIES:\n{bullets}\n\n"
        f"PREDICTIVE RISK — NEXT 12H:\n"
        f"  - Santa Ana wind shift (~14 m/s easterly) sustains 6-8h; ember risk "
        f"to San Onofre family housing is the dominant hazard until winds abate.\n"
        f"  - Mainside water pressure expected to recover to baseline (62-78 psi) "
        f"within 90 min of fire suppression.\n"
        f"  - If RF spectrogram analysis confirms adversary triggering action, "
        f"expect MARFORPAC J-2 escalation and force-protection condition uplift.\n\n"
        f"RECOMMENDED PRE-POSITIONING PER CCDR:\n{actions}\n\n"
        f"//SIGNED// I-COP Aggregator (OMNI) — Powered by Kamiwaza"
    )


def _precompute_briefs(fused: list[dict]) -> dict:
    correlation = _baseline_correlation(fused)
    brief = _baseline_brief(fused, correlation)

    live_correlation = None
    live_brief = None
    try:
        from concurrent.futures import ThreadPoolExecutor
        from shared.kamiwaza_client import chat, chat_json  # noqa: WPS433

        def _live_correlator():
            anomaly_window = [f for f in fused if f.get("is_anomaly")]
            sys_msg = (
                "You are the OMNI cross-domain installation correlator for USMC LOGCOM. "
                "You consume fused multi-source events across SIX streams: gate access, "
                "utility readings, fire/EMS dispatches, mass-notification, weather, "
                "GCSS-MC maintenance, IEEE WiFi/BT RF, drone RF detections, and NASA "
                "FIRMS thermal pings. You output strict JSON identifying anomalies that "
                "are corroborated ACROSS MULTIPLE DOMAINS in the same time window. "
                "Each anomaly must include `domains_crossed` (int) and `explainability` "
                "(one-line trace of the contributing signals)."
            )
            usr = (
                f"Installation: {INSTALLATION['name']}\n"
                f"As of: {T_NOW.isoformat()}\n\n"
                f"Anomalous fused events (last 24h):\n"
                f"{json.dumps(anomaly_window, indent=2)}\n\n"
                "Return JSON: {\"anomalies\": [{\"anomaly_id\": str, "
                "\"severity\": \"LOW|MEDIUM|HIGH\", "
                "\"domains_crossed\": int, "
                "\"contributing_streams\": [str], "
                "\"hypothesis\": str, "
                "\"recommended_action\": str, "
                "\"explainability\": str, "
                "\"confidence\": 0..1}]} -- 3 to 5 anomalies, sorted severity desc."
            )
            return chat_json(
                [{"role": "system", "content": sys_msg},
                 {"role": "user", "content": usr}],
                schema_hint=("anomalies[] with anomaly_id, severity, domains_crossed, "
                             "contributing_streams, hypothesis, recommended_action, "
                             "explainability, confidence"),
                temperature=0.25,
                max_tokens=1100,
            )

        def _live_brief(corr):
            sys_msg = (
                "You are the senior watch officer's AI battle-buddy in the MCB Camp "
                "Pendleton Installation EOC. Draft the Commander's I-COP Brief in plain "
                "text. Use Marine register: BLUF, then top 3 cross-domain anomalies, "
                "then predictive risk for the next 12 hours, then recommended "
                "pre-positioning per CCDR. End with '//SIGNED// I-COP Aggregator (OMNI)'. "
                "Do not exceed 360 words."
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
            try:
                from shared.kamiwaza_client import get_client  # noqa: WPS433
                client = get_client()
                resp = client.chat.completions.create(
                    model="gpt-5.4",
                    messages=messages,
                    max_completion_tokens=1100,
                )
                return resp.choices[0].message.content or ""
            except Exception:
                return chat(messages, temperature=0.35, max_tokens=1100)

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
        pass

    return {
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


# ---------------------------------------------------------------------------
def main() -> None:
    rng = random.Random(SEED)
    weather = _weather(rng)
    firms = _firms(rng)
    maint = _gcss_maintenance(rng)
    gates = _gate_events(rng)
    utils = _utility_events(rng)
    ems = _ems_events(rng)
    mn = _massnotify_events(rng)
    rf = _rf_events(rng)
    drone = _drone_rf_events(rng)
    fused = _fuse(gates, utils, ems, mn, weather, maint, rf, drone, firms)

    (OUT / "installations.json").write_text(json.dumps([INSTALLATION], indent=2))
    (OUT / "weather.json").write_text(json.dumps(weather, indent=2))
    (OUT / "firms.json").write_text(json.dumps(firms, indent=2))
    (OUT / "maintenance.json").write_text(json.dumps(maint, indent=2))
    (OUT / "gate_events.json").write_text(json.dumps(gates, indent=2))
    (OUT / "utility_events.json").write_text(json.dumps(utils, indent=2))
    (OUT / "ems_events.json").write_text(json.dumps(ems, indent=2))
    (OUT / "massnotify_events.json").write_text(json.dumps(mn, indent=2))
    (OUT / "rf_events.json").write_text(json.dumps(rf, indent=2))
    (OUT / "drone_rf_events.json").write_text(json.dumps(drone, indent=2))
    (OUT / "fused_timeline.json").write_text(json.dumps(fused, indent=2))
    (OUT / "personas.json").write_text(json.dumps(PERSONAS, indent=2))

    do_llm = os.getenv("OMNI_PRECOMPUTE_LIVE", "1") != "0"
    if do_llm:
        cached = _precompute_briefs(fused)
    else:
        corr = _baseline_correlation(fused)
        cached = {
            "as_of_iso": T_NOW.isoformat(),
            "installation": {"id": INSTALLATION["id"], "name": INSTALLATION["name"],
                             "centroid": INSTALLATION["centroid"]},
            "baseline_correlation": corr,
            "baseline_brief": _baseline_brief(fused, corr),
            "live_correlation": None,
            "live_brief": None,
        }
    (OUT / "cached_briefs.json").write_text(json.dumps(cached, indent=2))

    print("OMNI synthetic data:")
    print(f"  installations.json       1 base ({INSTALLATION['name']})")
    print(f"  weather.json             {len(weather)} hourly NASA Earthdata-shape readings")
    print(f"  firms.json               {len(firms)} NASA FIRMS thermal pings")
    print(f"  maintenance.json         {len(maint)} GCSS-MC asset records")
    print(f"  gate_events.json         {len(gates)} gate ingress/egress")
    print(f"  utility_events.json      {len(utils)} utility readings")
    print(f"  ems_events.json          {len(ems)} fire/EMS dispatches")
    print(f"  massnotify_events.json   {len(mn)} mass-notification events")
    print(f"  rf_events.json           {len(rf)} IEEE WiFi/BT RF events")
    print(f"  drone_rf_events.json     {len(drone)} drone-RF detections")
    print(f"  fused_timeline.json      {len(fused)} fused records")
    print(f"  personas.json            {len(PERSONAS)} role/permission trees")
    print(f"  cached_briefs.json       baseline + (live if reachable) hero outputs")
    n_anom = sum(1 for f in fused if f.get("is_anomaly"))
    print(f"\nIncident anchored at: {T_INCIDENT.isoformat()}")
    print(f"Total flagged anomalies in fused timeline: {n_anom}")


if __name__ == "__main__":
    main()
