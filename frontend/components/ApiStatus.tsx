"use client";

import { useEffect, useState } from "react";

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

type Status = "checking" | "online" | "offline";

/** Tiny live-updating dot showing whether the FastAPI backend is reachable.
 *  Polls /health every 10s, no UI disruption.
 */
export function ApiStatus() {
  const [status, setStatus] = useState<Status>("checking");

  useEffect(() => {
    let cancelled = false;
    async function check() {
      try {
        const r = await fetch(`${BASE}/health`, { cache: "no-store" });
        if (!cancelled) setStatus(r.ok ? "online" : "offline");
      } catch {
        if (!cancelled) setStatus("offline");
      }
    }
    check();
    const id = setInterval(check, 10_000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  const color =
    status === "online" ? "bg-success" : status === "offline" ? "bg-danger" : "bg-idle";
  const label =
    status === "online" ? "Backend online" : status === "offline" ? "Backend offline" : "Checking…";

  return (
    <div
      className="hidden md:flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.18em]"
      title={label}
    >
      <span
        className={`status-dot ${color} ${
          status === "online" ? "ambient-pulse" : ""
        }`}
      />
      <span className="text-dim">{label}</span>
    </div>
  );
}
