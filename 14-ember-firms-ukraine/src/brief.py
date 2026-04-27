# EMBER — combat-fire signature analytics + ASIB brief
# Part of the MDM 2026 Hackathon Templates (https://github.com/12fn/MDMhackathon-repos)
# MIT licensed. Built on GAI (Government Acquisitions, Inc.) + Kamiwaza (https://www.kamiwaza.ai/).
"""Daily ASIB-formatted brief generator. Uses chat() (free-form text)."""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

# Repo root is two levels up from this file (src/ -> 14-ember-firms-ukraine/ -> MDMhackathon-repos/).
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared.kamiwaza_client import chat  # noqa: E402


SYSTEM = """You are an all-source intelligence analyst attached to USMC LOGCOM CDAO.
You consume EMBER-classified satellite combustion clusters and produce a SIPR-style
ALL-SOURCE INTELLIGENCE BRIEF (ASIB). Voice: terse, declarative, US military.
Use 24h ZULU times. Use OPLAN-style headers. Round numbers. No marketing language.
Hedging only when evidence is weak. NEVER fabricate -- only cite the data given.
"""


PROMPT_TEMPLATE = """Produce an ASIB-formatted DAILY ALL-SOURCE BRIEF for {date_z}.

DATA:
- Total combustion clusters detected (FIRMS-derived): {n_total}
- Combat-attributable clusters: {n_combat}
- Industrial clusters: {n_industrial}
- Wildfire clusters: {n_wildfire}
- Structure / ambiguous: {n_other}
- Cumulative radiative power (combat clusters): {combat_frp:.0f} MW
- Top oblasts by combat activity: {top_oblasts}

TOP COMBAT-ATTRIBUTABLE CLUSTERS (highest cumulative FRP):
{cluster_block}

FORMAT (markdown, no preamble):
# DAILY ALL-SOURCE INTELLIGENCE BRIEF -- EMBER
**DTG:** {date_z}Z  **CLASS:** UNCLASSIFIED//FOUO (DEMO)  **ORIGIN:** USMC LOGCOM CDAO / EMBER

## 1. BLUF
(2-3 sentences -- the so-what for a Stand-In Force commander.)

## 2. OBSERVED COMBAT ACTIVITY
- Bullet per oblast with cluster count, dominant signature, and indicator.

## 3. INDUSTRIAL & ENERGY INFRASTRUCTURE EVENTS
- Bullet only the industrial clusters; tie to known facilities if oblast suggests one.

## 4. WILDFIRE / NON-KINETIC NOISE
- One sentence ruling these out as adversary action.

## 5. COLLECTION RECOMMENDATIONS
- 2-4 short bullets, each <= 20 words. Include the relevant ISR asset (UAS, MASINT, SIGINT, OSINT).

## 6. CONFIDENCE STATEMENT
(1 sentence -- caveat the FIRMS resolution and the LLM classifier.)
"""


def _fmt_cluster(c) -> str:
    cls = getattr(c, "llm", None) or {}
    label = cls.get("label", "unknown")
    conf = cls.get("confidence", 0.0)
    return (
        f"- cluster {c.cluster_id} | {label} (conf {conf:.2f}) | "
        f"{c.dominant_oblast} | n={c.n_pixels} | "
        f"max_K={c.max_brightness_k:.0f} max_FRP={c.max_frp_mw:.0f}MW | "
        f"spread {c.spread_km:.1f}km dur {c.duration_hours:.1f}h"
    )


def generate_brief(clusters_with_class, *, date_z: str | None = None) -> str:
    """clusters_with_class: list of objects with .llm dict + ClusterSummary fields."""
    if date_z is None:
        date_z = datetime.utcnow().strftime("%d%H%MZ %b %Y").upper()

    combat_labels = {"combat_artillery", "combat_armor"}
    n_combat = n_indus = n_wild = n_other = 0
    combat_frp = 0.0
    oblast_combat: dict[str, int] = {}

    for c in clusters_with_class:
        label = (getattr(c, "llm", None) or {}).get("label", "ambiguous")
        if label in combat_labels:
            n_combat += 1
            combat_frp += c.sum_frp_mw
            oblast_combat[c.dominant_oblast] = oblast_combat.get(c.dominant_oblast, 0) + 1
        elif label == "industrial":
            n_indus += 1
        elif label == "wildfire":
            n_wild += 1
        else:
            n_other += 1

    top_oblasts = ", ".join(
        f"{k}({v})" for k, v in
        sorted(oblast_combat.items(), key=lambda kv: -kv[1])[:5]
    ) or "n/a"

    # top combat clusters
    combat_clusters = [c for c in clusters_with_class
                       if (getattr(c, "llm", None) or {}).get("label") in combat_labels]
    combat_clusters.sort(key=lambda c: -c.sum_frp_mw)
    cluster_block = "\n".join(_fmt_cluster(c) for c in combat_clusters[:8]) or "- (none)"

    user = PROMPT_TEMPLATE.format(
        date_z=date_z,
        n_total=len(clusters_with_class),
        n_combat=n_combat,
        n_industrial=n_indus,
        n_wildfire=n_wild,
        n_other=n_other,
        combat_frp=combat_frp,
        top_oblasts=top_oblasts,
        cluster_block=cluster_block,
    )

    try:
        # Hero call -- use full gpt-5.4 if available
        text = chat(
            [{"role": "system", "content": SYSTEM},
             {"role": "user", "content": user}],
            model="gpt-5.4",
            temperature=0.3,
            max_tokens=1500,
        )
    except Exception:
        text = chat(
            [{"role": "system", "content": SYSTEM},
             {"role": "user", "content": user}],
            temperature=0.3,
            max_tokens=1500,
        )
    return text.strip()
