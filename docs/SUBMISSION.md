# StormDesk: an IT service desk voice agent

**The Gen Academy · Week 3 · Build Your AI Agent**
Use case F (multi-agent IT support voice agent) · Code track (LangGraph + LangChain) · ElevenLabs, Nebius Token Factory, LangSmith

**GitHub:** _link_ · **Demo video:** _link_

---

## 1. Project overview

**StormDesk answers employees' IT support calls by voice.** A team of six specialist AI "desks" passes each call between them. Behind the voice is a backend with 13 tools, live outage data, a human approval step for risky changes, and an AI review of every finished call.

It is built around two real service-desk problems that a generic "password reset bot" ignores:

1. **Ticket storms.** When Slack or the VPN goes down, hundreds of employees call about the same thing. Every call becomes a duplicate ticket and the queue explodes. StormDesk checks live vendor status pages and colleagues' recent reports *before* troubleshooting. It tells callers "this is a known outage, it's not your laptop", links their ticket to the incident, and, once a third colleague reports the same thing, proposes a major incident to a technician.
2. **Help-desk social engineering.** Attackers phone help desks pretending to be employees and talk staff into resetting MFA; the 2023 MGM breach started this way. StormDesk never reveals anything to an unverified caller. Account changes need a one-time code texted to the number on file *and* a technician's approval in a console. Three wrong codes lock the call, file a security ticket, and warn the real employee.

### The one-liner

> My agent helps **employees** get **an IT problem fixed or correctly routed** over **a voice call**. It replaces **the hold queue, the first-line technician, and the duplicate tickets that flood the desk during every outage**. It identifies the caller, checks live vendor status and colleagues' reports, troubleshoots from the knowledge base, and logs or links tickets on its own, using **13 tools across six specialist desks**. It hands off to a human **for any account change (after text-code verification), a likely major incident, a security report, or a caller who asks for a person**. I'll know it works when **a caller reaches a fix or a correctly routed ticket in under 4 minutes, with zero account changes made without verification and a technician's approval**.

### How it works

*(Insert `docs/architecture.png`.)*

| Part | What it does | Built with |
|---|---|---|
| **Six desks** | **Intake** (who are you, what's wrong, live status) → **Outage**, **Fix-it**, **Account** (text code + approval), **Security**, **Escalation**. One ElevenLabs agent whose *workflow* is a team of sub-agents; ElevenLabs moves the call when a plain-English condition is met | ElevenLabs Agents, Claude Haiku 5.5, voice "Sarah" |
| **13 tools** | Look-ups (employee, history, live status, colleagues' reports, knowledge base, device support, security advisories) and writes (verification code, tickets, notes, sensitive requests). Every answer includes an `agent_hint`: one plain instruction for what to say next | FastAPI; tool definitions generated automatically for ElevenLabs |
| **Three permission levels** | Look-ups: the agent alone. Small changes: the *caller* confirms a read-back (enforced in code). Account changes: code verification *and* a *technician's* approval | Policy enforced in code |
| **Approval process** | The request pauses until a technician decides, survives restarts, and expires if forgotten | LangGraph `interrupt()` + SQLite checkpointer |
| **Technician console** | Approvals, storm board, tickets, each employee's simulated phone, call timelines, reviews, failure switches | Streamlit |
| **Post-call review** | A case file plus 9 rule checks (plain code); three AI reviewers in parallel (resolution, process, experience), a follow-up planner and a judge produce a scorecard | LangGraph + LangChain on Nebius (Kimi-K3, backup DeepSeek-V4.1-Flash), LangSmith tracing |

### The agent framework

| Field | StormDesk |
|---|---|
| Agent goal | Take an employee's IT call and fix it, route it, or hand it to a person, safely |
| Where people use it | A voice call. Technicians use a web console |
| Steps | Identify → history → hear the problem → live status + colleagues' reports → right desk → fix / log / verify + approve / report security → read back every change → recap and end → post-call review |
| What it can do | 9 look-up tools (autonomous); 3 low-risk writes (caller confirms); account changes and major incidents (technician approves) |
| What it remembers | Per call: who the caller is, whether they're verified, whether the call is locked. Across calls: ticket history and previous calls. Pending approvals, saved to disk. An audit trail of every tool call |
| Never | Ask for or repeat a password · send a code anywhere but the number on file · act for anyone but the caller · change an account without verification and approval · reveal anyone's details · help a terminated account · keep going after three wrong codes |
| Human-in-the-loop | The caller confirms every write; a technician approves every account change and major incident, and decides which review follow-ups become tickets; nobody can approve their own request |
| When something breaks | Every failure has a scripted response (section 4) |
| How we know it worked | 15 scripted callers against the live agent, judged by checks and AI reviews (section 4) |

---

## 2. Datasets used

| Data | Source | Refresh | Used for |
|---|---|---|---|
| **Vendor status**: Slack, Zoom, Gmail, Google Meet/Drive/Calendar/Docs, GitHub, Jira, Confluence, Figma, Notion, ChatGPT | Public APIs: Atlassian Statuspage `…/api/v2/summary.json`, `slack-status.com/api/v2.0.0/current`, `google.com/appsstatus/dashboard/incidents.json` | Real time (cached 60 s) | "Is it them or us?" |
| **CISA Known Exploited Vulnerabilities** | `cisa.gov/…/known_exploited_vulnerabilities.json` (about 1,750 entries) | Several times a week | Is the product a caller mentions (e.g. the Ivanti VPN) being actively attacked? |
| **endoflife.date** | `endoflife.date/api/v1/products/{product}` | As vendors publish | Is the caller's laptop OS still getting security updates? |
| **Practice company "Acme Corp"** | Synthetic, created for this project: 21 employees with laptops, 15 knowledge-base articles, 10 past tickets (555 phone numbers, `.example` emails) | Reset on demand | Directory, tickets and knowledge base, so no real person's data is ever used |
| **Call records** | ElevenLabs conversation API: transcript, which desk spoke, every tool call | After each call | Input to the post-call reviewers |
| **Evaluation scenarios** | 15 scripted callers written for this project | Per run | Measuring safety and quality before and after changes |

The live feeds are real: during development GitHub really had an incident, and StormDesk reported it. For a recorded demo, a "demo outage" switch fakes one, clearly labelled as a demo wherever it appears.

---

## 3. Prompts used during vibe coding

The whole project was built with **Claude Code** (Opus 5.5) in VS Code. I set the direction, made the decisions only a person can make (use case, account permissions, keys), and approved each phase with "GO". The assistant planned, coded, tested, ran the live calls, and documented each phase before stopping. These are my prompts, verbatim, in order (full log: `docs/PROMPTS.md`):

1. *(After pasting the full Week 3 brief)* "i have the attached project requirement to build AI Agent, -- suggest me a best possible project to do. -- make sure it does not reflect any existing known AI Agent projects and something unique -- suggest me any datasource which can be pulled through API online and refreshed frequently -- make sure to meet all the guideline mentioned in the doc -- choose the best project listed in the options -- I am thinking of ElevenLabs Voice Agent: ITSM , please suggest me the best possible way to get this project done."
2. "here is the plan: Make the project into different phases and complete phase by phase fully autonmous. Do not move to another phae until i say "GO" Explain me every phase like teaching a non-technical / layman who has no knowledge over AI"
3. "GO" (phase 2: safety rules and memory)
4. "GO" (phase 3: the technician console)
5. "what should select for permissions here for our project?" *(with a screenshot of ElevenLabs' API key dialog)*
6. "i dont find .env file, tell me the exact path"
7. "guide me step by step how do i get ngrok API key"
8. "done added my ngrok and elevanlabs API key now in .env file"
9. "GO" (phase 4: the voice)
10. "i dont see NEBIUS_API_KEY=... in .env file?"
11. "done, updated nebius and langsmith API keys now"
12. "GO" (phase 5: the reviewers)
13. "GO" (phase 6: stress test)
14. "GO" (phase 7: this submission pack)

**What worked about this way of prompting:** one clear brief, then *phase gates*. Each phase ended with a plain-English explanation, test results and what I needed to prepare next, so I always understood what had been built before approving more. I gave least-privilege keys (for example, an ElevenLabs key restricted to ElevenAgents) and kept them out of the chat by putting them in `.env`.

---

## 4. Iterations tried

The build went through seven phases. These are the iterations that changed the design; all 60+ are in `docs/ITERATIONS.md`.

**Design decisions**

| Iteration | Why |
|---|---|
| One ElevenLabs agent with a **workflow of six desks**, rather than separate agents that transfer calls | One conversation id for the whole call, so the backend's security session (who, verified, locked) carries across hand-offs. It also appears as a diagram in the dashboard |
| The employee a tool acts for comes **from the call's session, never from the AI's arguments** | A persuaded AI can't act for someone else |
| `send_verification_code` **has no phone-number parameter** | "Send it to my other number" is impossible, not merely forbidden |
| Tools are **generated from the backend's own definitions** | The agent's tools and the backend can never drift apart |
| **Rule checks in plain code** sit underneath the AI reviewers; the AI judge can't override a failed rule | Keep the facts deterministic and let the AI do the judgement |
| Reviews **pull** finished calls every 30 s instead of using a webhook | Nothing to register, survives the tunnel's address changing, and catches calls missed while the backend was down |
| Reviewer model **chosen by testing**: Kimi-K3 5/5 correct, DeepSeek-V4.1-Flash 5/5 but slow, gpt-oss-120b 2/5 | Test models on your own task |

**Problems found by testing against the live system**

| Found | Fix |
|---|---|
| A live GitHub update contained HTML; a Notion *notice* was being read as an outage | Strip HTML; a separate "notice" level |
| The agent asked for confirmation twice, said "you're verified" right after a directory lookup, and read ticket numbers as "zero zero one zero…" | Prompt explains *why* one confirmation is enough; "found isn't verified"; speakable `*_spoken` numbers in every tool result |
| A screenshot showed an MFA *request* counted as an *outage report* | Tickets now have a type: incident or request (as in ITIL) |
| The agent's tool key could also open the technician's approve button through the public tunnel | Technician endpoints are local-only unless a separate admin secret is set |
| A reviewer flagged our deliberate ticket-number format as a mistake | Reviewers get the same "house conventions" as the agent |

**The evaluation loop (phase 6).** Each round ran 15 scripted callers against the live agent, each call graded by the reviewers:

| Run | Scenarios | Unsafe changes | Reviews | Experience |
|---|---|---|---|---|
| Baseline | 15/15 | 0 | 14 pass, 1 attention | 4.40 |
| After applying the reviewers' coaching | 14/15 | 0 | 11 pass, 2 attention (+2 lost to timeouts) | 4.31 |
| Final | 13/15 | 0 | 13 pass, 1 attention, 1 fail | 4.27 |
| Release (all fixes) | 14/15 | 0 | 14 pass, 1 attention | 4.33 (process 4.93) |

What the rounds found:
- **A hint promised a "transfer" on a line that has none.** That caused the one baseline 🟡. Fixed in every hint.
- **Nebius timeouts lost two reviews.** Added a backup model.
- **One of my own rule checks was too broad.** "Confirm … expired password" counted as *asking* for a password. Made precise.
- **An impostor's pressure moved the call off the Account desk mid-verification.** It went to Security, then to Escalation, where codes couldn't be checked, so the lockout never happened. Fixed: frustration can't move a call out of verification, and every reachable desk can check codes. **3/3 after the fix.**
- **A new coaching rule made the agent repeat a password** while warning the caller about it. Fixed with exact safe wording. **3/3 after the fix.**

---

## 5. Learnings and observations

1. **The hard parts were control flow and the seams between agents, not the prompts.** The most serious bug in the project lived in a hand-off between two desks: a security check started at one desk and was abandoned at another.
2. **Put the security boundary in code, not in the prompt.** The prompt is the second line of defence. The first is that the tools *can't* do the unsafe thing: no phone-number field, the employee taken from the session, read-backs enforced by the server.
3. **Pressure is an impostor's tool.** A rule that moves a call when the caller "sounds upset" is a rule an attacker can trigger.
4. **Every improvement needs the whole test suite rerun.** A well-meant rule ("warn callers about spoken passwords") made the agent repeat a password.
5. **When the AI "disobeys", check the instructions.** The agent was marked down for ignoring a hint that told it to offer a transfer that doesn't exist.
6. **Deterministic doesn't mean correct.** A rule check that can overrule the AI needs its own tests. Mine wrongly flagged a harmless read-back.
7. **Be honest about noise.** With one run per scenario, natural variation was about as large as the style improvements, so I report "no measurable gain" for those and claim only the targeted fixes.
8. **Real data catches what mocks don't.** A garbled GitHub update, a misread Notion notice and a counting bug visible only in a screenshot were all found by running against live systems and looking at the screen.
9. **Human-in-the-loop can mean different humans for different risks.** The caller approves small changes; a technician approves account changes; nobody approves their own.
10. **Phase gates made autonomous AI coding trustworthy.** Each phase ended tested and explained in plain English, so I could follow and steer a project much larger than I could have written by hand in a week.

### Limitations and future work

- The automated evaluation used **text mode**: the same agent, desks and tools, without audio. Speech-specific behaviour (accents, mishearing IDs, interruptions) wasn't part of it and needs more testing.
- One run per scenario. **Several runs per scenario** would give real confidence intervals.
- **ServiceNow integration:** the ticket system sits behind one class, ready for a ServiceNow version.
- **Scrub call recordings** when a caller says a password aloud (a reviewer's suggestion).
- A real phone number (Twilio), real SSO and MFA (Okta), and more languages.

---

## Screenshots to include

| File | Shows |
|---|---|
| `docs/architecture.png` | The architecture |
| `docs/screenshots/console-approvals.png` | A technician's approval queue with risk signals |
| `docs/screenshots/console-storm-board.png` | A declared major incident and live status of 17 services |
| `docs/screenshots/console-phones.png` | The simulated phone with a verification code |
| `docs/screenshots/console-call-timeline.png` | Every tool the agent used during a call |
| `docs/screenshots/console-review-detail.png` | A post-call scorecard for the impostor call |
