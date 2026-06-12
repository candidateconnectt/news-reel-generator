"use client";

import { useState } from "react";
import Link from "next/link";
import Nav from "@/components/Nav";

interface BrandForm {
  company_name: string;
  industry: string;
  primary_color: string;
  secondary_color: string;
  accent_color: string;
  font_style: string;
  brand_tone: string;
  visual_style: string;
  tagline: string;
  website_url: string;
  target_audience: string;
  key_products: string;
  brand_values: string;
}

interface CampaignForm {
  objective: string;
  key_messages: string;
  campaign_tone: string;
  target_platform: string;
  number_of_posts: number;
}

interface GeneratedPost {
  id: number;
  content_type: string;
  headline: string;
  supporting_text: string;
  cta: string;
  visual_description: string;
  mood: string;
  layout_strategy: string;
  final_path: string | null;
  final_url: string | null;
}

const OBJECTIVES = [
  { value: "brand_awareness", label: "Brand Awareness" },
  { value: "hiring", label: "Hiring / Recruitment" },
  { value: "product_launch", label: "Product Launch" },
  { value: "engagement", label: "Engagement" },
  { value: "lead_generation", label: "Lead Generation" },
  { value: "thought_leadership", label: "Thought Leadership" },
];

const PLATFORMS = [
  { value: "LinkedIn", label: "LinkedIn" },
  { value: "Instagram", label: "Instagram" },
  { value: "Twitter", label: "Twitter / X" },
  { value: "Facebook", label: "Facebook" },
];

const PROVIDERS = [
  { value: "gemini", label: "Gemini (Google)" },
  { value: "openai", label: "DALL-E 3 (OpenAI)" },
  { value: "minimax", label: "MiniMax" },
  { value: "openrouter", label: "OpenRouter" },
];

export default function SocialPostsPage() {
  const [brand, setBrand] = useState<BrandForm>({
    company_name: "",
    industry: "",
    primary_color: "#0057FF",
    secondary_color: "#FFFFFF",
    accent_color: "#FF6B35",
    font_style: "Inter",
    brand_tone: "Professional",
    visual_style: "Modern SaaS",
    tagline: "",
    website_url: "",
    target_audience: "",
    key_products: "",
    brand_values: "",
  });

  const [campaign, setCampaign] = useState<CampaignForm>({
    objective: "brand_awareness",
    key_messages: "",
    campaign_tone: "Professional",
    target_platform: "LinkedIn",
    number_of_posts: 8,
  });

  const [imageProvider, setImageProvider] = useState("gemini");
  const [keyChoice, setKeyChoice] = useState("primary");
  const [submitting, setSubmitting] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [posts, setPosts] = useState<GeneratedPost[]>([]);
  const [jobId, setJobId] = useState<string | null>(null);
  const [outputDir, setOutputDir] = useState<string | null>(null);

  const handleBrandChange = (field: keyof BrandForm, value: string) => {
    setBrand(prev => ({ ...prev, [field]: value }));
  };

  const handleCampaignChange = (field: keyof CampaignForm, value: string | number) => {
    setCampaign(prev => ({ ...prev, [field]: value }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!brand.company_name.trim()) {
      setError("Company name is required");
      return;
    }

    setSubmitting(true);
    setError(null);
    setStatus("Generating social posts...");
    setPosts([]);

    try {
      const payload = {
        brand: {
          company_name: brand.company_name,
          industry: brand.industry,
          primary_color: brand.primary_color,
          secondary_color: brand.secondary_color,
          accent_color: brand.accent_color,
          font_style: brand.font_style,
          brand_tone: brand.brand_tone,
          visual_style: brand.visual_style,
          tagline: brand.tagline,
          website_url: brand.website_url || `WWW.${brand.company_name.toUpperCase().replace(/\s+/g, '')}.COM`,
          target_audience: brand.target_audience,
          key_products: brand.key_products.split(',').map(s => s.trim()).filter(Boolean),
          brand_values: brand.brand_values.split(',').map(s => s.trim()).filter(Boolean),
        },
        campaign: {
          objective: campaign.objective,
          key_messages: campaign.key_messages.split(',').map(s => s.trim()).filter(Boolean),
          campaign_tone: campaign.campaign_tone,
          target_platform: campaign.target_platform,
          number_of_posts: campaign.number_of_posts,
        },
        image_provider: imageProvider,
        key_choice: keyChoice,
      };

      const API_BASE = "http://localhost:8000";

      const response = await fetch(`${API_BASE}/api/social-posts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const text = await response.text();
        throw new Error(`Failed to start generation (${response.status}): ${text}`);
      }

      const data = await response.json();
      setJobId(data.campaign_id);
      setOutputDir(data.output_directory);
      setStatus("Campaign started! Polling for results...");

      // Start polling for results
      pollForResults(data.campaign_id);

    } catch (e) {
      setError((e as Error).message);
      setStatus(null);
    } finally {
      setSubmitting(false);
    }
  };

  const pollForResults = async (jobId: string) => {
    let pollCount = 0;
    const maxPolls = 120; // 20 minutes max (background task takes time)

    const poll = async () => {
      if (pollCount >= maxPolls) {
        setStatus("Generation is taking longer than expected. Check back later.");
        return;
      }

      try {
        const response = await fetch(`http://localhost:8000/api/social-posts/${jobId}`);
        if (response.ok) {
          const data = await response.json();
          if (data.status === "completed" && data.posts) {
            setPosts(data.posts);
            setStatus(`Generated ${data.posts.length} posts!`);
            return;
          } else if (data.status === "failed") {
            setError(data.error || "Generation failed");
            setStatus(null);
            return;
          }
        }
      } catch {
        // Ignore polling errors
      }

      pollCount++;
      setStatus(`Generating... (${pollCount * 10}s elapsed)`);
      setTimeout(poll, 10000);
    };

    // Start polling after 20 seconds
    setTimeout(poll, 20000);
  };

  return (
    <div className="min-h-screen bg-black">
      <Nav />

      <main className="mx-auto max-w-5xl px-6 pt-16 pb-24">
        {/* Header */}
        <section className="mb-12">
          <div className="flex items-center gap-3 font-mono text-[10px] uppercase tracking-[0.2em] text-dim">
            <span className="text-brand">●</span>
            <span>Social Posts</span>
            <span className="h-px flex-1 bg-[var(--border)]" />
          </div>
          <h1 className="mt-6 font-display text-[clamp(36px,5vw,64px)] leading-[0.95] tracking-tight">
            AI Social Media
            <span className="block text-[var(--text-muted)]">Campaign Generator</span>
          </h1>
          <p className="mt-5 max-w-xl text-[var(--text-muted)] text-base leading-relaxed">
            Enter your brand details and campaign goals. DeepSeek acts as creative director,
            generating unique post concepts, headlines, and visuals — all branded consistently.
          </p>
        </section>

        <form onSubmit={handleSubmit} className="space-y-12">
          {/* Brand Information */}
          <section className="card p-8">
            <div className="flex items-center gap-3 font-mono text-[10px] uppercase tracking-[0.2em] text-dim mb-8">
              <span className="text-brand">01</span>
              <span className="h-px flex-1 bg-[var(--border)]" />
              <span>Brand Identity</span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <label className="block text-sm font-medium mb-2">Company Name *</label>
                <input
                  type="text"
                  value={brand.company_name}
                  onChange={(e) => handleBrandChange('company_name', e.target.value)}
                  className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2.5 focus:outline-none focus:ring-2 focus:ring-brand"
                  placeholder="Your Company"
                  required
                />
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">Industry</label>
                <input
                  type="text"
                  value={brand.industry}
                  onChange={(e) => handleBrandChange('industry', e.target.value)}
                  className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2.5 focus:outline-none focus:ring-2 focus:ring-brand"
                  placeholder="e.g. Transit Technology"
                />
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">Tagline</label>
                <input
                  type="text"
                  value={brand.tagline}
                  onChange={(e) => handleBrandChange('tagline', e.target.value)}
                  className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2.5 focus:outline-none focus:ring-2 focus:ring-brand"
                  placeholder="Your brand tagline"
                />
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">Website URL</label>
                <input
                  type="text"
                  value={brand.website_url}
                  onChange={(e) => handleBrandChange('website_url', e.target.value)}
                  className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2.5 focus:outline-none focus:ring-2 focus:ring-brand"
                  placeholder="WWW.YOURCOMPANY.COM"
                />
              </div>

              <div className="md:col-span-2">
                <label className="block text-sm font-medium mb-2">Target Audience</label>
                <input
                  type="text"
                  value={brand.target_audience}
                  onChange={(e) => handleBrandChange('target_audience', e.target.value)}
                  className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2.5 focus:outline-none focus:ring-2 focus:ring-brand"
                  placeholder="e.g. Urban commuters, fleet managers, transit operators"
                />
              </div>

              <div className="md:col-span-2">
                <label className="block text-sm font-medium mb-2">Key Products / Services</label>
                <input
                  type="text"
                  value={brand.key_products}
                  onChange={(e) => handleBrandChange('key_products', e.target.value)}
                  className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2.5 focus:outline-none focus:ring-2 focus:ring-brand"
                  placeholder="Comma-separated: Bus tracking, Fleet management, Rider app"
                />
              </div>

              <div className="md:col-span-2">
                <label className="block text-sm font-medium mb-2">Brand Values</label>
                <input
                  type="text"
                  value={brand.brand_values}
                  onChange={(e) => handleBrandChange('brand_values', e.target.value)}
                  className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2.5 focus:outline-none focus:ring-2 focus:ring-brand"
                  placeholder="Comma-separated: Innovation, Reliability, Safety"
                />
              </div>
            </div>

            {/* Colors */}
            <div className="mt-8">
              <h3 className="text-sm font-medium mb-4">Brand Colors</h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div>
                  <label className="block text-xs text-dim mb-2">Primary Color</label>
                  <div className="flex items-center gap-3">
                    <input
                      type="color"
                      value={brand.primary_color}
                      onChange={(e) => handleBrandChange('primary_color', e.target.value)}
                      className="w-12 h-10 rounded cursor-pointer border-0"
                    />
                    <input
                      type="text"
                      value={brand.primary_color}
                      onChange={(e) => handleBrandChange('primary_color', e.target.value)}
                      className="flex-1 bg-zinc-900 border border-zinc-800 rounded px-3 py-2 font-mono text-sm"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-xs text-dim mb-2">Secondary Color</label>
                  <div className="flex items-center gap-3">
                    <input
                      type="color"
                      value={brand.secondary_color}
                      onChange={(e) => handleBrandChange('secondary_color', e.target.value)}
                      className="w-12 h-10 rounded cursor-pointer border-0"
                    />
                    <input
                      type="text"
                      value={brand.secondary_color}
                      onChange={(e) => handleBrandChange('secondary_color', e.target.value)}
                      className="flex-1 bg-zinc-900 border border-zinc-800 rounded px-3 py-2 font-mono text-sm"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-xs text-dim mb-2">Accent Color</label>
                  <div className="flex items-center gap-3">
                    <input
                      type="color"
                      value={brand.accent_color}
                      onChange={(e) => handleBrandChange('accent_color', e.target.value)}
                      className="w-12 h-10 rounded cursor-pointer border-0"
                    />
                    <input
                      type="text"
                      value={brand.accent_color}
                      onChange={(e) => handleBrandChange('accent_color', e.target.value)}
                      className="flex-1 bg-zinc-900 border border-zinc-800 rounded px-3 py-2 font-mono text-sm"
                    />
                  </div>
                </div>
              </div>
            </div>

            {/* Tone & Style */}
            <div className="mt-8 grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <label className="block text-sm font-medium mb-2">Brand Tone</label>
                <select
                  value={brand.brand_tone}
                  onChange={(e) => handleBrandChange('brand_tone', e.target.value)}
                  className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2.5 focus:outline-none focus:ring-2 focus:ring-brand"
                >
                  <option>Professional</option>
                  <option>Playful</option>
                  <option>Bold</option>
                  <option>Luxury</option>
                  <option>Minimal</option>
                  <option>Friendly</option>
                  <option>Authoritative</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">Visual Style</label>
                <select
                  value={brand.visual_style}
                  onChange={(e) => handleBrandChange('visual_style', e.target.value)}
                  className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2.5 focus:outline-none focus:ring-2 focus:ring-brand"
                >
                  <option>Modern SaaS</option>
                  <option>Corporate Professional</option>
                  <option>Tech & Innovation</option>
                  <option>Minimal & Clean</option>
                  <option>Bold & Vibrant</option>
                  <option>Premium & Luxury</option>
                  <option>Friendly & Approachable</option>
                </select>
              </div>
            </div>
          </section>

          {/* Campaign Goals */}
          <section className="card p-8">
            <div className="flex items-center gap-3 font-mono text-[10px] uppercase tracking-[0.2em] text-dim mb-8">
              <span className="text-brand">02</span>
              <span className="h-px flex-1 bg-[var(--border)]" />
              <span>Campaign Goals</span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <label className="block text-sm font-medium mb-2">Objective</label>
                <select
                  value={campaign.objective}
                  onChange={(e) => handleCampaignChange('objective', e.target.value)}
                  className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2.5 focus:outline-none focus:ring-2 focus:ring-brand"
                >
                  {OBJECTIVES.map(opt => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">Target Platform</label>
                <select
                  value={campaign.target_platform}
                  onChange={(e) => handleCampaignChange('target_platform', e.target.value)}
                  className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2.5 focus:outline-none focus:ring-2 focus:ring-brand"
                >
                  {PLATFORMS.map(opt => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">Campaign Tone</label>
                <select
                  value={campaign.campaign_tone}
                  onChange={(e) => handleCampaignChange('campaign_tone', e.target.value)}
                  className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2.5 focus:outline-none focus:ring-2 focus:ring-brand"
                >
                  <option>Professional</option>
                  <option>Inspirational</option>
                  <option>Educational</option>
                  <option>Urgent</option>
                  <option>Playful</option>
                  <option>Trust-building</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">Number of Posts</label>
                <input
                  type="number"
                  min={1}
                  max={20}
                  value={campaign.number_of_posts}
                  onChange={(e) => handleCampaignChange('number_of_posts', parseInt(e.target.value) || 8)}
                  className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2.5 focus:outline-none focus:ring-2 focus:ring-brand"
                />
              </div>

              <div className="md:col-span-2">
                <label className="block text-sm font-medium mb-2">Key Messages</label>
                <textarea
                  value={campaign.key_messages}
                  onChange={(e) => handleCampaignChange('key_messages', e.target.value)}
                  className="w-full bg-zinc-900 border border-zinc-800 rounded px-3 py-2.5 focus:outline-none focus:ring-2 focus:ring-brand min-h-[80px]"
                  placeholder="Comma-separated key messages: Making transit smarter, Real-time visibility, Efficiency gains"
                />
              </div>
            </div>
          </section>

          {/* Image Provider */}
          <section className="card p-8">
            <div className="flex items-center gap-3 font-mono text-[10px] uppercase tracking-[0.2em] text-dim mb-6">
              <span className="text-brand">03</span>
              <span className="h-px flex-1 bg-[var(--border)]" />
              <span>Image Generation</span>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
              {PROVIDERS.map(provider => (
                <button
                  key={provider.value}
                  type="button"
                  onClick={() => setImageProvider(provider.value)}
                  className={`chip py-3 ${imageProvider === provider.value ? 'ring-2 ring-brand' : ''}`}
                >
                  {provider.label}
                </button>
              ))}
            </div>

            {(imageProvider === "gemini" || imageProvider === "openrouter") && (
              <div className="flex items-center gap-4">
                <span className="text-sm text-dim">API Key:</span>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => setKeyChoice("primary")}
                    className={`chip py-2 px-4 ${keyChoice === "primary" ? 'ring-2 ring-brand' : ''}`}
                  >
                    Primary
                  </button>
                  <button
                    type="button"
                    onClick={() => setKeyChoice("secondary")}
                    className={`chip py-2 px-4 ${keyChoice === "secondary" ? 'ring-2 ring-brand' : ''}`}
                  >
                    Secondary
                  </button>
                </div>
              </div>
            )}
          </section>

          {/* Error */}
          {error && (
            <div className="border border-[var(--danger)]/40 bg-[var(--danger)]/10 text-[var(--danger)] rounded-lg px-4 py-3 text-sm">
              {error}
            </div>
          )}

          {/* Status */}
          {status && (
            <div className="card p-6 border border-brand/40 bg-brand/5">
              <div className="flex items-center gap-3">
                <div className="w-3 h-3 rounded-full bg-brand animate-pulse" />
                <span className="text-sm">{status}</span>
              </div>
            </div>
          )}

          {/* Generated Posts */}
          {posts.length > 0 && (
            <section className="space-y-4">
              <h2 className="font-display text-2xl">Generated Posts ({posts.length})</h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {posts.map(post => (
                  <div key={post.id} className="card p-0 overflow-hidden">
                    {post.final_url && (
                      <div className="relative aspect-square bg-zinc-900">
                        <img
                          src={post.final_url}
                          alt={post.headline}
                          className="w-full h-full object-cover"
                          onError={(e) => {
                            (e.target as HTMLImageElement).style.display = 'none';
                            (e.target as HTMLImageElement).parentElement?.classList.add('hidden');
                          }}
                        />
                        {/* Download button */}
                        <a
                          href={post.final_url}
                          download={post.headline.replace(/\s+/g, '_').substring(0, 30) + '.jpg'}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="absolute bottom-3 right-3 bg-brand hover:bg-brand-dark text-white px-3 py-2 rounded-lg text-xs font-medium flex items-center gap-2 shadow-lg"
                        >
                          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M7 1v8M3 5l4 4 4-4M1 10v2a1 1 0 001 1h10a1 1 0 001-1v-2" />
                          </svg>
                          Download
                        </a>
                      </div>
                    )}
                    <div className="p-5">
                      <div className="flex items-center gap-2 mb-3">
                        <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-dim bg-zinc-800 px-2 py-1 rounded">
                          {post.content_type}
                        </span>
                        <span className="text-dim">•</span>
                        <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-dim">
                          {post.layout_strategy}
                        </span>
                      </div>
                      <h3 className="font-display text-lg mb-2">{post.headline}</h3>
                      <p className="text-sm text-dim mb-3 line-clamp-2">{post.supporting_text}</p>
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-dim">Mood: {post.mood}</span>
                        <span className="chip text-xs">{post.cta}</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Submit */}
          <div className="flex items-center justify-between pt-4">
            <Link href="/" className="text-sm text-dim hover:text-white transition-colors">
              ← Back to Reel Generator
            </Link>
            <button
              type="submit"
              disabled={submitting || !brand.company_name.trim()}
              className="btn-primary btn-brand group"
            >
              <span>{submitting ? "Generating..." : "Generate Campaign"}</span>
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
      </main>
    </div>
  );
}