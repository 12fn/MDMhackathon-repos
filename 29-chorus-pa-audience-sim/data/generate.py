"""CHORUS synthetic data generator.

Produces:
  data/personas.json        - 15 reusable persona definitions across 3 audience tiers
  data/scenarios.json       - 3 training scenarios with mission context
  data/cached_briefs.json   - 3 sample message + persona-reaction + brief bundles

Synthetic-persona pattern inspired by Park et al. 2024,
"Generative Agent Simulations of 1,000 People" (arXiv:2403.20252).
NO REAL PERSONS. NO REAL DATASET. All fake-but-plausible.

Seeded with random.Random(1776) for reproducibility.
"""
from __future__ import annotations

import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ---------------------------------------------------------------------------
# 15 reusable personas across 3 audience tiers
# ---------------------------------------------------------------------------
PERSONAS: list[dict] = [
    # ---- TIER 1: U.S. domestic information environment ----
    {
        "persona_id": "P01_LOCAL_PRESS",
        "tier": "Domestic media & oversight",
        "label": "Local-base press journalist",
        "demographics": "F, 38, beat reporter for a coastal Carolina daily near a major Marine installation; 12 yrs covering DoD; sources inside PAO and base CIWG.",
        "values": ["accuracy over access", "casualty transparency", "timeline discipline"],
        "concerns": ["evasive language", "passive voice masking responsibility", "blocked FOIA"],
        "trust_baseline": 0,
        "lens": "Reads every release for what is NOT said. Cross-checks against open-source flight tracking and ship AIS.",
        "trigger_phrases_negative": ["regret any loss", "fog of war", "unable to comment", "ongoing investigation"],
        "trigger_phrases_positive": ["named officer", "specific timeline", "we will publish findings", "next-of-kin notified"],
    },
    {
        "persona_id": "P02_CONGR_STAFFER",
        "tier": "Domestic media & oversight",
        "label": "Senate Armed Services Committee staffer",
        "demographics": "M, 33, professional staff member for a senior SASC senator; former O-3 infantry; reads every MARADMIN.",
        "values": ["civilian control", "Title 10 authorities", "appropriations linkage"],
        "concerns": ["preemption of investigations", "unfunded mandates implied", "inconsistent talking points across services"],
        "trust_baseline": 1,
        "lens": "Maps every statement to a hearing, an authorization line, and a constituent-letter risk surface.",
        "trigger_phrases_negative": ["pending CCMD review", "policy is being clarified", "no further details at this time"],
        "trigger_phrases_positive": ["briefed the committee", "we will testify", "appropriations footprint", "lessons-learned package"],
    },
    {
        "persona_id": "P03_VETERAN_INFLUENCER",
        "tier": "Domestic media & oversight",
        "label": "Veteran-community Substack influencer (200k subs)",
        "demographics": "M, 45, retired GySgt, runs a heterodox veteran newsletter; 200k subscribers, half active-duty.",
        "values": ["plain English", "respect for the rifleman", "no spin"],
        "concerns": ["jargon", "PowerPoint voice", "officers shielding officers"],
        "trust_baseline": -1,
        "lens": "Will quote your release in full and roast specific phrases. Drives a substantial slice of the lance-corporal underground.",
        "trigger_phrases_negative": ["robust", "leverage", "synergy", "kinetic outcome"],
        "trigger_phrases_positive": ["the Marine made this call", "we owned it", "here is what we changed"],
    },
    {
        "persona_id": "P04_MIL_SPOUSE",
        "tier": "Domestic media & oversight",
        "label": "Deployed-Marine spouse (FRG admin)",
        "demographics": "F, 31, spouse of a deployed 2/8 Marine, runs the unit Family Readiness Group Facebook group (1,400 members).",
        "values": ["are my Marines safe", "predictability", "honest casualty reporting"],
        "concerns": ["learning of incidents from Twitter first", "vague timelines", "policy changes mid-deployment"],
        "trust_baseline": 0,
        "lens": "Filters every statement through 'does this make my husband safer or less safe today.' Will share the post within 5 minutes.",
        "trigger_phrases_negative": ["operational details cannot be shared", "no impact on the mission", "we are aware of the reports"],
        "trigger_phrases_positive": ["families have been notified", "command will hold a town hall", "here is the unit POC"],
    },
    {
        "persona_id": "P05_GOLD_STAR_ADV",
        "tier": "Domestic media & oversight",
        "label": "Gold Star Family advocacy lead",
        "demographics": "F, 56, mother of a Marine KIA in 2019; runs a 501(c)(3) supporting next-of-kin notification reform.",
        "values": ["dignity of the fallen", "next-of-kin first", "no surprises in the press"],
        "concerns": ["families learning of incidents from media", "name releases without notification", "boilerplate condolences"],
        "trust_baseline": -2,
        "lens": "Has the contact list of every other Gold Star family in the affected unit's history. Influence is moral, not numerical.",
        "trigger_phrases_negative": ["thoughts and prayers", "ultimate sacrifice", "regret to inform"],
        "trigger_phrases_positive": ["families notified before this release", "named in coordination with next-of-kin", "investigation findings will be shared with the family first"],
    },
    # ---- TIER 2: Host-nation & coalition information environment ----
    {
        "persona_id": "P06_HOST_CIVIC",
        "tier": "Host-nation & coalition",
        "label": "Host-nation civic leader (mayor of a base-adjacent town)",
        "demographics": "M, 52, three-term mayor of a town of 18,000 outside a Marine air station overseas; coalition-friendly but politically exposed.",
        "values": ["noise abatement", "economic spillover", "respect for local custom"],
        "concerns": ["bypassed by U.S. spokespeople", "English-only releases", "incidents in local press before official notice"],
        "trust_baseline": 1,
        "lens": "Reads through translation; weights tone heavily. A bad release costs him his next election.",
        "trigger_phrases_negative": ["U.S. forces will continue operations", "regret the inconvenience", "in accordance with the SOFA"],
        "trigger_phrases_positive": ["mayor was briefed in advance", "town council POC named", "translated copy attached"],
    },
    {
        "persona_id": "P07_FOREIGN_PRESS",
        "tier": "Host-nation & coalition",
        "label": "Host-nation national press correspondent",
        "demographics": "F, 41, defense correspondent for a major host-nation broadsheet, accredited at the embassy press pool.",
        "values": ["sovereignty narrative", "casualty transparency", "domestic political resonance"],
        "concerns": ["U.S.-centric framing", "no host-nation casualty acknowledgment", "embassy not in synch with PACOM"],
        "trust_baseline": 0,
        "lens": "Looks for the host-nation angle in every release; will lead with it whether you provide it or not.",
        "trigger_phrases_negative": ["coordinated with allies", "no host-nation casualties reported", "our operations continue"],
        "trigger_phrases_positive": ["host-nation citizens were affected", "we are coordinating compensation", "joint statement with the embassy"],
    },
    {
        "persona_id": "P08_NATO_PA",
        "tier": "Host-nation & coalition",
        "label": "Coalition-partner PA officer (NATO O-4)",
        "demographics": "M, 38, public affairs officer at a NATO partner-nation MOD; works the same incident from his nation's lane.",
        "values": ["alliance coherence", "no daylight between national talking points", "advance notice"],
        "concerns": ["being surprised by U.S. release", "mismatched casualty figures", "diverging timelines"],
        "trust_baseline": 2,
        "lens": "Compares U.S. release line-by-line with his own MOD's release. Looks for things he can/cannot echo.",
        "trigger_phrases_negative": ["U.S.-led", "American leadership", "we will continue to act"],
        "trigger_phrases_positive": ["coalition partners briefed in advance", "joint findings will be released", "shared talking points attached"],
    },
    {
        "persona_id": "P09_NGO_AID",
        "tier": "Host-nation & coalition",
        "label": "International humanitarian NGO field director",
        "demographics": "F, 47, country director for a major INGO operating in the same theater; manages 200 local staff.",
        "values": ["civilian protection", "humanitarian space", "principled neutrality"],
        "concerns": ["military describing aid as a force multiplier", "blurred lines with NGO ops", "civilian casualty under-counts"],
        "trust_baseline": -1,
        "lens": "Reads every U.S. release for language that compromises her staff's safety on the ground.",
        "trigger_phrases_negative": ["humanitarian assistance", "winning hearts and minds", "civilian-military cooperation"],
        "trigger_phrases_positive": ["civilian harm assessment underway", "we are deconflicting with humanitarian actors", "ICRC has been notified"],
    },
    {
        "persona_id": "P10_RELIG_LEADER",
        "tier": "Host-nation & coalition",
        "label": "Host-nation religious leader (community elder)",
        "demographics": "M, 64, senior cleric in the affected village; voice on local radio; not a state actor.",
        "values": ["dignity of the dead", "respect for funeral rites", "community grief"],
        "concerns": ["bodies not returned per custom", "Friday-prayer references in U.S. talking points", "spokesperson tone-deaf to local mourning calendar"],
        "trust_baseline": -2,
        "lens": "His Friday sermon will frame the incident for the community for months. A clumsy U.S. release becomes the sermon.",
        "trigger_phrases_negative": ["regrettable incident", "minimize collateral", "thoughts are with"],
        "trigger_phrases_positive": ["bodies returned in accordance with local custom", "elders consulted on funeral arrangements", "we attended the prayers"],
    },
    # ---- TIER 3: Adversary / contested information environment ----
    {
        "persona_id": "P11_ADV_IO",
        "tier": "Adversary / contested IE",
        "label": "Foreign adversary IO analyst",
        "demographics": "Composite, 35-50, doctrinal IO/PSYOP analyst at a near-peer adversary's strategic-comms cell.",
        "values": ["narrative dominance", "wedge-driving", "Western alliance erosion"],
        "concerns": ["not enough U.S. self-incrimination to amplify"],
        "trust_baseline": -8,
        "lens": "Mines every U.S. release for one quotable line that can be re-cut into 30s of disinfo across 14 platforms.",
        "trigger_phrases_negative": ["fog of war", "unable to confirm", "investigation is ongoing", "regrettable"],
        "trigger_phrases_positive": ["we are publishing the after-action report", "named accountability", "civilian harm count attached"],
    },
    {
        "persona_id": "P12_TROLL_NETWORK",
        "tier": "Adversary / contested IE",
        "label": "Coordinated inauthentic-behavior network operator",
        "demographics": "Composite operator behind a network of 4,800 inauthentic accounts across X / TikTok / Telegram.",
        "values": ["engagement velocity", "amplification of any wedge", "deniability"],
        "concerns": ["U.S. release that doesn't give them an angle"],
        "trust_baseline": -10,
        "lens": "Pulls one phrase, machine-translates into 9 languages, A/B tests across the network within 90 minutes.",
        "trigger_phrases_negative": ["no comment", "unable to confirm", "operational security"],
        "trigger_phrases_positive": ["full transparency", "named individual", "documented timeline", "ICRC observers present"],
    },
    {
        "persona_id": "P13_DOMESTIC_DISINFO",
        "tier": "Adversary / contested IE",
        "label": "Domestic conspiracy-influencer node",
        "demographics": "M, 42, runs a 600k-follower Telegram channel that rebroadcasts adversary-aligned content with U.S.-flag framing.",
        "values": ["distrust of institutions", "anti-DoD prior", "narrative entrepreneurship"],
        "concerns": ["mainstream coverage that pre-empts his framing"],
        "trust_baseline": -6,
        "lens": "Will post the same release within 12 minutes of issuance with a hostile gloss. Plain language denies him the gloss.",
        "trigger_phrases_negative": ["DoD cannot confirm", "spokesperson said", "in coordination with"],
        "trigger_phrases_positive": ["here is the video", "here is the timeline", "we made this mistake, here is the fix"],
    },
    {
        "persona_id": "P14_HOSTILE_PARLIAMENT",
        "tier": "Adversary / contested IE",
        "label": "Adversary-aligned parliamentarian (third country)",
        "demographics": "M/F, 50s, member of parliament in a third country whose party platform opposes U.S. military presence in the region.",
        "values": ["sovereignty grievance", "domestic political capital", "anti-base messaging"],
        "concerns": ["U.S. bypass of his parliament's question hour"],
        "trust_baseline": -5,
        "lens": "Will table a parliamentary question within 24h citing the U.S. release verbatim.",
        "trigger_phrases_negative": ["U.S. forces will continue", "in our national interest", "no host-nation casualties"],
        "trigger_phrases_positive": ["briefed the host-nation parliament", "operations are paused pending review", "joint host-nation investigation"],
    },
    {
        "persona_id": "P15_NEUTRAL_OBS",
        "tier": "Adversary / contested IE",
        "label": "Neutral OSINT analyst (independent)",
        "demographics": "F, 29, runs a respected OSINT account; cited by Bellingcat-tier outlets; geolocates incidents within 6 hours.",
        "values": ["evidence over narrative", "geolocation discipline", "open-source verifiability"],
        "concerns": ["releases that contradict OSINT timelines", "missing satellite-imagery references"],
        "trust_baseline": 2,
        "lens": "Will publish a thread within 4 hours either supporting or shredding the U.S. timeline. A factual release earns durable credibility.",
        "trigger_phrases_negative": ["approximately", "in the vicinity of", "we are still gathering facts"],
        "trigger_phrases_positive": ["coordinates 33.21N 44.18E", "observed at 14:02 local", "satellite imagery to be released"],
    },
]


# ---------------------------------------------------------------------------
# 3 training scenarios — must match the brief exactly
# ---------------------------------------------------------------------------
SCENARIOS: list[dict] = [
    {
        "scenario_id": "SC_DRONE_STRIKE",
        "title": "Drone strike near civilian village in [theater]",
        "theater": "INDOPACOM — first island chain, near-peer-adjacent littoral",
        "classification_band": "UNCLASSIFIED // FOR PUBLIC RELEASE",
        "mission_context": (
            "A precision-strike UAS engaged a confirmed adversary fast-attack craft (FAC) "
            "operating in international waters 11 nm from a host-nation fishing village. "
            "Two FAC crew killed (combatants). Initial reports indicate fragmentation "
            "from the engagement reached the village; one host-nation civilian wounded "
            "(non-life-threatening), one fishing boat damaged. The strike was authorized "
            "under standing rules of engagement; review is underway at the strike cell. "
            "Incident occurred 06:42 local; you are drafting the first U.S. PA release at 09:15 local. "
            "Adversary state media has already published a hostile narrative."
        ),
        "trainee_objective": (
            "Draft a 200-500 word public statement that maintains alliance coherence, "
            "preserves host-nation political space, denies the adversary IO wedge, and "
            "does not pre-empt the formal investigation."
        ),
        "constraints": [
            "Do not name personnel pending notification.",
            "Do not classify intelligence sources.",
            "Acknowledge host-nation civilian harm if any has occurred.",
            "Coordinate language with host-nation MOD/embassy in real ops; here, draft as if coordination is in motion.",
        ],
        "audience_tiers_active": ["all"],
    },
    {
        "scenario_id": "SC_FRIENDLY_FIRE",
        "title": "Friendly-fire investigation announcement",
        "theater": "CENTCOM — combined-arms live-fire exercise with NATO partner",
        "classification_band": "UNCLASSIFIED // FOR PUBLIC RELEASE",
        "mission_context": (
            "During a multinational live-fire exercise, indirect fire from a U.S. battery "
            "impacted approximately 380 m off-target, killing one U.S. Marine (notified) "
            "and wounding two NATO partner-nation soldiers (notified). The CG has directed "
            "an AR 15-6-equivalent investigation. Range was made cold within 90 seconds. "
            "Exercise has been paused pending preliminary findings. You are drafting the "
            "release that announces the incident, the pause, and the investigation."
        ),
        "trainee_objective": (
            "Draft a 200-500 word release that names the loss with dignity, demonstrates "
            "alliance solidarity with the partner nation, frames the investigation credibly, "
            "and does not pre-judge the outcome."
        ),
        "constraints": [
            "Do not release the Marine's name (notified, but coordinate with family for public-release timing).",
            "Acknowledge the NATO partner casualties explicitly and with parity.",
            "State the investigation authority and an expected timeline for preliminary findings.",
            "Do not assign individual culpability.",
        ],
        "audience_tiers_active": ["all"],
    },
    {
        "scenario_id": "SC_BASE_CLOSURE",
        "title": "Base-closure community outreach",
        "theater": "CONUS — Marine installation slated for partial drawdown under Force Design",
        "classification_band": "UNCLASSIFIED // FOR PUBLIC RELEASE",
        "mission_context": (
            "Under Force Design 2030 implementation, the Department has directed the "
            "drawdown of one squadron and one logistics battalion from a CONUS Marine "
            "installation by FY28. Estimated impact: 1,400 personnel relocations, "
            "approximately $90M annual local economic footprint reallocation. Local "
            "congressional delegation, mayor, and chamber of commerce have requested "
            "early engagement. You are drafting the inaugural community outreach "
            "release announcing the drawdown plan and town-hall schedule."
        ),
        "trainee_objective": (
            "Draft a 200-500 word community-facing release that frames the change inside "
            "Force Design, respects the host community's economic equities, names a real "
            "engagement venue (town hall) and POC, and avoids talking-points jargon."
        ),
        "constraints": [
            "Do not over-promise on the timeline (FY28 is a planning horizon, not a commitment).",
            "Acknowledge economic impact directly with a number.",
            "Name a town-hall date and a community-liaison POC role (not a person).",
            "Do not characterize the change as permanent / irreversible / final.",
        ],
        "audience_tiers_active": ["all"],
    },
]


# ---------------------------------------------------------------------------
# Sample messages a trainee might write — used to seed cached_briefs.json
# ---------------------------------------------------------------------------
SAMPLE_TRAINEE_MESSAGES: dict[str, str] = {
    "SC_DRONE_STRIKE": (
        "U.S. forces conducted a precision engagement against an adversary fast-attack "
        "craft operating in international waters earlier today. The engagement was lawful "
        "and proportionate under standing rules of engagement. We are aware of reports of "
        "an injury to a host-nation civilian and damage to a fishing vessel in the vicinity; "
        "we regret any harm to non-combatants and are coordinating closely with our host-nation "
        "partners to verify the facts and provide appropriate assistance. A formal review is "
        "underway. We will not speculate on details ahead of the investigation. The United States "
        "remains committed to lawful operations in the region and to the safety of the local "
        "community. We will provide additional information as it becomes available through "
        "official channels."
    ),
    "SC_FRIENDLY_FIRE": (
        "During a routine multinational live-fire exercise yesterday, an indirect-fire round "
        "impacted off the intended target. Tragically, one U.S. Marine was killed and two "
        "soldiers from our partner-nation contingent were wounded. Our deepest condolences "
        "go to the family of the fallen Marine and to our partners. The Marine's family has "
        "been notified, and his name will be released after the standard 24-hour period. "
        "The exercise has been paused pending the outcome of an investigation directed by "
        "the commanding general. We will share findings with the family and with our coalition "
        "partners, and a public summary will follow. We will not pre-judge the investigation "
        "or comment on specific personnel actions. The strength of our alliance with our "
        "partner nation is unshaken."
    ),
    "SC_BASE_CLOSURE": (
        "As part of the Marine Corps' continued implementation of Force Design 2030, the "
        "Department has directed a planned drawdown of one squadron and one logistics "
        "battalion from this installation by FY28. We recognize that this change will have a "
        "real impact on the surrounding community — an estimated reduction of approximately "
        "$90M in annual local economic activity and the relocation of approximately 1,400 "
        "personnel and their families. We are committed to an open, sustained dialogue with "
        "the community throughout this transition. The installation will host a community "
        "town hall on the third Thursday of next month, with a community-liaison officer "
        "designated as the standing point of contact. The Marine Corps deeply values the "
        "decades-long partnership with this community and will work to ensure the transition "
        "is conducted with the same care and transparency the community has come to expect."
    ),
}


# ---------------------------------------------------------------------------
# Deterministic baseline persona-reaction synthesizer (no LLM needed)
# ---------------------------------------------------------------------------

def _baseline_reaction(persona: dict, message: str) -> dict:
    """Hash a message against a persona's trigger-phrase list to produce a
    deterministic reaction. Used by the precompute step as a fallback and by
    the live UI when the LLM call times out.
    """
    msg = message.lower()
    pos = sum(1 for p in persona["trigger_phrases_positive"] if p.lower() in msg)
    neg = sum(1 for p in persona["trigger_phrases_negative"] if p.lower() in msg)
    base = persona["trust_baseline"]
    delta = max(-10, min(10, base + (2 * pos) - (2 * neg)))
    if delta >= 4:
        risk, action = "LOW", "share"
    elif delta >= 0:
        risk, action = "MEDIUM", "ignore"
    elif delta >= -4:
        risk, action = "MEDIUM", "challenge"
    else:
        risk, action = "HIGH", "counter-message"

    if persona["tier"].startswith("Adversary") and delta < 0:
        action = "counter-message"
        risk = "HIGH"

    perceived = {
        "Domestic media & oversight": "Reads release as %s; will write follow-up by end of day." % (
            "credible" if delta >= 2 else ("guarded" if delta >= -2 else "evasive")
        ),
        "Host-nation & coalition": "Reads release as %s for local political space." % (
            "respectful" if delta >= 2 else ("acceptable" if delta >= -2 else "tone-deaf")
        ),
        "Adversary / contested IE": "Reads release as %s for IO exploitation." % (
            "low-yield (denies the wedge)" if delta >= 0 else "high-yield (gives the wedge)"
        ),
    }[persona["tier"]]

    concerns = []
    for phrase in persona["trigger_phrases_negative"]:
        if phrase.lower() in msg:
            concerns.append(f'Triggered by: "{phrase}".')
    if not concerns:
        if delta < 0:
            concerns.append(f"No specific trigger phrase, but tone misaligned with audience values: {', '.join(persona['values'][:2])}.")
        else:
            concerns.append("Generally aligned; would still want a named POC and a stated timeline.")

    return {
        "persona_id": persona["persona_id"],
        "perceived_message": perceived,
        "trust_delta": int(delta),
        "narrative_risk": risk,
        "predicted_action": action,
        "key_concerns_raised": concerns[:3],
        "_source": "baseline",
    }


def _baseline_brief(scenario: dict, message: str, reactions: list[dict]) -> str:
    """Deterministic Message Effectiveness Brief in the same shape the LLM
    will produce. Always available so the demo never hangs.
    """
    avg_delta = sum(r["trust_delta"] for r in reactions) / max(1, len(reactions))
    high_risk = [r for r in reactions if r["narrative_risk"] == "HIGH"]
    counters = [r for r in reactions if r["predicted_action"] == "counter-message"]
    bluf_word = "MIXED" if -2 <= avg_delta <= 2 else ("FAVORABLE" if avg_delta > 2 else "UNFAVORABLE")

    out = []
    out.append(f"# Message Effectiveness Brief — {scenario['title']}")
    out.append("")
    out.append("## BLUF")
    out.append(
        f"- **Aggregate audience reaction: {bluf_word}** (avg trust delta {avg_delta:+.1f}).\n"
        f"- **{len(high_risk)} of {len(reactions)} personas flag HIGH narrative risk.**\n"
        f"- **{len(counters)} personas predicted to counter-message.**"
    )
    out.append("")
    out.append("## Audience-by-Audience Scorecard")
    for r in sorted(reactions, key=lambda x: x["trust_delta"]):
        out.append(
            f"- **{r['persona_id']}** — trust {r['trust_delta']:+d}, risk {r['narrative_risk']}, "
            f"likely to **{r['predicted_action']}**. {r['perceived_message']}"
        )
    out.append("")
    out.append("## What Worked")
    out.append("- Acknowledgment of the incident is direct, not buried.")
    out.append("- Tone is measured and free of inflammatory language.")
    out.append("- Investigation pathway is named.")
    out.append("")
    out.append("## What Backfired")
    out.append("- Passive-voice and hedging phrasing (\"we are aware of reports\", \"regret any harm\") triggers domestic media and adversary IO personas alike.")
    out.append("- Host-nation persona coordination is implied but not demonstrated (no named MOD/embassy coordination).")
    out.append("- No named POC, no concrete timeline for next update — denies trust-building moves to neutral observers and OSINT.")
    out.append("")
    out.append("## Suggested Revisions")
    out.append("1. Replace \"we are aware of reports\" with a specific factual line acknowledging civilian harm if confirmed.")
    out.append("2. Add: \"We have notified our host-nation counterparts at MOD-[X] and Embassy-[Y] and are coordinating compensation.\"")
    out.append("3. Name the next briefing window (e.g., \"We will provide an updated statement within 24 hours.\") and a POC role.")
    out.append("4. Strip jargon (\"proportionate\", \"standing rules of engagement\") from the public-facing line; keep technical language for the back-channel briefing.")
    out.append("5. Lead with the host-nation civilian impact, not with the U.S. operation. Order matters for how each tier reads the rest.")
    out.append("")
    out.append("*Originator: CHORUS — PA/IO Audience Simulation Cell. Classification: UNCLASSIFIED // FOR TRAINING USE.*")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Optional LLM precompute — wraps shared.kamiwaza_client
# ---------------------------------------------------------------------------

def _precompute_briefs() -> None:
    """Try to call the LLM once per scenario to produce a richer brief.
    Always falls through to baseline output if the call fails or times out,
    so the cached_briefs.json is guaranteed to exist after this script runs.
    """
    cached: dict = {}
    for scenario in SCENARIOS:
        message = SAMPLE_TRAINEE_MESSAGES[scenario["scenario_id"]]
        reactions = [_baseline_reaction(p, message) for p in PERSONAS[:5]]
        brief = _baseline_brief(scenario, message, reactions)
        cached[scenario["scenario_id"]] = {
            "scenario_id": scenario["scenario_id"],
            "scenario_title": scenario["title"],
            "trainee_message": message,
            "personas_used": [p["persona_id"] for p in PERSONAS[:5]],
            "reactions": reactions,
            "brief_markdown": brief,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "baseline",
        }

    # Try LLM precompute — pure best effort, never blocks the file write.
    try:
        from shared.kamiwaza_client import chat  # type: ignore
        for scenario in SCENARIOS:
            try:
                msg = SAMPLE_TRAINEE_MESSAGES[scenario["scenario_id"]]
                reactions = cached[scenario["scenario_id"]]["reactions"]
                prompt = (
                    "You are CHORUS, a USMC Public Affairs / Information Operations training "
                    "simulator. Below is a scenario, a trainee's draft public statement, and "
                    "structured reactions from 5 synthetic personas. Produce a one-page "
                    "**Message Effectiveness Brief** in markdown with these sections in this "
                    "exact order:\n"
                    "  ## BLUF\n  ## Audience-by-Audience Scorecard\n"
                    "  ## What Worked\n  ## What Backfired\n  ## Suggested Revisions\n"
                    "Keep it under 450 words. Be concrete and specific.\n\n"
                    f"SCENARIO: {scenario['title']}\n{scenario['mission_context']}\n\n"
                    f"TRAINEE MESSAGE:\n{msg}\n\n"
                    f"REACTIONS:\n{json.dumps(reactions, indent=2)}\n"
                )
                text = chat(
                    [
                        {"role": "system", "content": "You are CHORUS, an objective PA/IO training analyst."},
                        {"role": "user", "content": prompt},
                    ],
                    model="gpt-5.4",
                    temperature=0.45,
                )
                if text and "BLUF" in text:
                    cached[scenario["scenario_id"]]["brief_markdown"] = text
                    cached[scenario["scenario_id"]]["source"] = "gpt-5.4-precompute"
            except Exception as e:  # noqa: BLE001
                print(f"[precompute] {scenario['scenario_id']} fell back to baseline: {e}")
    except Exception as e:  # noqa: BLE001
        print(f"[precompute] LLM unavailable, baseline only: {e}")

    (ROOT / "cached_briefs.json").write_text(json.dumps(cached, indent=2))


def main() -> None:
    rng = random.Random(1776)
    # Stable order; rng is here so future expansion (e.g. 50 personas sampled
    # to 15) stays reproducible.
    _ = rng.random()
    (ROOT / "personas.json").write_text(json.dumps(PERSONAS, indent=2))
    (ROOT / "scenarios.json").write_text(json.dumps(SCENARIOS, indent=2))
    _precompute_briefs()
    print(f"Wrote {len(PERSONAS)} personas, {len(SCENARIOS)} scenarios, and cached briefs.")
    print(f"  -> {ROOT}")


if __name__ == "__main__":
    main()
