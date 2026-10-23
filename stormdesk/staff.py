"""Who counts as a technician: active employees in the IT department."""

from stormdesk.identity import normalize_employee_id
from stormdesk.itsm import itsm


def get_technician(technician_id: str) -> dict | None:
    employee_id = normalize_employee_id(technician_id)
    employee = itsm.get_employee(employee_id) if employee_id else None
    if employee and employee["status"] == "active" and employee["department"] == "IT":
        return employee
    return None
