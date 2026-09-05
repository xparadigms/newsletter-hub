"use client";

import { useState } from "react";
import type { SectionKey } from "@/lib/types";

// "Generate" on a section page: make one more issue of this newsletter today,
// covering stories the last three issues did not.
//
// No password prompt here — the site asks once at the door and carries an
// httpOnly cookie, which the browser attaches to this request on its own.
// Nothing in this file decides whether the run is allowed.

type State = { kind: "idle" | "busy" | "done" | "error"; message?: string };

export default function GenerateButton({ section }: { section: SectionKey }) {
  const [state, setState] = useState<State>({ kind: "idle" });

  async function run() {
    setState({ kind: "busy" });
    try {
      const res = await fetch("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ section }),
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
    <div className="generate">
      <button
        type="button"
        className="generate__button"
        onClick={run}
        disabled={state.kind === "busy" || state.kind === "done"}
      >
        {state.kind === "busy"
          ? "Generating…"
          : state.kind === "done"
            ? "Started"
            : "Generate a new issue"}
      </button>
      {state.message && (
        <p className="generate__note" data-error={state.kind === "error"}>
          {state.message}
        </p>
      )}
    </div>
  );
}
