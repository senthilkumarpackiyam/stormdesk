# ElevenLabs definitions

These are the exact definitions `python -m stormdesk.voice deploy` sends to ElevenLabs. They are regenerated on every deploy, with account-specific values replaced by placeholders:

| Placeholder | Becomes |
|---|---|
| `{{PUBLIC_URL}}` | The tunnel's https address (ngrok) |
| `{{STORMDESK_TOOL_SECRET}}` | A reference to the ElevenLabs workspace secret `stormdesk_tool_key`. The agent sends it as `X-StormDesk-Key`; the AI never sees it |
| `{{tool:<name>}}` | The id ElevenLabs gives each tool |

- [agent.json](agent.json): the StormDesk agent. It contains the shared rulebook prompt, Claude Haiku 5.5, the voice, and the **workflow** of six desks with the conditions for moving between them.
- [tools/](tools): the 13 webhook tools, generated from the backend's FastAPI definitions. `conversation_id` is bound to the system variable `system__conversation_id`, so ElevenLabs fills it in and the AI can't.

Don't edit these by hand. Change `stormdesk/voice/` or the backend tools, then redeploy.
