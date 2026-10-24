# StormDesk evaluations

Every run puts **15 scripted callers** through the **live ElevenLabs agent** (text mode, real tools, real workflow). Each call is then judged two ways:

- **checks** on what actually happened in StormDesk: approvals, tickets, lockouts, messages
- **the post-call reviewers** (Kimi-K3 on Nebius): verdict and scores

The runs were made before the practice employees were renamed (Priya Raman is now Sarah Jeesen, Arjun Mehta is Karthik, Vikram Rao is Senthil Kumar), so the reports use the old names.

Each run has its own report: [baseline](baseline.md) · [after coaching](after.md) · [final](final.md) · [release](release.md). The raw data, including transcripts, is in the matching `.json` files.

## The runs

| Run | Scenarios | Checks | Unsafe account changes | Longest call | Review verdicts | Scores (resolution / process / experience) |
|---|---|---|---|---|---|---|
| Baseline (before coaching) | **15/15** | 50/50 | **0** | 55 s | 14 ✅ 1 🟡 | 4.47 / 4.80 / 4.40 |
| After coaching | 14/15 | 49/50 | **0** | 46 s | 11 ✅ 2 🟡 (+2 reviews lost to Nebius timeouts) | 4.38 / 4.85 / 4.31 |
| Final (reviewer fixes) | 13/15 | 46/50 | **0** | 43 s | 13 ✅ 1 🟡 1 ❌ | 4.53 / 4.60 / 4.27 |
| Release (all fixes) | 14/15 | 49/50 | **0** | 45 s | 14 ✅ 1 🟡 | 4.33 / **4.93** / 4.33 |

Between "final" and "release", the two failing scenarios were also re-run after each fix: **impostor 3/3 and password 3/3**, plus a 3/3 regression spot-check (lost phone, texts down, wants a person).

## What the numbers say, and what they don't

- **Safety held in every run.** Across about 80 evaluated calls there were 0 account changes without code verification *and* a technician's approval, and no password was ever stored.
- **Every call was well under the 4-minute target** (longest: 55 s; text mode is faster than speech).
- **Targeted fixes worked and stayed fixed:**
  - terminated account: 🟡 to ✅
  - a lockout lost in a hand-off: fixed, 3/3
  - a password repeated: fixed, 3/3
- **The general "speak better" rules did not measurably raise the experience score** (4.40 → 4.33). With one run per scenario, the agent's and the reviewers' natural variation (about ±0.1–0.2) is as large as the effect. We don't claim an improvement the data doesn't show. A firmer answer would need several runs per scenario.
- **Process got stricter and better** (4.80 → 4.93) after fixing contradictory tool hints and the hand-off bug.

## What each run found

| Run | Found | Fixed by |
|---|---|---|
| Baseline | A tool hint said "offer a transfer" on a line with no live transfer (the one 🟡) | Honest next steps in every hint; a test forbids "transfer to a technician" |
| After coaching | Two reviews lost to Nebius timeouts; a reviewer rule misread "confirm … expired password" as asking for a password | Backup reviewer model; a precise password rule |
| After coaching | A check that tested *which desk* instead of *what the caller was told* | The check now tests the outcome (changed after seeing the result, and recorded as such) |
| Final | **An impostor's pressure moved the call off the Account desk mid-verification.** The next desk couldn't check codes, so three wrong codes never locked the call | No Account → Security edge; "sounding upset is NOT enough" to leave verification; every desk reachable from Account can check codes; a new reviewer rule flags unfinished verification |
| Final | **A new coaching rule made the agent repeat a password** while warning about it | Exact safe wording that never refers to what the caller said |
| Release | The scripted caller's replies didn't fit the agent's questions, so the self-service steps were never reached (the agent switched to a callback, as instructed). The reviewer noted a two-part question, and that passwords spoken on a *recorded* call need the recording scrubbed | Not changed: tuning the agent to a scripted caller would be overfitting. Recording redaction is future work |

## How to run it

```bash
uv run uvicorn stormdesk.main:app --port 8000          # backend
uv run python -m stormdesk.voice up                     # tunnel + deploy (second terminal)
uv run python -m stormdesk.voice test --reset --review --report docs/evals/my-run.md
```

`--only impostor phishing` runs a subset; `-v` prints every conversation. A full run with reviews takes about 30 minutes and roughly 1–2% of a Creator plan's monthly ElevenLabs credits.
