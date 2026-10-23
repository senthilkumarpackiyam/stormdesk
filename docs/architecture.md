# Architecture

```mermaid
%%{init: {"flowchart": {"wrappingWidth": 420, "subGraphTitleMargin": {"top": 6, "bottom": 18}}}}%%
flowchart LR
    caller(["Employee on a call"])

    subgraph EL["ElevenLabs agent · six desks"]
        direction TB
        intake["Intake<br/>who? what's wrong? live status"]
        outage["Outage desk"]
        fixit["Fix-it desk"]
        account["Account desk<br/>text code + approval"]
        security["Security desk"]
        esc["Escalation desk"]
        intake --> outage & fixit & account & security & esc
        fixit --> account & security
        outage & fixit & account & security --> esc
    end

    subgraph BE["StormDesk backend · FastAPI"]
        direction TB
        tools["13 tools<br/>read · low-risk write · sensitive"]
        guards["Guards + policy<br/>caller from session, never from the AI"]
        appr["Approval graph (LangGraph)<br/>interrupt() + SQLite checkpoint"]
        storm["Ticket-storm detection"]
        outbox["Outbox<br/>when the ticket system is down"]
        db[("Practice company<br/>tickets, sessions, audit")]
        tools --> guards --> db
        tools --> appr
        tools --> storm --> appr
        tools --> outbox --> db
    end

    feeds[["Live data<br/>17 status pages · CISA KEV · endoflife.date"]]
    console["Technician console (Streamlit)<br/>approvals · storms · tickets · phones · reviews · drills"]

    subgraph RV["Post-call review · LangGraph + Nebius"]
        direction TB
        gather["Case file + 9 rule checks"]
        res["Resolution"]
        proc["Process"]
        exp["Experience"]
        fu["Follow-up planner"]
        judge["Judge: scorecard"]
        gather --> res & proc & exp
        res & proc & exp --> fu --> judge
    end

    caller -- voice --> EL
    EL -- "webhook tools + secret header<br/>(ngrok tunnel)" --> tools
    feeds --> tools
    appr <-- "approve / reject" --> console
    db --> console
    EL -. "finished calls (polled every 30 s)" .-> gather
    judge --> console
    RV -. traces .-> ls[("LangSmith")]
```

| Part | Technology | Role |
|---|---|---|
| Voice and conversation | ElevenLabs Agents (workflow of six sub-agents), Claude Haiku 5.5, voice "Sarah" | Talks to the caller; each desk has its own playbook and tools; ElevenLabs judges hand-off conditions |
| Tools | FastAPI, generated into ElevenLabs webhook tools from the same Pydantic models | 13 tools in three permission tiers; every answer carries an `agent_hint` |
| Human-in-the-loop | LangGraph `interrupt()` + SQLite checkpointer | Account changes and major incidents pause for a technician; survive restarts |
| Live data | Statuspage / Slack / Google feeds, CISA KEV, endoflife.date | "Is it them or us?", security advisories, out-of-support devices |
| Technician | Streamlit | Approvals, storm board, tickets, simulated phones, call timelines, reviews, failure drills |
| Quality | LangGraph + LangChain on Nebius Token Factory (Kimi-K3, backup DeepSeek-V4.1-Flash), LangSmith | Post-call scorecards; rule checks that the AI can't override |
| Evaluation | 15 scripted callers over ElevenLabs' WebSocket in text mode | Before/after runs with checks and reviews ([evals](evals/README.md)) |
