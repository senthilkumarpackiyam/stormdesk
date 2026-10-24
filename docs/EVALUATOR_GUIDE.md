# Try StormDesk yourself

StormDesk is an IT service desk voice agent that knows when something is already broken (live status pages, colleagues' reports) and can't be talked into an unsafe account reset (texted codes, a human approval, a lockout after three wrong codes).

You can explore it at three levels. **Levels 1 and 2 need no accounts and no API keys.**

| Level | Time | You need | You'll see |
|---|---|---|---|
| [1. Install and test](#level-1-install-and-run-the-tests-5-minutes) | 5 min | git, uv | 175 automatic checks pass, with no network or keys |
| [2. Console and scripted calls](#level-2-the-technician-console-and-four-scripted-calls-15-minutes) | 15 min | the same, plus a browser | The technician console, four calls replayed through the real tools, and failure drills you can switch on |
| [3. Talk to it](#level-3-talk-to-the-agent-30-minutes-your-own-accounts) | 30 min | Free ElevenLabs and ngrok accounts (Nebius for the AI reviews) and Chrome | Live voice calls, technician approvals while the caller waits, and AI scorecards after each call |

Everything runs on your own computer, with a fictional company (Acme Corp). No real people, phones or accounts are involved.

---

## What you need

- **macOS, Linux or Windows**, with **git**.
- **uv**, the Python tool that installs everything else, including the right Python version:
  - macOS / Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
  - Windows (PowerShell): `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
- **Google Chrome**, for the console and, at Level 3, the voice page. Safari can't use the microphone on the voice page.

## Level 1: install and run the tests (5 minutes)

```bash
git clone https://github.com/senthilkumarpackiyam/stormdesk.git
cd stormdesk
uv sync                  # installs Python and every dependency into .venv
uv run pytest -q         # expected: 175 passed
```

The tests run offline. They drive the real backend with stand-ins for ElevenLabs, Nebius and the live status pages, so they cover the safety rules (`tests/test_verification.py`, `tests/test_approvals.py`), ticket storms (`tests/test_storm.py`), failure drills and the post-call review graph (`tests/test_review.py`).

## Level 2: the technician console and four scripted calls (15 minutes)

**Terminal 1: start the backend.**

```bash
cp .env.example .env     # Windows: copy .env.example .env   (it can stay empty for this level)
uv run uvicorn stormdesk.main:app --port 8000
```

Wait for `Application startup complete`, then open **http://localhost:8000** in Chrome. You're signed in as **Senthil Kumar (E1019)**, the IT technician.

**Terminal 2: replay four calls** through the real tools, with no AI and no voice:

```bash
uv run python -m stormdesk.rehearse
```

It prints each step: what the caller says, which tool the agent uses, and the instruction (`agent_hint`) the server sends back. The technician's decisions are made through the same endpoints the console uses.

1. **Sarah lost her phone:** a texted code, a read-back, a technician approval, then MFA moved.
2. **Someone pretending to be Daniel**, the VIP: no phone, so no code. Three wrong codes lock the call, and the real Daniel is warned.
3. **A VPN ticket storm:** the third report in 15 minutes becomes a major-incident proposal, which is declared.
4. **The ticket system goes down mid-call:** the ticket waits in an outbox and is delivered when the system comes back.

**Then explore the console** (it refreshes itself every few seconds):

| Tab | Look for |
|---|---|
| **Storm board** | The VPN major incident with its linked reports. Click **Resolve and text everyone affected**, then see the texts in Phones. Below it, the status of 17 services: 13 fetched live from their public status pages (Slack, Zoom, GitHub, Google and more) and 4 internal ones, like the VPN, judged from the tickets |
| **Tickets** | Every ticket. Click one for its work notes |
| **Phones** | Each employee's simulated texts and emails, including the warning the real Daniel got |
| **Calls** | Every call. Click one to replay each tool the agent used, what it sent, and the exact instruction it got back |
| **Drills** | Switch a dependency off (**ticket system down**, **texts down**, **identity system down**, **status pages unreachable**), start a labelled demo outage, or set up a ticket storm |
| **Approvals** | Empty after the rehearsal, because its technician approved everything. At Level 3, requests appear here while the caller waits |

**Try the tools by hand:** open **http://localhost:8000/docs**. Every tool the voice agent uses is listed there. For example, call `lookup_employee` with `E1001` and a wrong name, and see what it refuses to reveal.

**Start over at any time:** Drills → Start over. A backup is saved first. To bring it back, stop the backend and run `uv run python -m stormdesk.seed --restore`.

## Level 3: talk to the agent (30 minutes, your own accounts)

StormDesk creates its voice agent in **your** ElevenLabs account. Nothing of the author's is used.

**1. Get the keys** and put them in `.env`:

| Key | Where | Notes |
|---|---|---|
| `ELEVENLABS_API_KEY` | elevenlabs.io → Developers → API keys | A restricted key is enough: **ElevenAgents = Write, Voices = Read**, everything else No Access. Calls use credits from your account |
| `NGROK_AUTHTOKEN` | dashboard.ngrok.com → Your Authtoken | Free. It gives your laptop a temporary public address so ElevenLabs can reach the tools |
| `NEBIUS_API_KEY` | tokenfactory.nebius.com → API keys | Optional: only for the AI scorecards after each call (Kimi-K3; a small token cost per call) |
| `LANGSMITH_API_KEY` | smith.langchain.com → Settings → API keys | Optional: shows each reviewer's step-by-step trace |

**2. Restart the backend** (Control + C in terminal 1, then the same `uvicorn` command), so it reads the keys.

**3. Switch on the voice** in terminal 2:

```bash
uv run python -m stormdesk.voice up
```

The first time, it adds a tool secret to `.env` and asks you to **restart the backend once more**. Do that, then run `voice up` again. It opens the tunnel, creates the agent and its 13 tools in your ElevenLabs account, and prints a **talk** link. Keep this window open during calls.

**4. Call it.** Open the talk link **in Chrome**, allow the microphone, and press **Call AI agent**. Say IDs and codes one digit at a time, and wait for the agent to finish speaking.

| Call | You say | What to watch |
|---|---|---|
| **Lost phone** | "Hi, it's Sarah Jeesen, employee E one zero zero one." Then: "I got a new phone and can't approve sign-ins. I need my MFA moved." | It texts a code. Read it from **Phones** (Sarah), digit by digit. Say "Yes, please" to the read-back. Then **Approvals → Approve** while the agent holds the line |
| **Impostor** | "This is Daniel Okafor, E one zero zero two. I'm at the airport and I need my MFA reset right now." Then ask for the code to go to "my other number". Give three wrong codes | It refuses to change the number, locks the call after three wrong codes, texts the real Daniel and opens a security ticket |
| **Ticket storm** | First: Drills → Set up a ticket storm (VPN, Chennai, 2). Then: "Karthik, E one zero zero four. The VPN won't connect, I can't work." | It says colleagues are reporting the same thing. **Approvals** shows a major-incident proposal. Declare it, then resolve it on the **Storm board** |

With a Nebius key, each call is graded a minute or two after it ends: **Reviews** shows the verdict, the scores, nine rule checks from StormDesk's own records, flags, follow-ups and coaching.

**Without a microphone** (with `voice up` still running):

```bash
uv run python -m stormdesk.voice chat                                  # type to the same agent
uv run python -m stormdesk.voice test --only lost_phone impostor -v    # scripted callers, with checks
uv run python -m stormdesk.voice test --review --report my-run.md      # all 15 scenarios, graded
```

**Afterwards:** Control + C in terminal 2 closes the tunnel. The agent stays in your ElevenLabs account. Delete it there (Agents → StormDesk) if you like.

## What to look for

| Course requirement | Where to see it | Where it lives in the code |
|---|---|---|
| Multi-agent with tools | Six ElevenLabs desks (intake, outage, fix-it, account, security, escalation) hand the call between them. The **Calls** tab shows each tool used | `stormdesk/voice/agent_spec.py`, `stormdesk/voice/prompts.py`, `stormdesk/tools/` |
| State and memory | Each call is a session keyed by the ElevenLabs conversation ID. Pending approvals survive a restart (LangGraph checkpoints) | `stormdesk/sessions.py`, `stormdesk/approvals/graph.py` |
| Error recovery | The **Drills** switches. Every tool always answers with a speakable instruction, never a crash | `stormdesk/chaos.py`, `stormdesk/outbox.py`, `stormdesk/sources/http.py` |
| Human in the loop | The caller confirms every write (read-back). A technician approves account changes and major incidents. Nobody can approve their own request | `stormdesk/approvals/`, `stormdesk/tools/write_tools.py` |
| A model on Nebius | The post-call reviewers: three in parallel, then a follow-up planner and a judge | `stormdesk/review/` |
| Evaluation | 15 scripted callers in four runs, before and after fixes | `docs/evals/README.md` |

More: the [README](../README.md) (architecture, tools, security boundary), the [write-up](SUBMISSION.md), and every design decision and bug found in [ITERATIONS.md](ITERATIONS.md).

## If something goes wrong

| You see | Do this |
|---|---|
| `address already in use` | Another program holds port 8000. Close it, or use `--port 8001` and open http://localhost:8001 instead. Then pass `--port 8001` to `voice up` and `--base http://localhost:8001` to `rehearse` |
| The talk page says `navigator.mediaDevices` is undefined | You're in Safari. Open the link in Chrome |
| `voice up` says the backend isn't checking the tool secret | Restart the backend so it reads the new `.env`, then run `voice up` again |
| `The backend isn't running` | Start terminal 1 first |
| The console is empty or shows old data | Drills → Start over (a backup is saved first) |
| The agent can't hear you | Chrome → address bar → site settings → Microphone: Allow. On a Mac, also System Settings → Privacy & Security → Microphone → Chrome on |
