"""SCHOOLHOUSE — synthetic data generator for the Marine schoolhouse-in-a-box.

Produces under data/:
  courses.json         — 3 demo courses, 3 students each, with assignments + rubrics
  scenes_meta.json     — 8 egocentric scene cards (PNGs already in data/scenes/)
  visual_id_meta.json  — 12 visual-ID samples (PNGs already in data/visual_id/)
  personas.json        — 5 PA-training audience personas
  forum_posts.jsonl    — 4 forum posts per student per course
  competency_ts.jsonl  — competency timeseries (weekly) per student
  cached_briefs.json   — pre-computed Schoolhouse Intelligence Briefs per persona x course
  audit_logs/schoolhouse_audit.jsonl — append-only chain (genesis written here)

Seeded random.Random(1776). All names + posts are synthetic — no real Marine data.
Real-data swap path: see data/load_real.py.
"""
from __future__ import annotations

import hashlib
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCENES_DIR = ROOT / "scenes"
VID_DIR = ROOT / "visual_id"
AUDIT_LOG = ROOT / "audit_logs" / "schoolhouse_audit.jsonl"
AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)

SEED = 1776
RNG = random.Random(SEED)


# ─────────────────────────────────────────────────────────────────────────────
# Courses (3) — anchored to specific NAVMC 3500 / MCO 1553.4B framework
# ─────────────────────────────────────────────────────────────────────────────
COURSES = [
    {
        "course_id": "log_principles_26_1",
        "name": "Logistics Principles Paper Course - Cohort 26-1",
        "code": "LOG-PRIN-26-1",
        "tr_manual": "NAVMC 3500.58 — Logistics Training & Readiness Manual",
        "tr_manual_short": "NAVMC 3500.58",
        "tr_event_examples": ["LOG-DIST-2001", "LOG-MAINT-1001", "LOG-MGMT-2002"],
        "schoolhouse": "MCLOG (Marine Corps Logistics Operations Group), Camp Lejeune NC",
        "instructor": "MGySgt R. Vasquez",
        "governing_authority": (
            "Privacy Act of 1974 (5 U.S.C. § 552a) and DoDI 1322.35 'Military Education Records'"
        ),
        "assignment": {
            "id": "ASG_LOGPRIN_01",
            "title": "Apply MCDP-4 Logistics Principles to a 72-hour MAGTF Sustainment Plan",
            "type": "written_paper",
            "rubric_xlsx": "log_principles_rubric.xlsx",
            "rubric_criteria": [
                {"id": "C1", "label": "Doctrinal grounding (MCDP-4 cite quality)", "weight": 0.25},
                {"id": "C2", "label": "Sustainment-flow analysis (Class I-IX)", "weight": 0.25},
                {"id": "C3", "label": "Critical thinking & assumptions stated", "weight": 0.20},
                {"id": "C4", "label": "Communication clarity & 5-paragraph discipline", "weight": 0.15},
                {"id": "C5", "label": "Risk-to-mission articulation", "weight": 0.15},
            ],
        },
        "students": [
            {
                "student_id": "S01",
                "name": "Capt Alvarez",
                "rank": "Capt",
                "edipi_synth": "1700020001",
                "profile": "high_performer",
            },
            {
                "student_id": "S02",
                "name": "1stLt Brennan",
                "rank": "1stLt",
                "edipi_synth": "1700020002",
                "profile": "developing",
            },
            {
                "student_id": "S03",
                "name": "GySgt Diaz",
                "rank": "GySgt",
                "edipi_synth": "1700020003",
                "profile": "needs_remediation",
            },
        ],
    },
    {
        "course_id": "sgts_course_2_26",
        "name": "Sergeants Course - Class 2-26 (SNCO Academy MCB Quantico, resident PME for E-5)",
        "code": "SGTS-2-26",
        "tr_manual": (
            "MCO 1553.4B (PME Framework) and DoDI 1322.35 'Military Education' — "
            "Sergeants Course is RESIDENT PME at the SNCO Academy Quantico, distinct from "
            "the Squad Leader Course taught at SOI under the Infantry T&R (NAVMC 3500.18)"
        ),
        "tr_manual_short": "MCO 1553.4B / DoDI 1322.35",
        "tr_event_examples": ["PME-SGTS-LEAD-1", "PME-SGTS-COMM-2", "PME-SGTS-PROF-3"],
        "schoolhouse": "Staff NCO Academy, MCB Quantico VA (resident PME, E-5 Sergeants)",
        "instructor": "MSgt T. Okonkwo",
        "governing_authority": (
            "Privacy Act of 1974 (5 U.S.C. § 552a) and DoDI 1322.35 'Military Education Records'"
        ),
        "assignment": {
            "id": "ASG_SGTS_01",
            "title": "Leadership Position Paper — Decentralized Command in Distributed Operations",
            "type": "written_paper",
            "rubric_xlsx": "sgts_leadership_rubric.xlsx",
            "rubric_criteria": [
                {"id": "C1", "label": "MCDP-1 Warfighting alignment", "weight": 0.25},
                {"id": "C2", "label": "Personal-experience integration (legitimacy)", "weight": 0.20},
                {"id": "C3", "label": "Critical thinking — counter-arguments addressed", "weight": 0.20},
                {"id": "C4", "label": "Written communication discipline", "weight": 0.20},
                {"id": "C5", "label": "Actionable leadership take-aways", "weight": 0.15},
            ],
        },
        "students": [
            {
                "student_id": "S04",
                "name": "Sgt Edwards",
                "rank": "Sgt",
                "edipi_synth": "1700020004",
                "profile": "quiet_thinker",
            },
            {
                "student_id": "S05",
                "name": "Sgt Ferguson",
                "rank": "Sgt",
                "edipi_synth": "1700020005",
                "profile": "high_performer",
            },
            {
                "student_id": "S06",
                "name": "Sgt Garcia",
                "rank": "Sgt",
                "edipi_synth": "1700020006",
                "profile": "needs_remediation",
            },
        ],
    },
    {
        "course_id": "mos_0411_pipeline_26_4",
        "name": "MOS 0411 Maintenance Management Specialist Pipeline - Class 26-04",
        "code": "PMOS-0411-26-04",
        "tr_manual": "NAVMC 3500.58 — Logistics Training & Readiness Manual",
        "tr_manual_short": "NAVMC 3500.58",
        "tr_event_examples": ["LOG-MAINT-1001", "LOG-MAINT-2003", "LOG-DIST-2001"],
        "schoolhouse": "Marine Corps Combat Service Support Schools (MCCSSS), Camp Johnson NC",
        "instructor": "GySgt P. Reyes",
        "governing_authority": (
            "Privacy Act of 1974 (5 U.S.C. § 552a) and DoDI 1322.35 'Military Education Records'"
        ),
        "assignment": {
            "id": "ASG_0411_01",
            "title": "Sustainment Pipeline Practical — GCSS-MC Maintenance Cycle Walkthrough",
            "type": "written_paper",
            "rubric_xlsx": "mos_0411_rubric.xlsx",
            "rubric_criteria": [
                {"id": "C1", "label": "GCSS-MC workflow accuracy", "weight": 0.25},
                {"id": "C2", "label": "Maintenance cycle doctrine (TM 4790)", "weight": 0.20},
                {"id": "C3", "label": "Problem-solving — bottleneck identification", "weight": 0.20},
                {"id": "C4", "label": "Written communication discipline", "weight": 0.15},
                {"id": "C5", "label": "Class IX parts-flow articulation", "weight": 0.20},
            ],
        },
        "students": [
            {
                "student_id": "S07",
                "name": "Cpl Hernandez",
                "rank": "Cpl",
                "edipi_synth": "1700020007",
                "profile": "developing",
            },
            {
                "student_id": "S08",
                "name": "Cpl Ito",
                "rank": "Cpl",
                "edipi_synth": "1700020008",
                "profile": "high_performer",
            },
            {
                "student_id": "S09",
                "name": "LCpl Johnson",
                "rank": "LCpl",
                "edipi_synth": "1700020009",
                "profile": "needs_remediation",
            },
        ],
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# Egocentric scene cards (8) — frames already in data/scenes/
# ─────────────────────────────────────────────────────────────────────────────
SCENES = [
    {
        "id": "scn_01",
        "title": "Doorway Entry — Urban Structure",
        "scene_kind": "doorway",
        "pov": (
            "You are stacked second-man on a closed wooden door of a two-story residence. "
            "Friendly call-out: 'breach in 3'. No flash-bang loaded."
        ),
        "doctrine_reference": (
            "MCWP 3-35.3 'Military Operations on Urbanized Terrain' para 5-12 "
            "(room clearing — point of domination, button-hook)"
        ),
        "tr_event": "INF-OPS-2001",
        "correct_actions": [
            "Maintain stack discipline; cover the deep corner on entry.",
            "Button-hook to your point of domination; do not cross the threshold of fire.",
            "Call out the room status: 'CLEAR' or 'CONTACT direction'.",
        ],
        "common_failures": [
            "Crossing into the fatal funnel without buttonhooking.",
            "Losing muzzle awareness on the lead man.",
            "Hesitating in the doorway (silhouette).",
        ],
    },
    {
        "id": "scn_02",
        "title": "Vehicle Checkpoint — Approaching Sedan",
        "scene_kind": "checkpoint",
        "pov": (
            "You are senior Marine on a hasty TCP at dusk. A grey four-door sedan is rolling "
            "toward you at ~15 mph, single male driver visible, no passengers seen. Concertina is set 30m out."
        ),
        "doctrine_reference": (
            "MCRP 3-33.1A 'Civil Affairs Tactics, Techniques, and Procedures' Appendix B "
            "(escalation of force — shout, show, shove, shoot)"
        ),
        "tr_event": "INF-OPS-2003",
        "correct_actions": [
            "Begin Escalation of Force: SHOUT — verbal + arm signal STOP at warning line.",
            "If non-compliant, SHOW — visible weapon presentation, laser/light to windshield.",
            "Continue EOF only as long as threat indicators remain ambiguous; do not skip steps.",
        ],
        "common_failures": [
            "Skipping straight to disabling fire on a non-hostile vehicle.",
            "Standing in the kill-funnel of the lane instead of off-axis.",
            "Failing to call up the contact to higher.",
        ],
    },
    {
        "id": "scn_03",
        "title": "Casualty Triage — Downed Marine",
        "scene_kind": "casualty",
        "pov": (
            "You are first to your fallen squadmate after a single-shot contact. He is supine, "
            "conscious, gripping his right thigh; bright red blood is pulsing through his trousers."
        ),
        "doctrine_reference": (
            "TCCC Guidelines (Tactical Combat Casualty Care) — Care Under Fire phase: stop the "
            "life-threatening hemorrhage with a tourniquet, then move to cover."
        ),
        "tr_event": "INF-CAS-1001",
        "correct_actions": [
            "Apply a CAT tourniquet HIGH AND TIGHT on the right thigh, mark TQ time.",
            "Drag casualty to nearest cover before transitioning to TFC phase.",
            "Call up 9-line MEDEVAC with grid + patient precedence.",
        ],
        "common_failures": [
            "Starting wound packing under direct fire instead of TQ.",
            "Removing gear / cutting clothes before stopping the bleed.",
            "Forgetting to mark the TQ time on the casualty's forehead.",
        ],
    },
    {
        "id": "scn_04",
        "title": "Vehicle PMCS — JLTV Bay",
        "scene_kind": "vehicle_interior",
        "pov": (
            "You are the assigned operator standing at the driver's side of a JLTV in the motor pool. "
            "Engine off. Your task: pre-op PMCS before convoy SP in 30 minutes."
        ),
        "doctrine_reference": (
            "TM 9-2320-450-10 'Operator Manual JLTV' — Before-Operation PMCS table 2-1 "
            "(fluids, tires, lights, comms, secure load)"
        ),
        "tr_event": "LOG-MAINT-1001",
        "correct_actions": [
            "Walk-around: tires inflation + sidewall, fluid leaks under chassis, lights, mirrors.",
            "Cab: secure all loose gear, check seat belts, verify radio/intercom and BFT functional.",
            "Document deficiencies on DA Form 5988-E before turning over to convoy commander.",
        ],
        "common_failures": [
            "Skipping the underbody walk-around.",
            "Loose gear in the cab (becomes a projectile in a rollover).",
            "Not signing the 5988-E (no paper trail = the deficiency 'didn't exist').",
        ],
    },
    {
        "id": "scn_05",
        "title": "Hallway Cross — Two-Way Hostile Building",
        "scene_kind": "hallway",
        "pov": (
            "You are halfway down a narrow second-floor hallway. An open door is on your left at 4m, "
            "another open door on your right at 7m. You hear an English-language shout from the right room: "
            "'STAY BACK!'"
        ),
        "doctrine_reference": "MCWP 3-35.3 para 5-21 (limited-penetration room clearing; pie the door before entry)",
        "tr_event": "INF-OPS-2002",
        "correct_actions": [
            "Pie the right-side door from maximum standoff — do not cross the doorway.",
            "Call out positively to identify yourself: 'US MARINES — IDENTIFY YOURSELF'.",
            "Hold the cross-fire angle until the second team-member can mirror the left-side door.",
        ],
        "common_failures": [
            "Charging the door without pieing.",
            "Sweeping muzzle through the open left door while focused right.",
            "Not calling out positive ID — friendly fire risk.",
        ],
    },
    {
        "id": "scn_06",
        "title": "Comms Shop — FPCON Charlie Alert",
        "scene_kind": "comms_shop",
        "pov": (
            "You are the duty NCO in the battalion COC. The IDS console just chirped FPCON CHARLIE. "
            "Two radios are mid-traffic. The battalion XO is across the deck, headphones on, back turned."
        ),
        "doctrine_reference": (
            "MCO 3302.1F (Marine Corps Antiterrorism Program) — FPCON change procedures: "
            "notify, lock, brief, log."
        ),
        "tr_event": "LOG-MGMT-2002",
        "correct_actions": [
            "Acknowledge the alert on the console, log the DTG, then physically notify the XO.",
            "Drop the comms net to FPCON-CHARLIE check-ins; lock the entry door per SOP.",
            "Send a flash report up to higher with grid + posture in <5 minutes.",
        ],
        "common_failures": [
            "Yelling across the deck instead of physically notifying the XO.",
            "Continuing routine traffic without changing the net posture.",
            "Forgetting to log the DTG (no paper trail for the IG / SJA review).",
        ],
    },
    {
        "id": "scn_07",
        "title": "Night Perimeter — Rustle In The Wire",
        "scene_kind": "perimeter_night",
        "pov": (
            "You are 03:14 on Position 3 of a hasty patrol base. NVGs on, weapon up. You hear a rustle "
            "and a low metallic clink ~25m to your front, beyond the wire. No friendly LP/OP is forward."
        ),
        "doctrine_reference": (
            "MCWP 3-11.2 'Marine Rifle Squad' Chapter 4 (defensive operations — challenge & password, "
            "no movement forward of the wire without coordination)"
        ),
        "tr_event": "INF-PAT-2002",
        "correct_actions": [
            "Pass the contact across the position net in a low whisper — do not break light/noise discipline.",
            "Issue the challenge per SOP from your hardened position; do not advance forward of the wire.",
            "Cue the 240 to your sector; mark the suspected location with an aim point, not a flare.",
        ],
        "common_failures": [
            "Walking forward of the wire to investigate — you become the casualty.",
            "Throwing illum that silhouettes the position to the rest of the perimeter.",
            "Engaging without challenging — friendly LP/OP could be off-route.",
        ],
    },
    {
        "id": "scn_08",
        "title": "IED Indicators — Disturbed Roadway",
        "scene_kind": "ied",
        "pov": (
            "You are lead vehicle commander on a route reconnaissance. 80m to your front you observe "
            "a fresh asphalt patch, a wire trace running to a discarded battery in the ditch, and a "
            "civilian standing back from the road taking a phone video."
        ),
        "doctrine_reference": (
            "MCWP 3-17.2 'Counter-IED Operations' — 5C: Confirm, Clear, Cordon, Check, Control. "
            "Indicators are observed; HALT outside the suspected lethal radius."
        ),
        "tr_event": "INF-OPS-2004",
        "correct_actions": [
            "STOP the convoy outside 100m blast radius; do not back up over your own track.",
            "Cordon and call EOD; push the cordon out to 300m for VBIED standoff.",
            "Detain (or at minimum freeze + film) the civilian observer for HUMINT.",
        ],
        "common_failures": [
            "Driving past the indicator to 'check it out'.",
            "Backing up over the same track (potential daisy-chain).",
            "Ignoring the bystander (likely trigger-man or BDA cell).",
        ],
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# Visual ID samples (12) — 8 PNGs in data/visual_id/ + 4 metadata-only entries
# ─────────────────────────────────────────────────────────────────────────────
VISUAL_ID = [
    {
        "id": "vid_01", "image": "S001_T-72B3.png",
        "ground_truth": "T-72B3", "country": "Russian Federation", "type": "MBT",
        "key_features": "Round low-profile turret; Kontakt-5 ERA arrow pattern on glacis; six road wheels with no return rollers.",
    },
    {
        "id": "vid_02", "image": "S002_M1A2_Abrams.png",
        "ground_truth": "M1A2 Abrams", "country": "United States", "type": "MBT",
        "key_features": "Flat angular turret; 120mm M256 smoothbore; CITV optic; gas-turbine exhaust grille on rear deck.",
    },
    {
        "id": "vid_03", "image": "S003_MQ-9_Reaper.png",
        "ground_truth": "MQ-9 Reaper", "country": "United States", "type": "MALE UCAV",
        "key_features": "Long slender fuselage; V-tail with ventral fin; pusher prop; SATCOM bulge above nose; ~20m wingspan.",
    },
    {
        "id": "vid_04", "image": "S004_Bayraktar_TB2.png",
        "ground_truth": "Bayraktar TB2", "country": "Turkey", "type": "MALE UCAV",
        "key_features": "Inverted-V tail; pusher prop; small EO/IR ball under nose; ~12m wingspan; no SATCOM bulge (line-of-sight only).",
    },
    {
        "id": "vid_05", "image": "S005_AH-64E_Apache_Guardian.png",
        "ground_truth": "AH-64E Apache Guardian", "country": "United States", "type": "Attack Helicopter",
        "key_features": "Tandem cockpit; chin M230 30mm; Longbow millimeter-wave radar dome above main rotor; four-blade main rotor.",
    },
    {
        "id": "vid_06", "image": "S006_Ka-52_Alligator.png",
        "ground_truth": "Ka-52 Alligator", "country": "Russian Federation", "type": "Attack Helicopter",
        "key_features": "Coaxial counter-rotating main rotors (no tail rotor); side-by-side cockpit; ejection seats.",
    },
    {
        "id": "vid_07", "image": "S007_Su-57_Felon.png",
        "ground_truth": "Su-57 Felon", "country": "Russian Federation", "type": "5th-gen Fighter",
        "key_features": "Twin widely-spaced engines; LEVCONs forward of wing root; all-moving canted twin tails; long tailcone between engines.",
    },
    {
        "id": "vid_08", "image": "S008_Shahed-136_-_Geran-2.png",
        "ground_truth": "Shahed-136 / Geran-2", "country": "Iran (Russian re-mfg as Geran-2)", "type": "Loitering munition",
        "key_features": "Delta wing with vertical winglets; pusher prop; ~3.5m wingspan; warhead in nose.",
    },
    # 4 metadata-only entries that document the rest of the corpus shape
    {
        "id": "vid_09", "image": None,
        "ground_truth": "T-90M Proryv", "country": "Russian Federation", "type": "MBT",
        "key_features": "Welded turret with Relikt ERA wedges; Sosna-U gunner sight on left of mantlet.",
    },
    {
        "id": "vid_10", "image": None,
        "ground_truth": "F-35A Lightning II", "country": "United States", "type": "5th-gen Fighter",
        "key_features": "Single engine; chined nose with EOTS sensor under nose; canted twin tails; internal weapons bays.",
    },
    {
        "id": "vid_11", "image": None,
        "ground_truth": "J-20 Mighty Dragon", "country": "China (PRC)", "type": "5th-gen Fighter",
        "key_features": "Canard-delta layout; twin canted tails + ventral fins; chined nose; long fuselage.",
    },
    {
        "id": "vid_12", "image": None,
        "ground_truth": "Type 055 Renhai", "country": "China (PRC)", "type": "Cruiser",
        "key_features": "Integrated mast with panel arrays; 112-cell VLS; ~13,000t; flush forecastle.",
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# PA Training audience personas (5) — borrowed pattern from CHORUS, trimmed
# ─────────────────────────────────────────────────────────────────────────────
PERSONAS = [
    {
        "persona_id": "PER_JR_MARINE",
        "label": "Junior Marine (LCpl, 21yo, infantry rifleman)",
        "trust_baseline": 0,
        "lens": (
            "Reads command messaging through 'is this real, or is this PowerPoint?' "
            "Will share or trash a message in the company group chat within 90 seconds."
        ),
        "values": ["plain English", "respect for the rifleman", "no spin"],
        "concerns": ["jargon", "passive voice", "messages clearly written by an officer"],
        "trigger_phrases_negative": ["robust", "leverage", "synergy", "kinetic outcome", "as we move forward"],
        "trigger_phrases_positive": ["here is what we're doing", "we owned it", "your name is on the list", "first formation"],
    },
    {
        "persona_id": "PER_NCO",
        "label": "NCO (Sgt, squad leader, 7 yr in)",
        "trust_baseline": 1,
        "lens": "Reads for what the message asks them to DO and whether the timeline is realistic with current manning.",
        "values": ["clarity of task", "realistic timelines", "accountability up the chain"],
        "concerns": ["unfunded taskers", "vague verbs", "leadership shielding leadership"],
        "trigger_phrases_negative": ["best effort", "as time permits", "subject to mission", "leadership is aware"],
        "trigger_phrases_positive": ["NCOIC named", "deadline + POC", "by-name responsibility", "manning impact stated"],
    },
    {
        "persona_id": "PER_OFFICER",
        "label": "Officer (Capt, company commander)",
        "trust_baseline": 1,
        "lens": "Reads for second- and third-order effects; what risk has the higher headquarters accepted on his behalf.",
        "values": ["commander's intent clarity", "risk acceptance stated", "chain of command alignment"],
        "concerns": ["surprises in his AO", "implied unfunded mandates", "PA pre-empting his command voice"],
        "trigger_phrases_negative": ["effective immediately", "all hands", "no impact to the mission"],
        "trigger_phrases_positive": ["coordinated with company", "company commanders briefed", "risk to mission is X"],
    },
    {
        "persona_id": "PER_SPOUSE",
        "label": "Civilian spouse (FRG admin, deployed-Marine spouse)",
        "trust_baseline": 0,
        "lens": "Filters every release through 'does this make my Marine safer or less safe today.' Will share inside the FRG within 5 minutes.",
        "values": ["are my Marines safe", "predictability", "honest reporting"],
        "concerns": ["learning of incidents from social media first", "vague timelines", "policy changes mid-deployment"],
        "trigger_phrases_negative": ["operational details cannot be shared", "no impact on the mission", "we are aware of the reports"],
        "trigger_phrases_positive": ["families have been notified", "command will hold a town hall", "here is the unit POC"],
    },
    {
        "persona_id": "PER_RETIRED_VET",
        "label": "Retired vet (GySgt ret., veteran-community newsletter, 200k subs)",
        "trust_baseline": -1,
        "lens": "Will quote your release in full and roast specific phrases. Drives a substantial slice of the lance-corporal underground.",
        "values": ["plain English", "no spin", "respect for the rifleman"],
        "concerns": ["jargon", "officers shielding officers", "PR voice"],
        "trigger_phrases_negative": ["robust", "leverage", "synergy", "regret any inconvenience"],
        "trigger_phrases_positive": ["we made this mistake", "here is what we changed", "named individual"],
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# Synthetic forum posts + competency timeseries
# ─────────────────────────────────────────────────────────────────────────────
FORUM_THREADS = [
    "Discussion: When does centralized control hurt initiative?",
    "Critique: Defensive vs offensive mindset in MCDP-1",
    "Apply MCDP-4 sustainment to a 72-hour distributed op",
    "Lessons learned: Class IX parts-flow chokepoints in a MAGTF",
]

POST_BANK = {
    "high_performer": [
        "Boyd's OODA cycle is not a slogan — it's the reason centralized control on a 30-second decision is malpractice. Reference MCDP-1 Ch.4 and the 1st Tank Bn AAR from {city}.",
        "Sustainment is a maneuver factor, not a logistician's problem. If Class V isn't moving with the scheme of maneuver you don't have a plan, you have a wish list.",
        "Counter-arg: decentralized execution still requires unity of effort. Without commander's intent at echelon, decentralization becomes diffusion.",
        "MCDP-4 makes this explicit — sustainment is the fourth maneuver factor and the one most often surrendered to a contractor binder.",
    ],
    "developing": [
        "I think centralized control can sometimes be useful when the stakes are high. Like in a TIC.",
        "Agree with the reading. We need to trust subordinates more, but we also need standards.",
        "MCDP-1 says we should use mission tactics. I think that means letting people figure it out.",
        "Re Class IX: the supply chain is complicated, especially when GCSS-MC goes down.",
    ],
    "needs_remediation": [
        "I agree with the reading.",
        "Good points above.",
        "I will read more about this.",
        "Agree, defensive is important too.",
    ],
    "quiet_thinker": [
        "Counter to the prevailing read: MCDP-1 is descriptive of how Marines fight, not prescriptive of how every commander must lead. The variance is the point.",
        "On Class IX: the pacing item is rarely the part. It is the demand-signal latency between the user and GCSS-MC. Fix the latency, the part flows.",
        "Reading the AAR linked above against MCDP-4: the 'logistics failure' is a planning failure that emerged late. The maneuver plan never had a sustainment phase.",
        "Quiet observation: every cohort's strongest defense of decentralization is also their weakest defense of accountability. We owe the next class both.",
    ],
}


def _word_count(s: str) -> int:
    return len(s.split())


def _depth_of_post(body: str) -> str:
    wc = _word_count(body)
    cite = "MCDP" in body or "MCWP" in body or "MCRP" in body or "GCSS-MC" in body or "Boyd" in body or "AAR" in body
    if wc > 38 and cite:
        return "synthesis"
    if wc > 25 and cite:
        return "analysis"
    if wc > 15:
        return "application"
    return "recall"


def _city_pick(rng: random.Random) -> str:
    return rng.choice(["Fallujah", "Helmand", "29 Palms", "Camp Pendleton", "Twentynine Palms", "Bridgeport"])


def generate_forum_posts() -> list[dict]:
    posts: list[dict] = []
    for course in COURSES:
        for student in course["students"]:
            bank = POST_BANK.get(student["profile"], POST_BANK["developing"])
            for i in range(4):
                body = bank[i % len(bank)].format(city=_city_pick(RNG))
                ts = (datetime(2026, 4, 1, tzinfo=timezone.utc)
                      + timedelta(days=i * 3, hours=RNG.randint(8, 20)))
                posts.append({
                    "course_id": course["course_id"],
                    "student_id": student["student_id"],
                    "thread": FORUM_THREADS[i % len(FORUM_THREADS)],
                    "body": body,
                    "word_count": _word_count(body),
                    "depth": _depth_of_post(body),
                    "ts": ts.isoformat(),
                })
    return posts


# Competency timeseries — weekly score 0-5 over 6 weeks
def generate_competency_ts() -> list[dict]:
    ts: list[dict] = []
    base_lookup = {
        "high_performer": 4.0,
        "quiet_thinker": 3.6,
        "developing": 2.8,
        "needs_remediation": 1.9,
    }
    delta_lookup = {
        "high_performer": 0.10,
        "quiet_thinker": 0.06,
        "developing": 0.05,
        "needs_remediation": -0.04,
    }
    for course in COURSES:
        for s in course["students"]:
            base = base_lookup.get(s["profile"], 2.5)
            d = delta_lookup.get(s["profile"], 0.04)
            for week in range(6):
                for comp in ("critical_thinking", "communication",
                             "doctrinal_knowledge", "problem_solving"):
                    score = max(0.0, min(5.0,
                        base + d * week + RNG.uniform(-0.25, 0.25)
                    ))
                    ts.append({
                        "course_id": course["course_id"],
                        "student_id": s["student_id"],
                        "week": week,
                        "competency": comp,
                        "score": round(score, 2),
                    })
    return ts


# ─────────────────────────────────────────────────────────────────────────────
# Pre-computed Schoolhouse Intelligence Briefs (cache-first)
# ─────────────────────────────────────────────────────────────────────────────
def _baseline_brief(course: dict, persona: str = "instructor") -> str:
    """Deterministic baseline brief for cache + fallback. Markdown."""
    cid = course["course_id"]
    name = course["name"]
    tr = course["tr_manual_short"]
    instr = course["instructor"]
    students = course["students"]
    # naive top performer / at-risk pick from profile
    top = next((s for s in students if s["profile"] in ("high_performer",)), students[0])
    at_risk = [s for s in students if s["profile"] == "needs_remediation"]
    quiet = [s for s in students if s["profile"] == "quiet_thinker"]

    if persona == "student":
        # Adaptive study plan
        return (
            f"# Adaptive Study Plan — {name}\n\n"
            f"_Anchored to {tr}._\n\n"
            f"## BLUF\n"
            f"You are tracking competent on Doctrinal Knowledge but weak on Critical Thinking. "
            f"Three drills below close that gap before {course['assignment']['title']} is due.\n\n"
            f"## Tonight (45 min)\n"
            f"- Re-read MCDP-1 Ch. 4 and write a 200-word counter-argument to your last forum post. "
            f"Cite one historical AAR.\n"
            f"- Run egocentric drill **scn_05 (Hallway Cross)** — narrate your sequence aloud before acting.\n\n"
            f"## This Week (2 hr total)\n"
            f"- Pair with {top['name']} on the Tactical Decision Game. They are scoring 4.3 on Critical Thinking.\n"
            f"- Outline your {course['assignment']['title']} against the 5 rubric criteria — one paragraph each.\n\n"
            f"## Schoolhouse Read-back\n"
            f"- Your competency trend (6 wks): Critical Thinking +0.4, Communication +0.2, Doctrinal +0.5, Problem Solving +0.3.\n\n"
            f"_UNCLASSIFIED // FOR TRAINING USE — Military Education Records governed by the Privacy Act "
            f"of 1974 (5 U.S.C. § 552a) and DoDI 1322.35._"
        )
    if persona == "co":
        # School CO health dashboard
        return (
            f"# Schoolhouse Health Brief — {course['schoolhouse']}\n\n"
            f"_Anchored to {tr}._\n\n"
            f"## BLUF\n"
            f"- Course **{name}** running with {len(students)} students; instructor **{instr}**.\n"
            f"- Cohort competency: **GREEN on Doctrinal**, **AMBER on Critical Thinking**, "
            f"**{len(at_risk)} student(s) flagged for intervention**.\n"
            f"- Instructor effectiveness signal: **EFFECTIVE** (consistent rubric alignment, intervention "
            f"recommendations precede grade slip by ~4 days).\n\n"
            f"## Curriculum Effectiveness\n"
            f"- Highest landing: written {course['assignment']['title']} (mean 86, spread 14).\n"
            f"- Lowest landing: forum thread 'When does centralized control hurt initiative?' "
            f"— recall-level posts cluster at {len(at_risk)*33}% of cohort.\n\n"
            f"## Recommended CO Moves\n"
            f"1. Authorize a 1:1 remediation block for {', '.join(s['name'] for s in at_risk) or 'flagged students'}.\n"
            f"2. Reissue MCDP-1 Ch. 4 reading with a counter-argument prompt — current prompt rewards agreement.\n"
            f"3. Cross-pollinate with sister schoolhouse cohort — {top['name']} can present to a peer cohort.\n\n"
            f"## Schoolhouse Risk\n"
            f"- T&R event coverage on {course['tr_event_examples'][0]} is at 80% — close-out by EOW.\n\n"
            f"_UNCLASSIFIED // FOR OFFICIAL USE — Military Education Records governed by the Privacy Act "
            f"of 1974 (5 U.S.C. § 552a) and DoDI 1322.35._"
        )
    # default: instructor cohort intervention list
    intv_lines = "\n".join(
        f"- **{s['name']}** ({s['student_id']}, {s['rank']}) — recommended action: "
        f"1:1 OPORD writing drill + re-issue MCDP-1 reading."
        for s in at_risk
    ) or "- _No students currently flagged for intervention._"
    quiet_lines = "\n".join(
        f"- **{s['name']}** ({s['student_id']}) — analysis-tier posts; surface in seminar."
        for s in quiet
    )
    return (
        f"# Schoolhouse Intelligence Brief — {name}\n\n"
        f"_Anchored to {tr}._\n_Schoolhouse: {course['schoolhouse']}._\n\n"
        f"## PARA 1 — BLUF\n"
        f"Cohort of {len(students)} on {course['code']}. Cohort competency map shows strength in "
        f"**Doctrinal Knowledge (3.9/5)**, weakness in **Critical Thinking (2.8/5)**. "
        f"{len(at_risk)} student(s) require instructor intervention before the {course['assignment']['title']} "
        f"is due. Instructor effectiveness signal: **EFFECTIVE**.\n\n"
        f"## PARA 2 — TOP PERFORMER\n"
        f"**{top['name']}** ({top['student_id']}, {top['rank']}) — synthesis-level forum work, "
        f"consistent 4+ rubric across all four competencies. Pull as a peer-coach for the "
        f"intervention cohort.\n\n"
        f"## PARA 3 — STUDENTS AT RISK\n"
        f"{intv_lines}\n\n"
        f"## PARA 4 — CURRICULUM EFFECTIVENESS\n"
        f"- Highest-landing: '{course['assignment']['title']}' — rubric criterion C1 (Doctrinal grounding) "
        f"is the most consistently scored.\n"
        f"- Lowest-landing: forum thread on centralized control — most posts stay at recall depth. "
        f"Re-prompt to require a counter-argument and one historical AAR cite.\n\n"
        f"## PARA 5 — RECOMMENDED INSTRUCTOR MOVES\n"
        f"1. Re-prompt the centralized-control thread (counter-argument required).\n"
        f"2. Pair {top['name']} with at-risk students on the next Tactical Decision Game.\n"
        f"3. Quiet thinkers to surface:\n{quiet_lines or '   _(none in this cohort)_'}\n"
        f"4. T&R coverage on {course['tr_event_examples'][0]} → close-out by EOW.\n\n"
        f"## COMPETENCY MAP — COHORT\n"
        f"| Student | Critical Thinking | Communication | Doctrinal | Problem Solving |\n"
        f"|---|---|---|---|---|\n"
        + "\n".join(
            f"| {s['name']} | "
            f"{('4.3' if s['profile'] == 'high_performer' else '3.7' if s['profile']=='quiet_thinker' else '2.5' if s['profile']=='developing' else '1.7')} | "
            f"{('4.1' if s['profile'] == 'high_performer' else '3.5' if s['profile']=='quiet_thinker' else '2.8' if s['profile']=='developing' else '1.9')} | "
            f"{('4.5' if s['profile'] == 'high_performer' else '3.8' if s['profile']=='quiet_thinker' else '3.2' if s['profile']=='developing' else '2.4')} | "
            f"{('4.2' if s['profile'] == 'high_performer' else '3.6' if s['profile']=='quiet_thinker' else '2.9' if s['profile']=='developing' else '2.0')} |"
            for s in students
        )
        + f"\n\n_UNCLASSIFIED // FOR OFFICIAL USE — Military Education Records governed by the Privacy Act "
          f"of 1974 (5 U.S.C. § 552a) and DoDI 1322.35._"
    )


def precompute_briefs() -> dict:
    """Three personas × three courses pre-cached so demo never waits on LLM."""
    out: dict = {}
    for course in COURSES:
        cid = course["course_id"]
        out[cid] = {}
        for persona in ("instructor", "student", "co"):
            out[cid][persona] = {
                "brief": _baseline_brief(course, persona=persona),
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "source": "baseline_cache",
            }
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Audit chain genesis
# ─────────────────────────────────────────────────────────────────────────────
def _sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def write_audit_genesis() -> None:
    """Append a genesis entry per course if the audit log is empty."""
    if AUDIT_LOG.exists() and AUDIT_LOG.stat().st_size > 0:
        return
    prev = "0" * 64
    with AUDIT_LOG.open("w") as f:
        for course in COURSES:
            body = {
                "event": "GENESIS",
                "course_id": course["course_id"],
                "course_name": course["name"],
                "tr_manual": course["tr_manual_short"],
                "schoolhouse": course["schoolhouse"],
                "originator": "SCHOOLHOUSE — synthetic seed",
                "prev_hash": prev,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            }
            body["entry_hash"] = _sha256_text(
                json.dumps(body, sort_keys=True, default=str)
            )
            f.write(json.dumps(body, default=str) + "\n")
            prev = body["entry_hash"]


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def main() -> None:
    (ROOT / "courses.json").write_text(json.dumps(COURSES, indent=2))
    (ROOT / "scenes_meta.json").write_text(json.dumps(SCENES, indent=2))
    (ROOT / "visual_id_meta.json").write_text(json.dumps(VISUAL_ID, indent=2))
    (ROOT / "personas.json").write_text(json.dumps(PERSONAS, indent=2))

    posts = generate_forum_posts()
    with (ROOT / "forum_posts.jsonl").open("w") as f:
        for p in posts:
            f.write(json.dumps(p) + "\n")

    ts = generate_competency_ts()
    with (ROOT / "competency_ts.jsonl").open("w") as f:
        for r in ts:
            f.write(json.dumps(r) + "\n")

    cached = precompute_briefs()
    (ROOT / "cached_briefs.json").write_text(json.dumps(cached, indent=2))

    write_audit_genesis()

    print(f"Courses: {len(COURSES)}")
    print(f"Students: {sum(len(c['students']) for c in COURSES)}")
    print(f"Forum posts: {len(posts)}")
    print(f"Competency timeseries: {len(ts)}")
    print(f"Scenes: {len(SCENES)}")
    print(f"Visual ID: {len(VISUAL_ID)} ({sum(1 for v in VISUAL_ID if v['image'])} with images)")
    print(f"Personas: {len(PERSONAS)}")
    print(f"Cached briefs: {sum(len(v) for v in cached.values())} ({len(COURSES)} courses × 3 personas)")


if __name__ == "__main__":
    main()
