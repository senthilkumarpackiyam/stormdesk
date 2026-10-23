"""A technician closing a ticket from the console.

Closing a major incident also closes every ticket linked to it and texts each affected person,
so nobody has to call back to ask whether the VPN is fixed."""

from stormdesk import messaging
from stormdesk.itsm import itsm
from stormdesk.itsm.local import CLOSED_STATES
from stormdesk.sources.vendor_status import SERVICES
from stormdesk.staff import get_technician


class ResolveError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def resolve_incident(number: str, technician_id: str, note: str = "") -> dict:
    technician = get_technician(technician_id)
    if not technician:
        raise ResolveError("forbidden", "Only active IT staff can resolve tickets.")
    incident = itsm.get_incident(number)
    if not incident:
        raise ResolveError("not_found", f"No incident {number}.")
    if incident["state"] in CLOSED_STATES:
        raise ResolveError("already_closed", f"{number} is already {incident['state']}.")

    by = f"{technician['full_name']} ({technician['employee_id']})"
    itsm.add_note(number, by, f"Resolved. {note}".strip())
    itsm.set_state(number, "resolved")
    children = itsm.children_of(number) if incident["is_major"] else []
    service = SERVICES.get(incident["service"] or "")
    name = service.name if service else "reported"
    notified = set()
    for child in children:
        itsm.add_note(child["number"], by, f"Resolved with major incident {number}.")
        itsm.set_state(child["number"], "resolved")
        if child["employee_id"] and child["employee_id"] not in notified:
            employee = itsm.get_employee(child["employee_id"])
            try:
                messaging.send(employee, "sms", f"Acme IT: the {name} problem (major incident {number}) is fixed. "
                                                f"Still not working for you? Call the service desk.")
                notified.add(child["employee_id"])
            except messaging.MessagingDown:
                pass
    if incident["employee_id"] and not incident["is_major"]:
        employee = itsm.get_employee(incident["employee_id"])
        try:
            messaging.send(employee, "sms", f"Acme IT: your ticket {number} has been resolved. "
                                            "Still having trouble? Call the service desk.")
            notified.add(incident["employee_id"])
        except messaging.MessagingDown:
            pass
    return {"number": number, "resolved_children": [c["number"] for c in children], "notified": len(notified)}
