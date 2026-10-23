"""The public tunnel: gives the backend on your laptop an https address ElevenLabs can call.

ngrok (through pyngrok, which downloads the ngrok program on first use) forwards
https://<something>.ngrok-free.app to http://localhost:<port>. Technician endpoints stay closed through
it: the backend refuses /admin requests that arrive via a tunnel (see require_admin_key)."""

import logging

import httpx
from pyngrok import conf, ngrok

from stormdesk.voice.config import voice_settings

logging.getLogger("pyngrok").setLevel(logging.WARNING)


def open_tunnel(port: int) -> str:
    if not voice_settings.ngrok_authtoken:
        raise SystemExit("NGROK_AUTHTOKEN is empty. Add it to .env first.")
    conf.get_default().auth_token = voice_settings.ngrok_authtoken
    options = {"domain": voice_settings.ngrok_domain} if voice_settings.ngrok_domain else {}
    tunnel = ngrok.connect(str(port), "http", **options)
    return tunnel.public_url.replace("http://", "https://", 1)


def close_tunnel() -> None:
    ngrok.kill()


def check_reachable(public_url: str) -> None:
    """Prove the round trip works: internet -> ngrok -> backend."""
    resp = httpx.get(f"{public_url}/health", headers={"ngrok-skip-browser-warning": "1"}, timeout=20)
    if resp.status_code != 200 or resp.json().get("service") != "stormdesk":
        raise SystemExit(f"The tunnel is up but the backend didn't answer through it (HTTP {resp.status_code}).")
