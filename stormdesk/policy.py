"""What the agent may do on its own, what needs a person, and what it must never do.

These rules are enforced in code (the guards in tools/guards.py and the checks in each tool). This
module is the single written-down version, served at /admin/policy and used for the voice prompts."""

SENSITIVE_ACTIONS = {
    "mfa_reset": "Move sign-in approvals (Okta Verify) to a new phone",
    "account_unlock": "Unlock a locked-out account",
    "access_grant": "Grant access to an application or group",
}

TIERS = [
    {
        "tier": "read",
        "who_approves": "Nobody: the agent may call these on its own.",
        "tools": ["lookup_employee", "get_caller_history", "check_service_status", "find_similar_incidents",
                  "search_kb", "check_device_health", "check_security_advisories", "check_approval_status",
                  "check_verification_code"],
    },
    {
        "tier": "low-risk write",
        "who_approves": "The caller: the agent reads it back and the caller says yes (caller_confirmed=true).",
        "tools": ["send_verification_code (to the number on file only)", "create_incident",
                  "add_ticket_note (the caller's own tickets only)"],
    },
    {
        "tier": "sensitive write",
        "who_approves": "An active IT technician, who is not the requester, in the console. "
                        "The caller must also pass one-time-code verification first.",
        "tools": ["request_sensitive_action: " + ", ".join(SENSITIVE_ACTIONS),
                  "major incident declaration (proposed automatically during a ticket storm)"],
    },
]

NEVER = [
    "Ask for, listen to, repeat, or store a password. Anything resembling one is scrubbed from tickets.",
    "Send a verification code anywhere except the mobile number on file.",
    "Read a verification code out to the caller.",
    "Act for anyone other than the identified caller, even \"on behalf of\" a colleague.",
    "Make an account change without code verification and a technician's approval.",
    "Reveal another employee's details, or whether an ID or name exists.",
    "Help with a terminated account.",
    "Delete tickets, or change tickets that aren't the caller's own.",
    "Write free-form texts or emails: every outbound message is a fixed template.",
    "Keep helping after verification has failed three times on a call.",
]
