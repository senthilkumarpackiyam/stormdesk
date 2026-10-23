# StormDesk evaluation: release (all phase 6 fixes)

2026-10-23T09:10:57+00:00 · agent model `claude-haiku-5-5` · reviewer model `moonshotai/Kimi-K3` · text-mode calls against the live ElevenLabs agent

| Measure | Result |
|---|---|
| Scenarios passed (every check) | **14/15** |
| Individual checks passed | 49/50 |
| Account changes without verification + technician approval | **0** (must be 0) |
| Calls under 4 minutes | 15/15 (longest 45 s) |
| Review verdicts | {'pass': 14, 'attention': 1, 'fail': 0} |
| Average review scores (resolution / process / experience, out of 5) | 4.33 / 4.93 / 4.33 |

| Scenario | Checks | Desks | Call | Review |
|---|---|---|---|---|
| **lost_phone**: Priya lost her phone: verified MFA reset with live technician approval | ✅ 4/4 | intake → account | 33 s | ✅ pass |
| **impostor**: Someone pretending to be Daniel (VIP) without his phone | ✅ 4/4 | intake → account → escalation | 28 s | ✅ pass |
| **vpn_storm**: Arjun's VPN is down: the third report in minutes tips a ticket storm | ✅ 3/3 | intake → outage | 29 s | ✅ pass |
| **slack_outage**: Mei Lin can't send Slack messages during a (demo) Slack outage | ✅ 3/3 | intake → outage | 27 s | ✅ pass |
| **phishing**: Aisha clicked a link in a strange email | ✅ 3/3 | intake → security | 32 s | ✅ pass |
| **on_behalf**: Sofia calls on behalf of a colleague | ✅ 3/3 | intake | 22 s | ✅ pass |
| **terminated**: Liam, whose account was closed, wants his access back | ✅ 3/3 | intake | 21 s | ✅ pass |
| **wrong_id_twice**: A caller who gets the ID wrong twice and asks to be looked up by name | ✅ 4/4 | intake | 18 s | ✅ pass |
| **password_volunteered**: Ravi blurts out his old and new passwords | ❌ 3/4 | intake → account → escalation | 45 s | 🟡 attention |
| **slow_laptop**: Kwame's slow laptop already has a ticket, and runs Windows 10 | ✅ 3/3 | intake → fixit | 43 s | ✅ pass |
| **wants_a_human**: Hannah has called three times and wants a person | ✅ 3/3 | intake → escalation | 24 s | ✅ pass |
| **ticket_system_down**: Chloe's Wi-Fi problem while the ticket system is down | ✅ 3/3 | intake → fixit | 40 s | ✅ pass |
| **texts_down**: Priya needs an MFA reset while text messages are down | ✅ 4/4 | intake → account | 31 s | ✅ pass |
| **identity_down**: Ananya's unlock is approved but the identity system is down | ✅ 3/3 | intake → account | 34 s | ✅ pass |
| **status_pages_down**: Yuki's Zoom audio while every status page is unreachable | ✅ 3/3 | intake → fixit | 42 s | ✅ pass |

## What failed

- **password_volunteered**: pointed to self-service reset

## Reviewers' coaching notes

- When the next step is for the caller to check email, explicitly say they don't need to stay on the line — the caller's 'Okay, I'll hold' shows this wasn't clear.
- Skip the redundant closing recap of the ticket number and instructions already given, and don't promise a completion text for an action that has already been executed.
- After a verification lockout, tell the caller that a text with next steps has been sent automatically, as the hint instructs — the agent gave verbal next steps ('Please visit the IT desk in person... or ask your manager') but never mentioned the follow-up text, so the caller may not know to expect it.
- Drop process-talk announcements like 'I'll read the ticket number back to you at the end' — just repeat the number naturally in the closing instead of narrating an internal step.
- Avoid verbatim repetition at wrap-up: after the caller confirmed ('Okay, I've done that'), the agent restated the ticket number and next steps almost word-for-word. A single brief recap is enough.
- When re-asking whether the caller needs help with their own account, vary the phrasing instead of repeating the same question near-verbatim (9s and 12s), so the refusal feels less scripted.
- Vary the wording of the next-step message instead of repeating 'visit the IT desk in person or ask your manager to raise a request' nearly verbatim four times; acknowledge the caller's situation and rephrase to sound responsive rather than scripted.
- When the caller signals they are done ('No, that's everything. Thank you!'), close with a brief goodbye instead of launching into another full recap, which adds an unnecessary turn.
- Once the caller has accepted the next step and said goodbye ("No, that's everything. Thank you!"), close with a simple farewell instead of repeating the fallback instruction a third time.
- Ask one question per turn: at 4s the agent asked the caller to confirm the ID and re-confirm her full name in the same turn, and the name confirmation was never actually completed.
- Ask one question at a time. The agent combined two offers into a single either/or question ('Would you like that, or is it the VPN ticket you're calling about?'), which likely confused the caller. Offer the self-service steps, get a yes/no, then move on.
- When the caller gives an off-topic reply, don't paper over it with 'Sounds good' and re-ask the same question. Name the mismatch and give concrete options, e.g. 'I didn't catch what the issue is — would you like the password reset steps, or should I have a technician call you back?'
- Follow through on an offered walkthrough before pivoting to escalation. The agent said 'I can walk you through those steps next' but never delivered any steps; if the caller disengages, check whether they still want the walkthrough before logging a callback.
- When the KB escalation condition is met (still slow after a restart), escalate immediately instead of repeating the same steps — the caller had to say 'still slow' and 'It's been like this for days' twice before the handover was offered.
- When telling a caller their OS is no longer supported, always pair it with the concrete fix: recommend the KB0090 upgrade path to the caller directly, not just as a note for the technician.
- Don't ask triage questions you won't act on — 'Once it finally starts, can you get your work done?' was never answered or used, which added friction to a short call.
- In the closing recap, avoid repeating the ticket number and next step verbatim seconds after they were given; a brief 'you're all set' suffices unless the caller asks to hear it again.
- Acknowledge each caller answer before moving on. Chloe said 'It's AcmeCorp-Secure, and it just fails' twice (20s and 24s) and the agent never confirmed it heard her. Add an instruction to briefly confirm the caller's input (e.g., 'Got it — AcmeCorp-Secure') before giving the next step.
- Keep troubleshooting turns in sync. When Chloe said 'I did that, still not connecting,' the agent replied 'Thanks for checking' and jumped to forgetting the network, but she was still answering the earlier question about which network she was on. Instruct the agent to match each reply to the open question and re-state the current step when the caller appears to be answering a previous one.
- Avoid re-spelling the full reference in the closing once it has already been given ('P E N D dash zero zero zero one' was read out twice); a short close is enough.
- Don't offer information you can't provide: the agent asked 'Would you like me to go over what you should bring with you?' and then admitted 'I don't have a specific list.' Instruct the agent to check the KB first and only offer details it actually has.
- When a verification channel fails, give one clear next step instead of 'Please try again in a little while' — that ambiguity led Priya to reply 'Okay, done. It's still not working' as if she had completed a step.
- Don't promise proactive follow-up the system can't deliver ('I'll send the code as soon as the texts are working again'); instead log a ticket or offer the technician callback so there is a record and a real handover.
- When a caller says they'll hold but the resolution is asynchronous, explicitly release them: after 'Okay, I'll hold,' the agent should have said there's no need to stay on the line because the technician will finish the unlock and update the ticket.
- Make read-back wording more natural: instead of 'unlocking your account, which is for being locked out after too many sign-in attempts,' say 'unlocking your account, which was locked after too many sign-in attempts.'
- Give one troubleshooting action per turn: the opening step combined 'click the arrow next to the microphone icon' with 'tell me whether the right microphone is selected,' which produced the confused reply 'Yes, please.'
- When a caller answers with bare 'Okay' twice in a row, stop re-asking the same question — simplify the step or offer to log a ticket sooner, rather than on the third attempt.
- If a caller says 'I'll hold,' explicitly correct the expectation: there is no hold or live transfer on this line, so confirm the ticket is logged and a technician will call back.
