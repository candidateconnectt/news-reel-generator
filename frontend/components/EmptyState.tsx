type Props = {
  title: string;
  /** Italic second line — adds editorial texture */
  hint?: string;
  cta?: React.ReactNode;
};

export default function EmptyState({ title, hint, cta }: Props) {
  return (
    <div className="card p-10 md:p-14 text-center">
      <div className="mx-auto mb-6 h-14 w-14 rounded-full border border-[var(--border)] grid place-items-center">
        <span className="font-display italic text-2xl text-[var(--text-dim)]">Ø</span>
      </div>
      <p className="font-display text-3xl md:text-4xl text-[var(--text)] leading-tight">
        {title}
      </p>
      {hint && (
        <p className="mt-3 text-[var(--text-muted)] text-sm max-w-md mx-auto">
          {hint}
        </p>
      )}
      {cta && <div className="mt-6 flex justify-center">{cta}</div>}
    </div>
  );
}
