const BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  "https://news-reel-generator-production.up.railway.app";

export interface Campaign {
  id: string;
  topic: string;
  voice: string;
  scene_count: number;
  aspect_ratio: string;
  status: string;
  error_message?: string | null;
  title?: string | null;
  video_url?: string | null;
  created_at: string;
  updated_at: string;
  completed_at?: string | null;
}

export interface SocialPost {
  id: string;
  company_name: string;
  status: string;
  posts_json?: PostData[] | null;
  created_at: string;
  completed_at?: string | null;
}

export interface PostData {
  id: number;
  content_type: string;
  headline: string;
  supporting_text: string;
  cta: string;
  final_url: string | null;
}

export interface CreateCampaignInput {
  topic: string;
  voice?: string;
  scene_count?: number;
}

export async function createCampaign(payload: CreateCampaignInput): Promise<Campaign> {
  const r = await fetch(`${BASE}/api/campaigns`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!r.ok) {
    const text = await r.text().catch(() => "");
    throw new Error(`Failed to create campaign (${r.status}): ${text}`);
  }
  return r.json();
}

export async function listCampaigns(): Promise<Campaign[]> {
  const r = await fetch(`${BASE}/api/campaigns`, { cache: "no-store" });
  if (!r.ok) throw new Error(`Failed to list campaigns (${r.status})`);
  return r.json();
}

export async function getCampaign(id: string): Promise<Campaign> {
  const r = await fetch(`${BASE}/api/campaigns/${id}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`Failed to get campaign (${r.status})`);
  return r.json();
}

// Social Posts API
export async function listSocialPosts(): Promise<SocialPost[]> {
  const r = await fetch(`${BASE}/api/social-posts`, { cache: "no-store" });
  if (!r.ok) throw new Error(`Failed to list social posts (${r.status})`);
  return r.json();
}

export async function getSocialPost(id: string): Promise<SocialPost> {
  const r = await fetch(`${BASE}/api/social-posts/${id}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`Failed to get social post (${r.status})`);
  return r.json();
}
