#!/usr/bin/env python3
"""TestFlight testers, through the App Store Connect API.

    python3 ios/scripts/asc_testers.py status
    python3 ios/scripts/asc_testers.py add someone@example.com

Internal testers must be users on the App Store Connect team; anyone else is
an external tester, in the "Testers" group. External testing needs Apple's Beta
App Review once per app (later builds are usually approved automatically), so
`add` fills in the review details from the BETA_* variables when they are
missing, puts the newest build in the group and submits it for review if it
has not been yet.

Needs ASC_KEY_P8 (the key file's contents), ASC_KEY_ID and ASC_ISSUER_ID.
"""

from __future__ import annotations

import json
import os
import sys
import time

import jwt  # PyJWT
import requests

APP = "6823045719"
GROUP = "Testers"
API = "https://api.appstoreconnect.apple.com"


def token() -> str:
    now = int(time.time())
    return jwt.encode(
        {"iss": os.environ["ASC_ISSUER_ID"], "iat": now, "exp": now + 1200, "aud": "appstoreconnect-v1"},
        os.environ["ASC_KEY_P8"],
        algorithm="ES256",
        headers={"kid": os.environ["ASC_KEY_ID"], "typ": "JWT"},
    )


def call(method: str, path: str, body: dict | None = None, ok=(200, 201, 204)) -> dict:
    r = requests.request(method, API + path, json=body, timeout=60,
                         headers={"Authorization": f"Bearer {token()}"})
    if r.status_code not in ok:
        raise SystemExit(f"{method} {path} -> {r.status_code}\n{r.text[:1500]}")
    return r.json() if r.text else {}


def latest_build() -> dict:
    data = call("GET", f"/v1/builds?filter[app]={APP}&sort=-uploadedDate&limit=1&include=buildBetaDetail")
    return data["data"][0]


def external_group() -> dict | None:
    for g in call("GET", f"/v1/apps/{APP}/betaGroups")["data"]:
        if g["attributes"]["name"] == GROUP and not g["attributes"]["isInternalGroup"]:
            return g
    return None


def status() -> None:
    review = call("GET", f"/v1/apps/{APP}/betaAppReviewDetail")["data"]["attributes"]
    print("review contact:", {k: review.get(k) for k in ("contactFirstName", "contactLastName", "contactEmail", "contactPhone")})
    locs = call("GET", f"/v1/apps/{APP}/betaAppLocalizations")["data"]
    print("beta localizations:", [(l["attributes"]["locale"], bool(l["attributes"].get("description")),
                                   l["attributes"].get("feedbackEmail")) for l in locs])
    print("groups:", [(g["attributes"]["name"], g["attributes"]["isInternalGroup"])
                      for g in call("GET", f"/v1/apps/{APP}/betaGroups")["data"]])
    b = latest_build()
    detail = call("GET", f"/v1/builds/{b['id']}/buildBetaDetail")["data"]["attributes"]
    print("latest build:", b["attributes"]["version"], b["attributes"]["processingState"], detail)
    subs = call("GET", f"/v1/betaAppReviewSubmissions?filter[build]={b['id']}")["data"]
    print("review submissions for it:", [s["attributes"].get("betaReviewState") for s in subs])


def add(email: str) -> None:
    # Review details, once per app. Apple asks for a person to contact.
    review = call("GET", f"/v1/apps/{APP}/betaAppReviewDetail")["data"]
    want = {
        "contactFirstName": os.environ.get("BETA_FIRST_NAME", "Heechang"),
        "contactLastName": os.environ.get("BETA_LAST_NAME", "Kang"),
        "contactEmail": os.environ.get("BETA_EMAIL", "heechang@xparadigms.com"),
        "contactPhone": os.environ.get("BETA_PHONE", ""),
        "demoAccountRequired": False,
        "notes": "No sign-in is needed to read. Generating a new issue asks for the site password, which "
                 "reviewers do not need: every screen can be tested by reading.",
    }
    missing = {k: v for k, v in want.items() if v != "" and not review["attributes"].get(k)}
    if missing:
        call("PATCH", f"/v1/betaAppReviewDetails/{review['id']}",
             {"data": {"type": "betaAppReviewDetails", "id": review["id"], "attributes": missing}})
        print("review details filled:", sorted(missing))

    locs = call("GET", f"/v1/apps/{APP}/betaAppLocalizations")["data"]
    if not any(l["attributes"].get("description") for l in locs):
        attrs = {
            "description": "The Brief: daily newsletters on startups, financial infrastructure, Japan and China, "
                           "in Japanese and Chinese with furigana, pinyin and Korean translations.",
            "feedbackEmail": os.environ.get("BETA_EMAIL", "heechang@xparadigms.com"),
        }
        en = next((l for l in locs if l["attributes"]["locale"].startswith("en")), None)
        if en:
            call("PATCH", f"/v1/betaAppLocalizations/{en['id']}",
                 {"data": {"type": "betaAppLocalizations", "id": en["id"], "attributes": attrs}})
        else:
            call("POST", "/v1/betaAppLocalizations", {"data": {"type": "betaAppLocalizations",
                 "attributes": {"locale": "en-US", **attrs},
                 "relationships": {"app": {"data": {"type": "apps", "id": APP}}}}})
        print("beta description set")

    group = external_group()
    if not group:
        group = call("POST", "/v1/betaGroups", {"data": {"type": "betaGroups",
                     "attributes": {"name": GROUP},
                     "relationships": {"app": {"data": {"type": "apps", "id": APP}}}}})["data"]
        print("created external group", GROUP)

    # The tester: create them in the group, or add an existing one to it.
    found = call("GET", f"/v1/betaTesters?filter[email]={email}&filter[apps]={APP}")["data"]
    if found:
        call("POST", f"/v1/betaGroups/{group['id']}/relationships/betaTesters",
             {"data": [{"type": "betaTesters", "id": found[0]["id"]}]})
    else:
        call("POST", "/v1/betaTesters", {"data": {"type": "betaTesters",
             "attributes": {"email": email},
             "relationships": {"betaGroups": {"data": [{"type": "betaGroups", "id": group["id"]}]}}}})
    print("tester in group:", email)

    build = latest_build()
    call("POST", f"/v1/betaGroups/{group['id']}/relationships/builds",
         {"data": [{"type": "builds", "id": build["id"]}]})
    print("build in group:", build["attributes"]["version"])

    # What to Test, required for external builds.
    blocs = call("GET", f"/v1/builds/{build['id']}/betaBuildLocalizations")["data"]
    if not blocs:
        call("POST", "/v1/betaBuildLocalizations", {"data": {"type": "betaBuildLocalizations",
             "attributes": {"locale": "en-US", "whatsNew": "Read the newsletters, stories, Explore and your profile."},
             "relationships": {"build": {"data": {"type": "builds", "id": build["id"]}}}}})

    subs = call("GET", f"/v1/betaAppReviewSubmissions?filter[build]={build['id']}")["data"]
    if not subs:
        call("POST", "/v1/betaAppReviewSubmissions", {"data": {"type": "betaAppReviewSubmissions",
             "relationships": {"build": {"data": {"type": "builds", "id": build["id"]}}}}})
        print("submitted for Beta App Review")
    else:
        print("review state:", subs[0]["attributes"].get("betaReviewState"))
    status()


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "add":
        add(sys.argv[2])
    else:
        status()
