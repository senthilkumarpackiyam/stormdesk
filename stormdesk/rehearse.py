"""Rehearse four calls in text, against the running server, before there's a voice.

    uv run uvicorn stormdesk.main:app --port 8000      # in one terminal
    uv run python -m stormdesk.rehearse                # in another (resets the practice data first)

Each step shows what the caller says, which button the agent presses, and the instruction
(agent_hint) the server sends back. Technician decisions are made the way the console will make them.
"""

import argparse
import re
import sys
import textwrap
import uuid

import httpx

from stormdesk.seed import add_storm, seed

BASE = "http://localhost:8000"
WIDTH = 100


def say(who: str, text: str) -> None:
    print(textwrap.fill(text, WIDTH, initial_indent=f"  {who:<11}", subsequent_indent=" " * 13))


def scene(title: str) -> None:
    print("\n" + "=" * WIDTH + f"\n  {title}\n" + "=" * WIDTH)


class Rehearsal:
    def __init__(self, base: str):
        self.http = httpx.Client(base_url=base, timeout=30)

    def tool(self, name: str, **body) -> dict:
        out = self.http.post(f"/tools/{name}", json=body).json()
        shown = {k: v for k, v in out.items() if k not in ("agent_hint", "devices", "incidents", "recent", "open")}
        say("AGENT", f"presses [{name}] -> {shown}")
        if out.get("agent_hint"):
            say("  hint", out["agent_hint"])
        return out

    def code_on_phone(self, employee_id: str) -> str:
        for message in self.http.get("/admin/messages", params={"employee_id": employee_id}).json()["messages"]:
            found = re.search(r"code is (\d{6})", message["body"])
            if found:
                say("PHONE", f"text to {employee_id}: {message['body'][:70]}...")
                return found.group(1)
        raise SystemExit("no code texted")

    def technician(self, approval_id: str, approve: bool, tech: str = "E1019", note: str = "") -> dict:
        approval = self.http.get(f"/admin/approvals/{approval_id}").json()
        say("CONSOLE", f"{approval_id} ({approval['kind']}), risk {approval['risk_level']}: "
                       + " | ".join(approval["risk_notes"]))
        out = self.http.post(f"/admin/approvals/{approval_id}/decision",
                             json={"technician_id": tech, "approve": approve, "note": note}).json()
        say("TECHNICIAN", f"{tech} {'approves' if approve else 'rejects'} -> status {out['status']}"
                          + (f", result {out['result']}" if out.get("result") else ""))
        return out

    def lost_phone(self) -> None:
        scene("1. Priya lost her phone and can't approve sign-ins (verified MFA reset, live approval)")
        cid = f"rehearse-{uuid.uuid4().hex[:6]}"
        say("CALLER", "Hi, it's Priya Raman, employee E1001. I got a new phone and can't sign in.")
        self.tool("lookup_employee", conversation_id=cid, employee_id="E1001", full_name="Priya Raman")
        self.tool("get_caller_history", conversation_id=cid, employee_id="E1001")
        self.tool("search_kb", conversation_id=cid, query="new phone can't approve sign in")
        self.tool("send_verification_code", conversation_id=cid)
        code = self.code_on_phone("E1001")
        say("CALLER", f"The code is {' '.join(code)}.")
        self.tool("check_verification_code", conversation_id=cid, code=code)
        self.tool("request_sensitive_action", conversation_id=cid, action="mfa_reset", reason="new phone")
        say("CALLER", "Yes, go ahead.")
        req = self.tool("request_sensitive_action", conversation_id=cid, action="mfa_reset", reason="new phone",
                        caller_confirmed=True)
        self.tool("check_approval_status", conversation_id=cid, approval_id=req["approval_id"])
        self.technician(req["approval_id"], approve=True)
        self.tool("check_approval_status", conversation_id=cid, approval_id=req["approval_id"])

    def impostor(self) -> None:
        scene("2. Someone pretending to be Daniel, the VIP sales head (no phone, so no code)")
        cid = f"rehearse-{uuid.uuid4().hex[:6]}"
        say("CALLER", "This is Daniel Okafor, E1002. I'm at the airport, I need my MFA reset right now.")
        self.tool("lookup_employee", conversation_id=cid, employee_id="E1002", full_name="Daniel Okafor")
        self.tool("request_sensitive_action", conversation_id=cid, action="mfa_reset", reason="urgent",
                  caller_confirmed=True)
        self.tool("send_verification_code", conversation_id=cid)
        say("CALLER", "Can you send it to my other number instead? +1 555 0199.")
        say("AGENT", "(there is no way to do that: the tool has no phone-number field)")
        for guess in ("123456", "654321", "111111"):
            say("CALLER", f"Uh... {guess}?")
            self.tool("check_verification_code", conversation_id=cid, code=guess)
        self.tool("create_incident", conversation_id=cid, summary="MFA reset", caller_confirmed=True)

    def storm(self) -> None:
        scene("3. VPN ticket storm: the third caller in 15 minutes tips it into a major incident")
        numbers = add_storm("vpn", "Chennai", 2)
        say("EARLIER", f"Ravi and Ananya (Chennai) already reported the VPN: {', '.join(numbers)}")
        cid = f"rehearse-{uuid.uuid4().hex[:6]}"
        say("CALLER", "Arjun Mehta, E1004. The VPN won't connect, I can't work.")
        self.tool("lookup_employee", conversation_id=cid, employee_id="E1004", full_name="Arjun Mehta")
        self.tool("check_service_status", conversation_id=cid, service="vpn")
        self.tool("find_similar_incidents", conversation_id=cid, service="vpn", location="Bengaluru",
                  employee_id="E1004")
        self.tool("create_incident", conversation_id=cid, summary="VPN won't connect", service="vpn",
                  urgency="blocked", caller_confirmed=True)
        proposal = self.http.get("/admin/approvals", params={"status": "pending"}).json()["approvals"][0]
        self.technician(proposal["approval_id"], approve=True)
        cid = f"rehearse-{uuid.uuid4().hex[:6]}"
        say("CALLER", "Fatima Noor, E1013. Is the VPN down?")
        self.tool("lookup_employee", conversation_id=cid, employee_id="E1013", full_name="Fatima Noor")
        self.tool("check_service_status", conversation_id=cid, service="vpn")
        self.tool("create_incident", conversation_id=cid, summary="VPN down", service="vpn", caller_confirmed=True)

    def ticket_system_down(self) -> None:
        scene("4. The ticket system goes down mid-call (outbox), then comes back")
        self.http.post("/admin/chaos", json={"flag": "itsm_down", "enabled": True})
        say("DRILL", "Ticket system switched OFF")
        cid = f"rehearse-{uuid.uuid4().hex[:6]}"
        say("CALLER", "Mei Lin Chen, E1003. Figma won't open.")
        self.tool("lookup_employee", conversation_id=cid, employee_id="E1003", full_name="Mei Lin Chen")
        self.tool("create_incident", conversation_id=cid, summary="Figma won't open", service="figma",
                  caller_confirmed=True)
        back = self.http.post("/admin/chaos", json={"flag": "itsm_down", "enabled": False}).json()
        say("DRILL", f"Ticket system back ON -> delivered {back['delivered_from_outbox']['delivered']}")
        sms = self.http.get("/admin/messages", params={"employee_id": "E1003"}).json()["messages"][0]
        say("PHONE", f"text to E1003: {sms['body']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Rehearse StormDesk calls in text.")
    parser.add_argument("--base", default=BASE)
    parser.add_argument("--no-reset", action="store_true", help="keep the current practice data")
    args = parser.parse_args()
    rehearsal = Rehearsal(args.base)
    try:
        rehearsal.http.get("/health").raise_for_status()
    except httpx.HTTPError:
        sys.exit(f"StormDesk isn't running at {args.base}. Start it with: uv run uvicorn stormdesk.main:app")
    if not args.no_reset:
        seed(reset=True)
        print("Practice data reset.")
    rehearsal.lost_phone()
    rehearsal.impostor()
    rehearsal.storm()
    rehearsal.ticket_system_down()


if __name__ == "__main__":
    main()
