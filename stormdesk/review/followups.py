"""Turning a reviewer's suggested follow-up into a real ticket. The reviewers only suggest; a technician
decides, in the console, which suggestions become work (writes need a human)."""

from stormdesk.itsm import itsm
from stormdesk.review import store
from stormdesk.staff import get_technician

PRIORITY = {"today": 2, "this_week": 3}
CATEGORY = {"security_team": "security"}


class FollowUpError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def create_ticket(conversation_id: str, index: int, technician_id: str) -> str:
    technician = get_technician(technician_id)
    if not technician:
        raise FollowUpError("forbidden", "Only active IT staff can turn follow-ups into tickets.")
    review = store.get(conversation_id)
    items = ((review or {}).get("report", {}).get("follow_up") or {}).get("items") or []
    if not 0 <= index < len(items):
        raise FollowUpError("not_found", f"No follow-up #{index} for {conversation_id}.")
    item = items[index]
    if item.get("ticket"):
        raise FollowUpError("already_created", f"Follow-up #{index} is already ticket {item['ticket']}.")
    employee = itsm.get_employee(review["employee_id"]) if review.get("employee_id") else None
    number = itsm.create_incident(
        employee_id=review.get("employee_id"),
        short_description=item["action"][:160],
        description=f"{item['reason']}\n\nOwner: {item['owner']}. Suggested by the post-call review of "
                    f"{conversation_id}; approved by {technician['full_name']} ({technician['employee_id']}).",
        category=CATEGORY.get(item["owner"], "follow-up"), service=None,
        location=employee["location"] if employee else None, priority=PRIORITY.get(item["urgency"], 3),
        ticket_type="request", channel="review", conversation_id=conversation_id,
    )
    store.set_follow_up_ticket(conversation_id, index, number)
    return number
