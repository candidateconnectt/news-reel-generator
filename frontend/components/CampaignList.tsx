"use client";

import useSWR from "swr";
import { listCampaigns } from "@/lib/api";
import StatusBadge from "./StatusBadge";
import VideoPlayer from "./VideoPlayer";

export default function CampaignList({ refreshKey }: { refreshKey: number }) {
  // SWR polls every 3s so the dashboard reflects status changes live.
  const { data, error } = useSWR(
    ["campaigns", refreshKey],
    () => listCampaigns(),
    { refreshInterval: 3000 },
  );

  if (error) return <p className="text-red-400">Failed to load campaigns.</p>;
  if (!data) return <p className="text-zinc-400">Loading…</p>;
  if (data.length === 0)
    return (
      <p className="text-zinc-500 text-sm">
        No campaigns yet. Enter a topic above to generate your first reel.
      </p>
    );

  return (
    <div className="space-y-3">
      {data.map((c) => (
        <div
          key={c.id}
          className="p-4 bg-zinc-900 rounded-lg border border-zinc-800 flex gap-4 items-start"
        >
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <StatusBadge status={c.status} />
              <span className="text-zinc-500 text-xs">
                {new Date(c.created_at).toLocaleString()}
              </span>
            </div>
            <h3 className="font-medium mt-1 truncate">
              {c.title || c.topic}
            </h3>
            <p className="text-zinc-400 text-sm truncate">{c.topic}</p>
            {c.error_message && (
              <p className="text-red-400 text-xs mt-1 break-words">
                {c.error_message}
              </p>
            )}
          </div>
          {c.status === "completed" && c.video_url && (
            <div className="w-32 flex-shrink-0">
              <VideoPlayer src={c.video_url} />
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
