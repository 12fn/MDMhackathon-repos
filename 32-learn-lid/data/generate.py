"""LEARN synthetic Moodle-shape course generator.

Produces (all under data/):
  course.json         - course metadata, 18 students, 6 assignments, 30 forum threads
  forum_posts.jsonl   - 200 forum posts of varied cognitive depth
  assignments.jsonl   - 100 submissions (excerpts + grades + late flag)
  cached_briefs.json  - 3 pre-computed cohort scenarios for cache-first demo

Seeded random.Random(1776) for full reproducibility.
NEVER use real Marine training data — every name and post is synthetic.

Real-data swap path: see data/load_real.py.
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# --- Cohort scenarios (3 pre-computable for cache-first hero brief) ----------
COURSE_NAME = "Infantry Officer Course - Bravo Cohort 26-1"
COURSE_VARIANTS = [
    {"id": "ioc_b261",   "name": "Infantry Officer Course - Bravo Cohort 26-1",       "code": "IOC-B26-1"},
    {"id": "pmos_0311",  "name": "PMOS 0311 Pipeline - Class 26-04",                  "code": "PMOS-0311-26-04"},
    {"id": "sgts_pme",   "name": "Sergeants School / Squad Leader PME - Section 12",  "code": "SGTS-PME-12"},
]

ASSIGNMENTS = [
    {"id": "A1", "name": "Doctrinal Reading Quiz - MCDP 1 Warfighting",  "rubric": "doctrinal_knowledge"},
    {"id": "A2", "name": "Tactical Decision Game - Defensive Operations",  "rubric": "problem_solving"},
    {"id": "A3", "name": "Written Order - 5-paragraph OPORD",  "rubric": "communication"},
    {"id": "A4", "name": "AAR - Live-Fire Squad Attack",  "rubric": "critical_thinking"},
    {"id": "A5", "name": "Case Study - Force on Force Lessons Learned",  "rubric": "critical_thinking"},
    {"id": "A6", "name": "Capstone Brief - Combined Arms Plan",  "rubric": "synthesis"},
]

FORUM_THREADS = [
    "Discussion: When does centralized control hurt initiative?",
    "Critique: Defensive vs offensive mindset in MCDP-1",
    "Apply MCDP-5 Planning to a 72-hour LZ seizure",
    "Lessons learned: 1st Marines Fallujah AAR readings",
    "Compare: Ridgway's leadership in Korea vs current doctrine",
    "Decision-making under uncertainty: Boyd's OODA in modern conflict",
    "How would you brief a non-doctrinal commander's intent?",
    "Case study: Failed amphibious raid - what went wrong?",
    "Apply MCWP 3-01 to a contested LZ scenario",
    "Discussion: Mission-type orders in DDIL environments",
    "Tactical patience vs decisive action - when to which?",
    "Reading reaction: Shattered Sword - intelligence assumptions",
    "Defensive in depth - terrain analysis exercise",
    "Combined arms integration at company level",
    "Logistics rebellion: when sustainment dictates the plan",
    "Casualty evacuation - planning factors discussion",
    "Civilian considerations under MCRP 3-03A.1",
    "Adversary EW exploitation - hardening RTOs",
    "Heat casualty mitigation - leader actions in tropical climates",
    "AAR best-practice - the brutally honest version",
    "Mentorship: how do you develop initiative in juniors?",
    "Critique: Boyd's OODA loop - is it overstated?",
    "MCDP-2 Intelligence - center of gravity practical",
    "Patrol base operations - security plan walkthrough",
    "Squad in the attack - reverse-slope considerations",
    "MOUT planning - synchronization with the breach",
    "Reception, staging, onward movement, and integration",
    "Force protection at port-of-debark",
    "Air-ground integration - CAS request brief",
    "Rules of engagement - decision tree for the squad leader",
]

STUDENT_FIRST_NAMES = ["Alvarez", "Brennan", "Chen", "Diaz", "Edwards", "Ferguson",
                      "Gomez", "Hayes", "Iverson", "Johnson", "Kim", "Lopez",
                      "Martinez", "Nguyen", "O'Connor", "Patel", "Quinn", "Romero"]
STUDENT_RANKS = ["Capt", "1stLt", "2ndLt", "GySgt", "SSgt", "Sgt"]

# Cognitive depth tiers (Bloom's). Each student picks a profile that biases
# their post depths over the cohort.
DEPTH_PROFILES = {
    "high_performer":   {"recall": 0.05, "application": 0.15, "analysis": 0.30, "synthesis": 0.30, "evaluation": 0.20},
    "solid":            {"recall": 0.15, "application": 0.30, "analysis": 0.30, "synthesis": 0.15, "evaluation": 0.10},
    "developing":       {"recall": 0.30, "application": 0.35, "analysis": 0.20, "synthesis": 0.10, "evaluation": 0.05},
    "needs_remediation":{"recall": 0.55, "application": 0.30, "analysis": 0.10, "synthesis": 0.04, "evaluation": 0.01},
    "rising_star":      {"recall": 0.05, "application": 0.20, "analysis": 0.30, "synthesis": 0.30, "evaluation": 0.15},
    "quiet_thinker":    {"recall": 0.10, "application": 0.20, "analysis": 0.35, "synthesis": 0.25, "evaluation": 0.10},
}

# Post bodies per cognitive depth - realistic-but-synthetic Marine voice.
POST_BODIES = {
    "recall": [
        "MCDP-1 says maneuver warfare is generating tempo. Tempo wins.",
        "Per the reading, mission-type orders push decisions down. Got it.",
        "Boyd's OODA is observe, orient, decide, act. Repeat faster than the enemy.",
        "Centralized control with decentralized execution. That's the key line.",
        "MCDP-5 Planning describes single-battle concept. Cited for the test.",
        "Friction is what makes the simple difficult. Clausewitz called that.",
        "The 5-paragraph OPORD is SMEAC. Situation, mission, execution, admin, command.",
        "Combined arms: complementary, not just additive. Doctrinal definition.",
    ],
    "application": [
        "Applying mission-type orders to our LZ scenario, the sub-element leaders need explicit intent or they'll wait for permission. We saw that in last week's lab.",
        "If we apply OODA inside a contested LZ, the orient step is what kills us when EW degrades comms. Pre-briefed contingencies matter more than re-orienting live.",
        "OPORD para 3 needs a clear DP for the breach. If I write it without a decision criterion, the squad leader stalls.",
        "I'd structure the company defensive belt with the strongpoint forward-right, weighted to the avenue of approach, similar to the MCWP 3-01 example.",
        "For the casualty evac plan, I'd push the CCP forward and pre-stage litters with 2nd squad, since they have the shortest pull.",
    ],
    "analysis": [
        "The reading's critique of attrition warfare assumes a peer adversary with comparable mass. Against an irregular force, attrition can degrade the population's tolerance faster than maneuver. That nuance isn't in MCDP-1.",
        "Boyd's OODA loop is sound but the loop assumes our orient step is faster than our adversary's act step. In an EW-saturated environment, we may orient slower, so the doctrinal answer becomes pre-rehearsed branches, not faster decision cycles.",
        "Comparing Ridgway's reorganization of 8th Army to today's distributed operations: he succeeded by re-centering on infantry fundamentals. Today we're decentralizing further but losing those same fundamentals to tech dependence.",
        "The Fallujah AAR shows synchronization failed at the company-battalion seam. Not at the squad. That's a planning-staff problem, not a small-unit-leader problem, and we should be careful not to learn the wrong lesson.",
        "The case study's failure point was the assumption that the adversary would react like a regular force. A red-team step in COA development would have surfaced this.",
    ],
    "synthesis": [
        "Synthesizing MCDP-1's tempo argument with MCDP-2's intelligence framework: tempo isn't just speed, it's relative information advantage. We can generate tempo by degrading their intel cycle, not just accelerating ours. That reframes the EW conversation entirely.",
        "If we combine mission-type orders with the AAR readings on Fallujah, the implication is that we should brief intent two echelons down by default — not as an exception. Our SOP does the opposite.",
        "Boyd's OODA + the casualty evac problem: the limiting factor isn't movement, it's decision authority. Pre-delegating CASEVAC launch to the squad leader collapses the loop. That's a doctrinal AND a policy fix.",
        "I'd combine the defensive-in-depth reading with the air-ground integration discussion: depth without overhead awareness is just sequential ambushes. We have to fold CAS into the depth calculation.",
        "The MOUT readings + the breach synchronization problem suggests we restructure our planning checklist around the breach as the limiting node, with everything else timed off it.",
    ],
    "evaluation": [
        "I disagree with the centralized-control critique in our reading. In a multi-domain fight where ISR feeds aren't symmetrical, the higher echelon may genuinely have a better picture for 30-60 minutes at a time. The doctrine's 'decentralize by default' becomes a liability if we treat it as a rule, not a judgment.",
        "Evaluating Ridgway against modern distributed-ops thinking: I'd say his centralizing move worked because the small-unit leadership was hollow. If your small-unit leadership is solid, the same move would suppress initiative. The lesson isn't 'centralize or decentralize' — it's 'diagnose first.'",
        "Critiquing our own CASEVAC plan: the plan optimizes for time-to-Role-2. But the metric we should optimize for is time-to-definitive-care. Those are different problems and our plan picks the wrong one.",
        "I'd argue the FAILED amphibious raid case study is misread by the field. The proximate cause was synchronization, but the root cause was cultural: the staff didn't trust the company commander to adapt. No process fix solves that.",
        "Our current breach SOP optimizes for casualty reduction at the obstacle, but it does so by forfeiting tempo at the objective. That trade is wrong against a peer adversary; we should re-balance.",
    ],
}

ASSIGNMENT_EXCERPTS = {
    "doctrinal_knowledge": [
        ("MCDP-1 defines maneuver warfare as a warfighting philosophy that seeks to shatter the enemy's cohesion through a series of rapid, violent, and unexpected actions which create a turbulent and rapidly deteriorating situation with which he cannot cope. The five characteristics are tempo, focus, surprise, boldness, and combined arms.", 92),
        ("Maneuver warfare is about moving fast and confusing the enemy. Tempo and surprise are key. From MCDP-1.", 71),
        ("Per MCDP-1, the maneuverist approach attempts to circumvent the enemy's strength to strike at his critical vulnerability. This integrates with MCDP-2's intelligence framework — we can't strike a vulnerability we haven't identified — and with MCDP-5's planning construct, which sequences our actions to mass effects at that vulnerability.", 96),
        ("Maneuver warfare = shatter cohesion. Combined arms is one of the five characteristics.", 64),
    ],
    "problem_solving": [
        ("DEFENSE COA: Position 1st platoon strongpoint vic Hill 348 weighted to NE avenue of approach. 2nd platoon main effort, mobile reserve vic checkpoint 12 prepared to counterattack along Route Blue. 3rd platoon screening line PL Red. Engagement area Tiger trigger at PL Green; mortars priority of fires to MEF-vic AA1. CASEVAC pull to CCP Bravo via Route White, Role-2 at FOB Hawk. DP1: shift fires if enemy reaches PL Green within 20 minutes of contact.", 89),
        ("Defensive plan: dig in along the ridge, mortars in support, reserve on the road. CASEVAC by truck. DP not specified.", 58),
        ("Defensive plan develops three engagement areas to channelize enemy advance into EA Tiger, where we mass mortars and direct fires. Reserve sited to counter-attack along either Route Blue (NE penetration) or Route Gold (E penetration), with explicit decision criteria for each. Contingency for EW degradation: pre-briefed signal flares as alternate trigger.", 94),
    ],
    "communication": [
        ("ORIENTATION: Friendly forces conducting offensive ops vic NTC Box 6. ENEMY: PL-equivalent OPFOR mech infantry, equipped T-72s, anticipated COA defense in sector. MISSION: Bravo Co destroys OPFOR forward security element NLT 0500 IOT enable BN main effort attack. EXECUTION: Concept of ops -- envelopment, main effort 2nd Plt north flank... [continued para 3, 4, 5 with sub-tasks per platoon]", 91),
        ("Order: We attack at 0500. 2nd Plt is main effort. 1st Plt supports by fire. 3rd Plt is reserve.", 62),
        ("OPORD includes complete SMEAC, with explicit task and purpose at the platoon level, sync matrix attached, comm plan with primary/alternate/contingency/emergency, and a clear decisive point. CCIR list nests with battalion's.", 95),
    ],
    "critical_thinking": [
        ("AAR: We achieved the objective but lost 4 simulated KIA at the breach. Root cause was over-reliance on the suppression element to fix the enemy MG team — when their grenadier missed first round, the suppression element was exposed for 6 additional seconds. Recommendation is to brief and rehearse the alternate suppression trigger (M203 follow-up grenade) as a primary, not a contingency.", 93),
        ("AAR: We took the objective. There were some issues with the breach. Need to do better next time.", 55),
        ("AAR: Achieved actions on the objective at T+0:42 (planned T+0:35). The 7-minute slip is attributable to a cascading delay at the breach (3 min) and confusion at the LOA marking (4 min). Root cause analysis: the breach delay was a rehearsal gap, fixable with one extra dry-iteration. The LOA confusion was a doctrinal-training gap — our default LOA marking SOP doesn't survive contested-environment EW degradation. Recommend two specific changes to BN SOP.", 96),
        ("AAR: We did the attack. Comms broke. Recommend better comms.", 48),
    ],
    "synthesis": [
        ("CAPSTONE BRIEF: Combined arms plan integrates ground maneuver (Co A main effort), CAS (priority of fires phase 2-3), arty (DPICM in EA Tiger phase 2 only, FASCAM phase 3), and EW (jam OPFOR coordination net t-15 through t+30). Branch plans for adversary preemption (collapse to defense in depth using EA Lion) and for sustainment shortfall (90-min logistics pause at PL Red). Risk decision points clearly nested with BN commander's intent.", 95),
        ("Capstone: We attack with all our weapons at once. Air, arty, ground. Hope it works.", 45),
        ("Capstone synthesizes maneuver, fires, EW, and sustainment into a single sync matrix. Decisive point identified explicitly (seizure of OBJ FALCON). Two branches and one sequel pre-planned. Logistics tail calculated to 72 hours. ROE walkthrough included for civilian-presence COA.", 93),
    ],
}


# --- Helpers -----------------------------------------------------------------

def _weighted_choice(rng: random.Random, weights: dict[str, float]) -> str:
    keys = list(weights.keys())
    vals = [weights[k] for k in keys]
    return rng.choices(keys, weights=vals, k=1)[0]


def _build_students(rng: random.Random, n: int = 18) -> list[dict]:
    """Assign each student a depth profile so the heatmap is interestingly varied."""
    profiles = (
        ["high_performer"] * 3
        + ["solid"] * 5
        + ["developing"] * 4
        + ["needs_remediation"] * 2
        + ["rising_star"] * 2
        + ["quiet_thinker"] * 2
    )
    rng.shuffle(profiles)
    students: list[dict] = []
    for i in range(n):
        last = STUDENT_FIRST_NAMES[i % len(STUDENT_FIRST_NAMES)]
        rank = STUDENT_RANKS[i % len(STUDENT_RANKS)]
        students.append({
            "student_id": f"S{i+1:02d}",
            "name": f"{rank} {last}",
            "rank": rank,
            "profile": profiles[i],
            "edipi_synth": f"{1000000000 + rng.randint(0, 999999999)}",  # synthetic EDIPI-shaped only
        })
    return students


# --- Main generators ---------------------------------------------------------

def generate(course_variant_idx: int = 0, *, seed: int = 1776) -> dict:
    rng = random.Random(seed + course_variant_idx)
    course = COURSE_VARIANTS[course_variant_idx]
    students = _build_students(rng)

    # Forum posts: 200 across 30 threads, distributed roughly per profile activity
    posts = []
    base_t = datetime(2026, 4, 1, 8, 0, 0, tzinfo=timezone.utc)
    posts_per_student_target = max(1, 200 // len(students))
    for s in students:
        # rising_star and high_performer post more; needs_remediation posts less
        post_count = posts_per_student_target + {
            "high_performer": 4, "rising_star": 5, "quiet_thinker": -2,
            "solid": 2, "developing": 0, "needs_remediation": -3,
        }[s["profile"]]
        post_count = max(2, post_count)
        for _ in range(post_count):
            depth = _weighted_choice(rng, DEPTH_PROFILES[s["profile"]])
            thread = rng.choice(FORUM_THREADS)
            body = rng.choice(POST_BODIES[depth])
            posts.append({
                "post_id": f"P{len(posts)+1:04d}",
                "student_id": s["student_id"],
                "thread": thread,
                "depth": depth,
                "body": body,
                "ts": (base_t + timedelta(hours=rng.randint(0, 28 * 24))).isoformat(),
                "word_count": len(body.split()),
            })
    # cap to 200
    rng.shuffle(posts)
    posts = posts[:200]

    # Assignments: 100 submissions across 6 assignments x 18 students (some skip)
    submissions = []
    for s in students:
        for a in ASSIGNMENTS:
            # 95% submit, less for needs_remediation
            submit_p = {"needs_remediation": 0.65}.get(s["profile"], 0.95)
            if rng.random() > submit_p:
                continue
            rubric = a["rubric"]
            # Bias submission quality by profile
            if s["profile"] in ("high_performer", "rising_star"):
                pool = ASSIGNMENT_EXCERPTS.get(rubric, ASSIGNMENT_EXCERPTS["critical_thinking"])
                # pick top-quality (high-grade) excerpts
                excerpt, grade = max(pool, key=lambda x: x[1])
                grade = grade - rng.randint(0, 3)
            elif s["profile"] in ("solid",):
                pool = ASSIGNMENT_EXCERPTS.get(rubric, ASSIGNMENT_EXCERPTS["critical_thinking"])
                excerpt, grade = sorted(pool, key=lambda x: -x[1])[1]
                grade = grade - rng.randint(0, 6)
            elif s["profile"] in ("quiet_thinker", "developing"):
                pool = ASSIGNMENT_EXCERPTS.get(rubric, ASSIGNMENT_EXCERPTS["critical_thinking"])
                excerpt, grade = rng.choice(pool)
            else:  # needs_remediation
                pool = ASSIGNMENT_EXCERPTS.get(rubric, ASSIGNMENT_EXCERPTS["critical_thinking"])
                excerpt, grade = min(pool, key=lambda x: x[1])
                grade = max(35, grade - rng.randint(0, 8))
            submissions.append({
                "submission_id": f"SUB{len(submissions)+1:04d}",
                "student_id": s["student_id"],
                "assignment_id": a["id"],
                "assignment_name": a["name"],
                "rubric_axis": rubric,
                "excerpt": excerpt,
                "grade": int(grade),
                "late": rng.random() < (0.4 if s["profile"] == "needs_remediation" else 0.08),
                "submitted_at": (base_t + timedelta(days=rng.randint(0, 28),
                                                    hours=rng.randint(0, 23))).isoformat(),
            })
        if len(submissions) >= 100:
            break
    submissions = submissions[:100]

    return {
        "course": course,
        "students": students,
        "assignments": ASSIGNMENTS,
        "forum_threads": FORUM_THREADS,
        "forum_posts": posts,
        "submissions": submissions,
    }


# --- Heuristic baseline (no LLM) — keeps the heatmap populated instantly ----

DEPTH_TO_SCORE = {
    "recall": 1.0, "application": 2.5, "analysis": 3.5,
    "synthesis": 4.5, "evaluation": 5.0,
}


def baseline_per_student(course: dict) -> dict[str, dict]:
    """Deterministic competency rubric per student, derived from the synth corpus.

    Returns: {student_id: {competency_evidence: {...}, cognitive_depth_observed: str,
                           growth_indicators, remediation_recommendations,
                           instructor_intervention_needed, confidence, _source}}
    """
    by_student: dict[str, dict] = {s["student_id"]: {"posts": [], "subs": []}
                                   for s in course["students"]}
    for p in course["forum_posts"]:
        by_student.setdefault(p["student_id"], {"posts": [], "subs": []})["posts"].append(p)
    for s in course["submissions"]:
        by_student.setdefault(s["student_id"], {"posts": [], "subs": []})["subs"].append(s)

    out: dict[str, dict] = {}
    for s in course["students"]:
        sid = s["student_id"]
        d = by_student[sid]

        # Cognitive depth = mean of depths in posts mapped to score
        if d["posts"]:
            depth_scores = [DEPTH_TO_SCORE[p["depth"]] for p in d["posts"]]
            mean_depth = sum(depth_scores) / len(depth_scores)
            # Threshold to a single observed band
            if mean_depth >= 4.5:
                depth_label = "evaluation"
            elif mean_depth >= 3.8:
                depth_label = "synthesis"
            elif mean_depth >= 3.0:
                depth_label = "analysis"
            elif mean_depth >= 2.0:
                depth_label = "application"
            else:
                depth_label = "recall"
        else:
            mean_depth = 1.5
            depth_label = "recall"

        # Per-competency baseline
        # critical_thinking: weighted on analysis/eval posts + critical_thinking-rubric grades
        ct_posts = [p for p in d["posts"] if p["depth"] in ("analysis", "synthesis", "evaluation")]
        ct_subs = [s for s in d["subs"] if s["rubric_axis"] in ("critical_thinking", "synthesis")]
        ct_score = min(5, (len(ct_posts) / max(1, len(d["posts"]))) * 5
                       + (sum(x["grade"] for x in ct_subs) / max(1, 100 * len(ct_subs))) * 1.0)

        # communication: post word_count + communication-rubric grades
        comm_words = sum(p["word_count"] for p in d["posts"])
        comm_subs = [s for s in d["subs"] if s["rubric_axis"] == "communication"]
        comm_score = min(5, (comm_words / 400.0)
                         + (sum(x["grade"] for x in comm_subs) / max(1, 100 * len(comm_subs))) * 2.0)

        # doctrinal_knowledge: doctrinal-rubric grades + recall+application post share
        doct_subs = [s for s in d["subs"] if s["rubric_axis"] == "doctrinal_knowledge"]
        doct_share = sum(1 for p in d["posts"] if p["depth"] in ("recall", "application", "analysis"))
        doct_share = doct_share / max(1, len(d["posts"]))
        doct_score = min(5, (sum(x["grade"] for x in doct_subs) / max(1, 100 * len(doct_subs))) * 3.5
                         + doct_share * 1.5)

        # problem_solving: problem-solving-rubric grades + application+synthesis post share
        ps_subs = [s for s in d["subs"] if s["rubric_axis"] == "problem_solving"]
        ps_share = sum(1 for p in d["posts"] if p["depth"] in ("application", "synthesis"))
        ps_share = ps_share / max(1, len(d["posts"]))
        ps_score = min(5, (sum(x["grade"] for x in ps_subs) / max(1, 100 * len(ps_subs))) * 3.5
                       + ps_share * 1.5)

        comp = {
            "critical_thinking":   round(max(0.0, ct_score), 2),
            "communication":       round(max(0.0, comm_score), 2),
            "doctrinal_knowledge": round(max(0.0, doct_score), 2),
            "problem_solving":     round(max(0.0, ps_score), 2),
        }

        # growth indicators: improvement of grades over time
        sub_sorted = sorted(d["subs"], key=lambda x: x["submitted_at"])
        grades_seq = [x["grade"] for x in sub_sorted]
        growth: list[str] = []
        if len(grades_seq) >= 3 and grades_seq[-1] > grades_seq[0] + 5:
            growth.append(f"Grade trajectory improving: {grades_seq[0]} -> {grades_seq[-1]}")
        if depth_label in ("analysis", "synthesis", "evaluation"):
            growth.append(f"Cognitive depth at {depth_label} consistently across forum work")
        if comp["critical_thinking"] >= 4.0:
            growth.append("Critical thinking strong; ready for more complex tactical decision games")
        if not growth:
            growth.append("Limited evidence in current artifacts; needs more posts/submissions")

        # remediation recommendations
        remed: list[str] = []
        if comp["doctrinal_knowledge"] < 2.5:
            remed.append("Doctrinal recall weak: assign focused MCDP-1/2/5 reading checks")
        if comp["communication"] < 2.5:
            remed.append("Communication weak: 1:1 OPORD writing drill with instructor review")
        if comp["critical_thinking"] < 2.0:
            remed.append("Critical thinking weak: pair with peer mentor on AAR write-ups")
        if comp["problem_solving"] < 2.0:
            remed.append("Problem solving weak: additional repetitions on tactical decision games")
        if all(v >= 4.0 for v in comp.values()):
            remed.append("Performing above standard: consider stretch assignment or peer-teach role")
        if not remed:
            remed.append("On track. Continue current sequence; monitor capstone performance.")

        # intervention flag
        intervention = (
            sum(1 for v in comp.values() if v < 2.5) >= 2
            or sum(1 for x in d["subs"] if x["late"]) >= 2
            or len(d["posts"]) <= 2
        )

        # confidence: more artifacts = higher confidence
        artifact_count = len(d["posts"]) + len(d["subs"])
        confidence = round(min(0.95, 0.4 + 0.04 * artifact_count), 2)

        out[sid] = {
            "student_id": sid,
            "competency_evidence": comp,
            "cognitive_depth_observed": depth_label,
            "growth_indicators": growth,
            "remediation_recommendations": remed,
            "instructor_intervention_needed": intervention,
            "confidence": confidence,
            "_source": "baseline",
            "_artifact_count": artifact_count,
        }
    return out


def baseline_cohort(per_student: dict[str, dict], course: dict) -> dict:
    """Cohort-level deterministic roll-up — feeds the brief generator."""
    students = course["students"]
    avg = {k: 0.0 for k in ("critical_thinking", "communication",
                            "doctrinal_knowledge", "problem_solving")}
    for sid, ev in per_student.items():
        for k in avg:
            avg[k] += ev["competency_evidence"][k]
    for k in avg:
        avg[k] = round(avg[k] / max(1, len(students)), 2)

    intervention = [sid for sid, ev in per_student.items()
                    if ev["instructor_intervention_needed"]]
    top = sorted(per_student.items(),
                 key=lambda kv: -sum(kv[1]["competency_evidence"].values()))[:3]
    top_ids = [t[0] for t in top]

    # Assignment effectiveness — mean grade per assignment
    by_assn: dict[str, list[int]] = {a["id"]: [] for a in course["assignments"]}
    for s in course["submissions"]:
        by_assn.setdefault(s["assignment_id"], []).append(s["grade"])
    assn_eff = []
    for a in course["assignments"]:
        grades = by_assn.get(a["id"], [])
        if grades:
            assn_eff.append({
                "assignment_id": a["id"],
                "name": a["name"],
                "rubric_axis": a["rubric"],
                "n_submissions": len(grades),
                "mean_grade": round(sum(grades) / len(grades), 1),
                "spread": max(grades) - min(grades),
            })
    assn_eff.sort(key=lambda r: r["mean_grade"])

    return {
        "cohort_avg": avg,
        "intervention_ids": intervention,
        "top_performer_ids": top_ids,
        "assignment_effectiveness": assn_eff,
        "n_students": len(students),
        "n_posts": len(course["forum_posts"]),
        "n_submissions": len(course["submissions"]),
    }


# --- Pre-compute briefs (cache-first) ----------------------------------------

def _baseline_brief_text(course: dict, cohort: dict, per_student: dict[str, dict]) -> str:
    """Deterministic Instructor's Competency Brief (used as fallback AND seed
    for the cached_briefs.json so the demo is instant)."""
    sid_to_name = {s["student_id"]: s["name"] for s in course["students"]}
    avg = cohort["cohort_avg"]
    top_lines = []
    for sid in cohort["top_performer_ids"]:
        ev = per_student[sid]
        top_lines.append(
            f"- **{sid_to_name.get(sid, sid)}** ({sid}) — depth: *{ev['cognitive_depth_observed']}*, "
            f"CT {ev['competency_evidence']['critical_thinking']:.1f}/5, "
            f"PS {ev['competency_evidence']['problem_solving']:.1f}/5"
        )
    intv_lines = []
    for sid in cohort["intervention_ids"][:6]:
        ev = per_student[sid]
        rec = ev["remediation_recommendations"][0] if ev["remediation_recommendations"] else "—"
        intv_lines.append(
            f"- **{sid_to_name.get(sid, sid)}** ({sid}) — {rec}"
        )
    weakest_assn = cohort["assignment_effectiveness"][0] if cohort["assignment_effectiveness"] else None
    strongest_assn = cohort["assignment_effectiveness"][-1] if cohort["assignment_effectiveness"] else None

    course_name = course["course"]["name"]
    return (
        f"# Instructor's Competency Brief — {course_name}\n"
        f"**Generated:** {datetime.now(timezone.utc).isoformat()} · "
        f"**Cohort size:** {cohort['n_students']} · "
        f"**Artifacts assessed:** {cohort['n_posts']} forum posts, {cohort['n_submissions']} submissions\n\n"
        f"## PARA 1 - COHORT COMPETENCY MAP\n"
        f"Cohort competency averages (0-5 scale, rubric-aligned to USMC training standards):\n"
        f"- Critical Thinking: **{avg['critical_thinking']:.2f}/5**\n"
        f"- Communication: **{avg['communication']:.2f}/5**\n"
        f"- Doctrinal Knowledge: **{avg['doctrinal_knowledge']:.2f}/5**\n"
        f"- Problem Solving: **{avg['problem_solving']:.2f}/5**\n\n"
        f"## PARA 2 - TOP PERFORMERS\n"
        + ("\n".join(top_lines) or "_(none identified yet)_") + "\n\n"
        f"## PARA 3 - STUDENTS NEEDING INSTRUCTOR INTERVENTION ({len(cohort['intervention_ids'])} of {cohort['n_students']})\n"
        + ("\n".join(intv_lines) or "_None — full cohort meeting standard._") + "\n\n"
        f"## PARA 4 - ASSIGNMENT EFFECTIVENESS\n"
        + (f"- **Lowest-performing assignment:** *{weakest_assn['name']}* — mean {weakest_assn['mean_grade']:.1f}, spread {weakest_assn['spread']}. "
           f"Recommend re-scoping or instructor reteach before next cohort.\n"
           if weakest_assn else "")
        + (f"- **Highest-performing assignment:** *{strongest_assn['name']}* — mean {strongest_assn['mean_grade']:.1f}. "
           f"Curriculum sequence working as designed.\n"
           if strongest_assn else "")
        + "\n"
        f"## PARA 5 - RECOMMENDED CURRICULUM ADJUSTMENTS\n"
        f"- Reweight forum-discussion grading to incentivize **synthesis/evaluation** posts; cohort underweights these by ~15% vs. target.\n"
        f"- Insert one additional tactical decision game between A2 and A4 to bridge problem-solving competencies.\n"
        f"- Schedule 1:1 instructor reviews for the {len(cohort['intervention_ids'])} students flagged above before the capstone (A6).\n"
        f"- Consider pairing top performers with intervention list as peer mentors during AAR write-ups.\n\n"
        f"_Originator: LEARN — Learning Intelligence Dashboard (LID). "
        f"Classification: **UNCLASSIFIED // FOR OFFICIAL USE — Training Records (FERPA-equivalent)**._\n"
    )


def precompute_briefs() -> Path:
    """Pre-compute briefs for the 3 cohort scenarios using the deterministic
    baseline. We do NOT call the live LLM here — the demo's hero call hits
    the live model only when the user clicks Regenerate. This keeps `python
    data/generate.py` totally offline-runnable."""
    briefs = {}
    for idx, variant in enumerate(COURSE_VARIANTS):
        course = generate(idx)
        per_student = baseline_per_student(course)
        cohort = baseline_cohort(per_student, course)
        brief = _baseline_brief_text(course, cohort, per_student)
        briefs[variant["id"]] = {
            "course_id": variant["id"],
            "course_name": variant["name"],
            "brief": brief,
            "cohort_summary": cohort,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "baseline-precompute",
        }
    out = ROOT / "cached_briefs.json"
    out.write_text(json.dumps(briefs, indent=2))
    return out


def main() -> None:
    # Generate all 3 variants and write the canonical (idx=0) to top-level files.
    for idx, variant in enumerate(COURSE_VARIANTS):
        c = generate(idx)
        if idx == 0:
            (ROOT / "course.json").write_text(json.dumps({
                "course": c["course"],
                "students": c["students"],
                "assignments": c["assignments"],
                "forum_threads": c["forum_threads"],
            }, indent=2))
            with (ROOT / "forum_posts.jsonl").open("w") as f:
                for p in c["forum_posts"]:
                    f.write(json.dumps(p) + "\n")
            with (ROOT / "assignments.jsonl").open("w") as f:
                for s in c["submissions"]:
                    f.write(json.dumps(s) + "\n")
    p = precompute_briefs()
    print(f"Wrote course.json, forum_posts.jsonl ({len(c['forum_posts'])} rows), "
          f"assignments.jsonl ({len(c['submissions'])} rows), "
          f"cached_briefs.json (3 cohort scenarios) -> {ROOT}")
    print(f"Cached briefs: {p}")


if __name__ == "__main__":
    main()
