"use client";

import { useState } from "react";
import { createCampaign } from "@/lib/api";

const VOICES = [
  { id: "en-US-GuyNeural",   label: "Guy",     desc: "US · male" },
  { id: "en-US-JennyNeural", label: "Jenny",   desc: "US · female" },
  { id: "en-GB-RyanNeural",  label: "Ryan",    desc: "UK · male" },
  { id: "en-IN-PrabhatNeural", label: "Prabhat", desc: "IN · male" },
];

const SCENE_PRESETS = [2, 3, 4, 5];

export default function GeneratorForm({ onCreated }: { onCreated: () => void }) {
  const [topic, setTopic] = useState("");
  const [voice, setVoice] = useState(VOICES[0].id);
  const [sceneCount, setSceneCount] = useState(3);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!topic.trim() || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      await createCampaign({ topic: topic.trim(), voice, scene_count: sceneCount });
      setTopic("");
      onCreated();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-10">
      {/* Section eyebrow */}
      <div className="flex items-center gap-3 font-mono text-[10px] uppercase tracking-[0.2em] text-dim">
        <span className="text-brand">01</span>
        <span className="h-px flex-1 bg-[var(--border)]" />
        <span>Topic</span>
      </div>

      <div>
        <label htmlFor="topic" className="sr-only">Topic</label>
        <input
          id="topic"
          className="editorial-input"
          placeholder="A trend, a headline, a curiosity…"
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          maxLength={500}
          required
        />
        <div className="mt-2 flex items-center justify-between text-[11px] font-mono text-dim">
          <span>be specific. the model works best with named topics.</span>
          <span>{topic.length} / 500</span>
        </div>
      </div>

      {/* Voice */}
      <div className="space-y-3">
        <div className="flex items-center gap-3 font-mono text-[10px] uppercase tracking-[0.2em] text-dim">
          <span className="text-brand">02</span>
          <span className="h-px flex-1 bg-[var(--border)]" />
          <span>Voice</span>
        </div>
        <div className="flex flex-wrap gap-2">
          {VOICES.map((v) => (
            <button
              key={v.id}
              type="button"
              aria-pressed={voice === v.id}
              onClick={() => setVoice(v.id)}
              className="chip"
            >
              <span className="text-[var(--text)]">{v.label}</span>
              <span className="ml-2 text-dim normal-case tracking-normal">{v.desc}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Scenes */}
      <div className="space-y-3">
        <div className="flex items-center gap-3 font-mono text-[10px] uppercase tracking-[0.2em] text-dim">
          <span className="text-brand">03</span>
          <span className="h-px flex-1 bg-[var(--border)]" />
          <span>Scenes</span>
        </div>
        <div className="flex items-center gap-2">
          {SCENE_PRESETS.map((n) => (
            <button
              key={n}
              type="button"
              aria-pressed={sceneCount === n}
              onClick={() => setSceneCount(n)}
              className="chip min-w-[44px] text-center"
            >
              {n}
            </button>
          ))}
        </div>
        <p className="text-[11px] font-mono text-dim">
          2–3 short and punchy · 4–5 balanced · 6+ cinematic
        </p>
      </div>

      {error && (
        <div className="border border-[var(--danger)]/40 bg-[var(--danger)]/10 text-[var(--danger)] rounded-lg px-4 py-3 text-sm">
          {error}
        </div>
      )}

      <div className="flex items-center justify-between pt-2">
        <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-dim">
          est. render · 2–3 min
        </span>
        <button
          type="submit"
          disabled={submitting || !topic.trim()}
          className="btn-primary btn-brand group"
        >
          <span>{submitting ? "Submitting…" : "Generate reel"}</span>
          <svg
            width="14" height="14" viewBox="0 0 14 14" fill="none"
            className="transition-transform group-hover:translate-x-0.5"
            stroke="currentColor" strokeWidth="1.6"
          >
            <path d="M2 7H12M8 3L12 7L8 11" />
          </svg>
        </button>
      </div>
    </form>
  );
}
