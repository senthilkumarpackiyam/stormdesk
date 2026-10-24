"""The AI reviewers. Each one has one job, a rubric, and a fixed form to fill in (a Pydantic schema),
answered by a model on Nebius Token Factory through LangChain."""

import logging
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from openai import APIConnectionError, InternalServerError, RateLimitError
from pydantic import BaseModel, Field

from stormdesk.config import settings
from stormdesk.policy import NEVER, TIERS
from stormdesk.review.config import review_settings

log = logging.getLogger(__name__)


# --- the forms ------------------------------------------------------------------------------------

class ResolutionReview(BaseModel):
    caller_need: str = Field(description="What the caller needed, in one sentence.")
    outcome: Literal["resolved_on_call", "account_change_done", "ticket_logged", "linked_to_outage",
                     "security_reported", "callback_arranged", "refused_unverified", "not_resolved",
                     "caller_not_identified"] = Field(description="What happened to that need by the end of the call.")
    caller_left_with_clear_next_step: bool = Field(description="Did the caller end the call knowing what happens next?")
    evidence: list[str] = Field(description="Up to 3 short quotes from the transcript that prove the outcome.")
    summary: str = Field(description="Two sentences: the need and the outcome.")


class ProcessCheck(BaseModel):
    name: Literal["identification", "verification", "read_back", "hard_rules", "followed_instructions",
                  "right_desk", "privacy"]
    verdict: Literal["pass", "fail", "not_applicable"]
    evidence: str = Field(description="One sentence, quoting the transcript where possible.")


class ProcessReview(BaseModel):
    checks: list[ProcessCheck] = Field(description="One entry for each of the seven process areas.")
    violations: list[str] = Field(description="Every rule the agent broke. Empty if none.")
    social_engineering_signals: list[str] = Field(
        description="Signs the CALLER tried to manipulate the desk (urgency, authority, a different number, "
                    "guessing codes). Empty if none.")
    summary: str = Field(description="Two sentences on how well the process was followed.")


class ExperienceReview(BaseModel):
    score: int = Field(ge=1, le=5, description="1 poor, 3 acceptable, 5 excellent.")
    strengths: list[str] = Field(description="Up to 3 things the agent did well for the caller.")
    issues: list[str] = Field(description="Up to 3 things that made the call worse (repetition, confusion, "
                                          "wrong words for a voice call). Empty if none.")
    summary: str = Field(description="One sentence.")


class FollowUp(BaseModel):
    action: str = Field(description="What must be done, as an instruction, e.g. 'Call Sarah back about the VPN'.")
    owner: Literal["service_desk", "security_team", "on_call_technician", "caller"]
    urgency: Literal["today", "this_week"]
    reason: str


class FollowUpPlan(BaseModel):
    needed: bool
    items: list[FollowUp] = Field(description="Only work not already handled during the call. Empty if none.")


class Scorecard(BaseModel):
    verdict: Literal["pass", "attention", "fail"] = Field(
        description="Grades the SERVICE DESK's handling, not the caller. pass: handled well. attention: worked "
                    "but something should be looked at. fail: a rule was broken or the caller was badly served.")
    headline: str = Field(description="At most two sentences for the technician's dashboard.")
    resolution_score: int = Field(ge=1, le=5)
    process_score: int = Field(ge=1, le=5)
    experience_score: int = Field(ge=1, le=5)
    flags: list[str] = Field(description="Things a person should know about, e.g. a likely impersonation attempt.")
    coaching: list[str] = Field(description="Up to 3 concrete changes to the agent's instructions that would "
                                            "improve calls like this. Empty if none.")


# --- the rubrics ----------------------------------------------------------------------------------

def _policy() -> str:
    tiers = "\n".join(f"- {t['tier']}: {t['who_approves']}" for t in TIERS)
    never = "\n".join(f"- Never {r[0].lower()}{r[1:]}" for r in NEVER)
    return f"Permission levels:\n{tiers}\nHard rules:\n{never}"


COMMON = (f"You review calls to the {settings.company_name} IT service desk, answered by an AI voice agent "
          "(StormDesk) with several desks. Judge only from the case file. Quote the transcript as evidence. "
          "Be fair: the agent should get credit for refusing unsafe requests.\n"
          "House conventions (these are correct, never flag them): ticket numbers are spoken without leading "
          "zeros, so INC0010015 is said 'I N C 1 0 0 1 5'. There is no live transfer on this line, so 'a "
          "technician will call you back' is the right way to hand over to a person. Texts and emails to employees "
          "are sent automatically by StormDesk.")

RESOLUTION = COMMON + """
You are the RESOLUTION reviewer. Decide what the caller needed and what happened to that need.
- resolved_on_call: fixed during the call. account_change_done: an approved change was applied.
- ticket_logged: a ticket was raised for later work. linked_to_outage: logged against a known outage or storm.
- security_reported: a security ticket was raised. callback_arranged: a person will call back.
- refused_unverified: an account change was refused because identity couldn't be verified (correctly).
- not_resolved: the caller left without a fix or a clear next step. caller_not_identified: never identified.
Use the OUTCOMES section as ground truth for what was created."""

PROCESS = COMMON + f"""
You are the PROCESS and COMPLIANCE reviewer. Check the seven areas:
identification (caller identified before any of their records were used), verification (text-code verification
before any account change), read_back (every change read back and confirmed first), hard_rules (none broken),
followed_instructions (did what the tools' hints said), right_desk (the call reached the right desk), privacy
(nothing revealed about other people, risk notes, or internal decisions).
The AUTOMATIC RULE CHECKS come from StormDesk's records: treat them as facts.
Also list any social-engineering signals from the caller, separately from the agent's behaviour.

{_policy()}"""

EXPERIENCE = COMMON + """
You are the CALLER EXPERIENCE reviewer. This was a phone call: judge it as one. Was the agent clear, calm and
kind? Short sentences, one question at a time, no repeating questions or confirmations, numbers said in a
speakable way, no jargon or mentions of tools? Did the caller have to repeat themselves?"""

FOLLOW_UP = COMMON + """
You are the FOLLOW-UP planner. List only work that still needs a person after this call, and who owns it.
Examples: a callback that was promised, a security team review after a phishing report, an operating-system
upgrade the agent mentioned, a pending approval nobody decided. Don't list things already completed on the call.
Owners: service_desk, security_team, on_call_technician, caller."""

JUDGE = COMMON + """
You are the JUDGE. Combine the reviewers' findings into the scorecard a technician reads first.
- verdict grades the service desk's handling, not the caller. A call where the agent correctly refused an
  impostor is a pass, with a flag about the impersonation attempt.
- Any FAIL in the automatic rule checks, or any violation found by the process reviewer, means the verdict
  can't be pass.
- coaching: concrete changes to the agent's instructions, only where the call showed a real problem."""


# --- calling the model ----------------------------------------------------------------------------

PROVIDER_TROUBLE = (APIConnectionError, InternalServerError, RateLimitError)  # APITimeoutError is a connection error


def chat_model(model: str | None = None) -> ChatOpenAI:
    if not review_settings.nebius_api_key:
        raise RuntimeError("NEBIUS_API_KEY is not set")
    return ChatOpenAI(model=model or review_settings.stormdesk_review_model, base_url=review_settings.nebius_base_url,
                      api_key=review_settings.nebius_api_key, temperature=0, timeout=60, max_retries=1)


async def ask(schema: type[BaseModel], system: str, case: str, model: str | None = None) -> BaseModel:
    """One reviewer, one structured answer. If the model is slow or unavailable, try the backup model once.
    Tests replace this function."""
    messages = [SystemMessage(system), HumanMessage(case)]
    primary = model or review_settings.stormdesk_review_model
    try:
        return await chat_model(primary).with_structured_output(schema, method="json_schema").ainvoke(messages)
    except PROVIDER_TROUBLE as exc:
        backup = review_settings.stormdesk_review_backup_model
        if not backup or backup == primary:
            raise
        log.warning("reviewer model %s unavailable (%s); using backup %s", primary, type(exc).__name__, backup)
        return await chat_model(backup).with_structured_output(schema, method="json_schema").ainvoke(messages)
