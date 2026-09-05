"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export default function EnterForm({ next }: { next: string }) {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/auth", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });
      if (!res.ok) {
        const data = (await res.json()) as { error?: string };
        setError(data.error ?? "Failed.");
        setBusy(false);
        return;
      }
      // replace(), not push(): the login screen should not sit in history
      // waiting for a back gesture to land on it.
      router.replace(next || "/");
      router.refresh();
    } catch {
      setError("Could not reach the server.");
      setBusy(false);
    }
  }

  return (
    <form className="enter" onSubmit={submit}>
      <label className="enter__label" htmlFor="password">
        Password
      </label>
      <input
        id="password"
        className="enter__input"
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        autoComplete="current-password"
        autoFocus
        enterKeyHint="go"
      />
      <button className="enter__button" type="submit" disabled={busy || !password}>
        {busy ? "…" : "Enter"}
      </button>
      {error && <p className="enter__error">{error}</p>}
    </form>
  );
}
