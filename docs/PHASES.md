# StormDesk build phases

Each phase is finished, tested, and explained before the next one starts.

| # | Phase (plain English) | What gets built | You need |
|---|---|---|---|
| 1 | **The toolbox** | Backend server, live data feeds, practice company, 7 look-up tools, tests | Nothing |
| 2 | **Safety rules and memory** | One-time-code identity check, ticket creation with a backup outbox, approval queue (LangGraph pauses for a human), storm → major-incident proposal, hard "never do" rules | Nothing |
| 3 | **The control room** | Streamlit console for the human technician: approvals, storm board, tickets, simulated phone inbox, demo switches | Nothing |
| 4 | **The voice** | ElevenLabs team of 5 voice agents wired to the tools through a public tunnel; first real calls | ElevenLabs API key, ngrok account |
| 5 | **The reviewer** | After each call, 3 AI reviewers + an orchestrator score it (resolved? process followed? follow-up needed?) on Nebius | Nebius Token Factory API key (LangSmith key optional) |
| 6 | **Stress test** | Failure drills, 12 test callers (including impostors), fixes; optional real ServiceNow | Optional: ServiceNow developer instance |
| 7 | **Submission pack** | README, architecture diagram, Google Doc draft, 5-minute demo script, GitHub | GitHub account |

---

## Phase 1: The toolbox ✅

**In one sentence:** before hiring the voice (phase 4), we built the desk it will sit at: the phone directory, the binder of how-to guides, the filing cabinet of past tickets, and windows onto the outside world.

**What was built**

- A small **server** (a program that waits for questions and answers them) with 7 **tools**. A tool is a button the AI can press to look something up. All 7 are look-up only, so none can change anything; that's why the AI may press them without asking anyone.
- **Live connections** to real public data: status pages for Slack, Zoom, Gmail and 14 other services, the US government's list of security holes attackers are using (CISA KEV), and the list of operating systems that no longer get security updates (endoflife.date).
- A **practice company**, Acme Corp: 20 fictional employees, their laptops, 15 how-to articles, and 10 past tickets. Practicing on fake data means we never touch anyone's real information.
- A **logbook** that records every button press: what was asked, what came back, how long it took. The phase 5 reviewer reads it.
- **45 automatic checks** (tests) that confirm everything behaves, including when things go wrong.

**Design decisions worth mentioning in the demo**

- *Every answer comes with a sticky note* (`agent_hint`) telling the AI what to say next. The rules live in code, not in the AI's judgement.
- *Impostors learn nothing.* A wrong name gets the exact same answer as a non-existent ID, so a caller can't fish for valid IDs or names.
- *Nothing breaks a call.* If a website doesn't answer, the server tries once more. If it's still down, it uses the last good copy and says how old it is; with no copy at all, it says "I can't confirm." It never crashes.
- *Real data caught real bugs:* GitHub's live update contained web code that came out garbled, and a Notion information notice was being read as an outage. Both were fixed and now have tests.

---

## Phase 2: Safety rules and memory ✅

**In one sentence:** the new help-desk employee now has the company rulebook, a way to check ID, a manager to sign off risky requests, and a notebook that remembers each call.

**What was built**

- **Memory for each call.** Once the caller is identified, the whole call is tied to that person. Every later action uses the person *the system* identified, never a name the AI passes in. The AI can't be talked into acting for "my colleague". Calls are remembered afterwards, so a third call this week gets noticed.
- **A one-time code**, like the one your bank texts you. It goes only to the mobile number on file; the tool has no box for a different number, so "send it to my other phone" is impossible. Three wrong guesses end the call's account help, file a security ticket, and text the real employee.
- **Three levels of permission:**
  1. *Look things up:* the AI does it alone.
  2. *Small changes* (log a ticket, add a note): the AI reads it back first. The system refuses until the caller says yes.
  3. *Risky changes* (reset sign-in approvals, unlock an account, grant access): the caller must pass the code check **and** an IT technician must approve. Nobody can approve their own request.
- **The approval process (LangGraph).** Think of a form that goes into a manager's in-tray. The process *pauses* and saves itself to disk. It can wait minutes, or survive the server restarting, then continues exactly where it stopped once the technician decides. While it waits, the AI keeps the caller company and checks back every 12 seconds. After 2 minutes it promises a text instead.
- **Risk notes for the technician**, written by plain rules rather than AI: "needed 2 tries for the code", "gave a wrong ID earlier", "VIP account", "another change in the last 24 hours". The technician sees them; the caller never hears them.
- **Ticket-storm detection.** When the third colleague in 30 minutes reports the same broken system, StormDesk asks the on-call technician to declare a major incident. Once declared, every affected person gets a text, and every new caller is linked to it automatically.
- **A safety net for outages of our own.** If the ticket system is down, the caller still gets a reference like PEND-0001. The request waits in an "outbox" and is filed automatically when the system returns, and the employee gets a text with the real number.
- **Never-do rules in code.** Passwords, codes and card numbers are scrubbed from every ticket. Terminated accounts get nothing. Texts are fixed templates, so the AI never writes free text to anyone.
- **Failure switches** for drills: ticket system down, text messages down, identity system down.
- **A rehearsal:** `uv run python -m stormdesk.rehearse` plays four complete calls in text: lost phone, impostor, VPN storm, ticket system down.
- **60 new automatic checks** (105 in total).

---

## Phase 3: The control room ✅

**In one sentence:** the human technician now has a screen: a live in-tray of requests to approve, a storm radar, the ticket list, each employee's simulated phone, a replay of every call, and the switches for rehearsing failures.

**What was built**

- **A console** (Streamlit, a tool that turns a Python script into a web page) with six tabs:
  - 🔔 **Approvals:** each request shows who, why, and the risk signals, with Approve and Reject buttons and an internal note. Major-incident proposals show their evidence. Your own request is greyed out.
  - 🌩️ **Storm board:** a bar fills as reports pile up ("3 of 3 reports in 30 minutes"). Declared major incidents get one button: *resolve and text everyone affected*. Below it, the live status of 17 services.
  - 🎫 **Tickets:** every ticket. Click one for its notes, linked reports, and a resolve button.
  - 📱 **Phones:** every employee's simulated texts and emails. During the demo, this is where you read the verification code aloud, like reading it off your phone.
  - 📞 **Calls:** every call, and a timeline of every button the AI pressed, what it sent, and the instruction it got back. This is the "show your work" screen.
  - 🧪 **Drills:** failure switches, the outbox, demo outages, set up a ticket storm, reset everything.
- **It updates by itself.** Approvals, the storm board and the phones refresh every 3–5 seconds, and a 🔔 pop-up appears when a new request arrives. When the voice agent asks for approval mid-call, the technician sees it within seconds.
- **The console only talks to the server through its front door** (the admin web addresses), never straight to the database, so it could run on a different computer.
- **A security fix found while planning Phase 4.** The voice agent will reach the server through a public tunnel. Before this phase, the agent's password would also have opened the technician's approve button. Now technician pages are **local-only** unless a separate admin password is set. A tricked or compromised AI can't approve its own requests.
- **Resolving a major incident** closes every linked report and texts each affected person: "the VPN problem is fixed".
- **21 new automatic checks** (127 in total), including tests that open the real console, type into boxes and click buttons. I also clicked through it in a real Chrome browser and took screenshots ([docs/screenshots](screenshots)).

---

## Phase 4: The voice ✅

**In one sentence:** StormDesk now answers the phone: one ElevenLabs agent made of six specialist desks that pass the call between them, using the tools from phases 1–3.

**What was built**

- **One agent, six desks** (a "workflow" of sub-agents):
  1. **Intake** asks who you are and what's wrong, and checks live status.
  2. **Outage desk:** "it's not you, Slack is down."
  3. **Fix-it desk:** step-by-step fixes.
  4. **Account desk:** text code, then technician approval.
  5. **Security desk:** phishing and suspicious activity.
  6. **Escalation desk:** when a person is needed.

  Think of one help desk with specialists sitting side by side. The receptionist listens, then turns the chair to the right colleague, and the caller never has to repeat themselves. ElevenLabs decides when to hand over, using plain-English conditions such as "the caller describes a suspicious email".
- **Instructions (prompts):** one shared rulebook for every desk, plus a short playbook per desk. The rulebook's "never do" list is copied word for word from `policy.py`, so the instructions and the enforced rules can never disagree.
- **Tools generated, not hand-copied:** the 13 tools ElevenLabs uses are built automatically from the backend's own definitions, so they can't drift apart. The conversation id is filled in by ElevenLabs itself (`system__conversation_id`), so the AI can't fake whose call it is.
- **A tunnel (ngrok)** gives your laptop a temporary public web address, so ElevenLabs can reach the tools. Technician pages stay closed through it, thanks to Phase 3's fix.
- **A secret handshake:** every tool call carries a random password stored in ElevenLabs' vault. The AI never sees it, and the backend refuses calls without it.
- **One command:** `voice up` opens the tunnel, checks the round trip works, deploys everything to ElevenLabs, and prints the link to talk to your agent.
- **A text-mode test caller:** it talks to the *real* agent over the same live connection a voice call uses, but in text. Five scripted callers (lost phone, impostor, VPN storm, Slack outage, phishing) play out whole conversations. Then the test checks what really happened in the backend: was the approval executed? Was the security ticket filed? Was the call locked?

**Results:** 5 of 5 scenarios pass. ElevenLabs' records confirm the hand-offs (Priya: Intake → Account desk; Aisha: Intake → Security desk). About 20 test conversations used 1,950 of 131,000 credits.

**What the tests taught us** (details in [ITERATIONS.md](ITERATIONS.md)): the agent asked for confirmation twice, told a caller "you're verified" before any code was checked, and read ticket numbers with leading zeros. Each was fixed in the prompt or the tool hints and re-tested.

---

## Phase 5: The reviewer ✅

**In one sentence:** after every call, a small team of AI reviewers on Nebius grades it, like a quality manager listening to call recordings, and the technician sees the scorecard in the console.

**What was built**

- **A case file for every call.** It combines ElevenLabs' record (every word, which desk said it, every button pressed) with StormDesk's own records (the audit trail, tickets, approvals, verification status).
- **8 rule checks: plain code, no AI.** Did the agent identify the caller before using their records? Verify before account changes? Read back before every change? Did it ever ask for a password, or say a code aloud? They read StormDesk's own records, so smooth wording can't fool them.
- **Five AI reviewers (LangGraph + Nebius Token Factory):**
  - **Resolution:** was the problem solved, or given a clear next step?
  - **Process:** were the rules followed? Did the *caller* show signs of manipulation?
  - **Experience:** was it a good phone call?
  - **Follow-up planner:** what still needs doing, and by whom?
  - **Judge:** writes the scorecard: pass, attention or fail, plus scores, flags and coaching tips.

  The first three work **at the same time**, like three colleagues each listening to the same recording for different things.
- **Safety rails:** if a rule check fails, the judge isn't allowed to say "pass". If one reviewer crashes, the others still finish. If Nebius is down entirely, a cautious scorecard is built from the rule checks alone.
- **Automatic:** the backend checks ElevenLabs for finished calls every 30 seconds and reviews them. Nothing to click.
- **Humans stay in charge:** reviewers only *suggest* follow-ups. The technician clicks **Create ticket** to make one real.
- **Console:** a new 🧑‍⚖️ Reviews tab with each call's scorecard.
- **LangSmith** records every review step by step, so you can show *how* a verdict was reached.
- **Model chosen by testing:** I compared three Nebius models on the same five real calls and picked the most accurate one (see ITERATIONS.md).

---

## Phase 6: Stress test ✅

**In one sentence:** we tried hard to break StormDesk with 15 tricky callers and four live failure drills, measured everything, fixed what broke, and measured again.

**What was built**

- **15 test callers**, up from 5. The new ones:
  - someone calling for a colleague
  - a terminated employee
  - a caller who gets their ID wrong twice
  - someone who blurts out their passwords
  - a slow laptop that already has a ticket
  - an angry caller demanding a person
  - **a live call during each failure drill:** ticket system down, texts down, identity system down, and a new one, *status pages unreachable*
- **Every test call is graded twice:** by plain checks on what really happened, and by the Phase 5 AI reviewers.
- **A report for every run** ([docs/evals](evals)): pass rates, safety numbers, call lengths, review scores, and the reviewers' coaching notes.

**What happened: four rounds of measure, change, measure**

1. **Baseline:** 15/15 scenarios, 0 unsafe account changes, every call under a minute. Safety was already solid. The reviewers' notes said it *sounded* repetitive at times.
2. **After coaching** (new speaking rules from the reviewers' notes): safety held, the one targeted fix worked, and the general style rules made **no measurable difference**. With one run per scenario, the AI's natural variation is about as big as the effect, so we don't claim an improvement we can't show.
3. **Final:** two real problems surfaced.
   - **A pushy impostor's pressure moved the call away from the verification desk mid-check,** so the lockout never happened.
   - **My new "warn about spoken passwords" rule made the agent repeat a password.** An improvement caused a regression.

   Both were fixed and re-tested three times each.
4. **Release:** the full suite with every fix (see [docs/evals/README.md](evals/README.md)).

**The lessons that matter most:**
- **Hand-offs between AI agents can break a security process.** Each desk that can inherit a check needs the tools to finish it.
- **Pressure is an impostor's tool,** so a caller "sounding upset" must never reroute a security check.
- **Every change, even a well-meant one, needs the whole test suite rerun.**

---

## Phase 7: Submission pack ✅

**In one sentence:** everything the course asks you to hand in, ready to submit.

- **Code-quality check** before anyone sees the code on GitHub, plus the full test suite (174 tests).
- **Architecture diagram** ([architecture.md](architecture.md), [architecture.png](architecture.png)): drawn from text, rendered in a real browser and checked by eye.
- **README** for reviewers: the one-liner, the results, the course's agent framework filled in, and a three-terminal quickstart.
- **Project write-up** ([SUBMISSION.md](SUBMISSION.md)): the Google Doc content. Overview, datasets, the prompts used, iterations and learnings.
- **Demo script** ([DEMO_SCRIPT.md](DEMO_SCRIPT.md)): a timed shot list with the exact lines to say, where to click, and what to do if something goes wrong while recording.
- **First commit**, made locally. Pushing to GitHub needs the repository address.
