"use client";

import { useState } from "react";
import useSWR from "swr";
import GeneratorForm from "@/components/GeneratorForm";
import LiveCampaignCard from "@/components/LiveCampaignCard";
import EmptyState from "@/components/EmptyState";
import { listCampaigns, type Campaign } from "@/lib/api";

const TERMINAL = new Set(["completed", "failed"]);

// Filter out old/stale campaigns (older than 30 minutes with non-terminal status)
function isStale(campaign: Campaign): boolean {
  if (TERMINAL.has(campaign.status)) return false; // completed/failed are fine
  const created = new Date(campaign.created_at);
  const now = new Date();
  const diffMs = now.getTime() - created.getTime();
  const diffMins = diffMs / (1000 * 60);
  // If processing for more than 30 mins, consider it stale
  return diffMins > 30;
}

/** The Generate view: editorial hero on top, asymmetric two-column
 *  body (form on the left, "Live" panel on the right).
 */
export default function Home() {
  const [refreshKey, setRefreshKey] = useState(0);
  const { data, error } = useSWR<Campaign[]>(
    ["campaigns", refreshKey],
    () => listCampaigns(),
    { refreshInterval: 2000 },
  );

  const campaigns = data ?? [];
  // Only show non-terminal and non-stale campaigns in the Live panel.
  const live = campaigns.filter((c) => !TERMINAL.has(c.status) && !isStale(c));

  return (
    <div className="mx-auto max-w-7xl px-6 pt-16 pb-24">
      {/* Editorial hero */}
      <section
        className="stagger mb-20 max-w-4xl"
        style={
          {
            // assign indices to children for staggered animation
            // (we use --i on each child in markup)
          } as React.CSSProperties
        }
      >
        <div
          className="flex items-center gap-3 font-mono text-[10px] uppercase tracking-[0.2em] text-dim"
          style={{ ["--i" as any]: 0 }}
        >
          <span className="text-brand">●</span>
          <span>Reel · MVP</span>
          <span className="h-px flex-1 bg-[var(--border)]" />
        </div>
        <h1
          className="mt-6 font-display text-[clamp(48px,7vw,96px)] leading-[0.95] tracking-tight"
          style={{ ["--i" as any]: 1 }}
        >
          From a topic,{" "}
          <span className="italic text-[var(--text-muted)]">a vertical short.</span>
        </h1>
        <p
          className="mt-5 max-w-xl text-[var(--text-muted)] text-base leading-relaxed"
          style={{ ["--i" as any]: 2 }}
        >
          Write a headline. The system drafts a script with Gemini, finds vertical
          stock on Pexels, voices it with edge-tts, and stitches a 9:16 MP4 — locally,
          in a few minutes.
        </p>
      </section>

      {/* Asymmetric two-column body */}
      <section className="grid grid-cols-1 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] gap-10 lg:gap-16">
        {/* Form */}
        <div
          className="card p-8 md:p-10 self-start fade-in"
          style={{ animationDelay: "120ms" }}
        >
          <GeneratorForm onCreated={() => setRefreshKey((k) => k + 1)} />
        </div>

        {/* Live panel */}
        <div className="space-y-5">
          <div
            className="flex items-baseline justify-between fade-in"
            style={{ animationDelay: "200ms" }}
          >
            <div>
              <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-dim">
                Live
              </p>
              <h2 className="mt-1 font-display text-2xl">
                {live.length === 0
                  ? "Nothing rendering."
                  : `${live.length} in progress`}
              </h2>
            </div>
            <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-dim hidden md:block">
              polling every 2s
            </p>
          </div>

          {error && (
            <div className="card p-6 text-sm text-[var(--danger)]">
              Failed to reach the backend. Is FastAPI running on port 8000?
            </div>
          )}

          {live.length === 0 && !error ? (
            <EmptyState
              title="Nothing rendering, yet."
              hint="Submit a topic on the left and it'll appear here while the worker stitches it together."
            />
          ) : (
            <div className="space-y-3">
              {live.map((c) => (
                <LiveCampaignCard key={c.id} initial={c} />
              ))}
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
