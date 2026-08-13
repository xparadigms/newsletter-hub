"use client";

import { useEffect } from "react";

export default function ServiceWorker() {
  useEffect(() => {
    if (!("serviceWorker" in navigator)) return;

    // Native apps don't strand you on an old build; take new versions as soon
    // as they're ready and reload once the new worker takes control.
    let reloading = false;
    navigator.serviceWorker.addEventListener("controllerchange", () => {
      if (reloading) return;
      reloading = true;
      window.location.reload();
    });

    const activateWhenWaiting = (reg: ServiceWorkerRegistration) => {
      if (reg.waiting) reg.waiting.postMessage("skip-waiting");
      reg.addEventListener("updatefound", () => {
        const next = reg.installing;
        next?.addEventListener("statechange", () => {
          // Only when an old worker is being replaced, never on first install.
          if (next.state === "installed" && navigator.serviceWorker.controller) {
            next.postMessage("skip-waiting");
          }
        });
      });
    };

    const register = () =>
      navigator.serviceWorker
        .register("/sw.js")
        .then(activateWhenWaiting)
        .catch(() => {});
    // Registering after load keeps the worker off the critical path.
    if (document.readyState === "complete") register();
    else {
      window.addEventListener("load", register);
      return () => window.removeEventListener("load", register);
    }
  }, []);

  return null;
}
