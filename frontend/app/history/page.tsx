"use client";

import { useState } from "react";
import useSWR from "swr";
import { listCampaigns, listSocialPosts, type Campaign, type SocialPost, type PostData } from "@/lib/api";
import Link from "next/link";

type Range = "all" | "today" | "week";
type Tab = "reels" | "social_posts";

function inRange(iso: string, r: Range): boolean {
  const t = new Date(iso).getTime();
  const now = Date.now();
  if (r === "all") return true;
  if (r === "today") {
    const start = new Date(); start.setHours(0, 0, 0, 0);
    return t >= start.getTime();
  }
  if (r === "week") return t >= now - 7 * 24 * 60 * 60 * 1000;
  return true;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function VideoCard({ campaign }: { campaign: Campaign }) {
  return (
    <div className="relative group">
      {campaign.video_url ? (
        <video
          src={campaign.video_url}
          className="w-full aspect-[9/16] object-cover rounded-lg"
          controls
          preload="metadata"
          playsInline
        />
      ) : (
        <div className="aspect-[9/16] bg-zinc-800 rounded-lg flex items-center justify-center text-zinc-500 text-xs font-mono">
          no video
        </div>
      )}
      {campaign.video_url && (
        <a
          href={campaign.video_url}
          download={`reel_${campaign.id}.mp4`}
          className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity bg-black/80 hover:bg-black p-2 rounded-lg text-white"
          title="Download reel"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M8 1v10M4 7l4 4 4-4M1 13v2a1 1 0 001 1h12a1 1 0 001-1v-2" />
          </svg>
        </a>
      )}
    </div>
  );
}

function SocialPostCard({ post, postData }: { post: SocialPost; postData: PostData }) {
  if (!postData.final_url) return null;

  return (
    <div className="relative group">
      <div className="aspect-square bg-zinc-800 rounded-lg overflow-hidden">
        <img
          src={postData.final_url}
          alt={postData.headline}
          className="w-full h-full object-cover"
        />
      </div>
      <a
        href={postData.final_url}
        download={`post_${post.id}_${postData.id}.jpg`}
        className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity bg-black/80 hover:bg-black p-2 rounded-lg text-white"
        title="Download post"
      >
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M8 1v10M4 7l4 4 4-4M1 13v2a1 1 0 001 1h12a1 1 0 001-1v-2" />
        </svg>
      </a>
      <div className="mt-2">
        <p className="text-xs font-mono text-zinc-400 uppercase tracking-wider">{postData.content_type}</p>
        <p className="font-medium text-sm mt-1 line-clamp-1">{postData.headline}</p>
      </div>
    </div>
  );
}

export default function HistoryPage() {
  const [tab, setTab] = useState<Tab>("reels");
  const [range, setRange] = useState<Range>("all");
  const [query, setQuery] = useState("");

  const { data: campaigns, error: campaignError } = useSWR<Campaign[]>(
    "history-campaigns",
    () => listCampaigns(),
    { refreshInterval: 10000 },
  );

  const { data: socialPosts, error: socialError } = useSWR<SocialPost[]>(
    "history-social-posts",
    () => listSocialPosts(),
    { refreshInterval: 10000 },
  );

  const completedCampaigns = (campaigns ?? []).filter(c => c.status === "completed" && inRange(c.created_at, range));
  // Only show social post campaigns that actually have generated posts
  const completedPosts = (socialPosts ?? []).filter(p =>
    p.status === "completed" &&
    inRange(p.created_at, range) &&
    (p.posts_json?.length ?? 0) > 0
  );

  const filteredCampaigns = query.trim()
    ? completedCampaigns.filter(c => (c.title ?? c.topic).toLowerCase().includes(query.toLowerCase()))
    : completedCampaigns;

  const filteredPosts = query.trim()
    ? completedPosts.filter(p => p.company_name.toLowerCase().includes(query.toLowerCase()))
    : completedPosts;

  return (
    <div className="mx-auto max-w-7xl px-6 pt-16 pb-24">
      {/* Header */}
      <header className="mb-12">
        <div className="flex items-center gap-3 font-mono text-[10px] uppercase tracking-[0.2em] text-dim">
          <span className="text-brand">●</span>
          <span>Archive</span>
          <span className="h-px flex-1 bg-[var(--border)]" />
        </div>
        <h1 className="mt-6 font-display text-[clamp(36px,5vw,64px)] leading-[0.95] tracking-tight">
          Past generations.
        </h1>
        <p className="mt-3 text-[var(--text-muted)] text-sm">
          Download your reels and social posts anytime.
        </p>
      </header>

      {/* Tabs */}
      <div className="flex gap-4 mb-8 border-b border-[var(--border)] pb-4">
        <button
          onClick={() => setTab("reels")}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
            tab === "reels" ? "bg-brand text-white" : "text-zinc-400 hover:text-white"
          }`}
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
            <path d="M2 2h12v12H2zM6 5v6l5-3z" />
          </svg>
          Reels ({completedCampaigns.length})
        </button>
        <button
          onClick={() => setTab("social_posts")}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
            tab === "social_posts" ? "bg-brand text-white" : "text-zinc-400 hover:text-white"
          }`}
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
            <rect x="1" y="1" width="6" height="6" rx="1" />
            <rect x="9" y="1" width="6" height="6" rx="1" />
            <rect x="1" y="9" width="6" height="6" rx="1" />
            <rect x="9" y="9" width="6" height="6" rx="1" />
          </svg>
          Social Posts ({completedPosts.length})
        </button>
      </div>

      {/* Search */}
      <div className="flex gap-3 mb-8">
        <div className="relative flex-1">
          <svg
            width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor"
            strokeWidth="1.5" className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500"
          >
            <circle cx="6" cy="6" r="4" />
            <path d="M9 9L12 12" />
          </svg>
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={tab === "reels" ? "Search reels..." : "Search social posts..."}
            className="w-full bg-zinc-900 border border-zinc-800 rounded-lg pl-10 pr-3 py-2.5 text-sm placeholder:text-zinc-500 focus:outline-none focus:ring-2 focus:ring-brand"
          />
        </div>
        <select
          value={range}
          onChange={(e) => setRange(e.target.value as Range)}
          className="bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand"
        >
          <option value="all">All time</option>
          <option value="today">Today</option>
          <option value="week">This week</option>
        </select>
      </div>

      {/* Reels Grid */}
      {tab === "reels" && (
        campaignError ? (
          <div className="card p-8 text-red-400 text-sm">
            Failed to load reels. Is the backend running?
          </div>
        ) : !campaigns ? (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-5">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="animate-pulse">
                <div className="aspect-[9/16] bg-zinc-800 rounded-lg" />
              </div>
            ))}
          </div>
        ) : filteredCampaigns.length === 0 ? (
          <div className="text-center py-16 text-zinc-500">
            <p className="font-display text-2xl">No reels yet</p>
            <p className="mt-2 text-sm">
              {campaigns.length > 0
                ? "No reels match your filters"
                : "Generate your first reel to see it here"}
            </p>
            <Link href="/" className="mt-6 inline-flex items-center gap-2 btn-primary">
              <span>Make a reel</span>
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.6">
                <path d="M2 7H12M8 3L12 7L8 11" />
              </svg>
            </Link>
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-5">
            {filteredCampaigns.map((c) => (
              <div key={c.id} className="group">
                <VideoCard campaign={c} />
                <div className="mt-3">
                  <p className="font-medium text-sm line-clamp-1">
                    {c.title || c.topic}
                  </p>
                  <p className="text-xs text-zinc-500 mt-1">
                    {formatDate(c.created_at)} · {c.scene_count} scenes
                  </p>
                </div>
              </div>
            ))}
          </div>
        )
      )}

      {/* Social Posts Grid */}
      {tab === "social_posts" && (
        socialError ? (
          <div className="card p-8 text-red-400 text-sm">
            Failed to load social posts. Is the backend running?
          </div>
        ) : !socialPosts ? (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-5">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="animate-pulse">
                <div className="aspect-square bg-zinc-800 rounded-lg" />
              </div>
            ))}
          </div>
        ) : filteredPosts.length === 0 ? (
          <div className="text-center py-16 text-zinc-500">
            <p className="font-display text-2xl">No social posts yet</p>
            <p className="mt-2 text-sm">
              {socialPosts.length > 0
                ? "No posts match your filters"
                : "Generate your first social post to see it here"}
            </p>
            <Link href="/social-posts" className="mt-6 inline-flex items-center gap-2 btn-primary">
              <span>Make a social post</span>
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.6">
                <path d="M2 7H12M8 3L12 7L8 11" />
              </svg>
            </Link>
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-5">
            {filteredPosts.map((post) => (
              <div key={post.id}>
                {/* Campaign header */}
                <div className="mb-3">
                  <p className="font-medium">{post.company_name}</p>
                  <p className="text-xs text-zinc-500">
                    {formatDate(post.created_at)} · {post.posts_json?.length || 0} posts
                  </p>
                </div>
                {/* Posts grid */}
                <div className="grid grid-cols-2 gap-2">
                  {(post.posts_json || []).slice(0, 4).map((postData) => (
                    <SocialPostCard key={postData.id} post={post} postData={postData} />
                  ))}
                </div>
              </div>
            ))}
          </div>
        )
      )}
    </div>
  );
}
