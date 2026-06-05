"use client";

import { useState } from "react";
import useSWR from "swr";
import type { Campaign } from "@/lib/api";
import { getCampaign } from "@/lib/api";
import StatusPill from "./StatusPill";
import VideoPlayer from "./VideoPlayer";
import VideoLightbox from "./VideoLightbox";

/** A card for one campaign in the "Live" panel. Polls every 2s while
 *  the status is non-terminal; stops polling once completed/failed.
 */
export default function LiveCampaignCard({ initial }: { initial: Campaign }) {
  const isTerminal =
    initial.status === "completed" || initial.status === "failed";
  const { data } = useSWR(
    ["campaign", initial.id],
    () => getCampaign(initial.id),
    {
      refreshInterval: isTerminal ? 0 : 2000,
      fallbackData: initial,
    },
  );
  const campaign = data ?? initial;
  const [lightbox, setLightbox] = useState(false);

  return (
    <>
      <article className="card overflow-hidden">
        <div className="grid grid-cols-[1fr_auto] gap-5 p-5">
          <div className="min-w-0">
            <div className="flex items-center gap-3">
              <StatusPill status={campaign.status} variant="solid" pulse />
              <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-dim">
                {new Date(campaign.created_at).toLocaleTimeString([], {
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </span>
            </div>
            <h3 className="mt-3 font-display text-xl leading-snug truncate">
              {campaign.title || campaign.topic}
            </h3>
            <p className="mt-1 text-sm text-muted truncate">{campaign.topic}</p>
            {campaign.error_message && (
              <p className="mt-2 text-xs text-[var(--danger)] break-words font-mono">
                {campaign.error_message}
              </p>
            )}
          </div>

          {campaign.status === "completed" && campaign.video_url && (
            <button
              onClick={() => setLightbox(true)}
              className="reel-card w-28 self-stretch card-interactive"
              aria-label="Open reel preview"
            >
              <video
                src={campaign.video_url}
                muted
                playsInline
                preload="metadata"
                className="w-full h-full object-cover"
              />
              <div className="play-overlay">
                <div className="h-9 w-9 rounded-full bg-white/95 grid place-items-center">
                  <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor" className="text-black translate-x-0.5">
                    <path d="M2 1L11 6L2 11V1Z" />
                  </svg>
                </div>
              </div>
            </button>
          )}
        </div>

        {campaign.status !== "completed" && campaign.status !== "failed" && (
          <div className="h-px bg-gradient-to-r from-transparent via-[var(--brand)]/30 to-transparent" />
        )}
      </article>

      {lightbox && (
        <VideoLightbox campaign={campaign} onClose={() => setLightbox(false)} />
      )}
    </>
  );
}
