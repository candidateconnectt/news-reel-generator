"use client";

import { useEffect } from "react";
import type { Campaign } from "@/lib/api";
import StatusPill from "./StatusPill";

export default function VideoLightbox({
  campaign,
  onClose,
}: {
  campaign: Campaign | null;
  onClose: () => void;
}) {
  useEffect(() => {
    if (!campaign) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    // Lock body scroll while open
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [campaign, onClose]);

  if (!campaign) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center fade-in"
      role="dialog"
      aria-modal="true"
      aria-label="Reel preview"
    >
      <div
        className="absolute inset-0 bg-black/85 backdrop-blur-md"
        onClick={onClose}
      />
      <div className="relative z-10 flex w-full max-w-5xl items-center gap-8 px-6">
        {/* Video — vertical 9:16 */}
        <div className="relative mx-auto h-[80vh] aspect-[9/16] rounded-xl overflow-hidden border border-[var(--border)] bg-black shadow-2xl">
          {campaign.video_url ? (
            <video
              src={campaign.video_url}
              controls
              autoPlay
              playsInline
              className="w-full h-full object-cover"
            />
          ) : (
            <div className="grid place-items-center h-full text-[var(--text-dim)] font-mono text-xs">
              no video url
            </div>
          )}
        </div>

        {/* Side metadata — hidden on small screens */}
        <aside className="hidden lg:block w-72 shrink-0">
          <div className="flex items-center gap-3 mb-3">
            <StatusPill status={campaign.status} variant="solid" />
            <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-dim">
              {new Date(campaign.created_at).toLocaleString()}
            </span>
          </div>
          <h2 className="font-display text-3xl leading-tight">
            {campaign.title || campaign.topic}
          </h2>
          <p className="mt-3 text-sm text-muted">{campaign.topic}</p>

          <dl className="mt-8 space-y-3 font-mono text-[10px] uppercase tracking-[0.18em]">
            <div className="flex justify-between border-t border-[var(--border-subtle)] pt-3">
              <dt className="text-dim">Voice</dt>
              <dd>{campaign.voice}</dd>
            </div>
            <div className="flex justify-between border-t border-[var(--border-subtle)] pt-3">
              <dt className="text-dim">Scenes</dt>
              <dd>{campaign.scene_count}</dd>
            </div>
            <div className="flex justify-between border-t border-[var(--border-subtle)] pt-3">
              <dt className="text-dim">Aspect</dt>
              <dd>{campaign.aspect_ratio}</dd>
            </div>
            <div className="flex justify-between border-t border-[var(--border-subtle)] pt-3">
              <dt className="text-dim">ID</dt>
              <dd className="truncate ml-3">{campaign.id.slice(0, 8)}</dd>
            </div>
          </dl>
        </aside>

        {/* Close button */}
        <button
          onClick={onClose}
          aria-label="Close"
          className="absolute top-2 right-2 lg:top-4 lg:right-4 h-9 w-9 rounded-full border border-[var(--border)] bg-[var(--bg-elevated)]/80 grid place-items-center text-[var(--text-muted)] hover:text-[var(--text)] hover:border-[var(--border-strong)] transition-colors"
        >
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M2 2L12 12M12 2L2 12" />
          </svg>
        </button>
      </div>
    </div>
  );
}
