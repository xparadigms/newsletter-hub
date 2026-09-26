"use client";

import { useState } from "react";

// Stocks only: name a company and get one article on it, in the same format as
// the daily three. The route counts it against the same daily cap as
// "Generate a new issue", since it costs about as much as one.

type State = { kind: "idle" | "busy" | "done" | "error"; message?: string };

export default function CompanyRequest() {
  const [company, setCompany] = useState("");
  const [state, setState] = useState<State>({ kind: "idle" });

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const name = company.trim();
    if (!name) return;
    setState({ kind: "busy" });
    try {
      const res = await fetch("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ section: "stocks", company: name }),
      });
      const data = (await res.json()) as {
        error?: string;
        message?: string;
        remaining?: number;
      };
      if (!res.ok) {
        setState({ kind: "error", message: data.error ?? "Failed." });
        return;
      }
      setCompany("");
      setState({
        kind: "done",
        message:
          data.remaining === undefined
            ? data.message
            : `${data.message} ${data.remaining} left today.`,
      });
    } catch {
      setState({ kind: "error", message: "Could not reach the server." });
    }
  }

  return (
    <form className="company-request" onSubmit={submit}>
      <label className="label company-request__label" htmlFor="company-request">
        Write about a company
      </label>
      <div className="company-request__row">
        <input
          id="company-request"
          className="enter__input company-request__input"
          value={company}
          onChange={(e) => {
            setCompany(e.target.value);
            if (state.kind !== "busy") setState({ kind: "idle" });
          }}
          placeholder="Ticker or name, e.g. NVDA or Toyota"
          maxLength={60}
          autoComplete="off"
          autoCapitalize="characters"
          spellCheck={false}
          enterKeyHint="go"
        />
        <button
          type="submit"
          className="generate__button"
          disabled={state.kind === "busy" || !company.trim()}
        >
          {state.kind === "busy" ? "Starting…" : "Write"}
        </button>
      </div>
      {state.message && (
        <p className="generate__note" data-error={state.kind === "error"}>
          {state.message}
        </p>
      )}
    </form>
  );
}
