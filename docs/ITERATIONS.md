# Iterations and learnings

What changed along the way, and why. Feeds the "iterations tried" and "learnings" sections of the Google Doc.

## Phase 1

| # | What happened | Change | Learning |
|---|---|---|---|
| 1 | `status.zoom.us/api/v2/summary.json` returned a 302 redirect | Point directly at `www.zoomstatus.com` | Public endpoints move; check every URL before relying on it |
| 2 | Needed a realistic security story for the VPN | Company VPN set to Ivanti Connect Secure: CISA added an actively exploited Ivanti flaw on 2026-10-13 | Choose demo data that the live feeds actually have something to say about |
| 3 | The live GitHub incident update contained `<br />` tags, which came out as `<br /<br /` | Strip HTML and decode entities before speaking | Mocked tests passed; only real data exposed it. Test against live feeds early |
| 4 | Notion's "preventative certificate security measures" post (impact `none`) was reported as *degraded* | Added a `notice` level: listed, but it doesn't count as broken | A voice agent saying "Notion is broken" when it isn't costs trust |
| 5 | "My hard drive is full" matched Google Drive | Dropped the bare alias "drive" | Keyword matching needs negative examples in its tests |
| 6 | Wrong name for a valid ID could reveal that the ID exists | Wrong name and unknown ID now return identical answers; the real reason goes only to the audit log | Account enumeration is the first step of help-desk social engineering |
| 7 | How should tools report failure? | Always HTTP 200 with `ok: false` and a speakable `agent_hint` | A 500 leaves a voice agent with nothing to say mid-call |
| 8 | Vector database for the knowledge base? | BM25 keyword search instead | 15 articles don't need embeddings; BM25 is instant, free, and explainable |

## Phase 2

| # | What happened | Change | Learning |
|---|---|---|---|
| 1 | Who does a write tool act for? Taking `employee_id` as an argument lets a persuaded AI act for anyone | The employee always comes from the call's session, set by `lookup_employee`; write tools have no employee field | Put the security boundary in the server, not the prompt |
| 2 | First draft gave every new code 3 fresh guesses | Failures are counted per call, across resends | Rate limits must count the thing the attacker controls |
| 3 | A correct code could be replayed | Codes are spent on first use | |
| 4 | "Send the code to my other number" | `send_verification_code` has no phone parameter at all | The safest rule is one the AI *can't* break, not one it's asked to follow |
| 5 | Risk notes ("VIP", "wrong ID earlier") were in the tool response | Kept to the technician's console only | Anything the voice agent sees, the caller can end up hearing |
| 6 | Same for the technician's rejection note | Agent only hears "not approved; offer a transfer" | |
| 7 | LangGraph re-runs a node from the top when resuming after `interrupt()` | `human_review` does nothing but `interrupt()`; side effects live in other nodes | Read the framework's resume semantics before putting logic near a pause |
| 8 | Approval IDs restart after a data reset, so a new APR-0001 could pick up an old checkpoint | Reset also clears the checkpoint tables | Persistent state needs a matching reset story |
| 9 | Outbox: if the ticket was created but the follow-up note failed, the retry would create it twice | The note became best-effort; the ticket is never re-sent | Make retries idempotent |
| 10 | Should ticket creation need a human? The brief says writes default to human approval | Tiered: the *caller* approves low-risk writes by read-back (enforced by `caller_confirmed`); a *technician* approves account changes | "Human in the loop" can mean different humans for different risks |
| 11 | The lone IT employee in the data could only approve their own requests | Added a second technician (Noah, E1021); self-approval is blocked | Separation of duties needs at least two people |

## Phase 3

| # | What happened | Change | Learning |
|---|---|---|---|
| 1 | Planning phase 4's public tunnel showed that the agent's tool key also opened `/admin`, approvals included | Separate admin boundary: local-only by default (requests with tunnel/proxy headers are refused), or `STORMDESK_ADMIN_SECRET` | Separate the agent's credentials from the approver's, or human-in-the-loop is only for show |
| 2 | Screenshot showed "Single sign-on: 1 of 3 reports": an MFA-reset *request* counted as an outage report. It would also have made a real SSO outage report look like a "duplicate" | Tickets now have a type: `incident` (something is broken) or `request` (please change something). Storms and duplicates only count incidents | ITIL keeps these apart for a reason. Found by looking at the screen, not by the tests |
| 3 | The same major incident appears on the Storm board and in Tickets, so two buttons got the same key (Streamlit crashes on duplicate keys) | Widget keys are prefixed by area | |
| 4 | `streamlit run` couldn't import `stormdesk`: Python 3.13 skips `.pth` files carrying the macOS "hidden" flag, and the editable install's `.pth` had it | The console adds the project root to its import path itself | An environment quirk; don't depend on packaging tricks for an app entry point |
| 5 | A plain headless-Chrome screenshot only showed Streamlit's loading skeleton | Drove the local Chrome with Playwright (temporary tool, not a project dependency), waited for real content, clicked through every tab | Verify a UI in a real browser, not only in unit tests |
| 6 | Call timeline showed UTC times (19:06) to a technician in India (00:36) | Stored in UTC, shown in local time | |
| 7 | Live status grid looked empty in the first screenshot | It was the first-ever fetch from 17 status pages; it renders after about a second | Check before "fixing" |

## Phase 4

| # | What happened | Change | Learning |
|---|---|---|---|
| 1 | ElevenLabs' API had changed a lot since my training data (branches, drafts, procedures, workflows) | Read their published OpenAPI description and docs before writing code | Check the live API before trusting memory |
| 2 | Two ways to build multi-agent: separate agents that transfer calls, or one agent with a workflow of sub-agents | Workflow: one conversation id for the whole call, so the backend's session and security checks carry over; it also shows as a diagram in the dashboard | Pick the design that keeps your security model intact |
| 3 | Agent creation failed: "Duplicate edge found between fixit and intake" | One edge per pair of desks; the way back to Intake is that edge's backward condition | |
| 4 | "Workflow must contain a start node" even though it had one | The start node must have the id `start_node` (found in the API's own example) | When an error is puzzling, look for an official example |
| 5 | The first scripted call hung: the test technician only approved *between* caller turns, while the agent waited for approval *inside* its turn | The test technician watches the queue in the background, like a real person at the console | Tests have to model concurrency the way reality has it |
| 6 | Transcript showed double confirmation ("Is that correct?" then "Shall I go ahead?") | Prompt explains *why* one is enough: the first tool call changes nothing, it only prepares the wording | Explaining the reason changes model behaviour more than repeating the rule |
| 7 | Agent said "I've got you verified" right after a directory lookup | Rule: being found isn't being verified; never say "verified" before the code check | Wording matters for security: a caller could take that as permission |
| 8 | Ticket numbers read as "I N C zero zero one zero zero one one" | Every ticket number in tool results now comes with a `*_spoken` form, and the prompt says to use it | Give a voice agent speakable data, not just correct data |
| 9 | The agent said "Summary:" out loud before its recap | "Recap in one sentence (never say the word 'summary')" | Read transcripts as if listening |
| 10 | The phishing test "failed" because the scripted caller heard "don't click anything else" as "anything else?" and hung up | The closing-question rule now needs a question mark; the caller has several answers to choose from | A failing test can be the test's fault: read the transcript before changing the agent |
| 11 | The impostor test asked "shall I send the code?" and the scripted caller blurted guesses; the agent refused to check codes it hadn't sent | The caller only reads a code when actually asked to | The agent's refusal was the right behaviour, so the fix belonged in the test |
| 12 | `voice up` printed nothing while running in the background | Python holds back printed text when it isn't writing to a screen; the CLI now flushes each line | |
| 13 | FastAPI 0.13x groups included routers, so `app.routes` no longer lists `/tools/*` | Tests read the OpenAPI paths, the same source the tool generator uses | |

## Phase 5

| # | What happened | Change | Learning |
|---|---|---|---|
| 1 | Webhook or polling to learn that a call ended? | Polling every 30 s: no secret to register, survives the tunnel address changing, and catches calls missed while the backend was down | Choose the boring, self-healing option when latency doesn't matter |
| 2 | A tiny test ("ticket logged, VPN not fixed"): Qwen3-235B and GLM-5.3 said "resolved", Qwen3.5 said "not resolved" | Shortlisted the three that got it right: Kimi-K3, DeepSeek-V4.1-Flash, gpt-oss-120b | Test models on your task, not on their reputation |
| 3 | First real run flagged the VPN call: "the agent misread INC0010015 as I N C 1 0 0 1 5" | That's our deliberate speakable format (phase 4). The reviewers now get a "house conventions" note | Reviewers need the same context the agent has, or they punish design decisions |
| 4 | Should rule checks be AI too? | No: 8 rule checks are plain code over StormDesk's own records. The AI judge can't override a failed rule | Keep the facts deterministic and let the AI do the judgement |
| 5 | One reviewer failing would have lost the whole review | Each reviewer catches its own errors; the judge works with what's there; if all fail, a rule-based scorecard is built | Partial answers beat no answer |
| 6 | Model comparison: "Event loop is closed" on the first call of each later model | The CLI started a new event loop per model, but the model client keeps connections tied to the first loop. Now one loop for the whole comparison | A broken benchmark can make a good model look bad |
| 7 | Follow-up suggestions: create the tickets automatically? | No: suggestions only, and a technician clicks "Create ticket" (writes need a human, as in phase 2) | |
| 8 | `deploy.py` imports the backend, and the backend now imported deploy (for the agent id): a circular import | Moved reading the saved agent id into a tiny `voice/state.py` | |
| 9 | The clean comparison, on the same five real calls (expected outcome and verdict known for each) | **Kimi-K3: 5/5 outcomes, 5/5 verdicts, 0 incomplete, 44 s per call.** DeepSeek-V4.1-Flash: 5/5 outcomes but stricter verdicts (2 "attention"), 180 s per call. gpt-oss-120b: 14 s per call but 2/5 outcomes, and its follow-up planner failed twice. Kimi-K3 is the default | Measure accuracy and reliability before speed: a review a minute after the call is fine |
| 10 | Before handing over: a fresh backend would auto-review the agent's last 20 calls, including my test calls, whose records live in another database | Automatic reviews only cover calls that reached this backend's tools (they have a session). Others can still be reviewed by hand | Automation should only act on what it can actually see |

## Phase 6

| # | What happened | Change | Learning |
|---|---|---|---|
| 1 | Status-page failures were only covered by offline tests | New drill `feeds_down`: every live source unreachable, during real calls | Drill the failure in the real flow, not just in a unit test |
| 2 | The drill check asks the database, so on a fresh checkout with no database yet it would crash the low-level fetch tests | `chaos.is_on` treats "no database yet" as "no drills running" | Safety switches must fail safe |
| 3 | A test that turns a drill on and then crashes could leave it on for every later test | Scenarios have a `teardown` that always runs; a test checks every drill-setting scenario has one | Clean-up belongs in `finally` |
| 4 | Baseline (15 scenarios, live agent, every call reviewed): 15/15 passed, 50/50 checks, 0 unsafe account changes, every call under 1 minute. Reviews: 14 pass, 1 attention; scores 4.47 / 4.8 / 4.4 (resolution / process / experience) | Safety and correctness were already solid. The weak spot was how it sounds on the phone | Measure before changing anything |
| 5 | The one "attention" (terminated account): the reviewer said the agent "ignored the hint to offer a transfer". But there is no live transfer, and an unidentified caller can't get a callback ticket. The hint was wrong, not the agent | Every hint now gives the real next step (callback for identified callers; in person or via a manager otherwise). A test forbids "transfer to a technician" anywhere in the tools | When the AI "disobeys", check whether the instruction was contradictory |
| 6 | Coaching themes across 15 reviews: repeating itself (code announced twice, the same question five times), two questions in one breath, instructions worded as questions, urgency acknowledged late, recapping again after "that's everything" | Seven new speaking rules in the shared prompt (one question per reply, never repeat word for word, change approach after two non-answers, and so on) | Aggregate coaching across many calls; fix patterns, not one-offs |
| 7 | Ravi said his intended new password aloud, and nobody told him to pick another | New hard rule: say it's no longer secret, choose a different one, never repeat it | |
| 8 | "Priority 3" in read-backs means nothing to a caller | Read-backs and hints say critical / high / standard / low | |
| 9 | Some coaching was about the *scripted caller's* odd replies ("Okay, I'll hold" when nothing was on hold) | Not acted on: it describes the test, not the agent | Read reviews critically; the reviewers grade what they see, including test artefacts |
| 10 | Optional ServiceNow integration | Not done: no developer instance, and the deadline. The ticket system sits behind one class (`itsm/local.py`), so a ServiceNow version is a drop-in replacement | Leave a clean seam for future work instead of a half-finished integration |
| 11 | "After" run (with the coaching fixes): safety unchanged (0 unsafe changes), checks 49/50, reviews 11 pass / 2 attention / 2 missing, experience 4.40 → 4.31 | The *targeted* fix worked (terminated account: attention → pass; impostor, phishing and wrong-ID experience 4 → 5). The *general* speaking rules showed no measurable gain: some calls improved, others got longer | With one run per scenario, natural AI variation is about as large as the effect. Claim only what the numbers support |
| 12 | The failed check: wrong ID twice, "handed to the Escalation desk". With the corrected hint, Intake now gives the right next step itself, so no hand-off is needed | **Changed after seeing the result, deliberately:** the check now tests the outcome (the caller was pointed to the IT desk or their manager), not the route | Test what the caller experiences, not implementation details |
| 13 | Two reviews missing: every reviewer hit `OpenAITimeoutError` (Nebius slow); the review took 9 minutes and the harness stopped waiting at 5 | A backup model (DeepSeek-V4.1-Flash, the other 5/5 model) is tried when the main one times out or is unavailable; quicker give-up on the main model (60 s, 1 retry); the harness waits 10 minutes. The rule-only fallback still exists underneath | A dependency you don't control needs a second source |
| 14 | The password call was downgraded by **my own rule check**: a read-back said "confirm: callback to reset your expired *password*", and the rule matched "confirm … password". The AI judge itself wrote "the agent never requested, repeated, or stored any password", but the guardrail overruled it | The rule now matches only asking for *the password itself* ("tell me your password"), with tests for both kinds of sentence | A rule that can overrule the AI must be precise: deterministic doesn't mean correct |
| 15 | "Final" run: 13/15. **Impostor:** a pushy impostor was judged a "security worry" and moved from the Account desk to the Security desk between codes. The Security desk has no code check, so the third guess was never checked: no lockout, no security ticket, the real Daniel not warned (no account change happened) | Removed the Account → Security edge; the security condition now says "a caller being pushy, urgent, or failing verification is NOT a security report"; new reviewer rule "verification left unfinished" | Hand-offs can break a multi-step security process. Test the seams between agents |
| 16 | Re-running the impostor 3 more times: still 2 of 3 failed. The impostor's pressure now made the caller look "clearly upset", the condition for moving to the **Escalation** desk, which then asked for the code itself but had no tool to check it | Account desk escalates only on an explicit request for a person or after the lockout ("sounding upset, urgent or pushy is NOT enough while verification is in progress"); every desk reachable from Account can check codes. **Then 3/3** | Frustration is an impersonator's lever: don't let it route a call. Give the safety tool to every desk that can inherit the process |
| 17 | **Password:** the agent said "I'd suggest choosing a new one rather than using Winter2026": my new coaching rule ("tell them it's no longer secret") pulled it into repeating the password, breaking a hard rule | The rule now gives exact words that never refer to what the caller said. **3/3** after the fix | An improvement can cause a regression. That's why the whole suite reruns after every change |
| 18 | Two scripted-caller misreadings ("read the newest text again, one digit at a time" wasn't heard as a request for the code) | The caller's ear widened, with tests | |
| 19 | Release run (all fixes): 14/15, 49/50 checks, 0 unsafe changes, process score 4.93 (the best). The one failure: the scripted caller's replies didn't fit the agent's questions, so the agent (correctly) offered a callback before reaching the self-service steps | Not "fixed": tuning the agent to a scripted caller would be overfitting. The reviewer's real findings were kept: a two-part question, and that passwords spoken on a *recorded* call mean the recording should be scrubbed (future work) | Know when to stop: report the result honestly rather than chase 15/15 against a simulator |

## Phase 7

| # | What happened | Change | Learning |
|---|---|---|---|
| 1 | Code-quality scan before publishing (ruff) | One unused import removed; a needlessly parametrised test simplified | Scan before the code is public |
| 2 | The architecture diagram failed to render: `graph` is a reserved word in Mermaid | Renamed the node; rendered in a real browser to check | Render diagrams, don't trust that they will |
| 3 | Box titles wrapped and hid behind the first box | Mermaid's `wrappingWidth` and `subGraphTitleMargin` set inside the diagram, so GitHub uses them too | Look at the output |
| 4 | The write-up said the prompts were "verbatim" but had quietly fixed two typos, and claimed voice had been "tested by hand" | Exact wording restored; the limitation now states only what's known | Documentation should be as honest as the evaluations |
| 5 | The first Google Doc looked right as text, but its rendered pages showed each caption sitting under the *previous* screenshot (images pushed to the next page left their captions behind), and the wide diagram was unreadable at page width | Captions placed under their images; a vertical version of the diagram for the doc; a corrected doc created (the Docs editing connector wasn't available to fix it in place) and the first renamed "OLD DRAFT" | Check the rendered page, not just the text |
