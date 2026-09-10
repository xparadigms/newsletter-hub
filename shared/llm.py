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

import os
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

    @property
    def cost(self) -> float | None:
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
        money = f"${cost:.4f}" if cost is not None else "unpriced model"
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


def complete(
    *,
    model: str,
    system: str,
    user: str,
    max_tokens: int,
    label: str = "",
) -> str:
    """Text from whichever vendor owns `model`, with the cost printed."""
    fn = _openai if model.startswith("gpt-") else _anthropic
    text, usage = fn(model, system, user, max_tokens)
    print(usage.line(label))
    return text
