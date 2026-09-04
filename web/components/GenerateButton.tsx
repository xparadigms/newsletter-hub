"use client";

import { useState } from "react";
import type { SectionKey } from "@/lib/types";

// "Generate" on a section page: make one more issue of this newsletter today,
// covering stories the last three issues did not.
//
// The password is remembered so the second press does not ask again, but it is
// only ever checked on the server — nothing here decides whether the run is
// allowed, and a wrong password comes back as a 401 from the API.

const KEY = "generate-password";

type State = { kind: "idle" | "busy" | "done" | "error"; message?: string };

export default function GenerateButton({ section }: { section: SectionKey }) {
  const [state, setState] = useState<State>({ kind: "idle" });

  async function run() {
    let password = "";
    try {
      password = window.localStorage.getItem(KEY) ?? "";
    } catch {
      // Private mode, or storage blocked. Ask every time instead.
    }
    if (!password) {
      password = window.prompt("Password") ?? "";
      if (!password) return;
    }

    setState({ kind: "busy" });
    try {
      const res = await fetch("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ section, password }),
      });
      const data = (await res.json()) as {
        error?: string;
        message?: string;
        remaining?: number;
      };

      if (!res.ok) {
        // A rejected password must not be remembered, or the button becomes
        // permanently broken with no way to retype it.
        if (res.status === 401) {
          try {
            window.localStorage.removeItem(KEY);
          } catch {}
        }
        setState({ kind: "error", message: data.error ?? "Failed." });
        return;
      }

      try {
        window.localStorage.setItem(KEY, password);
      } catch {}
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
