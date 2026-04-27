"""AGORA — Synthetic role/permission tree + ecosystem doc corpus generator.

Real reference (would plug in if available on accredited platform):
  USMC MarineNet ecosystem SSO catalog — LMS (MarineNet), Keycloak IdP,
  MS365 BBB collaboration, CMS (CCLEPP / TECOM portals). Real role/perm
  trees would come from the Keycloak ABAC export + per-app role JSON.

We synthesize:
  - personas.json     — 4 demo personas (PvtJoe / SgtJane / CaptDoe / Civilian)
                        each with a role/permission JSON tree spanning 4 apps.
  - corpus.jsonl      — 60 synthetic "ecosystem help" doc chunks across the
                        4 apps (LMS, CMS, BBB, Keycloak) with per-doc ABAC
                        tags (apps + min_role + classification).
  - embeddings.npy    — pre-computed cosine-normalized embedding matrix.
  - corpus_ids.json   — doc id list aligned to embeddings rows.
  - cached_briefs.json — 3 query scenarios pre-answered by each persona,
                        cache-first pattern so the demo is snappy.

Seed: 1776.
"""
from __future__ import annotations

import json
import os
import random
import sys
from pathlib import Path

import numpy as np

OUT = Path(__file__).parent
SEED = 1776

# Make repo importable
ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

# ─────────────────────────────────────────────────────────────────────────────
# Persona / role / permission tree
# ─────────────────────────────────────────────────────────────────────────────
APPS = ["LMS", "CMS", "BBB", "Keycloak"]
CLASSIFICATIONS = ["UNCLASS", "CUI", "FOUO"]
ROLE_RANK = {"none": 0, "viewer": 1, "student": 1, "instructor": 2,
             "author": 2, "moderator": 2, "host": 2, "operator": 2,
             "manager": 3, "approver": 3, "admin": 4, "auditor": 4}

PERSONAS = [
    {
        "id": "pvt_joe",
        "name": "PvtJoe",
        "rank": "Pvt",
        "billet": "LMS Student (boot)",
        "clearance": "UNCLASS",
        "duty_org": "MCRD San Diego, 1st RTBn",
        "color": "#00BB7A",
        "icon": "PVT",
        "roles": {
            "LMS":      {"role": "student",   "perms": ["course.enroll", "course.view", "course.submit", "transcript.view.self"]},
            "CMS":      {"role": "viewer",    "perms": ["page.view.public"]},
            "BBB":      {"role": "viewer",    "perms": ["meeting.join.invited"]},
            "Keycloak": {"role": "none",      "perms": []},
        },
        "abac": {
            "max_class": "UNCLASS",
            "unit_scope": ["MCRD-SD"],
            "audit_groups": [],
        },
    },
    {
        "id": "sgt_jane",
        "name": "SgtJane",
        "rank": "Sgt",
        "billet": "Unit Instructor / SNCO",
        "clearance": "CUI",
        "duty_org": "1st Marine Logistics Group",
        "color": "#0DCC8A",
        "icon": "SGT",
        "roles": {
            "LMS":      {"role": "instructor", "perms": ["course.create", "course.grade", "transcript.view.unit", "course.assign"]},
            "CMS":      {"role": "author",     "perms": ["page.view.public", "page.edit.unit"]},
            "BBB":      {"role": "moderator",  "perms": ["meeting.create", "meeting.moderate.unit"]},
            "Keycloak": {"role": "none",       "perms": []},
        },
        "abac": {
            "max_class": "CUI",
            "unit_scope": ["1st-MLG", "MCRD-SD"],
            "audit_groups": [],
        },
    },
    {
        "id": "capt_doe",
        "name": "CaptDoe",
        "rank": "Capt",
        "billet": "Battalion S-3 / Approver",
        "clearance": "CUI",
        "duty_org": "2nd Bn 1st Marines / I MEF",
        "color": "#00FFA7",
        "icon": "CPT",
        "roles": {
            "LMS":      {"role": "manager",    "perms": ["course.create", "course.grade", "transcript.view.battalion", "course.approve", "report.export"]},
            "CMS":      {"role": "approver",   "perms": ["page.view.public", "page.edit.unit", "page.publish.battalion"]},
            "BBB":      {"role": "host",       "perms": ["meeting.create", "meeting.moderate.battalion", "meeting.record"]},
            "Keycloak": {"role": "auditor",    "perms": ["user.view.unit", "audit.view.battalion"]},
        },
        "abac": {
            "max_class": "CUI",
            "unit_scope": ["2/1", "I-MEF", "1st-MLG"],
            "audit_groups": ["S3-approver"],
        },
    },
    {
        "id": "civ_quinn",
        "name": "Civilian (Quinn)",
        "rank": "GS-9 Contractor",
        "billet": "Curriculum Contractor (limited)",
        "clearance": "UNCLASS",
        "duty_org": "TECOM SETA — Vendor: Acme Learning",
        "color": "#7E7E7E",
        "icon": "CIV",
        "roles": {
            "LMS":      {"role": "author",   "perms": ["course.create", "course.view"]},
            "CMS":      {"role": "viewer",   "perms": ["page.view.public"]},
            "BBB":      {"role": "viewer",   "perms": ["meeting.join.invited"]},
            "Keycloak": {"role": "none",     "perms": []},
        },
        "abac": {
            "max_class": "UNCLASS",
            "unit_scope": ["TECOM-VENDOR"],
            "audit_groups": [],
        },
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# Doc corpus — 60 plausible ecosystem help chunks across 4 apps
# Each doc has ABAC tags: app, min_role, classification, scope (unit tag).
# ─────────────────────────────────────────────────────────────────────────────

# (app, title, body, min_role, classification, scope, tags)
DOC_TEMPLATES: list[tuple] = [
    # ── LMS (MarineNet-style) — 18 docs ────────────────────────────────────
    ("LMS", "Enrolling in a MarineNet course",
     "Students self-enroll from the course catalog. Click 'Enroll' on a course tile, accept the academic-honesty banner, and the course appears in 'My Courses'. SSO via Keycloak — no separate login.",
     "student", "UNCLASS", "ALL", ["enroll", "course", "student"]),
    ("LMS", "Submitting an assignment",
     "Open the assignment, click 'Submit', upload your file (PDF/DOCX, 25 MB max). The system stamps the SSO identity from Keycloak. Late submissions are flagged in the gradebook with a yellow chevron.",
     "student", "UNCLASS", "ALL", ["assignment", "submit"]),
    ("LMS", "Viewing your transcript",
     "Self-service transcripts are under Profile → Transcript. Export as PDF for promotion boards. Other Marines' transcripts are NOT visible to students — that's an instructor-or-above permission.",
     "student", "UNCLASS", "ALL", ["transcript", "self"]),
    ("LMS", "Resetting a forgotten password",
     "Password reset is delegated to Keycloak. Click 'Forgot password' on the login page and follow the email link. CAC users do NOT have a password to reset — re-insert the CAC and refresh.",
     "student", "UNCLASS", "ALL", ["password", "auth", "sso"]),
    ("LMS", "Course completion certificates",
     "On 100% completion the system auto-issues a PDF certificate with the SSO-stamped name and EDIPI. Certificates are stored under Profile → Certificates and synced nightly to MOL.",
     "student", "UNCLASS", "ALL", ["cert", "completion"]),
    ("LMS", "Creating a course (instructor)",
     "Instructors click '+ New Course' from the Instructor Dashboard. Fields: title, summary, target audience (rank/MOS), classification (UNCLASS/CUI), enrollment policy (open/invite-only/unit-scoped). CUI courses require an approver from O-3 or above.",
     "instructor", "CUI", "UNIT", ["course", "create", "instructor"]),
    ("LMS", "Grading rubric configuration",
     "Instructors define a rubric per assignment with weighted criteria. Rubric scores feed the gradebook, which is visible to instructors-and-above for their unit scope only.",
     "instructor", "CUI", "UNIT", ["grading", "rubric", "instructor"]),
    ("LMS", "Bulk-assigning a course to a unit",
     "Instructors can bulk-assign a course to all Marines in their unit_scope. The Keycloak ABAC tag controls which roster the assign-to picker exposes.",
     "instructor", "CUI", "UNIT", ["assign", "unit"]),
    ("LMS", "Battalion-level transcript reporting",
     "Battalion S-3s pull aggregate transcript reports (completion %, avg score, overdue count) for any course assigned inside their unit_scope. Export to CSV or push to GCSS-MC for readiness rollups.",
     "manager", "CUI", "BATTALION", ["report", "transcript", "battalion"]),
    ("LMS", "Approving a CUI course for publication",
     "S-3 approvers see a 'Pending Approval' queue. Each course pending publication shows author, classification, target unit, and a one-click approve/reject. Rejection prompts a comment field that returns to the author.",
     "manager", "CUI", "BATTALION", ["approve", "publish"]),
    ("LMS", "Delegated authoring for contractors",
     "Vendor authors (e.g. SETA contractors) can create draft courses but cannot publish. All vendor-authored content is stamped 'DRAFT — VENDOR' and routes to a uniformed approver.",
     "author", "UNCLASS", "VENDOR", ["vendor", "draft", "author"]),
    ("LMS", "Vendor identity boundary",
     "Vendor accounts are provisioned in a separate Keycloak realm. They never see CUI courses, transcripts of uniformed Marines, or unit roster data. Attempts surface a 'Not Authorized — vendor scope' banner.",
     "author", "UNCLASS", "VENDOR", ["vendor", "boundary", "abac"]),
    ("LMS", "Recovering a deleted course",
     "Soft-deleted courses live in the trash for 30 days. Only managers can restore. After 30 days, content is purged from primary storage but a manifest is retained in the audit log.",
     "manager", "CUI", "BATTALION", ["delete", "restore"]),
    ("LMS", "API integration with GCSS-MC",
     "The LMS publishes a course-completion webhook (JSON, mTLS) to GCSS-MC's readiness service. Webhook secret rotates quarterly via the Keycloak admin console.",
     "manager", "CUI", "BATTALION", ["api", "gcss", "integration"]),
    ("LMS", "Mobile app — offline course play",
     "The MarineNet mobile app caches enrolled courses for 14 days of offline play. Quiz answers sync on next handshake. Offline mode is disabled for CUI courses.",
     "student", "UNCLASS", "ALL", ["mobile", "offline"]),
    ("LMS", "Accessibility settings (508)",
     "Closed captions, screen-reader navigation, and high-contrast mode are toggled per-user in Profile → Accessibility. All courses are validated against Section 508 before publication.",
     "student", "UNCLASS", "ALL", ["accessibility", "508"]),
    ("LMS", "Quizzes and proctoring",
     "Instructors can mark a quiz as 'proctored', which forces the BBB integration to start a moderated session before the quiz unlocks. The session recording is retained per the course classification's policy.",
     "instructor", "CUI", "UNIT", ["quiz", "proctoring", "bbb"]),
    ("LMS", "Promotion-eligibility courses",
     "Promotion gates are tagged 'PROM-ELIG' on the course tile. The completion event publishes a structured record to MOL nightly. Only the Marine and their chain-of-command (within unit_scope) can view the record.",
     "student", "UNCLASS", "ALL", ["promotion", "mol"]),

    # ── CMS (web content) — 14 docs ────────────────────────────────────────
    ("CMS", "Public-facing pages",
     "The CMS hosts the public homepage, news feed, and external announcements. Anyone with a session — including unauthenticated visitors — can read the public namespace.",
     "viewer", "UNCLASS", "ALL", ["public", "page"]),
    ("CMS", "Editing a unit page",
     "Authors edit pages in their unit_scope. The WYSIWYG inserts SSO-stamped author metadata. Publish requires an Approver role at the battalion level for any page tagged CUI.",
     "author", "UNCLASS", "UNIT", ["edit", "page", "author"]),
    ("CMS", "Publishing a battalion announcement",
     "Battalion S-3s publish unit-wide announcements that surface on the unit homepage and push a Keycloak-bound notification to in-scope Marines.",
     "approver", "CUI", "BATTALION", ["publish", "announcement", "battalion"]),
    ("CMS", "Page version history",
     "Every save is versioned. Authors can diff versions; Approvers can roll back. A rollback emits an audit log line to Keycloak's audit store.",
     "author", "UNCLASS", "UNIT", ["versioning", "history"]),
    ("CMS", "Embedded BBB sessions on a page",
     "Pages can embed a live BBB room as an iframe. The room inherits the page's classification — embedding a CUI BBB room on a public page is rejected by the publish guard.",
     "author", "CUI", "UNIT", ["embed", "bbb", "page"]),
    ("CMS", "Image gallery upload",
     "Authors upload up to 50 images per page. Images are virus-scanned by the perimeter scanner; CUI images get an additional EXIF-strip pass.",
     "author", "UNCLASS", "UNIT", ["image", "upload"]),
    ("CMS", "Search index re-build",
     "The CMS search index re-builds nightly. Managers can trigger an on-demand rebuild from the admin tools panel. Public visitors see only the public-namespace facet.",
     "manager", "UNCLASS", "BATTALION", ["search", "index"]),
    ("CMS", "Vendor portal pages",
     "Vendor-facing pages live in a dedicated namespace with no CUI classification permitted. Uniformed Marines edit them via a 'Vendor Liaison' role; vendors view-only.",
     "author", "UNCLASS", "VENDOR", ["vendor", "portal"]),
    ("CMS", "Page classification guard",
     "When an author drops content tagged CUI (via the classification toolbar) into a public-namespace page, the system blocks save and surfaces a red banner: 'CUI content cannot be saved in a public namespace.'",
     "author", "CUI", "UNIT", ["classification", "guard"]),
    ("CMS", "RSS feed for unit news",
     "Each unit page exposes an RSS feed scoped to that unit. Subscribers must present a Keycloak token; anonymous RSS clients receive only the public namespace.",
     "viewer", "UNCLASS", "ALL", ["rss", "feed"]),
    ("CMS", "Restoring a deleted page",
     "Approvers can restore deleted pages within 90 days. After 90 days the page is purged from primary storage; a manifest stays in audit.",
     "approver", "CUI", "BATTALION", ["restore", "delete"]),
    ("CMS", "Page review workflow",
     "Authors submit pages for review. Approvers see a pending queue with diff view; comments thread inline. Approval triggers publish; rejection returns to draft.",
     "author", "UNCLASS", "UNIT", ["review", "workflow"]),
    ("CMS", "External-link warnings",
     "Links to non-.mil/.gov domains automatically render with an 'external link' interstitial. Authors can mark vetted vendor URLs as exempt.",
     "viewer", "UNCLASS", "ALL", ["external", "link"]),
    ("CMS", "Tag taxonomy",
     "Pages carry tags for cross-reference. The taxonomy is curated by Approvers; vendors and viewers cannot create tags.",
     "author", "UNCLASS", "UNIT", ["taxonomy", "tags"]),

    # ── BBB (Big Blue Button) — 14 docs ────────────────────────────────────
    ("BBB", "Joining a meeting from an invite",
     "Click the meeting link in your email or calendar. The room loads via SSO — no separate password. If you're not on the invite list and the room is unit-scoped, you'll see 'Not authorized for this room.'",
     "viewer", "UNCLASS", "ALL", ["join", "meeting"]),
    ("BBB", "Creating a unit meeting",
     "Moderators create meetings from the BBB dashboard. Required: title, classification (UNCLASS/CUI), invite list (people-picker is unit_scope-bound).",
     "moderator", "CUI", "UNIT", ["create", "meeting", "moderator"]),
    ("BBB", "Recording a session",
     "Hosts (Capt+) can record. Recording is announced in-room with a banner. Recordings inherit the meeting classification and retention policy.",
     "host", "CUI", "BATTALION", ["record", "host"]),
    ("BBB", "Battalion-wide town hall",
     "Hosts can convene battalion-wide town halls. The invite list auto-populates from the Keycloak unit_scope membership. Attendance is logged for the after-action.",
     "host", "CUI", "BATTALION", ["town-hall", "battalion"]),
    ("BBB", "Breakout rooms",
     "Moderators split a meeting into breakout rooms (max 10). Breakout chat is captured into the parent transcript; ABAC inherits from the parent room.",
     "moderator", "UNCLASS", "UNIT", ["breakout"]),
    ("BBB", "Polling and quizzes",
     "Moderators can run polls inline. Results are anonymized to participants; moderators see attributed results with SSO identity.",
     "moderator", "UNCLASS", "UNIT", ["poll", "quiz"]),
    ("BBB", "Screen sharing",
     "Any participant can request screen share; the moderator approves. CUI-marked rooms watermark the shared screen with the SSO identity of the sharer.",
     "viewer", "UNCLASS", "ALL", ["screen-share"]),
    ("BBB", "Closed captions",
     "Live closed captioning is opt-in per meeting. Captions are auto-generated by an on-prem ASR model (no cloud). Saved transcripts inherit the meeting's classification.",
     "viewer", "UNCLASS", "ALL", ["captions", "asr"]),
    ("BBB", "External / vendor invites",
     "Vendor accounts can join meetings only via explicit invite. The invite must be issued by a moderator inside the vendor's unit_scope. Vendors cannot create meetings.",
     "moderator", "UNCLASS", "VENDOR", ["vendor", "invite"]),
    ("BBB", "End-of-meeting after-action",
     "On meeting end, the system emits an after-action JSON to the unit's CMS page (transcript link, attendance, polls). After-action visibility inherits the room classification.",
     "moderator", "CUI", "UNIT", ["after-action"]),
    ("BBB", "Recording retention",
     "UNCLASS recordings retain 90 days; CUI recordings retain 1 year per the records-management policy. Hosts cannot extend retention without an Approver override.",
     "host", "CUI", "BATTALION", ["retention", "records"]),
    ("BBB", "Meeting access logs",
     "Auditors (Capt+) can pull access logs for any meeting in their unit_scope. Logs include join/leave times, SSO identity, and IP-class (CONUS / OCONUS / VPN).",
     "host", "CUI", "BATTALION", ["audit", "logs"]),
    ("BBB", "Mobile join",
     "iOS/Android clients support join + audio. Recording from mobile is disabled. CAC-on-mobile (via derived credential) is supported.",
     "viewer", "UNCLASS", "ALL", ["mobile"]),
    ("BBB", "Bandwidth-aware fallback",
     "When a participant's bandwidth drops below 256 kbps, the client auto-falls back to audio-only. CUI rooms display a banner if any participant is on degraded connection.",
     "viewer", "UNCLASS", "ALL", ["bandwidth", "audio"]),

    # ── Keycloak (IdP / SSO) — 14 docs ─────────────────────────────────────
    ("Keycloak", "Logging in with CAC",
     "Insert your CAC, click 'Sign in with CAC' on the SSO portal. The IdP validates the certificate against DoD PKI and issues a session token. CAC PIN is collected by the local middleware, never the browser.",
     "viewer", "UNCLASS", "ALL", ["cac", "login"]),
    ("Keycloak", "MFA enrollment",
     "Non-CAC accounts (e.g. vendor) must enroll MFA on first login. Supported: TOTP (authenticator app), WebAuthn hardware key. SMS is NOT permitted.",
     "viewer", "UNCLASS", "ALL", ["mfa"]),
    ("Keycloak", "Role assignment (operator)",
     "Operators assign roles inside their unit_scope only. The role picker greys out roles outside the operator's authority. All assignments are audit-logged.",
     "operator", "CUI", "UNIT", ["roles"]),
    ("Keycloak", "ABAC attribute model",
     "Each user carries: max_class (UNCLASS/CUI/SECRET), unit_scope (list of org tags), and audit_groups. Apps consume these via the OIDC userinfo claim.",
     "operator", "CUI", "UNIT", ["abac", "claims"]),
    ("Keycloak", "Auditor view of unit users",
     "Auditors (Capt+) can list users inside their unit_scope and view their last login, MFA status, and assigned roles per app. Auditors cannot reset passwords or change roles.",
     "auditor", "CUI", "BATTALION", ["audit", "users"]),
    ("Keycloak", "Realm separation — vendor vs uniformed",
     "Vendor accounts live in the 'vendor' realm; uniformed Marines in the 'usmc' realm. Cross-realm token issuance is blocked at the gateway. This is the bedrock of vendor data containment.",
     "auditor", "CUI", "BATTALION", ["realm", "vendor"]),
    ("Keycloak", "Session timeout",
     "UNCLASS sessions expire after 8 hours of activity, 30 minutes of idle. CUI sessions: 4 hours active, 15 minutes idle. Step-up auth required to re-elevate.",
     "viewer", "UNCLASS", "ALL", ["session"]),
    ("Keycloak", "Step-up authentication",
     "Sensitive actions (publish CUI page, approve course, export audit log) trigger a step-up: re-tap CAC or re-prove WebAuthn. The IdP records the step-up event with the action descriptor.",
     "viewer", "CUI", "UNIT", ["step-up"]),
    ("Keycloak", "Service account management",
     "Service accounts (machine-to-machine) are provisioned by Operators with a renewable client-credentials grant. Secrets rotate every 90 days; auto-rotation hooks publish the new secret to HashiCorp Vault.",
     "operator", "CUI", "UNIT", ["service-account"]),
    ("Keycloak", "Audit log search",
     "Auditors search audit logs by user, action, time range, and IP-class. Logs are immutable for 7 years (NARA records schedule).",
     "auditor", "CUI", "BATTALION", ["audit", "log"]),
    ("Keycloak", "Group-based access control",
     "Groups represent units (e.g. '2/1', 'I-MEF', '1st-MLG'). Group membership populates the unit_scope claim. Groups nest — a Marine in '2/1' inherits I-MEF visibility for downstream apps.",
     "operator", "CUI", "UNIT", ["groups", "rbac"]),
    ("Keycloak", "Federated login from partner nation",
     "Allied/coalition partners can federate via SAML from their own IdP. The federation is whitelisted at the realm level and capped at UNCLASS.",
     "operator", "CUI", "UNIT", ["federation", "saml"]),
    ("Keycloak", "Account deactivation on PCS / EAS",
     "On PCS or EAS the personnel system pushes a status change. Keycloak deactivates the account on EAS; on PCS, group memberships are remapped to the gaining unit.",
     "operator", "CUI", "UNIT", ["pcs", "eas"]),
    ("Keycloak", "Admin console — emergency lockout",
     "In an incident, an Operator can force-logout an entire group with a single command. The action is one-step but requires the operator's step-up auth and pages the on-call SOC.",
     "operator", "CUI", "BATTALION", ["incident", "lockout"]),
]


def make_corpus() -> list[dict]:
    rng = random.Random(SEED)
    docs = []
    for i, (app, title, body, min_role, classification, scope, tags) in enumerate(DOC_TEMPLATES):
        doc_id = f"DOC-{i+1:03d}"
        # Add a small synthetic "FAQ" rider so embeddings have a tiny bit of variety
        rider = rng.choice([
            "Common pitfalls: SSO token timeouts, mis-scoped unit_scope claim, expired CAC.",
            "Operator tip: check Keycloak audit log if access fails unexpectedly.",
            "If you see 'Not authorized', verify your role assignment for this app in Keycloak.",
            "For escalations, file a TECOM service request with the SSO request-id.",
            "ABAC checks happen at the gateway, not in the browser — clear cache rarely helps.",
        ])
        doc = {
            "doc_id": doc_id,
            "app": app,
            "title": title,
            "body": body + " " + rider,
            "min_role": min_role,
            "classification": classification,
            "scope": scope,  # ALL | UNIT | BATTALION | VENDOR
            "tags": tags,
            "embed_text": f"[{app}] {title}\n{body}\nTags: {', '.join(tags)}",
        }
        docs.append(doc)
    return docs


# ─────────────────────────────────────────────────────────────────────────────
# Cached scenario briefs (so the demo feels instant)
# ─────────────────────────────────────────────────────────────────────────────
SCENARIOS = [
    {
        "id": "transcript_export",
        "query": "How do I pull a battalion-wide transcript report and approve a CUI course for publication?",
        "best_for": "capt_doe",
    },
    {
        "id": "vendor_boundary",
        "query": "I'm a vendor — can I see uniformed Marines' transcripts and edit a battalion announcement?",
        "best_for": "civ_quinn",
    },
    {
        "id": "course_enroll_password",
        "query": "I forgot my password and I need to enroll in the new MarineNet course. What do I do?",
        "best_for": "pvt_joe",
    },
]


def _precompute_briefs(personas: list[dict], docs: list[dict], embeddings: np.ndarray) -> dict:
    """Pre-answer each scenario for each persona, cache the JSON-shape brief.

    Cache-first pattern: app reads from this; live calls only fire on demand.
    """
    try:
        from shared.kamiwaza_client import chat, embed as do_embed  # noqa: WPS433
    except Exception as e:  # noqa: BLE001
        print(f"[agora] cannot precompute briefs ({e}); writing placeholder.")
        return {"_placeholder": True, "scenarios": [s["id"] for s in SCENARIOS]}

    # Reuse same retrieval as the runtime
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from src.retrieval import authorize_doc, cosine_topk, render_answer  # type: ignore  # noqa: E402

    out: dict = {"scenarios": {}}
    for sc in SCENARIOS:
        per_persona: dict = {}
        # One embedding per scenario query, reused across personas
        try:
            qvec = np.array(do_embed([sc["query"]])[0], dtype=np.float32)
            qvec = qvec / (np.linalg.norm(qvec) + 1e-12)
        except Exception as e:  # noqa: BLE001
            print(f"[agora] embed failed for scenario {sc['id']}: {e}")
            qvec = None

        for persona in personas:
            if qvec is None:
                per_persona[persona["id"]] = {
                    "answer": "(cached brief unavailable — live call will run on demand.)",
                    "cited_docs": [],
                    "denied_docs": [],
                }
                continue
            # Authorize-then-rank (filter to docs persona can read)
            authorized_idx, denied = [], []
            for i, d in enumerate(docs):
                ok, why = authorize_doc(persona, d)
                if ok:
                    authorized_idx.append(i)
                else:
                    denied.append({"doc_id": d["doc_id"], "title": d["title"], "app": d["app"], "reason": why})

            top = cosine_topk(qvec, embeddings, authorized_idx, k=3)
            top_docs = [docs[i] for i, _ in top]

            try:
                answer = render_answer(persona, sc["query"], top_docs, hero=False)
            except Exception as e:  # noqa: BLE001
                print(f"[agora] render failed: {e}")
                answer = f"(cache miss — live call will run. Reason: {e})"

            per_persona[persona["id"]] = {
                "answer": answer,
                "cited_docs": [{"doc_id": d["doc_id"], "title": d["title"], "app": d["app"]} for d in top_docs],
                "denied_docs": denied,
            }
        out["scenarios"][sc["id"]] = {
            "query": sc["query"],
            "best_for": sc["best_for"],
            "by_persona": per_persona,
        }
    return out


def main(skip_briefs: bool = False) -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    # 1. personas
    (OUT / "personas.json").write_text(json.dumps(PERSONAS, indent=2))
    print(f"Wrote {len(PERSONAS)} personas → {OUT / 'personas.json'}")

    # 2. corpus
    docs = make_corpus()
    with (OUT / "corpus.jsonl").open("w") as f:
        for d in docs:
            f.write(json.dumps(d) + "\n")
    print(f"Wrote {len(docs)} docs → {OUT / 'corpus.jsonl'}")

    # 3. embeddings
    try:
        from shared.kamiwaza_client import embed as do_embed  # noqa: WPS433
        texts = [d["embed_text"] for d in docs]
        vecs = []
        batch = 32
        for i in range(0, len(texts), batch):
            vecs.extend(do_embed(texts[i : i + batch]))
        mat = np.array(vecs, dtype=np.float32)
        norms = np.linalg.norm(mat, axis=1, keepdims=True) + 1e-12
        mat = mat / norms
        np.save(OUT / "embeddings.npy", mat)
        (OUT / "corpus_ids.json").write_text(json.dumps([d["doc_id"] for d in docs]))
        print(f"Wrote embeddings ({mat.shape}) → {OUT / 'embeddings.npy'}")
    except Exception as e:  # noqa: BLE001
        # Determinstic placeholder so the app boots even without network/keys
        print(f"[agora] embed failed ({e}); writing deterministic random fallback.")
        rng = np.random.default_rng(SEED)
        mat = rng.normal(size=(len(docs), 384)).astype(np.float32)
        norms = np.linalg.norm(mat, axis=1, keepdims=True) + 1e-12
        mat = mat / norms
        np.save(OUT / "embeddings.npy", mat)
        (OUT / "corpus_ids.json").write_text(json.dumps([d["doc_id"] for d in docs]))

    # 4. cached briefs
    if not skip_briefs:
        embeddings = np.load(OUT / "embeddings.npy")
        briefs = _precompute_briefs(PERSONAS, docs, embeddings)
        (OUT / "cached_briefs.json").write_text(json.dumps(briefs, indent=2))
        print(f"Wrote cached briefs → {OUT / 'cached_briefs.json'}")
    else:
        # Empty stub so the app's cache-read still works
        if not (OUT / "cached_briefs.json").exists():
            (OUT / "cached_briefs.json").write_text(json.dumps({"scenarios": {}}, indent=2))


if __name__ == "__main__":
    skip = "--skip-briefs" in sys.argv
    main(skip_briefs=skip)
