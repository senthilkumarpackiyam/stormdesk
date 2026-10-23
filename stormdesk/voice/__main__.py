"""StormDesk voice commands.

    uv run python -m stormdesk.voice up            # tunnel + deploy + print the talk link; Ctrl+C to stop
    uv run python -m stormdesk.voice chat          # type to the deployed agent (text mode, no voice minutes)
    uv run python -m stormdesk.voice test          # scripted calls with checks on what really happened
    uv run python -m stormdesk.voice deploy --url https://...   # deploy against a URL you already have
    uv run python -m stormdesk.voice export        # write elevenlabs/ definitions only, no account changes
    uv run python -m stormdesk.voice links         # print the talk and dashboard links
"""

import argparse
import asyncio
import signal
import sys
import time
from pathlib import Path

import httpx

from stormdesk.config import settings
from stormdesk.voice import deploy as deployer
from stormdesk.voice import report, tunnel
from stormdesk.voice.chat import interactive
from stormdesk.voice.scenarios import SCENARIOS, run


def _agent_id() -> str:
    agent_id = deployer.load_state().get("agent_id")
    if not agent_id:
        sys.exit("No agent deployed yet. Run: uv run python -m stormdesk.voice up")
    return agent_id


def _print_links(agent_id: str) -> None:
    for name, url in deployer.links(agent_id).items():
        print(f"  {name:<10} {url}")


def cmd_up(args) -> None:
    local = f"http://localhost:{args.port}"
    try:
        httpx.get(f"{local}/health", timeout=5).raise_for_status()
    except httpx.HTTPError:
        sys.exit(f"The backend isn't running on {local}. Start it first: "
                 f"uv run uvicorn stormdesk.main:app --port {args.port}")
    created = not settings.tool_secret
    deployer.ensure_tool_secret()
    unprotected = httpx.post(f"{local}/tools/search_kb", json={"query": "vpn"}, timeout=10).status_code == 200
    if unprotected:
        sys.exit("The backend isn't checking the tool secret yet"
                 + (" (it was just created in .env)" if created else "")
                 + ". Restart the backend so it reads .env, then run this again.")
    print("Opening the tunnel...")
    public_url = tunnel.open_tunnel(args.port)
    try:
        tunnel.check_reachable(public_url)
        print(f"  public URL {public_url}  (forwards to {local})")
        print("Deploying the tools and the agent to ElevenLabs...")
        state = deployer.deploy(public_url)
        print(f"  agent {state['agent_id']} with {len(state['tool_ids'])} tools\n\nTalk to StormDesk:")
        _print_links(state["agent_id"])
        print("\nKeep this running during calls. Ctrl+C closes the tunnel.")
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        tunnel.close_tunnel()
        print("Tunnel closed.")


def cmd_deploy(args) -> None:
    state = deployer.deploy(args.url)
    print(f"Deployed agent {state['agent_id']} with {len(state['tool_ids'])} tools.")
    _print_links(state["agent_id"])


def cmd_export(args) -> None:
    deployer.export()
    print(f"Wrote the agent and tool definitions to {deployer.EXPORT_DIR}")


def cmd_links(args) -> None:
    _print_links(_agent_id())


def cmd_chat(args) -> None:
    asyncio.run(interactive(_agent_id()))


async def _run_all(agent_id: str, scenarios, admin: httpx.Client, verbose: bool, review: bool) -> list:
    results = []
    for scenario in scenarios:
        print(f"\n== {scenario.name}: {scenario.title}")
        result = await run(agent_id, scenario, admin, print if verbose else (lambda _: None), review=review)
        results.append(result)
        if result.error:
            print(f"   ERROR {result.error}")
        print(f"   conversation {result.conversation_id} · {result.duration_s or '?'} s · desks: "
              f"{' -> '.join(result.desks) or '?'} · agent hung up: {'yes' if result.ended_by_agent else 'no'}")
        print(f"   tools: {', '.join(result.tools) or 'none'}")
        for check, ok in result.checks:
            print(f"   {'PASS' if ok else 'FAIL'}  {check}")
        if result.review:
            print(f"   review: {result.review.get('verdict')} · {result.review.get('headline')}")
    return results


def cmd_test(args) -> None:
    agent_id = _agent_id()
    admin = httpx.Client(base_url=args.backend, timeout=30)
    chosen = [s for s in SCENARIOS if not args.only or s.name in args.only]
    if args.reset:
        admin.post("/admin/reset", json={"confirm": True})
    results = asyncio.run(_run_all(agent_id, chosen, admin, args.verbose, args.review))
    passed = sum(r.passed for r in results)
    print(f"\n{passed}/{len(results)} scenarios passed")
    if args.report:
        summary = report.summarise(admin, results)
        report.write(Path(args.report), args.label or Path(args.report).stem, results, summary)
        print(f"Report written to {args.report} (and .json)")
    sys.exit(0 if passed == len(results) else 1)


def main() -> None:
    sys.stdout.reconfigure(line_buffering=True)  # show progress straight away, even when piped to a file
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    up = sub.add_parser("up", help="open the tunnel, deploy, and keep running")
    up.add_argument("--port", type=int, default=8000)
    up.set_defaults(func=cmd_up)
    dep = sub.add_parser("deploy", help="deploy against an existing public URL")
    dep.add_argument("--url", required=True)
    dep.set_defaults(func=cmd_deploy)
    sub.add_parser("export", help="write elevenlabs/ only").set_defaults(func=cmd_export)
    sub.add_parser("links", help="print the talk and dashboard links").set_defaults(func=cmd_links)
    sub.add_parser("chat", help="type to the deployed agent").set_defaults(func=cmd_chat)
    test = sub.add_parser("test", help="run the scripted test calls")
    test.add_argument("--backend", default=settings.backend_url, help="where to check results (admin API)")
    test.add_argument("--only", nargs="*", help="scenario names to run")
    test.add_argument("--reset", action="store_true", help="reset the practice data first")
    test.add_argument("-v", "--verbose", action="store_true", help="print the conversations")
    test.add_argument("--review", action="store_true", help="also grade each call with the post-call reviewers")
    test.add_argument("--report", help="write a markdown report (and .json) to this path")
    test.add_argument("--label", help="title for the report, e.g. 'baseline'")
    test.set_defaults(func=cmd_test)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
