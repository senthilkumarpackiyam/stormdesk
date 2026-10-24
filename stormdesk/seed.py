"""The practice company: Acme Corp's employees, laptops, knowledge base, and past tickets.

Everything here is fictional (555 phone numbers, .example email domain).

    uv run python -m stormdesk.seed --reset                  # wipe and reload
    uv run python -m stormdesk.seed --storm vpn --location Chennai --count 2
                                                             # add fresh reports to set up a ticket storm
"""

import argparse
import json

from stormdesk import timeutil
from stormdesk.approvals.graph import clear_checkpoints
from stormdesk.itsm.local import insert_incident
from stormdesk.store.db import connect, init_db

# id, full name, department, title, location, manager, vip, status, laptop model, os product, os release, os label
EMPLOYEES = [
    ("E1001", "Sarah Jeesen", "Finance", "Senior Accountant", "Chennai", "E1011", 0, "active",
     "Dell Latitude 7440", "windows", "11-24h2-w", "Windows 11 24H2"),
    ("E1002", "Daniel Okafor", "Sales", "VP Sales EMEA", "London", "E1020", 1, "active",
     "MacBook Pro 14", "macos", "14", "macOS 14 Sonoma"),
    ("E1003", "Mei Lin Chen", "Engineering", "Staff Engineer", "Austin", "E1016", 0, "active",
     "MacBook Pro 16", "macos", "26", "macOS 26 Tahoe"),
    ("E1004", "Karthik", "Engineering", "Software Engineer", "Bengaluru", "E1016", 0, "active",
     "Lenovo ThinkPad X1 Carbon", "windows", "11-25h2-e", "Windows 11 25H2"),
    ("E1005", "Sofia Alvarez", "HR", "HR Business Partner", "Austin", "E1020", 0, "active",
     "MacBook Air 13", "macos", "15", "macOS 15 Sequoia"),
    ("E1006", "Kwame Mensah", "Operations", "Logistics Coordinator", "London", "E1018", 0, "active",
     "HP EliteBook 840", "windows", "10-22h2", "Windows 10 22H2"),
    ("E1007", "Hannah Schmidt", "Legal", "Corporate Counsel", "London", "E1020", 0, "active",
     "Surface Laptop 6", "windows", "11-24h2-e", "Windows 11 24H2"),
    ("E1008", "Ravi Shankar", "Finance", "Financial Analyst", "Chennai", "E1011", 0, "active",
     "Dell Latitude 5450", "windows", "11-23h2-e", "Windows 11 23H2"),
    ("E1009", "Aisha Khan", "Marketing", "Marketing Manager", "Austin", "E1020", 0, "active",
     "MacBook Air 15", "macos", "26", "macOS 26 Tahoe"),
    ("E1010", "Tomas Silva", "Customer Support", "Support Lead", "Bengaluru", "E1018", 0, "active",
     "Lenovo ThinkPad T14", "windows", "11-24h2-e", "Windows 11 24H2"),
    ("E1011", "Grace Park", "Finance", "Chief Financial Officer", "Austin", "E1020", 1, "active",
     "MacBook Pro 14", "macos", "26", "macOS 26 Tahoe"),
    ("E1012", "Liam O'Brien", "Sales", "Account Executive", "London", "E1002", 0, "terminated",
     "Lenovo ThinkPad T14", "windows", "11-24h2-e", "Windows 11 24H2"),
    ("E1013", "Fatima Noor", "Engineering", "QA Engineer", "Bengaluru", "E1016", 0, "active",
     "Dell XPS 13", "windows", "11-25h2-e", "Windows 11 25H2"),
    ("E1014", "Ethan Brooks", "Sales", "Sales Engineer", "Remote", "E1002", 0, "active",
     "MacBook Pro 14", "macos", "15", "macOS 15 Sequoia"),
    ("E1015", "Ananya Iyer", "Finance", "Payroll Specialist", "Chennai", "E1011", 0, "active",
     "Dell Latitude 7440", "windows", "11-24h2-e", "Windows 11 24H2"),
    ("E1016", "Marcus Lee", "Engineering", "VP Engineering", "Austin", "E1020", 1, "active",
     "MacBook Pro 16", "macos", "26", "macOS 26 Tahoe"),
    ("E1017", "Yuki Tanaka", "Design", "Product Designer", "Remote", "E1016", 0, "active",
     "MacBook Pro 14", "macos", "26", "macOS 26 Tahoe"),
    ("E1018", "Chloe Dubois", "Operations", "Head of Operations", "London", "E1020", 0, "active",
     "Surface Laptop 7", "windows", "11-25h2-e", "Windows 11 25H2"),
    ("E1019", "Senthil Kumar", "IT", "Service Desk Technician", "Chennai", "E1018", 0, "active",
     "Lenovo ThinkPad P1", "windows", "11-25h2-e", "Windows 11 25H2"),
    ("E1020", "Olivia Bennett", "Executive", "Chief Executive Officer", "Austin", None, 1, "active",
     "MacBook Pro 14", "macos", "26", "macOS 26 Tahoe"),
    ("E1021", "Noah Fischer", "IT", "Service Desk Lead", "London", "E1018", 0, "active",
     "Lenovo ThinkPad P1", "windows", "11-25h2-e", "Windows 11 25H2"),
]

# kb_id, title, category, service, keywords, steps, escalate_if, sensitive_action
KB_ARTICLES = [
    ("KB0010", "VPN won't connect", "network", "vpn",
     "vpn connect connecting connection fail failed failing error remote access ivanti secure access tunnel home",
     ["Check that normal websites load, so we know your home or hotel internet is working.",
      "Fully quit the Ivanti Secure Access app from the system tray or menu bar, then open it again.",
      "Make sure the connection is set to vpn dot acme dot example, then click Connect.",
      "Sign in on the Acme single sign-on page and approve the push on your phone.",
      "If it still fails, restart the laptop and try once more."],
     "Still failing after a restart, or the app shows a certificate or security warning "
     "(treat any warning as a security issue).", None),
    ("KB0011", "VPN keeps disconnecting", "network", "vpn",
     "vpn disconnect disconnects disconnecting drops drop dropping dropped keeps unstable timeout kicked off",
     ["Plug the laptop into power: battery saver can drop the VPN.",
      "If you're on Wi-Fi, move closer to the router or try a cable.",
      "In Ivanti Secure Access, disconnect, wait ten seconds, and reconnect.",
      "Close video calls you aren't using; weak connections drop under load."],
     "Drops continue several times an hour, or colleagues report the same thing.", None),
    ("KB0020", "Lost, replaced, or new phone: MFA re-enrollment", "account", "sso",
     "mfa multi factor two factor 2fa authenticator okta verify push lost phone new phone stolen replaced "
     "codes not arriving approve sign in approvals",
     ["Your sign-in approvals need to move to your new phone.",
      "That needs a verified identity and a technician's approval, so I'll set that up.",
      "Once approved, open Okta Verify on the new phone and scan the setup code we email you."],
     "Always needs technician approval.", "mfa_reset"),
    ("KB0021", "Account locked out", "account", "sso",
     "locked lockout locked out account disabled too many attempts log in login sign in blocked",
     ["Lockouts clear on their own after 30 minutes.",
      "If you can't wait, I can request an unlock: that needs your identity verified and a technician's approval.",
      "After the unlock, sign in on one device first, so old saved passwords elsewhere don't lock you again."],
     "Locked again within a day of an unlock.", "account_unlock"),
    ("KB0022", "Password expired or forgotten", "account", "sso",
     "password passwords expired forgot forgotten reset change new",
     ["For your security, I never ask for or listen to passwords on a call.",
      "Go to passwords dot acme dot example on any device.",
      "Choose Forgot password, approve the push on your phone, and set a new password.",
      "If you don't have your phone either, I can request an MFA reset first."],
     "The self-service portal fails, or the caller has no access to their MFA device.", None),
    ("KB0030", "Slack not loading or messages not sending", "collaboration", "slack",
     "slack loading load messages message sending send notifications channels workspace crash crashing",
     ["Check whether Slack works in a web browser at acme dot slack dot com.",
      "Quit Slack completely and reopen it.",
      "In Slack, open Help, then Troubleshooting, then Clear cache and restart.",
      "Check other websites load, in case you're offline."],
     "The browser version fails too and Slack's status page shows no incident.", None),
    ("KB0031", "Zoom audio or video problems", "collaboration", "zoom",
     "zoom audio sound microphone mic speaker camera video echo hear meeting",
     ["In Zoom, click the arrow next to the microphone icon and pick the right microphone and speaker.",
      "Close other apps that might be using the camera or microphone, like Google Meet.",
      "Leave and rejoin the meeting.",
      "On a Mac, open System Settings, Privacy, Microphone and Camera, and allow Zoom."],
     "Hardware isn't detected by any app.", None),
    ("KB0032", "Google Meet camera or microphone not working", "collaboration", "google_meet",
     "google meet camera mic microphone video black screen detected browser permission",
     ["Click the camera icon in the browser's address bar and allow camera and microphone for Meet.",
      "Close Zoom or other apps that might be holding the camera.",
      "Reload the Meet tab.",
      "Try Chrome if you're using another browser."],
     "Camera fails in every app.", None),
    ("KB0040", "Gmail not syncing", "email", "gmail",
     "gmail email emails mail sync syncing inbox updating missing phone offline",
     ["Check Gmail in a web browser at mail dot google dot com.",
      "On your phone, pull down to refresh, and check the app is allowed to use mobile data.",
      "Remove and re-add your Acme account in the mail app.",
      "Check the Spam folder and any filters for missing emails."],
     "Web Gmail is also failing and Google's status page shows no incident.", None),
    ("KB0050", "Office Wi-Fi won't connect", "network", "wifi",
     "wifi wi-fi wireless network office connect internet acmecorp-secure",
     ["Make sure you're joining AcmeCorp-Secure, not AcmeCorp-Guest.",
      "Turn Wi-Fi off and on again.",
      "Forget the AcmeCorp-Secure network and rejoin it with your Acme sign-in.",
      "Restart the laptop."],
     "Still failing, or several people in the same office are affected.", None),
    ("KB0051", "Printer jobs stuck", "hardware", "printing",
     "printer print printing stuck queue jam jammed offline paper toner job",
     ["Check the printer's screen for a paper jam or low toner.",
      "Cancel the stuck job from the print queue on your laptop.",
      "Turn the printer off for 30 seconds and back on.",
      "Re-add the printer from the Acme self-service app."],
     "The printer shows a hardware error.", None),
    ("KB0060", "Laptop running slow", "hardware", None,
     "slow laptop computer sluggish freezing frozen hang hanging fan hot performance disk full storage",
     ["Save your work and restart the laptop; many slowdowns clear after a restart.",
      "Close browser tabs and apps you aren't using.",
      "Check free disk space: keep at least 10 percent free.",
      "Install pending system updates tonight, with the laptop plugged in."],
     "Still slow after a restart and updates, or the operating system is out of support.", None),
    ("KB0070", "Suspicious email, link, or pop-up (phishing)", "security", None,
     "phishing suspicious email link clicked attachment scam fake popup pop up hacked virus malware strange "
     "weird unexpected login prompt certificate warning gift card",
     ["Don't click any more links or open attachments in that message.",
      "If you typed your password into a page from that message, tell me now: that's urgent.",
      "Use the Report phishing button in Gmail to send it to the security team.",
      "Leave your laptop on and connected so security can check it."],
     "The caller clicked a link, entered credentials, or opened an attachment: route to security now.", None),
    ("KB0080", "Software install or access request", "access", None,
     "install software access request permission admin rights license application app tool grant group",
     ["Tell me the software or system and why you need it.",
      "Access changes need your manager's and a technician's approval, so I'll file the request.",
      "You'll get an email once it's approved, usually within one business day."],
     "Always needs approval.", "access_grant"),
    ("KB0090", "Operating system out of support", "hardware", None,
     "unsupported support end life eol upgrade windows 10 old version update operating system os",
     ["Your laptop's operating system no longer gets security updates from the vendor.",
      "Back up anything that isn't already in Google Drive.",
      "I'll create an upgrade ticket, and a technician will book a time with you.",
      "Until then, avoid installing unknown software, and connect to the VPN weekly for updates."],
     "Always create an upgrade ticket.", None),
]

# employee, short description, category, service, priority, state, days ago
PAST_INCIDENTS = [
    ("E1001", "VPN disconnects every few minutes when working from home", "network", "vpn", 3, "in_progress", 1),
    ("E1001", "Gmail not syncing on phone", "email", "gmail", 4, "resolved", 20),
    ("E1002", "Echo on Zoom calls", "collaboration", "zoom", 3, "resolved", 5),
    ("E1004", "Need GitHub access for the payments repo", "access", "github", 3, "resolved", 12),
    ("E1006", "Laptop very slow to start", "hardware", None, 3, "on_hold", 3),
    ("E1007", "Printer on London 2nd floor jammed", "hardware", "printing", 4, "resolved", 9),
    ("E1009", "Locked out after password change", "account", "sso", 2, "resolved", 15),
    ("E1011", "Boardroom projector not detected", "hardware", None, 2, "resolved", 8),
    ("E1013", "Wi-Fi drops in Bengaluru office", "network", "wifi", 3, "resolved", 6),
    ("E1017", "Suspicious invoice email", "security", None, 2, "resolved", 25),
]


RESET_ORDER = (
    "reviews", "audit_log", "demo_outages", "chaos", "outbox", "identity_changes", "approvals", "messages",
    "verification_codes", "sessions", "work_notes", "incidents", "kb_articles", "devices", "employees",
)


def _email(name: str) -> str:
    return name.lower().replace("'", "").replace(" ", ".") + "@acme.example"


def seed(reset: bool = False) -> None:
    init_db()
    if reset:
        clear_checkpoints()
    with connect() as conn:
        if reset:
            for table in RESET_ORDER:
                conn.execute(f"DELETE FROM {table}")
        for (eid, name, dept, title, loc, mgr, vip, status, model, os_product, os_release, os_label) in EMPLOYEES:
            num = eid[1:]
            conn.execute(
                "INSERT INTO employees VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (eid, name, _email(name), f"+1-555-01{num[2:]}", dept, title, loc, mgr, vip, status),
            )
            conn.execute(
                "INSERT INTO devices VALUES (?, ?, 'laptop', ?, ?, ?, ?)",
                (f"LT-{num}", eid, model, os_product, os_release, os_label),
            )
        for (kb_id, title, category, service, keywords, steps, escalate_if, action) in KB_ARTICLES:
            conn.execute(
                "INSERT INTO kb_articles VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (kb_id, title, category, service, keywords, json.dumps(steps), escalate_if, action),
            )
        locations = {e[0]: e[4] for e in EMPLOYEES}
        for (eid, desc, category, service, priority, state, days) in PAST_INCIDENTS:
            insert_incident(conn, employee_id=eid, short_description=desc, category=category, service=service,
                            location=locations[eid], priority=priority, state=state,
                            created_at=timeutil.ago_iso(days=days))


def seed_if_empty() -> None:
    """Load the practice company on first start. On later starts, bring renamed employees up to date."""
    init_db()
    with connect() as conn:
        empty = conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0] == 0
        if not empty:
            # A database made before a rename keeps its tickets and calls; only the names and emails change.
            for eid, name, *_ in EMPLOYEES:
                conn.execute("UPDATE employees SET full_name = ?, email = ? WHERE employee_id = ? AND full_name != ?",
                             (name, _email(name), eid, name))
    if empty:
        seed()


def add_storm(service: str, location: str, count: int, exclude: str = "E1001") -> list[str]:
    """Open `count` fresh reports for one service from colleagues at one location."""
    callers = [e for e in EMPLOYEES if e[4] == location and e[0] != exclude and e[7] == "active"]
    if len(callers) < count:
        raise ValueError(f"Only {len(callers)} other active employees in {location}.")
    numbers = []
    with connect() as conn:
        for i, emp in enumerate(callers[:count]):
            numbers.append(insert_incident(
                conn, employee_id=emp[0], short_description=f"{service.upper()} not working", category="network",
                service=service, location=location, priority=3, created_at=timeutil.ago_iso(minutes=12 - i * 4),
            ))
    return numbers


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="wipe all tables and reload the practice company")
    parser.add_argument("--storm", metavar="SERVICE", help="add fresh reports for SERVICE (e.g. vpn)")
    parser.add_argument("--location", default="Chennai")
    parser.add_argument("--count", type=int, default=2)
    args = parser.parse_args()
    if args.reset:
        seed(reset=True)
        print(f"Reloaded {len(EMPLOYEES)} employees, {len(KB_ARTICLES)} KB articles, {len(PAST_INCIDENTS)} incidents.")
    else:
        seed_if_empty()
    if args.storm:
        try:
            numbers = add_storm(args.storm, args.location, args.count)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        print(f"Added {len(numbers)} open {args.storm} reports from {args.location}: {', '.join(numbers)}")


if __name__ == "__main__":
    main()
