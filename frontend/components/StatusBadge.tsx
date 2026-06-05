import type { CampaignStatus } from "@/lib/types";

const COLORS: Record<CampaignStatus, string> = {
  pending: "bg-zinc-700 text-zinc-200",
  processing: "bg-blue-900 text-blue-200",
  ready_to_render: "bg-purple-900 text-purple-200",
  rendering: "bg-amber-900 text-amber-200",
  completed: "bg-emerald-900 text-emerald-200",
  failed: "bg-red-900 text-red-200",
};

export default function StatusBadge({ status }: { status: string }) {
  const color = COLORS[status as CampaignStatus] ?? COLORS.pending;
  return (
    <span className={`text-xs font-medium px-2 py-0.5 rounded ${color}`}>
      {status}
    </span>
  );
}
