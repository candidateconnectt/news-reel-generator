# Make.com Scenario — "Reel Pipeline"

Build this scenario in the Make.com dashboard. It's the bridge between your FastAPI backend (state + rendering) and the asset-lookup chain (Gemini + Pexels). The full module-by-module config is below — copy it into Make.com module by module.

---

## 0. Pre-flight (do this first)

### Add connections (Make.com → Connections)

| Connection | Type | Setup |
|---|---|---|
| Google Gemini | Google Gemini App | Paste `GEMINI_API_KEY` from https://aistudio.google.com/apikey |

### Add scenario variables (Scenario settings → Variables)

| Variable | Example | Purpose |
|---|---|---|
| `APP_BASE_URL` | `http://localhost:8000` (dev) or your deployed URL | FastAPI base |
| `PEXELS_API_KEY` | your key | Pexels HTTP auth header |
| `MAKE_COM_CALLBACK_SECRET` | run `openssl rand -hex 32` | HMAC secret FastAPI uses to verify callbacks — must match FastAPI's `.env` |

### Make.com plan sizing

Per reel ≈ 1 Gemini + 5 Pexels + 1 success callback + 1 fail callback = **~7 ops**.
- Free (1k ops/mo): ~140 reels/mo
- Core ($10.59/mo, 10k ops): ~1,400 reels/mo
- Pick what fits the demo.

---

## 1. Trigger — Custom Webhook

- **Module**: Webhooks → **Custom webhook**
- **Method**: POST
- Make.com auto-generates a URL like `https://hook.eu2.make.com/xxxxxx` — copy this; FastAPI will fire it
- **Expected payload** (this is exactly what FastAPI sends):
  ```json
  {
    "campaign_id": "5f9b3a1c-...",
    "topic": "AI news this week",
    "voice": "en-US-GuyNeural",
    "scene_count": 5,
    "aspect_ratio": "9:16"
  }
  ```

---

## 2. Gemini — Generate Script

- **App**: Google Gemini
- **Action**: Generate Content
- **Model**: `gemini-2.5-flash` (cheap, fast — pin this exact version)
- **System prompt**:
  > You are a short-form video scriptwriter for vertical news shorts (TikTok / Reels / YouTube Shorts). Output ONLY valid JSON. Keep narration punchy: 1–2 short sentences per scene. No emojis. No on-screen text. No hashtags.
- **User prompt** (templated):
  ```
  Topic: {{1.topic}}
  Number of scenes: {{1.scene_count}}
  Aspect ratio: {{1.aspect_ratio}}
  Voice tone: {{1.voice}}
  ```
- **Response format / schema** — set `response_mime_type = application/json` and paste the schema below:
  ```json
  {
    "type": "object",
    "properties": {
      "title": {"type": "string"},
      "voiceover_full": {"type": "string"},
      "scenes": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "narration": {"type": "string"},
            "search_term": {"type": "string"}
          },
          "required": ["narration", "search_term"]
        }
      }
    },
    "required": ["title", "voiceover_full", "scenes"]
  }
  ```
- **Output variable**: `script`

**Sample output** (what the bundle looks like for downstream modules):
```json
{
  "title": "AI Just Changed Everything",
  "voiceover_full": "OpenAI dropped a bombshell ... It changes how we use ChatGPT forever ...",
  "scenes": [
    {"narration": "OpenAI just dropped a bombshell update.", "search_term": "artificial intelligence server"},
    {"narration": "It changes how we use ChatGPT forever.", "search_term": "smartphone chatbot typing"}
  ]
}
```
The `...` in `voiceover_full` is the pause marker — FastAPI's TTS layer expands it to ~250ms of silence.

---

## 3. Iterator over scenes

- **App**: Flow Control → **Iterator**
- **Array**: `{{2.script.scenes}}`
- This makes Modules 4–5 run once per scene.

---

## 4. HTTP — Pexels Search (per scene)

- **Method**: GET
- **URL**: `https://api.pexels.com/videos/search`
- **Query string**:
  - `query` = `{{3.search_term}}`
  - `orientation` = `portrait`
  - `size` = `medium`
  - `per_page` = `3`
- **Headers**:
  - `Authorization` = `{{PEXELS_API_KEY}}`
  - `User-Agent` = `ReelBot/1.0`
- **Parse response** (in a follow-up step or inline using Make.com's JSON transformer):
  - Take `body.videos[*].video_files[*]`
  - Filter: `width < height` (vertical) **and** `width >= 720`
  - Pick the entry with the largest `file_size` (or highest `width` if sizes tie)
  - Extract `link` → that becomes `video_url` for that scene

**Fallback** (add a router with these conditions):
- If the filtered list is empty → try landscape, then just `body.videos[0].video_files[0].link` as last resort
- If `body.videos` is empty → fail the campaign via the error handler

---

## 5. Array Aggregator

- **App**: Flow Control → **Array Aggregator**
- **Source module**: Module 4's parsed result
- **Stop and resume**: enabled (so we collect all scene results into a single array)
- **Output**: `scenes_aggregated` = `[{narration, search_term, video_url}, ...]`

---

## 6. HTTP — Callback to FastAPI (success)

- **Method**: POST
- **URL**: `{{APP_BASE_URL}}/api/campaigns/{{1.campaign_id}}/script`
- **Headers**:
  - `Content-Type`: `application/json`
  - `X-Webhook-Secret`: `{{MAKE_COM_CALLBACK_SECRET}}`
- **Body** (JSON, use the bundled variables):
  ```json
  {
    "title": "{{2.script.title}}",
    "voiceover_full": "{{2.script.voiceover_full}}",
    "scenes": {{5.scenes_aggregated}}
  }
  ```
- **Response handling**: any 2xx = success. Any 4xx/5xx = route to the error handler.

---

## 7. Webhook Response

- **Module**: Webhooks → **Webhook Response**
- **Status**: 200
- **Body**: `{"status": "received"}`

---

## Error handler (route the Break to a fail callback)

On any module error, **Break** with a router that hits:
- **Method**: POST
- **URL**: `{{APP_BASE_URL}}/api/campaigns/{{1.campaign_id}}/fail`
- **Headers**:
  - `Content-Type`: `application/json`
  - `X-Webhook-Secret`: `{{MAKE_COM_CALLBACK_SECRET}}`
- **Body**:
  ```json
  {
    "reason": "{{error.message}}",
    "module": "{{error.module}}"
  }
  ```

**Scenario settings**:
- **Max errors**: 3
- **Auto-resume**: yes
- **Sequential processing**: yes (one reel at a time per scenario execution — keeps Gemini/Pexels rate limits happy)

---

## How to test it in Make.com (Run once)

1. Save the scenario.
2. Click **Run once**.
3. Make.com prompts you to send a test payload to the webhook URL. Use:
   ```json
   {
     "campaign_id": "test-uuid-1234",
     "topic": "SpaceX Starship Mars",
     "voice": "en-US-GuyNeural",
     "scene_count": 3,
     "aspect_ratio": "9:16"
   }
   ```
4. Watch modules light up green. If the FastAPI side isn't ready yet, Module 6 will fail with a connection error — that's expected during scenario-only testing.

---

## What FastAPI must expose for this scenario to work end-to-end

| Endpoint | Purpose | Auth |
|---|---|---|
| `POST /api/campaigns` | Create campaign, fire Make.com webhook, return 202 | (open in MVP) |
| `POST /api/campaigns/{id}/script` | Receive Make.com callback, persist script + clip URLs, kick off background render | HMAC via `X-Webhook-Secret` |
| `POST /api/campaigns/{id}/fail` | Receive Make.com error callback, mark campaign `failed` | HMAC via `X-Webhook-Secret` |
| `GET /api/campaigns` | List all campaigns (dashboard) | (open in MVP) |
| `GET /api/campaigns/{id}` | Get one campaign's status + `video_url` (polling) | (open in MVP) |

These map 1:1 to the spec in `implementation.md` + the Make.com flow above. The single design difference vs the original spec: `POST /api/campaigns` fires a Make.com webhook (step 1) instead of starting the worker directly.
