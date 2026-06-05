"use client";

import { useState } from "react";
import CampaignForm from "@/components/CampaignForm";
import CampaignList from "@/components/CampaignList";

export default function Home() {
  // Bump this to force the list to re-fetch after a new campaign is created.
  const [refreshKey, setRefreshKey] = useState(0);
  return (
    <main className="max-w-5xl mx-auto p-6 space-y-8">
      <header className="space-y-1">
        <h1 className="text-3xl font-bold tracking-tight">Autonomous News Reel Generator</h1>
        <p className="text-zinc-400">
          Topic → Gemini script → Pexels clips → edge-tts voiceover → stitched MP4
        </p>
      </header>
      <CampaignForm onCreated={() => setRefreshKey((k) => k + 1)} />
      <CampaignList refreshKey={refreshKey} />
    </main>
  );
}
