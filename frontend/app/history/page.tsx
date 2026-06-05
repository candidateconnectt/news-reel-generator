"use client";

import { useState, useMemo } from "react";
import useSWR from "swr";
import { listCampaigns, type Campaign } from "@/lib/api";
import HistoryCard from "@/components/HistoryCard";
import EmptyState from "@/components/EmptyState";
import Link from "next/link";

type Range = "all" | "today" | "week";

function inRange(iso: string, r: Range): boolean {
  if (r === "all") return true;
  const t = new Date(iso).getTime();
  const now = Date.now();
  if (r === "today") {
    const start = new Date(); start.setHours(0, 0, 0, 0);
    return t >= start.getTime();
  }
  if (r === "week") return t >= now - 7 * 24 * 60 * 60 * 1000;
  return true;
}

export default function HistoryPage() {
  const { data, error } = useSWR<Campaign[]>(
    "history-campaigns",
    () => listCampaigns(),
    { refreshInterval: 5000 },
  );
  const [range, setRange] = useState<Range>("all");
  const [query, setQuery] = useState("");

  // CRITICAL: history = only completed reels (per user requirement).
  const completed = useMemo(() => {
    const all = (data ?? []).filter((c) => c.status === "completed");
    const inWindow = all.filter((c) => inRange(c.created_at, range));
    if (!query.trim()) return inWindow;
    const q = query.toLowerCase();
    return inWindow.filter(
      (c) =>
        (c.title ?? "").toLowerCase().includes(q) ||
        c.topic.toLowerCase().includes(q),
    );
  }, [data, range, query]);

  return (
    <div className="mx-auto max-w-7xl px-6 pt-16 pb-24">
      {/* Header */}
      <header
        className="stagger flex flex-col gap-6 md:flex-row md:items-end md:justify-between mb-12"
      >
        <div style={{ ["--i" as any]: 0 }}>
          <div className="flex items-center gap-3 font-mono text-[10px] uppercase tracking-[0.2em] text-dim">
            <span className="text-brand">●</span>
            <span>Archive</span>
            <span className="h-px w-12 bg-[var(--border)]" />
          </div>
          <h1
            className="mt-4 font-display text-[clamp(40px,6vw,72px)] leading-[0.95] tracking-tight"
            style={{ ["--i" as any]: 1 }}
          >
            Past reels.
          </h1>
          <p
            className="mt-3 text-[var(--text-muted)] max-w-md"
            style={{ ["--i" as any]: 2 }}
          >
            Only successfully generated reels appear here. Click any tile to
            open the player and inspect the metadata.
          </p>
        </div>

        <div
          className="flex items-center gap-3 fade-in"
          style={{ animationDelay: "260ms" }}
        >
          <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-dim">
            {completed.length} reel{completed.length === 1 ? "" : "s"}
          </span>
        </div>
      </header>

      {/* Controls */}
      <div
        className="flex flex-col sm:flex-row gap-3 mb-8 fade-in"
        style={{ animationDelay: "320ms" }}
      >
        <div className="relative flex-1">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search by title or topic…"
            className="w-full bg-[var(--bg-surface)] border border-[var(--border)] rounded-lg pl-10 pr-3 py-2.5 text-sm placeholder:text-dim focus:border-[var(--border-strong)] transition-colors"
          />
          <svg
            width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor"
            strokeWidth="1.5"
            className="absolute left-3.5 top-1/2 -translate-y-1/2 text-dim"
          >
            <circle cx="6" cy="6" r="4" />
            <path d="M9 9L12 12" />
          </svg>
        </div>
        <div className="flex gap-2">
          {(["all", "today", "week"] as Range[]).map((r) => (
            <button
              key={r}
              onClick={() => setRange(r)}
              aria-pressed={range === r}
              className="chip"
            >
              {r === "all" ? "All time" : r === "today" ? "Today" : "This week"}
            </button>
          ))}
        </div>
      </div>

      {/* Grid */}
      {error ? (
        <div className="card p-8 text-sm text-[var(--danger)]">
          Could not load history. Is the backend running?
        </div>
      ) : !data ? (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-5">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="reel-card animate-pulse" />
          ))}
        </div>
      ) : completed.length === 0 ? (
        <EmptyState
          title="No reels yet."
          hint={
            data.length > 0
              ? `You have ${data.length} campaign${data.length === 1 ? "" : "s"} in the system, but none have completed yet. Once a render finishes, it'll show up here.`
              : "Once you generate a reel, it'll show up here."
          }
          cta={
            <Link href="/" className="btn-primary btn-brand group">
              <span>Make a reel</span>
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none" className="transition-transform group-hover:translate-x-0.5" stroke="currentColor" strokeWidth="1.6">
                <path d="M2 7H12M8 3L12 7L8 11" />
              </svg>
            </Link>
          }
        />
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-5 stagger">
          {completed.map((c, i) => (
            <div key={c.id} style={{ ["--i" as any]: i }}>
              <HistoryCard campaign={c} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
