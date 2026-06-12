"use client";

import { useState } from "react";
import type { Campaign } from "@/lib/api";
import VideoLightbox from "./VideoLightbox";

export default function HistoryCard({ campaign }: { campaign: Campaign }) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="card card-interactive group text-left w-full overflow-hidden"
        aria-label={`Open reel: ${campaign.title || campaign.topic}`}
      >
        <div className="reel-card">
          {campaign.video_url ? (
            <video
              src={campaign.video_url}
              muted
              playsInline
              preload="metadata"
            />
          ) : (
            <div className="grid place-items-center h-full text-dim font-mono text-xs">
              no video
            </div>
          )}
          <div className="play-overlay">
            <div className="h-11 w-11 rounded-full bg-white/95 grid place-items-center shadow-lg">
              <svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor" className="text-black translate-x-0.5">
                <path d="M2 1L13 7L2 13V1Z" />
              </svg>
            </div>
          </div>
        </div>
        <div className="p-4">
          <p className="font-display text-base leading-snug line-clamp-2">
            {campaign.title || campaign.topic}
          </p>
          <div className="mt-2 flex items-center justify-between text-[10px] font-mono uppercase tracking-[0.16em] text-dim">
            <span>
              {new Date(campaign.created_at).toLocaleDateString(undefined, {
                month: "short",
                day: "numeric",
              })}
            </span>
            <span className="text-[var(--text-dim)]">
              {campaign.scene_count} sc · {campaign.aspect_ratio}
            </span>
          </div>
        </div>
      </button>

      {open && (
        <VideoLightbox campaign={campaign} onClose={() => setOpen(false)} />
      )}
    </>
  );
}
