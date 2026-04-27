"""STOCKROOM agent — two LLM moves.

1. `parse_nl_query(question, columns)` -> structured filter dict.
   Uses chat_json for deterministic structured output. Falls back to a
   keyword heuristic on timeout so the demo never blocks.

2. `generate_brief(scenario_id, inventory_df)` -> markdown brief.
   Cache-first: serves data/cached_briefs.json instantly. The live "Regenerate"
   path uses the hero gpt-5.4 model under a 35s wall-clock timeout, with a
   deterministic fallback so the spinner never hangs.
"""
from __future__ import annotations

import concurrent.futures
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

# Repo root for shared imports
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.kamiwaza_client import chat, chat_json  # noqa: E402

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
CACHED_BRIEFS_PATH = DATA_DIR / "cached_briefs.json"

HERO_TIMEOUT_S = 35.0
PARSE_TIMEOUT_S = 12.0


# ---------------------------------------------------------------------------
# 1. Natural-language query parser (chat_json)
# ---------------------------------------------------------------------------

PARSE_SYSTEM = """You translate a USMC supply NCO's natural-language question
about an inventory of ~5,000 items into a structured filter spec.

The inventory has these columns and value vocabularies:

  - nsn                      (string, e.g. "1005-12-345-6789")
  - nomenclature             (string)
  - category                 (one of: "Class I — Subsistence", "Class II — Clothing & Individual Equip",
                              "Class III — POL", "Class IV — Construction", "Class V — Ammunition",
                              "Class VI — Personal Demand", "Class VII — Major End Items",
                              "Class VIII — Medical", "Class IX — Repair Parts",
                              "Class X — Non-Mil Programs")
  - qty_on_hand              (int)
  - qty_required             (int)
  - shortage                 (int, qty_required - qty_on_hand, clipped at 0)
  - condition_code           (one of "A","B","C","F"; F = unserviceable / NMC)
  - sensitivity_class        (one of "ROUTINE","SENSITIVE","CCI","ARMS","HAZMAT")
  - location_id              (string id, e.g. "ARM-101", "WHSE-A1", "VBAY-02")
  - responsible_marine       (string, "Rank Lastname, F.")
  - days_since_inventory     (int)
  - days_since_lateral_transfer (int; 9999 means never)
  - inventory_overdue        (bool)
  - nmc_impacting            (bool, true for Class VII/IX in condition F)

Return JSON of shape:
{
  "filters": [
    {"column": <col>, "op": <op>, "value": <value>}
  ],
  "sort_by":   <col or null>,
  "ascending": <bool>,
  "limit":     <int or null>,
  "explanation": "<one sentence describing what the filter does>"
}

Allowed ops: "eq", "neq", "gt", "gte", "lt", "lte", "in", "contains", "is_true", "is_false".
Use "in" with a list value for multi-value membership.
Use "contains" for case-insensitive substring on string columns.
Use "is_true"/"is_false" for boolean columns (no value needed).
Combine filters with AND.

If the user mentions "sensitive items" interpret as sensitivity_class in
["SENSITIVE","CCI","ARMS"]. If "lateral-transferred in N days" interpret as
days_since_lateral_transfer > N. If "overdue for inventory" interpret as
inventory_overdue is_true.
"""


def _heuristic_parse(question: str) -> dict:
    """Last-resort keyword-based parser. Returns a filter spec."""
    q = question.lower()
    filters: list[dict] = []
    explanation_bits: list[str] = []

    if "sensitive" in q or "arms" in q or "cci" in q:
        filters.append({"column": "sensitivity_class", "op": "in",
                        "value": ["SENSITIVE", "CCI", "ARMS"]})
        explanation_bits.append("sensitive items")

    m = re.search(r"(?:in|within|over|past|last)\s*(\d+)\s*days?", q)
    if m and "lateral" in q:
        n = int(m.group(1))
        filters.append({"column": "days_since_lateral_transfer", "op": "gt", "value": n})
        explanation_bits.append(f"no lateral transfer in {n} days")

    if "overdue" in q and "inventor" in q:
        filters.append({"column": "inventory_overdue", "op": "is_true", "value": None})
        explanation_bits.append("overdue for inventory")

    if "nmc" in q or "non-mission" in q or "deadlined" in q:
        filters.append({"column": "nmc_impacting", "op": "is_true", "value": None})
        explanation_bits.append("NMC-impacting items")

    if "shortage" in q or "short " in q:
        filters.append({"column": "shortage", "op": "gt", "value": 0})
        explanation_bits.append("with a quantity shortage")

    if "armory" in q or "armory room" in q:
        filters.append({"column": "location_id", "op": "in",
                        "value": ["ARM-101", "ARM-102", "ARM-103"]})
        explanation_bits.append("in the armory")

    m_loc = re.search(r"(WHSE-[AB]\d|VBAY-\d{2}|ARM-\d{3}|COMSEC-\d|HAZ-Y\d|MED-CAGE)",
                      question, re.IGNORECASE)
    if m_loc:
        filters.append({"column": "location_id", "op": "eq",
                        "value": m_loc.group(1).upper()})
        explanation_bits.append(f"at {m_loc.group(1).upper()}")

    if not filters:
        # Last fallback — substring match on nomenclature
        kw = next((w for w in q.split()
                   if len(w) > 4 and w not in {"items", "show", "find", "list"}),
                  None)
        if kw:
            filters.append({"column": "nomenclature", "op": "contains", "value": kw})
            explanation_bits.append(f"nomenclature contains '{kw}'")

    return {
        "filters":    filters,
        "sort_by":    "days_since_inventory",
        "ascending":  False,
        "limit":      200,
        "explanation": ("Heuristic parse: " + ", ".join(explanation_bits)
                        if explanation_bits else "Unfiltered (keyword parse)"),
    }


def parse_nl_query(question: str) -> dict:
    """Parse NL question -> filter spec via chat_json (with timeout fallback)."""
    msgs = [
        {"role": "system", "content": PARSE_SYSTEM},
        {"role": "user", "content": f"Question: {question}\n\nReturn the JSON filter spec."},
    ]

    def _go() -> dict:
        return chat_json(
            msgs,
            schema_hint='{"filters":[{"column":str,"op":str,"value":any}],"sort_by":str,"ascending":bool,"limit":int,"explanation":str}',
            temperature=0.1,
        )

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            spec = ex.submit(_go).result(timeout=PARSE_TIMEOUT_S)
        # sanity check shape
        if not isinstance(spec, dict) or "filters" not in spec:
            raise ValueError("malformed spec")
        spec.setdefault("sort_by", None)
        spec.setdefault("ascending", True)
        spec.setdefault("limit", None)
        spec.setdefault("explanation", "")
        return spec
    except Exception:
        return _heuristic_parse(question)


def apply_filter_spec(df: pd.DataFrame, spec: dict) -> pd.DataFrame:
    """Apply a parsed filter spec to the inventory DataFrame."""
    out = df
    for f in spec.get("filters", []):
        col = f.get("column")
        op = (f.get("op") or "eq").lower()
        val = f.get("value")
        if col not in out.columns:
            continue
        try:
            if op == "eq":
                out = out[out[col] == val]
            elif op == "neq":
                out = out[out[col] != val]
            elif op == "gt":
                out = out[pd.to_numeric(out[col], errors="coerce") > float(val)]
            elif op == "gte":
                out = out[pd.to_numeric(out[col], errors="coerce") >= float(val)]
            elif op == "lt":
                out = out[pd.to_numeric(out[col], errors="coerce") < float(val)]
            elif op == "lte":
                out = out[pd.to_numeric(out[col], errors="coerce") <= float(val)]
            elif op == "in":
                vals = val if isinstance(val, list) else [val]
                out = out[out[col].isin(vals)]
            elif op == "contains":
                out = out[out[col].astype(str).str.contains(str(val), case=False, na=False)]
            elif op == "is_true":
                out = out[out[col].astype(bool)]
            elif op == "is_false":
                out = out[~out[col].astype(bool)]
        except Exception:
            continue
    sort_by = spec.get("sort_by")
    if sort_by and sort_by in out.columns:
        out = out.sort_values(sort_by, ascending=bool(spec.get("ascending", True)))
    limit = spec.get("limit")
    if isinstance(limit, int) and limit > 0:
        out = out.head(limit)
    return out


# ---------------------------------------------------------------------------
# 2. Hero brief — cache-first, hero model with timeout, deterministic fallback
# ---------------------------------------------------------------------------

HERO_SYSTEM = """You are STOCKROOM, an AI logistics analyst supporting the
USMC supply NCO under the LOGCOM "Inventory Control Management" use case.

Compose a polished **"Readiness & Lateral Transfer Brief"** in markdown with
these EXACT section headers, in order:

  ### BLUF
  ### Items overdue for inventory
  ### NMC-impacting shortages
  ### Sensitive-item & lateral-transfer flags
  ### Recommended actions for the supply NCO

Constraints:
  - BLUF is one bold sentence summarizing accountability posture.
  - "Items overdue for inventory": cite hard numbers per sensitivity class
    (ROUTINE/SENSITIVE/CCI/ARMS/HAZMAT) and name the top 3 responsible Marines.
  - "NMC-impacting shortages": top 5 Class VII / Class IX items in condition F
    or with shortage > 0 (NSN, nomenclature, qty, location).
  - "Sensitive-item & lateral-transfer flags": items in ARMS/CCI/SENSITIVE not
    laterally transferred in > 60 days, or in a location off their category bias.
  - "Recommended actions": exactly THREE numbered actions, each tied to a
    specific Marine or location, executable today.
  - ~350 words. Do NOT mention the AI provider or model name.
"""


def _summarize(df: pd.DataFrame) -> dict:
    overdue = df[df["inventory_overdue"]] if "inventory_overdue" in df.columns else df.head(0)
    by_sens = overdue.groupby("sensitivity_class").size().to_dict() if len(overdue) else {}
    top_marines = (overdue.groupby("responsible_marine").size()
                   .sort_values(ascending=False).head(5).to_dict()) if len(overdue) else {}
    nmc = (df[df["nmc_impacting"]].head(8) if "nmc_impacting" in df.columns
           else df.head(0))
    nmc_recs = nmc[
        ["item_id", "nsn", "nomenclature", "qty_on_hand", "qty_required",
         "shortage", "condition_code", "location_id", "responsible_marine"]
    ].to_dict("records") if len(nmc) else []
    shortage = (df[df.get("shortage", 0) > 0]
                .sort_values("shortage", ascending=False).head(8)
                if "shortage" in df.columns else df.head(0))
    short_recs = shortage[
        ["item_id", "nsn", "nomenclature", "qty_on_hand", "qty_required",
         "shortage", "category", "location_id", "responsible_marine"]
    ].to_dict("records") if len(shortage) else []
    sensitive_stale = df[
        (df.get("sensitivity_class", "ROUTINE").isin(["ARMS", "CCI", "SENSITIVE"]))
        & (df.get("days_since_lateral_transfer", 0) > 60)
    ].head(10) if "days_since_lateral_transfer" in df.columns else df.head(0)
    stale_recs = sensitive_stale[
        ["item_id", "nsn", "nomenclature", "sensitivity_class",
         "days_since_lateral_transfer", "location_id", "responsible_marine"]
    ].to_dict("records") if len(sensitive_stale) else []
    return {
        "as_of":                 datetime.now(timezone.utc).isoformat(),
        "total_items":           int(len(df)),
        "by_category":           df["category"].value_counts().to_dict() if "category" in df.columns else {},
        "by_sensitivity":        df["sensitivity_class"].value_counts().to_dict() if "sensitivity_class" in df.columns else {},
        "by_location":           df["location_id"].value_counts().to_dict() if "location_id" in df.columns else {},
        "overdue_total":         int(len(overdue)),
        "overdue_by_sensitivity":{k: int(v) for k, v in by_sens.items()},
        "top_marines_overdue":   {k: int(v) for k, v in top_marines.items()},
        "nmc_items":             nmc_recs,
        "shortage_items":        short_recs,
        "sensitive_stale_lateral":stale_recs,
    }


def _fallback_brief(scenario: dict, summary: dict) -> str:
    overdue_total = summary["overdue_total"]
    by_sens = summary["overdue_by_sensitivity"]
    top_marines = summary["top_marines_overdue"]
    nmc = summary["nmc_items"][:5]
    shortage = summary["shortage_items"][:5]
    stale = summary["sensitive_stale_lateral"][:5]
    top_marine_lines = [f"- **{m}** — {c} overdue" for m, c in top_marines.items()]
    nmc_lines = [
        f"- **{r['nomenclature']}** ({r['nsn']}) — qty {r['qty_on_hand']}/{r['qty_required']}, "
        f"cond **{r['condition_code']}**, loc {r['location_id']}, custody {r['responsible_marine']}"
        for r in nmc
    ]
    short_lines = [
        f"- **{r['nomenclature']}** ({r['nsn']}) — short **{r['shortage']}** ({r['qty_on_hand']}/{r['qty_required']}), "
        f"loc {r['location_id']}"
        for r in shortage
    ]
    stale_lines = [
        f"- **{r['nomenclature']}** ({r['nsn']}) — class {r['sensitivity_class']}, "
        f"{r['days_since_lateral_transfer']} days since last lateral transfer, "
        f"loc {r['location_id']}, custody {r['responsible_marine']}"
        for r in stale
    ]
    return (
        f"### BLUF\n"
        f"**{scenario.get('title', 'Supply NCO brief')} — {overdue_total:,} of "
        f"{summary['total_items']:,} items are outside their inventory cadence; "
        f"accountability posture is AMBER.**\n\n"
        f"### Items overdue for inventory\n"
        + "\n".join(f"- {k}: **{v}** items overdue" for k, v in by_sens.items())
        + "\n\nTop responsible Marines by overdue count:\n"
        + "\n".join(top_marine_lines) + "\n\n"
        f"### NMC-impacting shortages\n"
        + ("\n".join(nmc_lines) if nmc_lines else "_No NMC-impacting items detected._")
        + "\n\nAdditional shortages worth chasing:\n"
        + ("\n".join(short_lines) if short_lines else "_No quantity shortages._")
        + "\n\n"
        f"### Sensitive-item & lateral-transfer flags\n"
        + ("\n".join(stale_lines) if stale_lines
           else "_No sensitive items beyond the 60-day lateral-transfer threshold._")
        + "\n\n"
        f"### Recommended actions for the supply NCO\n"
        f"1. Direct **{next(iter(top_marines), 'top responsible Marine')}** to close out the overdue inventory backlog before EOB; pair with the duty NCO.\n"
        f"2. Pull the top-5 NMC end items for an immediate condition recheck and cross-reference with the Class IX shortage list above.\n"
        f"3. Schedule lateral-transfer cycles for the sensitive items above; prioritize **ARM-101 / ARM-102 / COMSEC-1**.\n"
    )


def load_cached_briefs() -> dict[str, str]:
    if CACHED_BRIEFS_PATH.exists():
        try:
            return json.loads(CACHED_BRIEFS_PATH.read_text())
        except Exception:
            return {}
    return {}


def generate_brief(scenario: dict, df: pd.DataFrame, *, use_cache: bool = True) -> dict:
    """Return {"brief": str, "source": "cache"|"hero"|"fallback"}."""
    cached = load_cached_briefs() if use_cache else {}
    if cached.get(scenario["id"]):
        return {"brief": cached[scenario["id"]], "source": "cache"}

    summary = _summarize(df)
    prompt = (
        f"Scenario: {scenario.get('title', '')}\n"
        f"Frame: {scenario.get('frame', '')}\n\n"
        f"INVENTORY SUMMARY (JSON):\n{json.dumps(summary, indent=2, default=str)}\n\n"
        "Compose the Readiness & Lateral Transfer Brief now."
    )
    msgs = [
        {"role": "system", "content": HERO_SYSTEM},
        {"role": "user",   "content": prompt},
    ]

    def _go() -> str:
        return chat(msgs, model="gpt-5.4", temperature=0.4)

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            text = ex.submit(_go).result(timeout=HERO_TIMEOUT_S)
        if text and "BLUF" in text:
            # persist back into cache for next run
            try:
                briefs = load_cached_briefs()
                briefs[scenario["id"]] = text
                CACHED_BRIEFS_PATH.write_text(json.dumps(briefs, indent=2))
            except Exception:
                pass
            return {"brief": text, "source": "hero"}
    except Exception:
        pass
    return {"brief": _fallback_brief(scenario, summary), "source": "fallback"}
