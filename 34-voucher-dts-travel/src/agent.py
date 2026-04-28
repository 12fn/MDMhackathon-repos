# VOUCHER — DTS + Citi Manager travel program validation
# Part of the MDM 2026 Hackathon Templates (https://github.com/12fn/MDMhackathon-repos)
# MIT licensed. Built on GAI (Government Acquisitions, Inc.) + Kamiwaza (https://www.kamiwaza.ai/).
"""VOUCHER agent — two-tier travel-program QA pipeline.

Tier 1 (chat_json):  Per-record validation — typed JSON verdict per DTS record:
                     issues_found[], severity, auto_correctable, recommended_action,
                     confidence.

Tier 2 (chat):       Hero "Travel Program Quarterly Brief" for the unit S-1
                     (gpt-5.4, 35s wall-clock timeout, cache-first).

A deterministic rule-based baseline backstops both tiers so the UI always
renders a populated issues table and a complete brief — even if the LLM is
unavailable, slow, or returns malformed JSON.
"""
from __future__ import annotations

import concurrent.futures
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.kamiwaza_client import chat, chat_json  # noqa: E402

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
CACHED_BRIEFS_PATH = DATA_DIR / "cached_briefs.json"
CACHED_VALIDATIONS_PATH = DATA_DIR / "cached_validations.json"

# Hero LLM call timeouts (seconds).
HERO_CALL_TIMEOUT_S = 35.0
PER_RECORD_CALL_TIMEOUT_S = 12.0

# Issue taxonomy — matches data/generate.py seed tags
ISSUE_TAGS = [
    "amount_mismatch",
    "missing_receipt",
    "rate_above_per_diem",
    "non_authorized_expense",
    "card_charge_no_voucher",
    "voucher_no_card_charge",
    "duplicate_charge",
]

SEVERITY_BY_ISSUE = {
    "amount_mismatch":         "warn",
    "missing_receipt":         "warn",
    "rate_above_per_diem":     "warn",
    "non_authorized_expense":  "escalate",
    "card_charge_no_voucher":  "escalate",
    "voucher_no_card_charge":  "warn",
    "duplicate_charge":        "escalate",
}

DOLLAR_EXPOSURE_BY_ISSUE = {
    "amount_mismatch":         220,
    "missing_receipt":         175,
    "rate_above_per_diem":     290,
    "non_authorized_expense":  180,
    "card_charge_no_voucher":  110,
    "voucher_no_card_charge":  145,
    "duplicate_charge":        165,
}


# ─────────────────────────────────────────────────────────────────────────────
# I/O helpers
# ─────────────────────────────────────────────────────────────────────────────
def load_dts_records() -> list[dict]:
    """Load DTS records from CSV, restoring voucher_lines as parsed JSON.

    Real DTS schema columns (JTR-aligned snake_case):
      doc_number, ta_number, traveler_edipi, traveler_name, traveler_grade,
      ao_edipi, ao_name, trip_purpose, trip_start, trip_end, status,
      total_authorized, total_voucher, mode_of_travel.

    The validator/UI code historically used `record_id`, `voucher_total`,
    `depart_date`, `return_date`, `trip_reason`, `transport_mode`. We expose
    BOTH the real (JTR-aligned) names AND those legacy aliases so neither tier
    has to know about the schema rename.
    """
    out: list[dict] = []
    p = DATA_DIR / "dts_records.csv"
    with p.open() as f:
        for row in csv.DictReader(f):
            try:
                row["voucher_lines"] = json.loads(row.pop("voucher_lines_json", "[]"))
            except Exception:
                row["voucher_lines"] = []
            for k in ("nights", "per_diem_lodging_ceiling", "per_diem_mie"):
                try:
                    row[k] = int(row[k])
                except Exception:
                    pass
            # Total fields — accept either new (total_voucher / total_authorized)
            # or legacy (voucher_total) column.
            try:
                row["total_voucher"] = float(row.get("total_voucher",
                                                    row.get("voucher_total", 0)) or 0.0)
            except Exception:
                row["total_voucher"] = 0.0
            try:
                row["total_authorized"] = float(row.get("total_authorized", 0) or 0.0)
            except Exception:
                row["total_authorized"] = 0.0
            # Legacy alias used by the validator + UI
            row["voucher_total"] = row["total_voucher"]
            # record_id alias — real DTS field is doc_number (6 letters + 6 digits)
            row["record_id"] = row.get("doc_number") or row.get("record_id", "")
            # date aliases
            row["depart_date"] = row.get("trip_start") or row.get("depart_date", "")
            row["return_date"] = row.get("trip_end") or row.get("return_date", "")
            # purpose / mode aliases
            row["trip_reason"] = row.get("trip_purpose") or row.get("trip_reason", "")
            row["transport_mode"] = row.get("mode_of_travel") or row.get("transport_mode", "")
            row["seeded_issues"] = [t for t in (row.get("seeded_issues") or "").split(",") if t]
            out.append(row)
    return out


def load_citi_transactions() -> list[dict]:
    """Load Citi GTCC transactions. The new schema links via `linked_doc_number`
    (real DTS document number). Legacy code expects `linked_dts_record` — alias
    both directions for backward compatibility."""
    out: list[dict] = []
    p = DATA_DIR / "citi_statements.csv"
    with p.open() as f:
        for row in csv.DictReader(f):
            try:
                row["amount"] = float(row["amount"])
            except Exception:
                row["amount"] = 0.0
            # Alias new (linked_doc_number) <-> legacy (linked_dts_record)
            link = row.get("linked_doc_number") or row.get("linked_dts_record", "")
            row["linked_doc_number"] = link
            row["linked_dts_record"] = link
            out.append(row)
    return out


def load_per_diem() -> dict[str, dict]:
    p = DATA_DIR / "per_diem_rates.json"
    raw = json.loads(p.read_text())
    return {r["city"]: r for r in raw["rates"]}


def load_manifest() -> dict:
    p = DATA_DIR / "manifest.json"
    if not p.exists():
        return {"scenarios": [], "dts_records": 0, "citi_transactions": 0}
    return json.loads(p.read_text())


def load_cached_briefs() -> dict[str, dict]:
    if not CACHED_BRIEFS_PATH.exists():
        return {}
    try:
        return json.loads(CACHED_BRIEFS_PATH.read_text())
    except Exception:
        return {}


def load_cached_validations() -> dict[str, dict] | None:
    if not CACHED_VALIDATIONS_PATH.exists():
        return None
    try:
        return json.loads(CACHED_VALIDATIONS_PATH.read_text())
    except Exception:
        return None


def save_cached_validations(validations: list[dict]) -> None:
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "validations": validations,
    }
    CACHED_VALIDATIONS_PATH.write_text(json.dumps(payload, indent=2))


# ─────────────────────────────────────────────────────────────────────────────
# Fuse DTS record with its matching Citi transactions
# ─────────────────────────────────────────────────────────────────────────────
def fuse_record(record: dict, citi_txns: list[dict]) -> dict:
    """Attach the linked Citi transactions to a DTS record."""
    rid = record["record_id"]
    matches = [c for c in citi_txns if c.get("linked_dts_record") == rid]
    return {**record, "citi_transactions": matches}


# ─────────────────────────────────────────────────────────────────────────────
# Tier 0 — deterministic baseline validator (always runs first)
# ─────────────────────────────────────────────────────────────────────────────
NON_AUTHORIZED_KEYWORDS = [
    "casino", "bellagio", "kay jewelers", "liquor", "amc theaters",
    "best buy", "cabo wabo",
]


def baseline_validate(record: dict, per_diem: dict[str, dict]) -> dict:
    """Rule-based validation. Output schema matches the LLM tier."""
    issues: list[str] = []
    voucher_total = float(record.get("voucher_total") or 0.0)
    citi = record.get("citi_transactions", [])
    # M&IE is paid via per-diem, not voucher line — exclude meals + non-authorized
    # charges from the reconciliation total. Phantom voucher lines (note set)
    # are ALSO excluded — they're already covered by their own seeded issue tag.
    citi_reconcilable = [
        c for c in citi
        if c.get("merchant_category") not in ("meals", "non_authorized")
    ]
    citi_sum = sum(float(c.get("amount") or 0.0) for c in citi_reconcilable)
    voucher_reconcilable_total = sum(
        float(l.get("amount", 0))
        for l in record.get("voucher_lines", [])
        if l.get("category") not in ("mie", "incidentals")
        and not l.get("note")  # exclude phantom / receipt-missing lines
    )

    # 1. Amount mismatch (>$5 AND >2%) — compare reconcilable totals only
    diff = voucher_reconcilable_total - citi_sum
    if (abs(diff) > 5.0
            and voucher_reconcilable_total > 0
            and abs(diff) / voucher_reconcilable_total > 0.02):
        issues.append("amount_mismatch")

    # 2. Missing receipt (line >$75 with note 'receipt_missing' or no card backup
    #    in the lodging category)
    for line in record.get("voucher_lines", []):
        if (line.get("note") == "receipt_missing"
                or (line.get("amount", 0) > 75
                    and line.get("category") == "lodging"
                    and not any(c["merchant_category"] == "lodging" for c in citi))):
            issues.append("missing_receipt")
            break

    # 3. Rate above per-diem (lodging line rate > city ceiling)
    city = record.get("tdy_city", "")
    ceiling = per_diem.get(city, {}).get("lodging_per_night")
    if ceiling:
        for line in record.get("voucher_lines", []):
            if line.get("category") == "lodging":
                rate = float(line.get("rate_per_unit") or 0)
                if rate > ceiling * 1.10:  # 10% tolerance
                    issues.append("rate_above_per_diem")
                    break

    # 4. Non-authorized expense (Citi merchant matches blocklist or category)
    for c in citi:
        merch = (c.get("merchant") or "").lower()
        if c.get("merchant_category") == "non_authorized" or any(
                kw in merch for kw in NON_AUTHORIZED_KEYWORDS):
            issues.append("non_authorized_expense")
            break

    # 5. Card charge with no matching voucher — proxy: a Citi line whose
    #    category isn't represented in voucher_lines AND isn't 'meals' (meals are
    #    paid via M&IE not as a separate voucher line)
    voucher_cats = {l.get("category") for l in record.get("voucher_lines", [])}
    for c in citi:
        cat = c.get("merchant_category")
        if cat in (None, "meals", "lodging", "airfare", "rental_car", "ground_trans"):
            continue  # legitimate categories
        # Anything else (incl. unknown vendors like Best Buy) → flag
        if cat not in voucher_cats:
            issues.append("card_charge_no_voucher")
            break
    # Also: explicit Best Buy / Home Depot / etc. with no voucher reimbursement
    # category match
    for c in citi:
        merch = (c.get("merchant") or "").upper()
        if any(kw in merch for kw in ("BEST BUY", "HOME DEPOT", "STAPLES", "TARGET")):
            if "card_charge_no_voucher" not in issues:
                issues.append("card_charge_no_voucher")
            break

    # 6. Voucher line with no card charge (note 'claimed_no_card_match')
    for line in record.get("voucher_lines", []):
        if line.get("note") == "claimed_no_card_match":
            issues.append("voucher_no_card_charge")
            break

    # 7. Duplicate charge (same merchant + same amount within 24h)
    for i, a in enumerate(citi):
        for b in citi[i + 1:]:
            if (a.get("merchant") == b.get("merchant")
                    and abs(float(a.get("amount", 0)) - float(b.get("amount", 0))) < 0.01):
                issues.append("duplicate_charge")
                break
        if "duplicate_charge" in issues:
            break

    # De-dup, preserve order
    seen = set()
    issues = [i for i in issues if not (i in seen or seen.add(i))]

    # Severity = max of constituent severities
    severity = "info"
    for i in issues:
        s = SEVERITY_BY_ISSUE.get(i, "warn")
        if s == "escalate":
            severity = "escalate"
            break
        elif s == "warn" and severity != "escalate":
            severity = "warn"

    if not issues:
        rec_action = "Clean — no further action."
        auto_correctable = True
    else:
        actions = {
            "amount_mismatch":         "Reconcile DTS voucher against Citi sum; correct in DTS.",
            "missing_receipt":         "Request receipt from traveler; attach in DTS within 5 days.",
            "rate_above_per_diem":     "Lodging exceeds GSA ceiling; require justification memo.",
            "non_authorized_expense":  "Refer to Agency Program Coordinator (APC) for cardholder counseling.",
            "card_charge_no_voucher":  "Identify transaction or open dispute with Citi; possible mis-use.",
            "voucher_no_card_charge":  "Verify reimbursement is supported; potential fraud indicator.",
            "duplicate_charge":        "Open duplicate-billing dispute with Citi; pull merchant detail.",
        }
        rec_action = actions[issues[0]]
        auto_correctable = severity != "escalate"

    dollar_exposure = round(sum(DOLLAR_EXPOSURE_BY_ISSUE.get(i, 0) for i in issues), 2)
    confidence = 0.62 if issues else 0.90

    return {
        "record_id": record["record_id"],
        "issues_found": issues,
        "severity": severity,
        "auto_correctable": auto_correctable,
        "recommended_action": rec_action,
        "confidence": confidence,
        "dollar_exposure": dollar_exposure,
        "_source": "baseline",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Tier 1 — LLM per-record validator (chat_json)
# ─────────────────────────────────────────────────────────────────────────────
PER_RECORD_SYSTEM = """You are VOUCHER, a travel-program QA agent for a USMC unit S-1.
You audit one DTS record (authorization + voucher) at a time, fused with the
Citi Manager government-travel-card transactions linked to that traveler.

Detect any of the following issue tags. Use ONLY these tags verbatim:
  - amount_mismatch        : voucher total differs from Citi sum by >$5 AND >2%
  - missing_receipt        : voucher line >$75 has no Citi card backup
  - rate_above_per_diem    : lodging or M&IE rate exceeds GSA per-diem ceiling
  - non_authorized_expense : Citi charge at a non-travel merchant (jewelry,
                              casino, liquor, big-box electronics, theater)
  - card_charge_no_voucher : Citi charge in TDY window with no matching voucher line
  - voucher_no_card_charge : voucher line claimed but no Citi charge present
  - duplicate_charge       : same vendor + same amount within 24 hours

Return JSON ONLY (no prose) with EXACTLY these keys:
  - record_id           : the record_id verbatim
  - issues_found        : list of issue tags from the taxonomy above (may be empty)
  - severity            : "info" | "warn" | "escalate"
                          (escalate if any: non_authorized_expense, duplicate_charge,
                           card_charge_no_voucher; warn if any other issues; info if clean)
  - auto_correctable    : true if S-1 can fix in DTS without traveler interview
  - recommended_action  : ONE sentence (<=160 chars), imperative voice
  - confidence          : float 0..1
"""


def _per_record_user_prompt(record: dict, per_diem: dict[str, dict]) -> str:
    city = record.get("tdy_city", "")
    pd_row = per_diem.get(city, {})
    citi_brief = [
        {"merchant": c["merchant"], "category": c["merchant_category"],
         "amount": c["amount"], "post_date": c["post_date"]}
        for c in record.get("citi_transactions", [])
    ]
    citi_sum = round(sum(c["amount"] for c in citi_brief), 2)
    return (
        f"DTS RECORD:\n"
        f"  record_id   : {record['record_id']}\n"
        f"  unit        : {record.get('unit')}\n"
        f"  traveler    : {record.get('traveler_rank')} {record.get('traveler_name')}\n"
        f"  city        : {city}  (lodging ceiling ${pd_row.get('lodging_per_night','?')}/night, "
        f"M&IE ${pd_row.get('mie_per_day','?')}/day)\n"
        f"  trip_window : {record.get('depart_date')} -> {record.get('return_date')} "
        f"({record.get('nights')} nights)\n"
        f"  voucher_total : ${record.get('voucher_total'):.2f}\n"
        f"  voucher_lines :\n"
        + "\n".join(f"    - {l}" for l in record.get('voucher_lines', []))
        + f"\n\nCITI TRANSACTIONS (sum ${citi_sum:.2f}):\n"
        + "\n".join(f"  - {c}" for c in citi_brief)
        + "\n\nReturn the JSON verdict now."
    )


def _llm_validate(record: dict, per_diem: dict[str, dict]) -> dict | None:
    """Run a bounded LLM validation. Returns None on timeout / parse failure."""
    msgs = [
        {"role": "system", "content": PER_RECORD_SYSTEM},
        {"role": "user", "content": _per_record_user_prompt(record, per_diem)},
    ]

    def _go() -> dict:
        return chat_json(
            msgs,
            schema_hint=(
                '{"record_id":str,"issues_found":[str],"severity":str,'
                '"auto_correctable":bool,"recommended_action":str,"confidence":float}'
            ),
            temperature=0.15,
            max_tokens=400,
        )

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(_go).result(timeout=PER_RECORD_CALL_TIMEOUT_S)
    except (concurrent.futures.TimeoutError, Exception):
        return None


def validate_record(record: dict, per_diem: dict[str, dict],
                    *, use_llm: bool = True) -> dict:
    """Validate one fused record. LLM result overlays the deterministic baseline."""
    base = baseline_validate(record, per_diem)
    if not use_llm:
        return base

    raw = _llm_validate(record, per_diem)
    if not raw or not isinstance(raw, dict):
        return base

    out = dict(base)
    # Overlay LLM fields where present and well-typed
    if isinstance(raw.get("issues_found"), list):
        # Only accept tags from our taxonomy
        clean = [t for t in raw["issues_found"] if t in ISSUE_TAGS]
        # Union with baseline's findings — LLM adds nuance, baseline is the
        # safety net (we never lose a deterministic flag).
        merged: list[str] = []
        for t in (base["issues_found"] + clean):
            if t not in merged:
                merged.append(t)
        out["issues_found"] = merged
    if raw.get("severity") in ("info", "warn", "escalate"):
        # Take max severity between LLM and baseline
        order = {"info": 0, "warn": 1, "escalate": 2}
        out["severity"] = max(out["severity"], raw["severity"], key=lambda s: order[s])
    if isinstance(raw.get("auto_correctable"), bool):
        out["auto_correctable"] = raw["auto_correctable"] and out["severity"] != "escalate"
    if isinstance(raw.get("recommended_action"), str) and raw["recommended_action"].strip():
        out["recommended_action"] = raw["recommended_action"].strip()[:240]
    if isinstance(raw.get("confidence"), (int, float)):
        try:
            out["confidence"] = max(0.0, min(1.0, float(raw["confidence"])))
        except Exception:
            pass
    out["_source"] = "llm"
    out["dollar_exposure"] = round(
        sum(DOLLAR_EXPOSURE_BY_ISSUE.get(i, 0) for i in out["issues_found"]), 2
    )
    return out


def validate_all(*, scenario_code: str | None = None,
                 use_llm: bool = True,
                 progress_cb=None) -> list[dict]:
    """Run the per-record validator across the whole corpus (or one unit)."""
    dts = load_dts_records()
    citi = load_citi_transactions()
    per_diem = load_per_diem()
    if scenario_code:
        dts = [r for r in dts if r["unit_code"] == scenario_code]
    out: list[dict] = []
    for i, r in enumerate(dts):
        fused = fuse_record(r, citi)
        verdict = validate_record(fused, per_diem, use_llm=use_llm)
        # Stash a short side-by-side snippet for the UI drilldown
        verdict["_record"] = {
            "record_id": fused["record_id"],
            "unit": fused.get("unit"),
            "unit_code": fused.get("unit_code"),
            "traveler": f"{fused.get('traveler_rank')} {fused.get('traveler_name')}",
            "trip_reason": fused.get("trip_reason"),
            "tdy_city": fused.get("tdy_city"),
            "depart_date": fused.get("depart_date"),
            "return_date": fused.get("return_date"),
            "voucher_total": fused.get("voucher_total"),
            "voucher_lines": fused.get("voucher_lines"),
            "citi_transactions": fused.get("citi_transactions"),
        }
        out.append(verdict)
        if progress_cb:
            progress_cb(i + 1, len(dts), verdict)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Tier 2 — hero quarterly brief
# ─────────────────────────────────────────────────────────────────────────────
QUARTERLY_BRIEF_SYSTEM = """You are VOUCHER, a travel-program QA agent supporting the unit
S-1 for a USMC battalion / regiment / MEF HQ. You audit DTS authorizations,
vouchers, and Citi Manager government-travel-card statements end-to-end.

Compose a polished one-page TRAVEL PROGRAM QUARTERLY BRIEF in markdown with
these EXACT five section headers, in order:

  ## BLUF
  ## Top Issue Categories
  ## Records to Escalate
  ## Training Opportunities
  ## Recommendation

Constraints:
  - BLUF: state record count, total flagged issues, dollar exposure, # to escalate.
  - Top Issue Categories: bulleted, ranked, with counts.
  - Records to Escalate: bullet specific record_ids by name+rank with the issue tag.
  - Training Opportunities: 3 bullets, each tied to a category surfaced this quarter.
  - Recommendation: a single tight paragraph the S-1 can paste into the next staff brief.
  - End with a one-line classification line: 'CUI // Travel Program Data'.
  - Total length under 400 words. Plain markdown. No code fences. No emoji.
  - Refer to the AI engine as 'the agent' or 'VOUCHER' — do not name underlying models.
"""


def _build_brief_prompt(scenario: dict, validations: list[dict]) -> list[dict]:
    issue_counts: dict[str, int] = {}
    dollar_exposure = 0.0
    escalated_lines: list[str] = []
    for v in validations:
        for tag in v.get("issues_found", []):
            issue_counts[tag] = issue_counts.get(tag, 0) + 1
        dollar_exposure += float(v.get("dollar_exposure") or 0.0)
        if v.get("severity") == "escalate":
            r = v.get("_record", {})
            escalated_lines.append(
                f"- {v['record_id']} | {r.get('traveler')} | {r.get('tdy_city')} | "
                f"flags: {','.join(v['issues_found'])}"
            )
    user_prompt = (
        f"UNIT: {scenario.get('unit')} (code {scenario.get('unit_code')})\n"
        f"QUARTER: {scenario.get('quarter')}\n"
        f"RECORDS PROCESSED: {len(validations)}\n"
        f"ISSUE COUNTS BY CATEGORY: {json.dumps(issue_counts)}\n"
        f"TOTAL DOLLAR EXPOSURE: ${dollar_exposure:,.2f}\n\n"
        f"ESCALATED RECORDS:\n" + "\n".join(escalated_lines[:15]) + "\n\n"
        "Compose the quarterly brief now."
    )
    return [
        {"role": "system", "content": QUARTERLY_BRIEF_SYSTEM},
        {"role": "user", "content": user_prompt},
    ]


def _call_chat_with_timeout(msgs: list[dict], timeout_s: float, **kw) -> str | None:
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(lambda: chat(msgs, **kw)).result(timeout=timeout_s)
    except (concurrent.futures.TimeoutError, Exception):
        return None


def _fallback_brief(scenario: dict, validations: list[dict]) -> str:
    """Deterministic brief used when the LLM hero call times out / errors AND
    no cached brief exists for this scenario."""
    n = len(validations)
    issue_counts: dict[str, int] = {}
    dollar_exposure = 0.0
    escalations = []
    for v in validations:
        for tag in v.get("issues_found", []):
            issue_counts[tag] = issue_counts.get(tag, 0) + 1
        dollar_exposure += float(v.get("dollar_exposure") or 0.0)
        if v.get("severity") == "escalate":
            r = v.get("_record", {})
            escalations.append((v["record_id"], r.get("traveler"),
                                ",".join(v["issues_found"])))
    issue_block = "\n".join(
        f"- **{k.replace('_',' ').upper()}**: {c} record(s)"
        for k, c in sorted(issue_counts.items(), key=lambda kv: -kv[1])
    ) or "- (no issues found this quarter)"
    esc_block = "\n".join(
        f"- `{rid}` — {nm} ({tags})" for (rid, nm, tags) in escalations[:10]
    ) or "- (none)"
    return (
        f"# Travel Program Quarterly Brief — {scenario.get('unit')} ({scenario.get('quarter')})\n\n"
        f"## BLUF\n"
        f"Of **{n} DTS travel records** processed this quarter, the agent flagged "
        f"**{sum(issue_counts.values())} issues** across "
        f"**{len(issue_counts)} categor{'y' if len(issue_counts)==1 else 'ies'}**, "
        f"with an estimated **${dollar_exposure:,.2f}** in financial exposure. "
        f"S-1 attention is recommended on **{len(escalations)} escalation(s)**.\n\n"
        f"## Top Issue Categories\n{issue_block}\n\n"
        f"## Records to Escalate\n{esc_block}\n\n"
        f"## Training Opportunities\n"
        f"- Reinforce per-diem ceiling guidance at the next S-1 brief.\n"
        f"- Remind cardholders that Citi GTC is **official-travel-only**.\n"
        f"- Push the voucher-within-5-days SOP — orphan card charges accumulate when vouchers lag.\n\n"
        f"## Recommendation\n"
        f"S-1 review the {len(escalations)} escalated record(s) by end of next pay period, "
        f"return any auto-correctable findings to the traveler, and brief the unit CO on the "
        f"dollar-exposure trend at the next staff meeting.\n\n"
        f"_Originator: VOUCHER agent / S-1 travel-program QA cell. "
        f"Classification: **CUI // Travel Program Data**._\n"
    )


def generate_brief(scenario: dict, validations: list[dict],
                   *, use_cache: bool = True, hero: bool = True) -> dict:
    """Tier 2: cache-first hero quarterly brief.

    Strategy (so the demo never hangs on a spinner):
      1. If a cached brief exists for this scenario, serve it instantly.
      2. Otherwise, run the hero gpt-5.4 call under wall-clock timeout.
      3. On timeout / err, run the standard mini chain under timeout.
      4. Last resort: render a deterministic brief from the validations.
    """
    sid = scenario.get("scenario_id")
    cached = load_cached_briefs()
    if use_cache and sid in cached and cached[sid].get("brief"):
        return cached[sid]

    msgs = _build_brief_prompt(scenario, validations)

    if hero:
        text = _call_chat_with_timeout(
            msgs, HERO_CALL_TIMEOUT_S,
            model="gpt-5.4", temperature=0.4, max_tokens=900,
        )
        if text and "BLUF" in text:
            payload = _persist_brief(scenario, text, source="gpt-5.4",
                                     validations=validations)
            return payload

    text = _call_chat_with_timeout(msgs, HERO_CALL_TIMEOUT_S,
                                   temperature=0.4, max_tokens=900)
    if text and "BLUF" in text:
        payload = _persist_brief(scenario, text, source="default-chain",
                                 validations=validations)
        return payload

    return {
        "scenario_id": sid,
        "unit": scenario.get("unit"),
        "unit_code": scenario.get("unit_code"),
        "quarter": scenario.get("quarter"),
        "brief": _fallback_brief(scenario, validations),
        "source": "deterministic-fallback",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "record_count": len(validations),
    }


def _persist_brief(scenario: dict, brief: str, *, source: str,
                   validations: list[dict]) -> dict:
    cached = load_cached_briefs()
    payload = {
        "scenario_id": scenario.get("scenario_id"),
        "unit": scenario.get("unit"),
        "unit_code": scenario.get("unit_code"),
        "quarter": scenario.get("quarter"),
        "brief": brief,
        "source": source,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "record_count": len(validations),
    }
    cached[scenario.get("scenario_id")] = payload
    try:
        CACHED_BRIEFS_PATH.write_text(json.dumps(cached, indent=2))
    except Exception:
        pass
    return payload


# ─────────────────────────────────────────────────────────────────────────────
# CLI smoke-test
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("VOUCHER agent — baseline-only smoke test (no LLM calls)")
    results = validate_all(use_llm=False)
    sev_counts = {}
    issue_counts = {}
    for r in results:
        sev_counts[r["severity"]] = sev_counts.get(r["severity"], 0) + 1
        for t in r["issues_found"]:
            issue_counts[t] = issue_counts.get(t, 0) + 1
    print(f"  records validated: {len(results)}")
    print(f"  severity counts:   {sev_counts}")
    print(f"  issue counts:      {issue_counts}")
