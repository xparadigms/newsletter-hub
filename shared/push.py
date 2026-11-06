"""iOS notifications when a newsletter is published.

Called from store.upsert_issue once per publish: for a section that splits
an edition into several articles, only part 1 notifies, so a reader gets one
"Startup News is out" rather than six. Each phone hears about its own mode's
newsletters — the app registers its token with the mode it is in.

Needs APNS_KEY_P8 (the APNs auth key file's contents) and APNS_KEY_ID; without
them this does nothing. TestFlight and App Store builds use Apple's
production push service, which is what this talks to.
"""

from __future__ import annotations

import os
import time
from typing import Any

from . import http, store

TEAM_ID = os.environ.get("APPLE_TEAM_ID", "N7DWY66V6B")
TOPIC = "com.heechangkang.thebrief"
APNS = "https://api.push.apple.com/3/device/"
SECTION_NAMES = {
    "startup": "Startup News",
    "business": "Business Insight",
    "fintech": "Finance Infra",
    "stocks": "Three Companies",
    "china": "China Daily",
    "mandarin": "Mandarin Basics",
    "japan": "Japan Daily Talk",
    "watch": "Watch Weekly",
}
MODES = {
    "japan": {"startup", "business", "fintech", "stocks"},
    "china": {"china", "mandarin"},
}


def configured() -> bool:
    return bool(os.environ.get("APNS_KEY_P8") and os.environ.get("APNS_KEY_ID"))


def _token() -> str:
    import jwt  # PyJWT

    return jwt.encode(
        {"iss": TEAM_ID, "iat": int(time.time())},
        os.environ["APNS_KEY_P8"],
        algorithm="ES256",
        headers={"kid": os.environ["APNS_KEY_ID"]},
    )


def _devices(section: str) -> list[str]:
    base, key = store._config()
    modes = [m for m, sections in MODES.items() if section in sections]
    if not modes:
        return []
    resp = http.request_with_retry(
        "GET", f"{base}/rest/v1/push_devices", label="Supabase", headers=store._headers(key),
        params={"select": "token", "mode": f"in.({','.join(modes)})"},
    )
    resp.raise_for_status()
    return [r["token"] for r in resp.json()]


def _forget(token: str) -> None:
    base, key = store._config()
    http.request_with_retry(
        "DELETE", f"{base}/rest/v1/push_devices", label="Supabase",
        headers=store._headers(key, "return=minimal"), params={"token": f"eq.{token}"},
    )


def notify(row: dict[str, Any], stored: dict[str, Any]) -> int:
    """Tell every phone in this section's mode that the issue is out."""
    if not configured():
        return 0
    run_key = row.get("run_key") or ""
    if ":p" in run_key and not run_key.endswith(":p1"):
        return 0  # later articles of the same edition stay quiet
    section = row["section"]
    slug = stored.get("slug") or row.get("slug") or ""
    payload = {
        "aps": {
            "alert": {"title": SECTION_NAMES.get(section, "The Brief"), "body": row.get("title") or ""},
            "sound": "default",
            "thread-id": section,
        },
        "link": f"thebrief://post/{section}/{slug}" if slug else f"thebrief://section/{section}",
    }

    import httpx  # HTTP/2 is required by Apple's push service

    sent = 0
    headers = {
        "authorization": f"bearer {_token()}",
        "apns-topic": TOPIC,
        "apns-push-type": "alert",
        "apns-priority": "10",
    }
    with httpx.Client(http2=True, timeout=15) as client:
        for token in _devices(section):
            resp = client.post(APNS + token, json=payload, headers=headers)
            if resp.status_code == 200:
                sent += 1
            elif resp.status_code == 410 or "BadDeviceToken" in resp.text or "Unregistered" in resp.text:
                _forget(token)  # the app was deleted, or the token was never valid
            else:
                print(f"  ⚠ push {resp.status_code}: {resp.text[:200]}")
    print(f"  ✓ Notified {sent} device(s)")
    return sent


if __name__ == "__main__":
    # python -m shared.push test "Message"  — a test notification to every phone.
    import sys

    if len(sys.argv) >= 2 and sys.argv[1] == "test":
        message = sys.argv[2] if len(sys.argv) > 2 else "Notifications are working."
        for mode in MODES:
            section = sorted(MODES[mode])[0]
            notify({"section": section, "title": message, "run_key": "test"}, {})
