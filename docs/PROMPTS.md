# Vibe-coding prompt log

The Week 3 Google Doc must include the prompts used with AI coding tools. Each prompt to the coding assistant is logged here, verbatim where practical.

Tool: Claude Code (VS Code extension), model Claude Opus 5.5.

---

### Prompt 1: choosing the project (2026-10-22)

> i have the attached project requirement to build AI Agent,
> -- suggest me a best possible project to do.
> -- make sure it does not reflect any existing known AI Agent projects and something unique
> -- suggest me any datasource which can be pulled through API online and refreshed frequently
> -- make sure to meet all the guideline mentioned in the doc
> -- choose the best project listed in the options
> -- I am thinking of ElevenLabs Voice Agent: ITSM , please suggest me the best possible way to get this project done.
>
> *(followed by the full Week 3 project brief, pasted)*

**Outcome:** the StormDesk concept (ticket storms plus resistance to social engineering), the architecture (ElevenLabs voice → FastAPI + LangGraph backend → Nebius QA pipeline), and a list of live data sources, each confirmed to return HTTP 200.

### Prompt 2: phased build (2026-10-22)

> here is the plan:
> Make the project into different phases and complete phase by phase fully autonmous.
> Do not move to another phae until i say "GO"
> Explain me every phase like teaching a non-technical / layman who has no knowledge over AI

**Outcome:** the 7-phase plan in [PHASES.md](PHASES.md); Phase 1 built and tested.

### Prompt 3: start phase 2 (2026-10-23)

> GO

**Outcome (phase 2):** per-call sessions, one-time-code verification, tiered write tools, the LangGraph approval graph with `interrupt()` and a SQLite checkpointer, storm → major-incident proposals, the outbox, redaction, failure switches, the text rehearsal, and 60 new tests.

### Prompt 4: start phase 3 (2026-10-23)

> GO

**Outcome:** the Streamlit console (approvals, storm board, tickets, phones, call timelines, drills); a separate admin boundary (local-only unless `STORMDESK_ADMIN_SECRET`); resolving a major incident with notifications; the request-vs-incident split; 21 new tests including AppTest UI tests; verified by clicking through in real Chrome via Playwright.

### Prompts 5–8: account setup (2026-10-23)

> *(screenshot of the ElevenLabs "Create API Key" dialog)* what should select for permissions here for our project?

> i dont find .env file, tell me the exact path

> guide me step by step how do i get ngrok API key

> done added my ngrok and elevanlabs API key now in .env file

**Outcome:** a least-privilege ElevenLabs key (ElevenAgents = Write, Voices and User = Read, everything else No Access, 30-day expiry, credit cap); `.env` created with empty slots; the ngrok Authtoken (not "API key") steps; a pre-flight check confirming both keys work, without displaying them.

### Prompt 9: start phase 4 (2026-10-23)

> GO

**Outcome:** the ElevenLabs agent with a six-desk workflow, tools generated from the backend, the ngrok tunnel, the one-command `voice up`, the text-mode client, five scripted end-to-end scenarios (5/5 passing against the real agent), and 15 new offline tests.

### Prompts 10–12: Nebius and LangSmith keys (2026-10-23)

> i dont see NEBIUS_API_KEY=... in .env file?

> done, updated nebius and langsmith API keys now

**Outcome:** empty `NEBIUS_API_KEY` / `LANGSMITH_API_KEY` slots added to `.env` and `.env.example`; a pre-flight check found Nebius at its new address (`api.tokenfactory.nebius.com`, 30 models) and LangSmith working, without displaying either key.

### Prompt 13: start phase 5 (2026-10-23)

> GO

**Outcome:** the post-call review pipeline: case file, 8 rule checks, a LangGraph graph of 5 AI reviewers on Nebius (3 in parallel), guardrails and fallbacks, automatic pickup of finished calls, the console's Reviews tab with technician-approved follow-up tickets, LangSmith tracing, a model comparison, and 16 new tests.

### Prompt 14: start phase 6 (2026-10-23)

> GO

**Outcome:** 15 scenarios (10 new, including four live failure drills and the new `feeds_down` drill), every call graded by the reviewers, an evaluation report (markdown + JSON), a baseline run, coaching-driven prompt and hint fixes, and an "after" run to measure them.

### Prompt 15: start phase 7 (2026-10-23)

> GO

**Outcome:** a code-quality pass, the architecture diagram (Mermaid, rendered to PNG), the README rebuilt for reviewers (one-liner, results, the agent framework filled in), the project write-up for the Google Doc (`docs/SUBMISSION.md`), the 5-minute demo script, and the first commit.

### Prompt 16: publish (2026-10-23)

> github repository url : https://github.com/senthilkumarpackiyam/stormdesk
> i would prefer option (a)

**Outcome:** pushed to GitHub (public). The write-up was created as a Google Doc in Drive from `docs/SUBMISSION.md`, with the diagram and screenshots embedded from the repository. A render check of the first version found captions under the wrong screenshots and an unreadably wide diagram, so a corrected doc was created (captions under their images, a vertical diagram) and the first one was renamed "OLD DRAFT".

### Prompt 17: a guided test of the voice agent (2026-10-24)

> guide me step by step like teaching a layman who is non-technical that how to test this voice agent functionality. do not move to next step until i say go

> done, check if old copy running or not

> go

**Outcome:** a step-by-step walkthrough in plain English (stop old copies, start the backend, open the console, reset the data, start the voice link, test calls, read the reviews), pausing for "go" after each step. Paused at step 3 by the next prompt.

### Prompt 18: redesign the console (2026-10-24)

*(With a screenshot of a Verint screen: blue header bands with white letters.)*

> hold on, I dont like the way streamlit shows the application. It is very dull and outdated application and not attractive at all. Could you check if the below changes are possible now to od?
> -- Change the employee names to Senthil Kumar, Sarah Jeesen, and Karthik
> -- I want a modernized , futuristic icon for the company name "StormDesk". The icon should represent the business function. Use the official and shuttle colors.
> -- Use the headers something like attached picture highlighted background blue format with white letters.
> -- Over all application should be futuristic and attractive.
> -- Use the official colors
> -- check if this can be a html5 application rather than streamlit one

Asked three questions, the answers were: names → **"Senthil as the technician"** (Senthil Kumar replaces the IT technician, Sarah Jeesen the lost-phone caller, Karthik the VPN caller); colours → **"Blue + Shuttle Gray (Recommended)"**; Streamlit → **"Replace it completely"**.

**Outcome:** the employees renamed everywhere (practice data, agent speech-recognition keywords, scenarios, tests, demo script). The Streamlit console was replaced by an HTML5 page served by the backend itself at `/console` (plain HTML, CSS and JavaScript, no build step, nothing extra to install): royal-blue header bands with white letters, Shuttle Gray text, a cyan accent, and a new logo. All seven tabs kept, with the same features. Every server value is escaped before display, under a strict Content-Security-Policy. Checked in Chrome with Playwright, including typing that survives refreshes, the admin-key prompt and phone width. New screenshots. 169 tests.

### Prompt 19: polish the console (2026-10-24)

*(With a screenshot of the new console.)*

> i see the application as attached:
>
> few problems that needs to be solved for sure:
>
> -- it is still showing old employees in the list
> -- I dont like the storm desk font. make it modern and futuristic
> -- I dont like the icon, alter it, no hexagon but use headset with storm, use different color than blue
> -- I see all the fonts and sizes are very smal, make it liitle bigger in fotn size to see
> -- remaining all are good

**Outcome:** on every start, StormDesk now brings renamed employees up to date in an existing database without wiping its tickets or calls (with a test), and the user's practice data was updated straight away. The name "StormDesk" is set in Orbitron with an amber "Desk". The new logo is an amber-to-orange headset with a storm cloud and a lightning bolt inside it, and no hexagon. Every text size is 15% larger. Checked in Chrome at desktop and phone width.

### Prompt 20: the live test calls, and what came after (2026-10-24)

> go

*(Step by step: reset the data, start the voice, open the talk link. Safari couldn't use the microphone, so the link was opened in Chrome. Then three live calls.)*

> shutdown

> do all four

**Outcome:** three live voice calls (Sarah's lost phone, an impostor posing as Daniel, Karthik's VPN storm) all worked and were graded pass by the reviewers. Karthik's call showed the agent asking a single-name caller for a surname twice. The fix is an explicit rule with an example. The scripted Karthik caller now answers the ID question the way a person would, and a new check fails if a surname is asked for. Re-run against the live agent: Karthik passed twice, and lost phone, impostor and wrong-ID passed as regressions. Fresh screenshots were taken from scripted calls with real reviews, then everything was published and the doc refreshed.

