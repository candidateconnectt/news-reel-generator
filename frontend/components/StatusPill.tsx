import type { CampaignStatus } from "@/lib/types";

type Variant = "default" | "solid" | "ghost";

const STYLES: Record<CampaignStatus, { dot: string; text: string; label: string }> = {
  pending:        { dot: "bg-idle",    text: "text-muted",  label: "Queued" },
  processing:     { dot: "bg-info",    text: "text-info",   label: "Processing" },
  ready_to_render:{ dot: "bg-info",    text: "text-info",   label: "Ready" },
  rendering:      { dot: "bg-warning", text: "text-warning",label: "Rendering" },
  completed:      { dot: "bg-success", text: "text-success",label: "Completed" },
  failed:         { dot: "bg-danger",  text: "text-danger", label: "Failed" },
};

export default function StatusPill({
  status,
  variant = "default",
  pulse = false,
}: {
  status: string;
  variant?: Variant;
  pulse?: boolean;
}) {
  const s = STYLES[status as CampaignStatus] ?? STYLES.pending;
  const isLive = status === "rendering" || status === "processing" || pulse;

  const inner = (
    <>
      <span className={`status-dot ${s.dot} ${isLive ? "ambient-pulse" : ""}`} />
      <span className="font-mono text-[10px] uppercase tracking-[0.16em]">{s.label}</span>
    </>
  );

  if (variant === "solid") {
    return (
      <span className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full border border-[var(--border)] bg-[var(--bg-elevated)]">
        {inner}
      </span>
    );
  }
  if (variant === "ghost") {
    return <span className={`inline-flex items-center gap-2 ${s.text}`}>{inner}</span>;
  }
  return (
    <span className={`inline-flex items-center gap-2 ${s.text}`}>{inner}</span>
  );
}
