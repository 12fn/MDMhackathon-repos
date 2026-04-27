"""Synthesize VOUCHER demo dataset.

Produces:
  - data/per_diem_rates.json : GSA-style per-diem rates for 14 named cities
  - data/dts_records.csv     : 100 DTS authorization + voucher pairs across
                               3 unit-quarter scenarios (Camp Pendleton, Camp
                               Lejeune, MARFORPAC HQ — 1 quarter each).
  - data/citi_statements.csv : 100 Citi Manager card transactions, partially
                               linked to those vouchers, with seeded mismatches:
                               * amount mismatches (5 records)
                               * missing receipts on lines >$75 (4 records)
                               * lodging rates above per-diem (4 records)
                               * non-authorized expenses (4 records)
                               * orphan card charges (4 records)
                               * orphan voucher lines (4 records)
                               * duplicate charges (3 records)
  - data/cached_briefs.json  : pre-computed quarterly narrative briefs for
                               each of the 3 scenarios (cache-first pattern).

Deterministic: random.Random(1776).
"""
from __future__ import annotations

import json
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent

# ──────────────────────────────────────────────────────────────────────────────
# Reference tables
# ──────────────────────────────────────────────────────────────────────────────
PER_DIEM = [
    # (city, state, lodging_$/night, mie_$/day) — GSA-plausible FY26 rates
    ("San Diego",        "CA", 217, 79),
    ("Oceanside",        "CA", 174, 74),
    ("Twentynine Palms", "CA", 110, 64),
    ("Quantico",         "VA", 184, 79),
    ("Arlington",        "VA", 277, 84),
    ("Norfolk",          "VA", 134, 74),
    ("Jacksonville",     "NC", 110, 64),
    ("Camp Lejeune",     "NC", 110, 64),
    ("Honolulu",         "HI", 252, 134),
    ("Okinawa",          "JP", 178, 124),
    ("Yuma",             "AZ", 102, 64),
    ("Beaufort",         "SC", 110, 64),
    ("Washington",       "DC", 277, 84),
    ("Albany",           "GA", 105, 64),
]

UNITS = [
    {"unit": "1st Marine Division (Camp Pendleton)", "code": "1MARDIV",
     "quarter": "FY26-Q2", "city_pool": ["San Diego", "Oceanside",
                                         "Twentynine Palms", "Yuma",
                                         "Honolulu", "Quantico"]},
    {"unit": "II MEF Force HQ (Camp Lejeune)", "code": "IIMEF",
     "quarter": "FY26-Q2", "city_pool": ["Camp Lejeune", "Jacksonville",
                                         "Norfolk", "Quantico", "Arlington",
                                         "Beaufort", "Washington"]},
    {"unit": "MARFORPAC HQ (Camp H.M. Smith, HI)", "code": "MARFORPAC",
     "quarter": "FY26-Q2", "city_pool": ["Honolulu", "Okinawa", "San Diego",
                                          "Quantico", "Arlington", "Washington"]},
]

# Plausible rank distribution for synthetic Marines
RANKS = ["LCpl", "Cpl", "Sgt", "SSgt", "GySgt", "MSgt", "1stSgt",
         "WO1", "CWO2", "CWO3",
         "2ndLt", "1stLt", "Capt", "Maj", "LtCol", "Col"]

LAST_NAMES = ["MARTINEZ", "JOHNSON", "WILLIAMS", "BROWN", "JONES", "GARCIA",
              "MILLER", "DAVIS", "RODRIGUEZ", "WILSON", "ANDERSON", "TAYLOR",
              "THOMAS", "MOORE", "JACKSON", "MARTIN", "LEE", "PEREZ",
              "THOMPSON", "WHITE", "HARRIS", "SANCHEZ", "CLARK", "RAMIREZ",
              "LEWIS", "ROBINSON", "WALKER", "YOUNG", "ALLEN", "KING",
              "WRIGHT", "SCOTT", "TORRES", "NGUYEN", "HILL", "FLORES",
              "GREEN", "ADAMS", "NELSON", "BAKER", "HALL", "RIVERA",
              "CAMPBELL", "MITCHELL", "CARTER", "ROBERTS"]

FIRST_INITIAL = list("ABCDEFGHJKLMNOPRSTW")

# Travel reasons (plausible for the LOGCOM/MARFORPAC mission set)
TRIP_REASONS = [
    "TAD — Conference attendance",
    "TAD — Training course",
    "TAD — School / PME",
    "TAD — Inspection / IG team",
    "TAD — Liaison visit",
    "TAD — Site survey",
    "TAD — Working group",
    "TAD — Equipment fielding",
    "PCS in-route travel",
    "TAD — Funeral honors detail",
]

# Authorized travel-related MCC categories vs. flagged categories
AUTHORIZED_VENDORS = [
    ("MARRIOTT GAITHERSBG MD",         "lodging"),
    ("HILTON GARDEN INN",              "lodging"),
    ("RESIDENCE INN BY MARRIOTT",      "lodging"),
    ("HAMPTON INN",                    "lodging"),
    ("SHERATON ARLINGTON HOTEL",       "lodging"),
    ("EMBASSY SUITES",                 "lodging"),
    ("DELTA AIR LINES",                "airfare"),
    ("UNITED AIRLINES",                "airfare"),
    ("AMERICAN AIRLINES",              "airfare"),
    ("SOUTHWEST AIRLINES",             "airfare"),
    ("HERTZ RENT-A-CAR",               "rental_car"),
    ("ENTERPRISE RENT-A-CAR",          "rental_car"),
    ("AVIS RENT-A-CAR",                "rental_car"),
    ("BUDGET RENT-A-CAR",              "rental_car"),
    ("UBER TRIP",                      "ground_trans"),
    ("LYFT * RIDE",                    "ground_trans"),
    ("YELLOW CAB CO",                  "ground_trans"),
    ("WMATA SMARTRIP",                 "ground_trans"),
    ("CHILIS RESTAURANT",              "meals"),
    ("APPLEBEES NEIGHBORHOOD GRILL",   "meals"),
    ("OLIVE GARDEN",                   "meals"),
    ("CRACKER BARREL",                 "meals"),
    ("STARBUCKS",                      "meals"),
    ("PANERA BREAD",                   "meals"),
    ("SUBWAY SANDWICHES",              "meals"),
    ("CHIPOTLE MEXICAN GRILL",         "meals"),
]

NON_AUTHORIZED_VENDORS = [
    ("CABO WABO CANTINA",              "non_authorized"),
    ("BELLAGIO CASINO LAS VEGAS",      "non_authorized"),
    ("KAY JEWELERS",                   "non_authorized"),
    ("BEST BUY #0481",                 "non_authorized"),
    ("LIQUOR BARN OUTLET",             "non_authorized"),
    ("AMC THEATERS #284",              "non_authorized"),
    ("WALMART SUPERCENTER",            "non_authorized"),  # MCC ambiguous
]


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
def per_diem_lookup(city: str) -> tuple[int, int]:
    for c, _, lod, mie in PER_DIEM:
        if c == city:
            return lod, mie
    return 110, 64  # standard CONUS default


def random_date(rng: random.Random, start: datetime, end: datetime) -> datetime:
    delta = (end - start).total_seconds()
    return start + timedelta(seconds=rng.uniform(0, delta))


def make_traveler(rng: random.Random) -> tuple[str, str]:
    rank = rng.choice(RANKS)
    name = f"{rng.choice(FIRST_INITIAL)}. {rng.choice(LAST_NAMES)}"
    return rank, name


def fmt_money(x: float) -> float:
    return round(x, 2)


# ──────────────────────────────────────────────────────────────────────────────
# Generators
# ──────────────────────────────────────────────────────────────────────────────
def generate_dts_and_citi(rng: random.Random) -> tuple[list[dict], list[dict]]:
    """Generate fused DTS records + matching/mismatched Citi card transactions.

    Returns (dts_records, citi_transactions).
    """
    dts: list[dict] = []
    citi: list[dict] = []

    # Spread 100 trips roughly evenly across 3 units (33 / 33 / 34)
    per_unit_counts = [33, 33, 34]

    record_seq = 0
    citi_seq = 0

    # Quarter window: 1 Jan 2026 -> 31 Mar 2026 (FY26-Q2)
    q_start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    q_end   = datetime(2026, 3, 31, tzinfo=timezone.utc)

    # Pre-decide which records carry which seeded issues so the totals are
    # deterministic and cover every issue type.  Indices are global record_seq.
    seeded_issues = {
        # amount mismatch — Citi sum off by >$5/2% from voucher sum
        "amount_mismatch":      [3, 17, 41, 62, 88],
        # voucher line >$75 with no Citi backup
        "missing_receipt":      [9, 28, 55, 77],
        # lodging rate above GSA per-diem ceiling
        "rate_above_per_diem":  [12, 31, 49, 84],
        # non-authorized expense (jewelry/casino/liquor/etc) appears in Citi
        "non_authorized":       [7, 26, 58, 91],
        # orphan card charge — Citi charge in TDY window with no matching voucher line
        "card_charge_no_voucher": [22, 47, 70, 95],
        # voucher line claimed but no Citi charge present
        "voucher_no_card_charge": [14, 38, 65, 81],
        # duplicate charges (same vendor + same amount within 24h)
        "duplicate":            [19, 44, 73],
    }
    # Build a flat lookup record_idx -> set of seeded issue tags
    seeded_lookup: dict[int, list[str]] = {}
    for tag, idxs in seeded_issues.items():
        for i in idxs:
            seeded_lookup.setdefault(i, []).append(tag)

    for unit_i, unit in enumerate(UNITS):
        for _ in range(per_unit_counts[unit_i]):
            record_seq += 1
            rec_id = f"DTS-{2026}-{record_seq:05d}"
            tag_list = seeded_lookup.get(record_seq - 1, [])  # 0-indexed seed
            rank, name = make_traveler(rng)
            city = rng.choice(unit["city_pool"])
            lod_rate, mie_rate = per_diem_lookup(city)

            # Trip duration 2-7 nights
            nights = rng.randint(2, 7)
            depart = random_date(rng, q_start, q_end - timedelta(days=nights + 2))
            depart = depart.replace(hour=rng.randint(6, 18), minute=0, second=0, microsecond=0)
            ret = depart + timedelta(days=nights)

            # ── DTS authorized line items ──
            # lodging
            base_lod = lod_rate * (1 + rng.uniform(-0.10, 0.05))  # claim near per-diem
            if "rate_above_per_diem" in tag_list:
                base_lod = lod_rate * rng.uniform(1.18, 1.42)  # clearly above ceiling
            voucher_lodging = fmt_money(base_lod * nights)

            # M&IE — DTS pays 75% on travel days, 100% other days; simplify
            voucher_mie = fmt_money(mie_rate * (nights * 1.0 + 0.5))

            # Airfare or POV mileage
            if city in ("San Diego", "Oceanside", "Twentynine Palms",
                        "Camp Lejeune", "Jacksonville", "Yuma", "Beaufort"):
                # local-ish or POV more likely
                if rng.random() < 0.45:
                    airfare = fmt_money(rng.uniform(280, 720))
                    transport_mode = "AIR"
                else:
                    airfare = fmt_money(rng.uniform(0, 0))
                    transport_mode = "POV"
            else:
                airfare = fmt_money(rng.uniform(420, 1180))
                transport_mode = "AIR"

            # rental car (~50% of trips)
            if rng.random() < 0.55:
                rental = fmt_money(rng.uniform(180, 540))
            else:
                rental = 0.0

            # ground transport (taxi/uber, modest)
            ground = fmt_money(rng.uniform(0, 95))

            # incidentals/baggage
            incidentals = fmt_money(rng.uniform(0, 60))

            voucher_total = fmt_money(voucher_lodging + voucher_mie + airfare + rental
                                       + ground + incidentals)

            # ── Citi card charges ──
            # Default behavior: Citi sums roughly match voucher (within $5).
            citi_records_for_trip: list[dict] = []

            def add_citi(vendor: str, vendor_kind: str, amt: float,
                         date: datetime, last4: str = "1873") -> None:
                nonlocal citi_seq
                citi_seq += 1
                citi_records_for_trip.append({
                    "txn_id": f"CITI-{2026}-{citi_seq:05d}",
                    "card_last4": last4,
                    "traveler_rank": rank,
                    "traveler_name": name,
                    "unit_code": unit["code"],
                    "unit": unit["unit"],
                    "post_date": date.strftime("%Y-%m-%d"),
                    "merchant": vendor,
                    "merchant_category": vendor_kind,
                    "amount": fmt_money(amt),
                    "linked_dts_record": rec_id,
                })

            traveler_last4 = f"{1000 + (record_seq * 7) % 9000:04d}"

            # lodging charge — usually matches voucher
            charged_lodging = voucher_lodging
            if "amount_mismatch" in tag_list:
                # Make Citi total NOT match: extra night charge
                charged_lodging = voucher_lodging + lod_rate * 1.0 + rng.uniform(8, 35)
            if "missing_receipt" in tag_list and rng.random() < 0.5:
                # Drop the lodging line in Citi (we'll add a synthetic >$75 voucher
                # line below that has no card backup)
                pass  # leave voucher claim, do NOT add Citi line for lodging
            else:
                add_citi("MARRIOTT GAITHERSBG MD" if city in ("Arlington","Washington","Quantico")
                         else "HILTON GARDEN INN", "lodging",
                         charged_lodging, depart + timedelta(days=1),
                         last4=traveler_last4)

            # airfare
            if airfare > 0:
                add_citi(rng.choice([
                    "DELTA AIR LINES", "UNITED AIRLINES",
                    "AMERICAN AIRLINES", "SOUTHWEST AIRLINES"]),
                    "airfare", airfare, depart - timedelta(days=2),
                    last4=traveler_last4)

            # rental
            if rental > 0:
                add_citi(rng.choice(["HERTZ RENT-A-CAR", "ENTERPRISE RENT-A-CAR",
                                     "AVIS RENT-A-CAR", "BUDGET RENT-A-CAR"]),
                         "rental_car", rental, depart,
                         last4=traveler_last4)

            # ground transport (split into 1-3 charges)
            if ground > 0:
                ground_left = ground
                while ground_left > 5:
                    leg = min(ground_left, fmt_money(rng.uniform(8, 38)))
                    add_citi(rng.choice(["UBER TRIP", "LYFT * RIDE",
                                          "YELLOW CAB CO", "WMATA SMARTRIP"]),
                             "ground_trans", leg,
                             depart + timedelta(days=rng.randint(0, max(0, nights - 1))),
                             last4=traveler_last4)
                    ground_left -= leg

            # meals on card (M&IE is reimbursed, but Marines often charge meals;
            # plausible for ~half the trips a couple of meal charges hit the card)
            if rng.random() < 0.5 and nights >= 2:
                for _ in range(rng.randint(1, 3)):
                    add_citi(rng.choice(["CHILIS RESTAURANT", "APPLEBEES NEIGHBORHOOD GRILL",
                                          "OLIVE GARDEN", "CRACKER BARREL", "STARBUCKS",
                                          "PANERA BREAD", "SUBWAY SANDWICHES",
                                          "CHIPOTLE MEXICAN GRILL"]),
                             "meals", fmt_money(rng.uniform(8, 65)),
                             depart + timedelta(days=rng.randint(0, max(0, nights - 1))),
                             last4=traveler_last4)

            # ── Inject seeded issues ──
            if "non_authorized" in tag_list:
                vend = rng.choice(NON_AUTHORIZED_VENDORS)
                add_citi(vend[0], "non_authorized",
                         fmt_money(rng.uniform(45, 410)),
                         depart + timedelta(days=rng.randint(0, nights)),
                         last4=traveler_last4)

            if "card_charge_no_voucher" in tag_list:
                # Add a Citi charge in the TDY window that the voucher doesn't claim
                add_citi(rng.choice(["BEST BUY #0481", "STAPLES OFFICE",
                                      "HOME DEPOT #6711", "TARGET T-2204"]),
                         "ground_trans",  # MCC vague enough to need review
                         fmt_money(rng.uniform(38, 240)),
                         depart + timedelta(days=rng.randint(0, nights)),
                         last4=traveler_last4)

            if "duplicate" in tag_list and citi_records_for_trip:
                # Duplicate the lodging charge (same vendor, same amount, +6h)
                base = next((c for c in citi_records_for_trip if c["merchant_category"] == "lodging"),
                             citi_records_for_trip[0])
                citi_seq += 1
                dup = dict(base)
                dup["txn_id"] = f"CITI-{2026}-{citi_seq:05d}"
                # Same post_date; LLM/heuristic should flag as duplicate within 24h
                citi_records_for_trip.append(dup)

            citi.extend(citi_records_for_trip)

            # ── DTS record ──
            voucher_lines = []
            voucher_lines.append({"category": "lodging",
                                  "rate_per_unit": fmt_money(base_lod),
                                  "units": nights,
                                  "amount": voucher_lodging})
            voucher_lines.append({"category": "mie",
                                  "rate_per_unit": mie_rate,
                                  "units": nights,
                                  "amount": voucher_mie})
            if airfare > 0:
                voucher_lines.append({"category": "airfare", "rate_per_unit": airfare,
                                      "units": 1, "amount": airfare})
            if rental > 0:
                voucher_lines.append({"category": "rental_car", "rate_per_unit": rental,
                                      "units": 1, "amount": rental})
            if ground > 0:
                voucher_lines.append({"category": "ground_trans",
                                      "rate_per_unit": ground, "units": 1,
                                      "amount": ground})
            if incidentals > 0:
                voucher_lines.append({"category": "incidentals",
                                      "rate_per_unit": incidentals, "units": 1,
                                      "amount": incidentals})

            # Inject 'voucher_no_card_charge': add a phantom voucher line that
            # has no Citi backup at all.
            if "voucher_no_card_charge" in tag_list:
                phantom_amt = fmt_money(rng.uniform(85, 240))
                voucher_lines.append({"category": "rental_car",
                                      "rate_per_unit": phantom_amt,
                                      "units": 1, "amount": phantom_amt,
                                      "note": "claimed_no_card_match"})
                voucher_total = fmt_money(voucher_total + phantom_amt)

            if "missing_receipt" in tag_list:
                # Add a >$75 line with no Citi backup
                missing_amt = fmt_money(rng.uniform(95, 320))
                voucher_lines.append({"category": "incidentals",
                                      "rate_per_unit": missing_amt, "units": 1,
                                      "amount": missing_amt,
                                      "note": "receipt_missing"})
                voucher_total = fmt_money(voucher_total + missing_amt)

            dts.append({
                "record_id": rec_id,
                "unit_code": unit["code"],
                "unit": unit["unit"],
                "quarter": unit["quarter"],
                "traveler_rank": rank,
                "traveler_name": name,
                "card_last4": traveler_last4,
                "trip_reason": rng.choice(TRIP_REASONS),
                "tdy_city": city,
                "depart_date": depart.strftime("%Y-%m-%d"),
                "return_date": ret.strftime("%Y-%m-%d"),
                "nights": nights,
                "transport_mode": transport_mode,
                "per_diem_lodging_ceiling": lod_rate,
                "per_diem_mie": mie_rate,
                "voucher_total": voucher_total,
                "voucher_lines": voucher_lines,
                "auth_status": "APPROVED",
                "voucher_status": "SUBMITTED",
                "_seeded_issues": tag_list,  # internal hint, used by baseline
            })

    return dts, citi


# ──────────────────────────────────────────────────────────────────────────────
# Cached briefs — pre-compute the hero quarterly narratives
# ──────────────────────────────────────────────────────────────────────────────
def _baseline_brief(unit: dict, dts_subset: list[dict],
                    citi_subset: list[dict]) -> str:
    """Deterministic narrative used when no LLM is available at generate time.

    Same shape the hero LLM call produces. The hero call (when available) will
    overwrite this in cached_briefs.json.
    """
    n = len(dts_subset)
    issue_counts: dict[str, int] = {}
    dollar_exposure = 0.0
    escalations = []
    for r in dts_subset:
        for tag in r.get("_seeded_issues", []):
            issue_counts[tag] = issue_counts.get(tag, 0) + 1
            dollar_exposure += {
                "amount_mismatch": 220,
                "missing_receipt": 175,
                "rate_above_per_diem": 290,
                "non_authorized": 180,
                "card_charge_no_voucher": 110,
                "voucher_no_card_charge": 145,
                "duplicate": 165,
            }.get(tag, 75)
            if tag in ("non_authorized", "duplicate", "card_charge_no_voucher"):
                escalations.append((r["record_id"], r["traveler_rank"],
                                    r["traveler_name"], tag))

    issue_block = "\n".join(
        f"- **{k.replace('_',' ').upper()}**: {v} record(s)"
        for k, v in sorted(issue_counts.items(), key=lambda kv: -kv[1])
    ) or "- (no issues found this quarter)"

    esc_block = "\n".join(
        f"- `{rid}` — {rank} {nm} ({tag.replace('_',' ')})"
        for (rid, rank, nm, tag) in escalations[:8]
    ) or "- (none)"

    return (
        f"# Travel Program Quarterly Brief — {unit['unit']} ({unit['quarter']})\n\n"
        f"## BLUF\n"
        f"Of **{n} DTS travel records** processed this quarter, the agent flagged "
        f"**{sum(issue_counts.values())} issues** across "
        f"**{len(issue_counts)} categor{'y' if len(issue_counts)==1 else 'ies'}**, with an "
        f"estimated **${dollar_exposure:,.2f}** in financial exposure to the unit. "
        f"S-1 attention is recommended on **{len(escalations)} record(s)** flagged for "
        f"escalation review. The remaining records are clean or auto-correctable inside DTS.\n\n"
        f"## Top Issue Categories\n{issue_block}\n\n"
        f"## Records to Escalate\n{esc_block}\n\n"
        f"## Training Opportunities\n"
        f"- Reinforce per-diem ceiling guidance (lodging) at next S-1 brief — multiple "
        f"records exceeded the GSA-published city rate.\n"
        f"- Remind cardholders that Citi GTC is **official-travel-only**; any non-authorized "
        f"merchant code charge generates a Service-level finding.\n"
        f"- Push the voucher-within-5-days SOP — orphan card charges accumulate when "
        f"vouchers lag.\n\n"
        f"## Recommendation\n"
        f"S-1 review the {len(escalations)} escalated record(s) by the end of next pay period, "
        f"return any auto-correctable findings to the traveler with the recommended action, "
        f"and brief the unit CO on the dollar-exposure trend at the next staff meeting.\n\n"
        f"_Originator: VOUCHER agent / S-1 travel-program QA cell. "
        f"Classification: **CUI // Travel Program Data**._\n"
    )


def _try_llm_brief(unit: dict, dts_subset: list[dict],
                   citi_subset: list[dict]) -> str | None:
    """Try to call the hero LLM for this scenario's brief. Returns None on any
    failure so the baseline brief is used instead."""
    try:
        # Make `shared` importable
        ROOT = OUT.resolve().parent.parent.parent
        sys.path.insert(0, str(ROOT))
        from shared.kamiwaza_client import chat
    except Exception:
        return None

    n = len(dts_subset)
    issue_counts: dict[str, int] = {}
    sample_records = []
    for r in dts_subset:
        for tag in r.get("_seeded_issues", []):
            issue_counts[tag] = issue_counts.get(tag, 0) + 1
        if r.get("_seeded_issues"):
            sample_records.append(
                f"- {r['record_id']} | {r['traveler_rank']} {r['traveler_name']} | "
                f"{r['tdy_city']} | total ${r['voucher_total']:.2f} | "
                f"flags: {','.join(r['_seeded_issues'])}"
            )

    sys_prompt = (
        "You are VOUCHER, a travel-program QA agent supporting the unit S-1 "
        "for a USMC battalion / regiment / MEF HQ. You audit DTS authorizations, "
        "vouchers, and Citi Manager government-travel-card statements end-to-end.\n\n"
        "Compose a polished one-page TRAVEL PROGRAM QUARTERLY BRIEF in markdown "
        "with these EXACT five section headers, in order:\n"
        "  ## BLUF\n"
        "  ## Top Issue Categories\n"
        "  ## Records to Escalate\n"
        "  ## Training Opportunities\n"
        "  ## Recommendation\n\n"
        "Constraints:\n"
        "- BLUF: state record count, total flagged issues, dollar exposure, and # to escalate.\n"
        "- Top Issue Categories: bulleted, ranked, with counts.\n"
        "- Records to Escalate: bullet specific record_ids by name+rank with the issue tag.\n"
        "- Training Opportunities: 3 bullets, each tied to a category surfaced in this quarter.\n"
        "- Recommendation: a single tight paragraph the S-1 can paste into the next staff brief.\n"
        "- End with a one-line classification line: 'CUI // Travel Program Data'.\n"
        "- Total length under 400 words. Plain markdown. No code fences. No emoji.\n"
        "- Refer to the AI engine as 'the agent' or 'VOUCHER' — do not name underlying models.\n"
    )
    user_prompt = (
        f"UNIT: {unit['unit']} (code {unit['code']})\n"
        f"QUARTER: {unit['quarter']}\n"
        f"RECORDS PROCESSED: {n}\n"
        f"ISSUE COUNTS BY CATEGORY: {json.dumps(issue_counts)}\n\n"
        f"SAMPLE FLAGGED RECORDS:\n" + "\n".join(sample_records[:12]) + "\n\n"
        "Compose the quarterly brief now."
    )
    try:
        return chat(
            [{"role": "system", "content": sys_prompt},
             {"role": "user",   "content": user_prompt}],
            model="gpt-5.4",
            temperature=0.4,
            max_tokens=900,
        )
    except Exception:
        try:
            return chat(
                [{"role": "system", "content": sys_prompt},
                 {"role": "user",   "content": user_prompt}],
                temperature=0.4,
                max_tokens=900,
            )
        except Exception:
            return None


def precompute_briefs(dts: list[dict], citi: list[dict]) -> dict[str, dict]:
    """Pre-compute one quarterly brief per unit-quarter scenario.

    Cache-first pattern: the Streamlit app will read these instantly. Live
    re-generation is offered behind a "Regenerate" button.
    """
    out: dict[str, dict] = {}
    for unit in UNITS:
        scenario_id = f"{unit['code']}_{unit['quarter']}"
        dts_subset = [r for r in dts if r["unit_code"] == unit["code"]]
        citi_subset = [c for c in citi if c["unit_code"] == unit["code"]]
        live = _try_llm_brief(unit, dts_subset, citi_subset)
        if live and "BLUF" in live:
            brief = live
            source = "gpt-5.4"
        else:
            brief = _baseline_brief(unit, dts_subset, citi_subset)
            source = "baseline-deterministic"
        out[scenario_id] = {
            "scenario_id": scenario_id,
            "unit": unit["unit"],
            "unit_code": unit["code"],
            "quarter": unit["quarter"],
            "brief": brief,
            "source": source,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "record_count": len(dts_subset),
            "citi_txn_count": len(citi_subset),
        }
        print(f"  cached brief for {scenario_id} ({source})")
    return out


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────
def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rng = random.Random(1776)

    # 1) per-diem reference table
    per_diem_json = [
        {"city": c, "state": s, "lodging_per_night": lod, "mie_per_day": mie}
        for (c, s, lod, mie) in PER_DIEM
    ]
    (OUT / "per_diem_rates.json").write_text(json.dumps({
        "source": "GSA per-diem rates (FY26-plausible synthetic values)",
        "rates": per_diem_json,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }, indent=2))
    print(f"wrote per_diem_rates.json ({len(per_diem_json)} cities)")

    # 2) DTS records + Citi transactions
    dts, citi = generate_dts_and_citi(rng)

    # CSV writers (avoid pandas dep at generate time — keep generate.py minimal)
    import csv

    dts_csv = OUT / "dts_records.csv"
    with dts_csv.open("w", newline="") as f:
        fieldnames = [
            "record_id", "unit_code", "unit", "quarter",
            "traveler_rank", "traveler_name", "card_last4",
            "trip_reason", "tdy_city", "depart_date", "return_date", "nights",
            "transport_mode", "per_diem_lodging_ceiling", "per_diem_mie",
            "voucher_total", "voucher_lines_json",
            "auth_status", "voucher_status", "seeded_issues",
        ]
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in dts:
            w.writerow({
                "record_id": r["record_id"],
                "unit_code": r["unit_code"],
                "unit": r["unit"],
                "quarter": r["quarter"],
                "traveler_rank": r["traveler_rank"],
                "traveler_name": r["traveler_name"],
                "card_last4": r["card_last4"],
                "trip_reason": r["trip_reason"],
                "tdy_city": r["tdy_city"],
                "depart_date": r["depart_date"],
                "return_date": r["return_date"],
                "nights": r["nights"],
                "transport_mode": r["transport_mode"],
                "per_diem_lodging_ceiling": r["per_diem_lodging_ceiling"],
                "per_diem_mie": r["per_diem_mie"],
                "voucher_total": r["voucher_total"],
                "voucher_lines_json": json.dumps(r["voucher_lines"]),
                "auth_status": r["auth_status"],
                "voucher_status": r["voucher_status"],
                "seeded_issues": ",".join(r["_seeded_issues"]),
            })
    print(f"wrote dts_records.csv ({len(dts)} records)")

    citi_csv = OUT / "citi_statements.csv"
    with citi_csv.open("w", newline="") as f:
        fieldnames = [
            "txn_id", "card_last4", "traveler_rank", "traveler_name",
            "unit_code", "unit", "post_date", "merchant",
            "merchant_category", "amount", "linked_dts_record",
        ]
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for c in citi:
            w.writerow(c)
    print(f"wrote citi_statements.csv ({len(citi)} transactions)")

    # 3) Pre-compute hero briefs (cache-first)
    print("Pre-computing hero quarterly briefs...")
    briefs = precompute_briefs(dts, citi)
    (OUT / "cached_briefs.json").write_text(json.dumps(briefs, indent=2))
    print(f"wrote cached_briefs.json ({len(briefs)} scenarios)")

    # 4) Manifest for the UI
    (OUT / "manifest.json").write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dts_records": len(dts),
        "citi_transactions": len(citi),
        "scenarios": [
            {"scenario_id": f"{u['code']}_{u['quarter']}",
             "unit": u["unit"], "code": u["code"], "quarter": u["quarter"]}
            for u in UNITS
        ],
        "sources_simulated": [
            "Defense Travel System (DTS) — authorizations + vouchers",
            "Citi Manager Government Travel Card statements",
            "GSA per-diem rate tables",
        ],
    }, indent=2))
    print("wrote manifest.json")


if __name__ == "__main__":
    main()
