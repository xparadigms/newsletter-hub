"""One call, either vendor, and a printed price for every one of them.

The generators used to call anthropic.Anthropic directly. Two of them now run on
OpenAI, and rather than let each file grow its own client and its own idea of
what a response looks like, they all go through complete() and get back the same
pair: the text, and what it cost.

The cost line is the point as much as the routing is. A model swap is a pricing
decision, and the only honest way to talk about one is to measure the tokens the
issues actually use rather than estimate from character counts — reasoning
tokens in particular are invisible in the output and billed as output.

OpenAI goes over plain requests rather than the SDK, for the reason store.py
does: one HTTP call does not justify another dependency tree.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from typing import Any, NamedTuple

import anthropic

from . import http

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"

# USD per million tokens, from the vendors' own pricing pages, read 2026-09-10:
# platform.claude.com/docs/en/docs/about-claude/pricing and
# developers.openai.com/api/docs/pricing. Wrong numbers here produce confident
# wrong cost lines, so check the pages rather than adjusting from memory.
PRICES: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-sonnet-5": (2.00, 10.00),
    "gpt-6-astra": (10.00, 50.00),
    "gpt-5.5": (5.00, 30.00),
}


class Usage(NamedTuple):
    model: str
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int = 0

    # True when the call ran on the Claude subscription through Claude Code,
    # which bills nothing per token.
    subscription: bool = False

    @property
    def cost(self) -> float | None:
        if self.subscription:
            return 0.0
        price = PRICES.get(self.model)
        if not price:
            return None
        # Reasoning tokens are already inside output_tokens on both vendors;
        # they are tracked separately only so the log can show where the spend
        # went when an issue costs more than its visible length suggests.
        return (
            self.input_tokens * price[0] + self.output_tokens * price[1]
        ) / 1_000_000

    def line(self, label: str = "") -> str:
        bits = [
            f"{self.input_tokens:,} in",
            f"{self.output_tokens:,} out",
        ]
        if self.reasoning_tokens:
            bits.append(f"{self.reasoning_tokens:,} reasoning")
        cost = self.cost
        money = (
            "subscription"
            if self.subscription
            else f"${cost:.4f}" if cost is not None else "unpriced model"
        )
        where = f" {label}" if label else ""
        return f"  llm{where}: {self.model} — {', '.join(bits)} = {money}"


def _openai(model: str, system: str, user: str, max_tokens: int) -> tuple[str, Usage]:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    resp = http.request_with_retry(
        "POST",
        OPENAI_RESPONSES_URL,
        label="OpenAI",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "instructions": system,
            "input": user,
            # Reasoning tokens count against this budget as well as against the
            # bill, so a limit sized to the visible output alone truncates the
            # issue with status "incomplete" and no error.
            "max_output_tokens": max_tokens,
        },
        timeout=600,
    )
    resp.raise_for_status()
    data: dict[str, Any] = resp.json()

    text = "".join(
        c.get("text", "")
        for item in data.get("output", [])
        if item.get("type") == "message"
        for c in item.get("content", [])
    ).strip()

    u = data.get("usage") or {}
    usage = Usage(
        model=model,
        input_tokens=u.get("input_tokens", 0),
        output_tokens=u.get("output_tokens", 0),
        reasoning_tokens=(u.get("output_tokens_details") or {}).get("reasoning_tokens", 0),
    )

    if data.get("status") == "incomplete":
        reason = (data.get("incomplete_details") or {}).get("reason", "unknown")
        print(f"  ⚠ OpenAI stopped early ({reason}) — the issue may be cut short")
    if not text:
        raise RuntimeError(f"OpenAI returned no text (status {data.get('status')!r})")
    return text, usage


def _anthropic(model: str, system: str, user: str, max_tokens: int) -> tuple[str, Usage]:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    client = anthropic.Anthropic(api_key=key)
    # Streamed, not create(). The SDK refuses a non-streaming request whose
    # max_tokens implies a generation that could run past ten minutes, and a
    # full trilingual issue is exactly that size. get_final_message() collects
    # the stream, so callers still get one string and one usage record.
    with client.messages.stream(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    ) as stream:
        final = stream.get_final_message()
    return final.content[0].text, Usage(
        model=model,
        input_tokens=final.usage.input_tokens,
        output_tokens=final.usage.output_tokens,
    )


class ClaudeCodeError(RuntimeError):
    """Claude Code did not return a usable answer: rate limited, logged out,
    missing, or timed out. The caller falls back to the API."""


def _child_env() -> dict[str, str]:
    """The environment for a Claude Code subprocess.

    Without ANTHROPIC_API_KEY: with it set, Claude Code bills the API key and
    ignores the subscription, which would defeat the point while looking like
    it worked.

    With thinking off: Claude Code thinks by default, and the API calls these
    replace never did. On a full issue it thought for over 15 minutes before
    writing, so the first run on the subscription timed out; the same request
    without thinking took under a minute.
    """
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    env["MAX_THINKING_TOKENS"] = "0"
    return env


def _claude_code(model: str, system: str, user: str, max_tokens: int) -> tuple[str, Usage]:
    """One completion through the Claude Code CLI, billed to the subscription.

    Enabled per workflow by giving it a CLAUDE_CODE_OAUTH_TOKEN secret (made
    with `claude setup-token`). Claude Code is made to behave like a bare
    completion: no tools, the caller's system prompt instead of its own, and an
    empty working directory so no CLAUDE.md is picked up. Not --bare, which
    would refuse the OAuth token.

    The child's environment comes from _child_env().
    """
    exe = shutil.which("claude")
    if not exe:
        raise ClaudeCodeError("the claude CLI is not installed")

    env = _child_env()
    env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] = str(max_tokens)
    with tempfile.TemporaryDirectory() as cwd:
        system_file = os.path.join(cwd, "system.txt")
        with open(system_file, "w", encoding="utf-8") as f:
            f.write(system)
        try:
            proc = subprocess.run(
                [
                    exe, "-p",
                    "--model", model,
                    "--output-format", "json",
                    "--system-prompt-file", system_file,
                    "--tools", "",
                    "--max-turns", "1",
                    "--no-session-persistence",
                    # A developer machine's own settings (model, hooks) must
                    # not leak into a newsletter call.
                    "--setting-sources", "project",
                ],
                input=user,
                capture_output=True,
                text=True,
                cwd=cwd,
                env=env,
                timeout=900,
            )
        except subprocess.TimeoutExpired as e:
            raise ClaudeCodeError("timed out after 15 minutes") from e

    try:
        out = json.loads(proc.stdout)
    except ValueError:
        detail = (proc.stderr or proc.stdout).strip()[-400:]
        raise ClaudeCodeError(f"exit {proc.returncode}: {detail}") from None
    if proc.returncode != 0 or out.get("is_error") or not out.get("result"):
        raise ClaudeCodeError(f"exit {proc.returncode}: {str(out.get('result'))[:400]}")

    usage = out.get("usage") or {}
    return out["result"], Usage(
        model=model,
        input_tokens=(usage.get("input_tokens") or 0)
        + (usage.get("cache_read_input_tokens") or 0)
        + (usage.get("cache_creation_input_tokens") or 0),
        output_tokens=usage.get("output_tokens") or 0,
        subscription=True,
    )


_URL = re.compile(r"https?://[^\s\"'<>\\\]\)]+")


def claude_code_search(
    model: str, system: str, user: str, *, max_turns: int = 25, timeout: int = 1500
) -> tuple[str, set[str], Usage]:
    """A research session through Claude Code with web search, on the
    subscription. Returns (final text, every URL the searches returned, usage).

    The URLs are what source links are verified against, the same role the
    API's web_search_tool_result blocks play. They come from the stream-json
    transcript, since the plain json output keeps only the final answer.

    Sonnet 4.6 cannot be used here: through Claude Code on a subscription, its
    second turn is refused with "Usage credits required for 1M context", even
    with CLAUDE_CODE_DISABLE_1M_CONTEXT set. Sonnet 5 and Opus 5.5 work.
    Raises ClaudeCodeError on any failure so the caller can fall back to the API.
    """
    exe = shutil.which("claude")
    if not exe:
        raise ClaudeCodeError("the claude CLI is not installed")
    env = _child_env()
    with tempfile.TemporaryDirectory() as cwd:
        system_file = os.path.join(cwd, "system.txt")
        with open(system_file, "w", encoding="utf-8") as f:
            f.write(system)
        try:
            proc = subprocess.run(
                [
                    exe, "-p",
                    "--model", model,
                    "--output-format", "stream-json", "--verbose",
                    "--system-prompt-file", system_file,
                    "--tools", "WebSearch",
                    "--allowedTools", "WebSearch",
                    "--max-turns", str(max_turns),
                    "--no-session-persistence",
                    "--setting-sources", "project",
                ],
                input=user,
                capture_output=True,
                text=True,
                cwd=cwd,
                env=env,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as e:
            raise ClaudeCodeError(f"timed out after {timeout}s") from e

    urls: set[str] = set()
    result: dict[str, Any] | None = None
    for line in proc.stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") == "assistant":
            for block in event.get("message", {}).get("content", []):
                if block.get("type") == "tool_use":
                    print(f"    search: {block.get('input', {}).get('query', block.get('input'))}")
        elif event.get("type") == "user" and event.get("tool_use_result"):
            urls.update(_URL.findall(json.dumps(event["tool_use_result"], ensure_ascii=False)))
        elif event.get("type") == "result":
            result = event
    if not result or result.get("is_error") or not result.get("result"):
        detail = (result or {}).get("result") or proc.stderr.strip()[-400:]
        raise ClaudeCodeError(f"exit {proc.returncode}: {str(detail)[:400]}")

    usage = result.get("usage") or {}
    return result["result"], urls, Usage(
        model=model,
        input_tokens=(usage.get("input_tokens") or 0)
        + (usage.get("cache_read_input_tokens") or 0)
        + (usage.get("cache_creation_input_tokens") or 0),
        output_tokens=usage.get("output_tokens") or 0,
        subscription=True,
    )


def complete(
    *,
    model: str,
    system: str,
    user: str,
    max_tokens: int,
    label: str = "",
) -> str:
    """Text from whichever vendor owns `model`, with the cost printed.

    Claude models go through the subscription first when the workflow provides
    CLAUDE_CODE_OAUTH_TOKEN, and fall back to the API key if that fails — a
    usage limit reached at 07:00 must not cost the morning its issue.
    """
    if model.startswith("gpt-"):
        text, usage = _openai(model, system, user, max_tokens)
    elif os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
        try:
            text, usage = _claude_code(model, system, user, max_tokens)
        except ClaudeCodeError as e:
            print(f"  ⚠ subscription call failed, using the API key instead: {e}")
            text, usage = _anthropic(model, system, user, max_tokens)
    else:
        text, usage = _anthropic(model, system, user, max_tokens)
    print(usage.line(label))
    return text
