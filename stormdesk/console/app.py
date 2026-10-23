"""StormDesk console: the screen the human technician works from.

    uv run streamlit run stormdesk/console/app.py

Approvals, the storm board, and the phones refresh by themselves every few seconds, so a request
made on a live call shows up here while the caller is still on the line."""

import re
import sys
from pathlib import Path

# `streamlit run` puts only this file's folder on the import path. The editable install's .pth file
# would add the project root, but Python 3.13 skips .pth files carrying the macOS "hidden" flag.
ROOT = str(Path(__file__).resolve().parents[2])
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import httpx  # noqa: E402
import streamlit as st  # noqa: E402

from stormdesk.console.client import BackendError, connect  # noqa: E402
from stormdesk.timeutil import humanize, parse  # noqa: E402

st.set_page_config(page_title="StormDesk Console", page_icon="⛈️", layout="wide")

STATE_ICON = {"operational": "🟢", "degraded": "🟡", "outage": "🔴", "unknown": "⚪"}
RISK_COLOR = {"low": "green", "medium": "orange", "high": "red", "n/a": "gray"}
STATUS_COLOR = {"pending": "orange", "approved": "blue", "executed": "green", "rejected": "red",
                "expired": "gray", "failed": "red"}
KIND_LABEL = {"mfa_reset": "MFA reset", "account_unlock": "Account unlock", "access_grant": "Access grant",
              "major_incident": "Major incident"}
DRILL_LABEL = {"itsm_down": "Ticket system down", "sms_down": "Text messages down",
               "identity_down": "Identity system down", "feeds_down": "Status pages unreachable"}
VERDICT_ICON = {"pass": "✅", "attention": "🟡", "fail": "❌"}
RULE_ICON = {"pass": "✅", "fail": "❌", "warn": "⚠️", "n/a": "—", "not_applicable": "—"}
LOCATIONS = ["Chennai", "Bengaluru", "London", "Austin", "Remote"]

api = connect()
try:
    api.get("/admin/overview")
except httpx.HTTPError:
    st.error(f"Can't reach StormDesk at {api.base_url}. Start it first: "
             "`uv run uvicorn stormdesk.main:app --port 8000`")
    st.stop()
except BackendError as exc:
    st.error(f"StormDesk refused the console: {exc.detail}")
    st.stop()

EMPLOYEES = {e["employee_id"]: e for e in api.get("/admin/employees")["employees"]}


def who(employee_id: str | None) -> str:
    employee = EMPLOYEES.get(employee_id or "")
    return f"{employee['full_name']} ({employee_id})" if employee else (employee_id or "—")


def when(ts: str | None) -> str:
    return humanize(ts) if ts else "—"


def clock(ts: str) -> str:
    """Stored times are UTC; the technician reads their own local time."""
    return parse(ts).astimezone().strftime("%H:%M:%S")


def flash(area: str, message: str, kind: str = "success") -> None:
    st.session_state.setdefault(f"flash-{area}", []).append((kind, message))


def show_flash(area: str) -> None:
    for kind, message in st.session_state.pop(f"flash-{area}", []):
        getattr(st, kind)(message)


def attempt(area: str, action, success: str) -> dict | None:
    """Run a backend call from a button; show the outcome on the next refresh of that area."""
    try:
        result = action()
    except BackendError as exc:
        flash(area, exc.detail, "error")
        return None
    flash(area, success)
    return result


# --- sidebar ---------------------------------------------------------------------------------------

with st.sidebar:
    st.title("⛈️ StormDesk")
    st.caption("Service desk console · Acme Corp")
    technicians = [e for e in EMPLOYEES.values() if e["department"] == "IT" and e["status"] == "active"]
    technician = st.selectbox("Signed in as", [t["employee_id"] for t in technicians], format_func=who,
                              key="technician")

    @st.fragment(run_every="3s")
    def pulse():
        overview = api.get("/admin/overview")
        waiting = overview["pending_approvals"]
        st.metric("Waiting for your approval", waiting, border=True)
        if waiting > st.session_state.get("seen_pending", 0):
            st.toast(f"{waiting} approval{'s' if waiting != 1 else ''} waiting", icon="🔔")
        st.session_state["seen_pending"] = waiting
        left, right = st.columns(2)
        left.metric("Open tickets", overview["open_incidents"])
        right.metric("Major incidents", overview["major_incidents"])
        if overview["storms_building"]:
            st.warning(f"Ticket storm building on {overview['storms_building']} service(s)", icon="🌩️")
        if overview["outbox_pending"]:
            st.warning(f"{overview['outbox_pending']} ticket(s) waiting in the outbox", icon="📮")
        to_look_at = overview["reviews"].get("attention", 0) + overview["reviews"].get("fail", 0)
        if to_look_at:
            st.warning(f"{to_look_at} call review(s) need a look", icon="🧑‍⚖️")
        for flag in overview["drills_on"]:
            st.error(f"Drill on: {DRILL_LABEL[flag]}", icon="🧪")
        for service in overview["demo_outages"]:
            st.info(f"Demo outage: {service}", icon="🎬")

    pulse()
    st.caption(f"Backend: {api.base_url}")

tab_approvals, tab_storm, tab_tickets, tab_phones, tab_calls, tab_reviews, tab_drills = st.tabs(
    ["🔔 Approvals", "🌩️ Storm board", "🎫 Tickets", "📱 Phones", "📞 Calls", "🧑‍⚖️ Reviews", "🧪 Drills"])


# --- approvals -------------------------------------------------------------------------------------

def decide(approval_id: str, approve: bool) -> None:
    note = st.session_state.get(f"note-{approval_id}", "")
    result = attempt("approvals", lambda: api.post(f"/admin/approvals/{approval_id}/decision",
                                                   {"technician_id": technician, "approve": approve, "note": note}),
                     f"{approval_id} {'approved' if approve else 'rejected'}.")
    if result and result["status"] == "failed":
        flash("approvals", f"{approval_id} was approved but could not be applied: {result['result']}", "error")


def approval_card(approval: dict) -> None:
    approval_id = approval["approval_id"]
    major = approval["kind"] == "major_incident"
    with st.container(border=True):
        title, badge = st.columns([4, 1], vertical_alignment="center")
        subject = approval["service"].upper() if major else who(approval["employee_id"])
        title.markdown(f"#### {KIND_LABEL[approval['kind']]} · {subject}")
        with badge:
            st.badge(f"risk: {approval['risk_level']}", color=RISK_COLOR.get(approval["risk_level"], "gray"))
        ticket = approval["incident_number"] or approval["details"].get("ticket_reference")
        employee = EMPLOYEES.get(approval["employee_id"] or "")
        context = f" · {employee['department']}, {employee['location']}" if employee else ""
        st.caption(f"{approval_id} · requested {when(approval['created_at'])}"
                   + (f" · ticket {ticket}" if ticket else "") + context)
        st.markdown(f"**{'Why' if major else 'Caller says'}:** {approval['reason']}")
        if approval["details"].get("resource"):
            st.markdown(f"**Access to:** {approval['details']['resource']}")
        st.markdown("**Evidence:**" if major else "**Risk signals:**")
        for note in approval["risk_notes"]:
            st.markdown(f"- {note}")
        own = approval["employee_id"] == technician
        st.text_input("Note (internal; never read to the caller)", key=f"note-{approval_id}")
        yes, no = st.columns(2)
        yes.button("Declare major incident" if major else "Approve", key=f"approve-{approval_id}", type="primary",
                   disabled=own, width="stretch", on_click=decide, args=(approval_id, True))
        no.button("Not a major incident" if major else "Reject", key=f"reject-{approval_id}", disabled=own,
                  width="stretch", on_click=decide, args=(approval_id, False))
        if own:
            st.caption("This is your own request: another technician has to decide it.")


@st.fragment(run_every="3s")
def approvals_panel():
    show_flash("approvals")
    pending = api.get("/admin/approvals", status="pending")["approvals"]
    if not pending:
        st.success("Nothing waiting for approval.", icon="✅")
    for approval in reversed(pending):  # oldest first: first come, first served
        approval_card(approval)
    decided = [a for a in api.get("/admin/approvals", limit=30)["approvals"] if a["status"] != "pending"]
    if decided:
        st.markdown("##### Recently decided")
        st.dataframe(
            [{"Approval": a["approval_id"], "What": KIND_LABEL[a["kind"]],
              "For": who(a["employee_id"]) if a["employee_id"] else (a["service"] or "").upper(),
              "Status": a["status"], "Decided by": who(a["decided_by"]) if a["decided_by"] else "—",
              "When": when(a["decided_at"] or a["completed_at"])} for a in decided],
            hide_index=True, width="stretch",
        )


with tab_approvals:
    approvals_panel()


# --- storm board -----------------------------------------------------------------------------------

def resolve(number: str, area: str) -> None:
    note = st.session_state.get(f"{area}-resolve-note-{number}", "")
    result = attempt(area, lambda: api.post(f"/admin/incidents/{number}/resolve",
                                            {"technician_id": technician, "note": note}), f"{number} resolved.")
    if result and result["notified"]:
        flash(area, f"Texted {result['notified']} affected employee(s); closed {len(result['resolved_children'])} "
                    "linked ticket(s).", "info")


@st.fragment(run_every="5s")
def storm_panel():
    show_flash("storm")
    rows = api.get("/admin/storm-board")["services"]
    if not rows:
        st.success("No ticket storms. It's quiet.", icon="🌤️")
    for row in rows:
        with st.container(border=True):
            major = row["major_incident"]
            if major:
                st.markdown(f"#### 🔴 {row['service']}: major incident {major['number']}")
                st.markdown(f"{major['summary']} · declared {major['opened']} · "
                            f"**{major['linked_open']}** linked ticket(s) still open")
                st.text_input("Resolution note", key=f"storm-resolve-note-{major['number']}",
                              placeholder="e.g. VPN gateway restarted")
                st.button("Resolve and text everyone affected", key=f"storm-resolve-{major['number']}",
                          type="primary", on_click=resolve, args=(major["number"], "storm"))
            else:
                st.markdown(f"#### 🌩️ {row['service']}")
                st.progress(min(1.0, row["open_reports"] / row["threshold"]),
                            text=f"{row['open_reports']} of {row['threshold']} reports in the last "
                                 f"{row['window_minutes']} minutes")
                if row["proposal"]:
                    st.badge(f"Waiting for a technician: {row['proposal']} (see Approvals)", color="orange")
            places = ", ".join(f"{n} from {loc}" for loc, n in row["locations"].items())
            if places:
                st.caption(f"Reports: {places}")


@st.fragment(run_every="20s")
def live_status():
    services = api.get("/status/overview")["services"]
    broken = [s for s in services if s["state"] in ("degraded", "outage")]
    st.caption(f"{len(services)} services checked live · {len(broken)} with a known issue · refreshes every 20 s")
    for start in range(0, len(services), 4):
        for column, service in zip(st.columns(4), services[start:start + 4]):
            with column.container(border=True, height=175):
                label = f"{STATE_ICON.get(service['state'], '⚪')} **{service['service']}**"
                if service["demo"]:
                    label += " · 🎬 demo"
                if service["stale"]:
                    label += " · stale"
                st.markdown(label)
                st.caption(service["summary"][:160])


with tab_storm:
    storm_panel()
    st.markdown("##### Live service status")
    live_status()


# --- tickets ---------------------------------------------------------------------------------------

def ticket_detail(number: str) -> None:
    ticket = api.get(f"/admin/incidents/{number}")
    with st.container(border=True):
        st.markdown(f"#### {ticket['number']} · {ticket['short_description']}")
        st.caption(f"P{ticket['priority']} · {ticket['state']} · {ticket['category']} · "
                   f"{ticket['service'] or 'no service'} · {ticket['location'] or '—'} · opened "
                   f"{when(ticket['created_at'])} via {ticket['channel']}")
        if ticket["employee_id"]:
            st.markdown(f"**Caller:** {who(ticket['employee_id'])}")
        if ticket["parent_number"]:
            st.markdown(f"**Part of major incident:** {ticket['parent_number']}")
        if ticket["description"]:
            st.markdown(f"**Details:** {ticket['description']}")
        if ticket["children"]:
            st.markdown(f"**Linked reports ({len(ticket['children'])}):** "
                        + ", ".join(f"{c['number']} ({who(c['employee_id'])}, {c['state']})"
                                    for c in ticket["children"]))
        st.markdown("**Work notes**")
        for note in ticket["notes"] or [{"author": "", "note": "No notes yet.", "created_at": None}]:
            st.markdown(f"- {note['note']}" + (f"  \n  <small>{note['author']} · {when(note['created_at'])}</small>"
                                               if note["created_at"] else ""), unsafe_allow_html=True)
        if ticket["state"] not in ("resolved", "closed"):
            st.text_input("Resolution note", key=f"tickets-resolve-note-{number}")
            label = "Resolve major incident and text everyone affected" if ticket["is_major"] else "Resolve"
            st.button(label, key=f"tickets-resolve-{number}", on_click=resolve, args=(number, "tickets"))


with tab_tickets:
    show_flash("tickets")
    controls = st.columns([1, 1, 3], vertical_alignment="bottom")
    open_only = controls[0].toggle("Open only", value=True, key="tickets_open_only")
    controls[1].button("Refresh", key="tickets_refresh", icon="🔄")
    search = controls[2].text_input("Search", key="tickets_search", placeholder="number, summary, service, name")
    tickets = api.get("/admin/incidents", open_only=open_only, limit=300)["incidents"]
    rows = [{
        "Number": t["number"], "P": t["priority"], "State": t["state"],
        "Type": "major" if t["is_major"] else t["ticket_type"],
        "Summary": ("⭐ " if t["is_major"] else "") + t["short_description"],
        "Service": t["service"] or "", "Caller": who(t["employee_id"]) if t["employee_id"] else "",
        "Location": t["location"] or "", "Major incident": t["parent_number"] or "", "Opened": when(t["created_at"]),
    } for t in tickets]
    if search:
        rows = [r for r in rows if search.lower() in " ".join(map(str, r.values())).lower()]
    st.caption(f"{len(rows)} ticket(s). Click a row for details.")
    picked = st.dataframe(rows, hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row",
                          key="tickets_table")
    if picked.selection.rows:
        ticket_detail(rows[picked.selection.rows[0]]["Number"])


# --- phones ----------------------------------------------------------------------------------------

@st.fragment(run_every="3s")
def phones_panel():
    ids = list(EMPLOYEES)
    employee_id = st.selectbox("Whose phone?", ids, index=ids.index("E1001") if "E1001" in ids else 0,
                               format_func=who, key="phone_of")
    employee = EMPLOYEES[employee_id]
    inbox = api.get("/admin/messages", employee_id=employee_id, limit=30)["messages"]
    phone, everyone = st.columns([2, 3])
    with phone:
        codes = [m for m in inbox if re.search(r"code is \d{6}", m["body"])]
        if codes:
            st.metric("Latest verification code", re.search(r"code is (\d{6})", codes[0]["body"]).group(1),
                      help=f"Texted {when(codes[0]['created_at'])}", border=True)
        with st.container(border=True, height=480):
            st.caption(f"📱 {employee['mobile']} · ✉️ {employee['email']}")
            if not inbox:
                st.caption("No messages yet.")
            for message in inbox:
                with st.chat_message("sms" if message["channel"] == "sms" else "email",
                                     avatar="💬" if message["channel"] == "sms" else "✉️"):
                    st.markdown(message["body"])
                    st.caption(when(message["created_at"]))
    with everyone:
        st.markdown("##### Every message sent")
        st.dataframe([{"To": who(m["employee_id"]), "How": m["channel"], "Message": m["body"],
                       "When": when(m["created_at"])}
                      for m in api.get("/admin/messages", limit=50)["messages"]],
                     hide_index=True, width="stretch", height=480)


with tab_phones:
    st.caption("Nothing really leaves this machine: these are the texts and emails StormDesk would send.")
    phones_panel()


# --- calls -----------------------------------------------------------------------------------------

def start_review(conversation_id: str, area: str) -> None:
    attempt(area, lambda: api.post(f"/admin/reviews/{conversation_id}/run"),
            f"Review of {conversation_id} started. It takes about half a minute.")


with tab_calls:
    show_flash("calls")
    st.caption("Every call, and every button the voice agent pressed during it.")
    st.button("Refresh", key="calls_refresh", icon="🔄")
    calls = api.get("/admin/sessions", limit=50)["sessions"]
    call_rows = [{"Call": s["conversation_id"], "Caller": s["full_name"] or "not identified",
                  "Verified": "✅" if s["verified_at"] else "", "Locked": "🔒" if s["locked"] else "",
                  "Last ticket": s["last_ticket"] or "", "Started": when(s["created_at"])} for s in calls]
    picked_call = st.dataframe(call_rows, hide_index=True, width="stretch", on_select="rerun",
                               selection_mode="single-row", key="calls_table")
    if picked_call.selection.rows:
        conversation_id = call_rows[picked_call.selection.rows[0]]["Call"]
        entries = list(reversed(api.get("/admin/audit", conversation_id=conversation_id, limit=200)["entries"]))
        try:
            call_review = api.get(f"/admin/reviews/{conversation_id}")
            st.info(f"{VERDICT_ICON.get(call_review['verdict'], '⏳')} Review: {call_review['headline'] or call_review['status']}"
                    " (details in the Reviews tab)", icon="🧑‍⚖️")
        except BackendError:
            st.button("Review this call now", key=f"review-now-{conversation_id}", on_click=start_review,
                      args=(conversation_id, "calls"))
        st.markdown(f"##### Timeline of {conversation_id} ({len(entries)} steps)")
        for entry in entries:
            icon = "✅" if entry["ok"] else "⚠️"
            with st.expander(f"{icon} {clock(entry['ts'])} · **{entry['tool']}** · {entry['latency_ms']} ms"):
                hint = entry["response"].get("agent_hint")
                if hint:
                    st.info(hint, icon="💡")
                left, right = st.columns(2)
                left.caption("Agent sent")
                left.json({k: v for k, v in entry["request"].items() if k != "conversation_id"})
                right.caption("Server answered")
                right.json({k: v for k, v in entry["response"].items() if k != "agent_hint"}, expanded=False)


# --- reviews ---------------------------------------------------------------------------------------

def create_follow_up(conversation_id: str, index: int) -> None:
    attempt("reviews", lambda: api.post(f"/admin/reviews/{conversation_id}/follow-ups/{index}",
                                        {"technician_id": technician}), "Follow-up ticket created.")


def _score(value) -> str:
    return f"{value}/5" if value else "—"


def review_detail(review: dict) -> None:
    report = review["report"] or {}
    card = report.get("scorecard") or {}
    resolution = report.get("resolution") or {}
    process = report.get("process") or {}
    experience = report.get("experience") or {}
    cid = review["conversation_id"]
    with st.container(border=True):
        st.markdown(f"#### {VERDICT_ICON.get(review['verdict'], '⏳')} {(review['verdict'] or review['status']).upper()}"
                    f" · {who(review['employee_id']) if review['employee_id'] else 'caller not identified'}")
        if card.get("headline"):
            st.markdown(card["headline"])
        cols = st.columns(4)
        cols[0].metric("Resolution", _score(card.get("resolution_score")))
        cols[1].metric("Process", _score(card.get("process_score")))
        cols[2].metric("Experience", _score(card.get("experience_score")))
        cols[3].metric("Call length", f"{(report.get('metrics') or {}).get('duration_s') or '?'} s")
        st.caption(f"Desks: {' → '.join(report.get('desks') or []) or '—'} · outcome: {resolution.get('outcome', '—')}"
                   f" · model: {review['model']} · [ElevenLabs transcript](https://elevenlabs.io/app/agents/history/{cid})")
        if review.get("error"):
            st.warning(f"Incomplete: {review['error']}")
        for flag in card.get("flags") or []:
            st.warning(flag, icon="🚩")

        rules_col, ai_col = st.columns(2)
        with rules_col:
            st.markdown("**Rule checks** (from StormDesk's records)")
            st.dataframe([{"": RULE_ICON.get(c["result"], c["result"]), "Check": c["label"], "Detail": c["detail"]}
                          for c in report.get("rule_checks", [])], hide_index=True, width="stretch")
        with ai_col:
            st.markdown("**Process review** (AI)")
            st.dataframe([{"": RULE_ICON.get(c["verdict"], c["verdict"]), "Area": c["name"], "Evidence": c["evidence"]}
                          for c in process.get("checks", [])], hide_index=True, width="stretch")
        for violation in process.get("violations") or []:
            st.error(f"Violation: {violation}")
        for signal in process.get("social_engineering_signals") or []:
            st.warning(f"Caller behaviour: {signal}", icon="🕵️")

        need, feel = st.columns(2)
        with need:
            st.markdown(f"**What the caller needed:** {resolution.get('caller_need', '—')}")
            for quote in resolution.get("evidence") or []:
                st.markdown(f"> {quote}")
        with feel:
            st.markdown(f"**Caller experience:** {experience.get('summary', '—')}")
            for item in experience.get("strengths") or []:
                st.markdown(f"- 👍 {item}")
            for item in experience.get("issues") or []:
                st.markdown(f"- 👎 {item}")

        items = (report.get("follow_up") or {}).get("items") or []
        st.markdown(f"**Follow-ups** ({len(items)})")
        for i, item in enumerate(items):
            text, action = st.columns([4, 1], vertical_alignment="center")
            text.markdown(f"**{item['owner'].replace('_', ' ')} · {item['urgency'].replace('_', ' ')}:** "
                          f"{item['action']}  \n<small>{item['reason']}</small>", unsafe_allow_html=True)
            if item.get("ticket"):
                action.badge(item["ticket"], color="green")
            else:
                action.button("Create ticket", key=f"followup-{cid}-{i}", on_click=create_follow_up, args=(cid, i))
        if card.get("coaching"):
            st.markdown("**Coaching for the agent's instructions**")
            for tip in card["coaching"]:
                st.markdown(f"- 💡 {tip}")
        opinion = report.get("elevenlabs_opinion") or {}
        if opinion.get("call_successful"):
            st.caption(f"For comparison, ElevenLabs' built-in analysis rated this call: {opinion['call_successful']}.")
        st.button("Re-run review", key=f"rerun-{cid}", on_click=start_review, args=(cid, "reviews"))


with tab_reviews:
    show_flash("reviews")
    st.caption("After every call, three AI reviewers on Nebius (resolution, process, caller experience), a follow-up "
               "planner and a judge grade it. Rule checks come from StormDesk's own records, not the AI.")
    st.button("Refresh", key="reviews_refresh", icon="🔄")
    reviews = api.get("/admin/reviews", limit=50)["reviews"]
    counts = {v: sum(1 for r in reviews if r["verdict"] == v) for v in ("pass", "attention", "fail")}
    tiles = st.columns(4)
    tiles[0].metric("Calls reviewed", len(reviews))
    tiles[1].metric("✅ Pass", counts["pass"])
    tiles[2].metric("🟡 Attention", counts["attention"])
    tiles[3].metric("❌ Fail", counts["fail"])
    review_rows = [{"": VERDICT_ICON.get(r["verdict"], "⏳"), "Caller": who(r["employee_id"]) if r["employee_id"] else "—",
                    "Headline": r["headline"] or r["status"], "When": when(r["call_started_at"] or r["created_at"]),
                    "Call": r["conversation_id"]} for r in reviews]
    picked_review = st.dataframe(review_rows, hide_index=True, width="stretch", on_select="rerun",
                                 selection_mode="single-row", key="reviews_table")
    if picked_review.selection.rows:
        review_detail(reviews[picked_review.selection.rows[0]])


# --- drills ----------------------------------------------------------------------------------------

def set_drill(flag: str) -> None:
    enabled = st.session_state[f"chaos-{flag}"]
    result = attempt("drills", lambda: api.post("/admin/chaos", {"flag": flag, "enabled": enabled}),
                     f"{DRILL_LABEL[flag]}: {'ON' if enabled else 'off'}.")
    delivered = (result or {}).get("delivered_from_outbox", {}).get("delivered", [])
    if delivered:
        flash("drills", "Delivered from the outbox: " + ", ".join(f"{d['ref']} → {d['result']}" for d in delivered),
              "info")


def start_demo_outage() -> None:
    body = {"service": st.session_state["demo_service"], "title": st.session_state["demo_title"],
            "impact": st.session_state["demo_impact"] or "outage"}
    attempt("drills", lambda: api.post("/admin/demo-outage", body), f"Demo outage started on {body['service']}.")


def clear_demo_outage(service_key: str) -> None:
    attempt("drills", lambda: api.delete(f"/admin/demo-outage/{service_key}"), f"Demo outage on {service_key} cleared.")


def add_storm_reports() -> None:
    body = {"service": st.session_state["storm_service"], "location": st.session_state["storm_location"],
            "count": st.session_state["storm_count"]}
    attempt("drills", lambda: api.post("/admin/demo-storm", body),
            f"Opened {body['count']} {body['service']} report(s) from {body['location']}.")


def reset_data() -> None:
    attempt("drills", lambda: api.post("/admin/reset", {"confirm": True}), "Practice data reset.")
    st.session_state["reset_confirm"] = False


with tab_drills:
    show_flash("drills")
    chaos = api.get("/admin/chaos")
    services = api.get("/admin/services")["services"]
    service_names = {s["key"]: s["name"] for s in services}
    switches, scenarios = st.columns(2, gap="large")

    with switches:
        st.markdown("##### Failure switches")
        st.caption("Break a dependency on purpose and watch StormDesk cope.")
        for flag, description in chaos["descriptions"].items():
            st.session_state[f"chaos-{flag}"] = chaos["flags"][flag]
            st.toggle(DRILL_LABEL[flag], key=f"chaos-{flag}", help=description, on_change=set_drill, args=(flag,))
        st.markdown("##### Outbox")
        entries = api.get("/admin/outbox")["entries"]
        if entries:
            st.dataframe([{"Ref": e["ref"], "What": e["kind"], "Status": e["status"], "Ticket": e["result"] or "",
                           "Tries": e["attempts"], "Queued": when(e["created_at"])} for e in entries],
                         hide_index=True, width="stretch")
        else:
            st.caption("Empty.")
        st.button("Deliver queued tickets now", key="housekeeping",
                  on_click=lambda: attempt("drills", lambda: api.post("/admin/housekeeping"), "Housekeeping ran."))

    with scenarios:
        st.markdown("##### Demo outage")
        st.caption("Real outages happen at random. This one is labelled 'demo' everywhere it appears.")
        st.selectbox("Service", list(service_names), format_func=service_names.get, key="demo_service")
        st.text_input("What's broken", value="Users unable to connect", key="demo_title")
        st.segmented_control("Impact", ["outage", "degraded"], default="outage", key="demo_impact")
        st.button("Start demo outage", key="demo_start", on_click=start_demo_outage)
        for demo in api.get("/admin/demo-outages")["demo_outages"]:
            st.button(f"Clear demo outage: {service_names.get(demo['service_key'], demo['service_key'])}",
                      key=f"demo_clear-{demo['service_key']}", on_click=clear_demo_outage,
                      args=(demo["service_key"],))

        st.markdown("##### Set up a ticket storm")
        st.caption("Open reports from colleagues, so the next caller about the same thing tips it over.")
        st.selectbox("Service", list(service_names), index=list(service_names).index("vpn"),
                     format_func=service_names.get, key="storm_service")
        st.selectbox("Office", LOCATIONS, key="storm_location")
        st.number_input("Reports", min_value=1, max_value=3, value=2, key="storm_count")
        st.button("Add reports", key="storm_add", on_click=add_storm_reports)

        st.markdown("##### Start over")
        st.checkbox("I understand this wipes every ticket, call and approval", key="reset_confirm")
        st.button("Reset practice data", key="reset", disabled=not st.session_state.get("reset_confirm"),
                  on_click=reset_data)
