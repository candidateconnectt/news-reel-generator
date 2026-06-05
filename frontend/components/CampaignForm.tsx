"use client";

import { useState } from "react";
import { createCampaign } from "@/lib/api";

const VOICES = [
  { id: "en-US-GuyNeural", label: "Guy (en-US)" },
  { id: "en-US-JennyNeural", label: "Jenny (en-US)" },
  { id: "en-GB-RyanNeural", label: "Ryan (en-GB)" },
  { id: "en-IN-PrabhatNeural", label: "Prabhat (en-IN)" },
];

export default function CampaignForm({ onCreated }: { onCreated: () => void }) {
  const [topic, setTopic] = useState("");
  const [voice, setVoice] = useState(VOICES[0].id);
  const [sceneCount, setSceneCount] = useState(5);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!topic.trim()) return;
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
    <form onSubmit={handleSubmit} className="space-y-4 p-4 bg-zinc-900 rounded-lg border border-zinc-800">
      <div>
        <label className="block text-sm font-medium mb-1">Topic</label>
        <input
          className="w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-brand"
          placeholder="e.g. AI news this week, SpaceX Starship, OpenAI release"
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          maxLength={500}
        />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium mb-1">Voice</label>
          <select
            className="w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-2"
            value={voice}
            onChange={(e) => setVoice(e.target.value)}
          >
            {VOICES.map((v) => (
              <option key={v.id} value={v.id}>
                {v.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">Scenes</label>
          <input
            type="number"
            min={1}
            max={20}
            className="w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-2"
            value={sceneCount}
            onChange={(e) => setSceneCount(parseInt(e.target.value, 10) || 5)}
          />
        </div>
      </div>
      {error && <p className="text-red-400 text-sm">{error}</p>}
      <button
        type="submit"
        disabled={submitting || !topic.trim()}
        className="bg-brand hover:bg-brand-dark disabled:opacity-50 disabled:cursor-not-allowed px-4 py-2 rounded font-medium"
      >
        {submitting ? "Creating…" : "Generate Reel"}
      </button>
    </form>
  );
}
