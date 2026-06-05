# Autonomous News Reel Generator (MVP) – Technical Architecture

## Project Overview

We are building an MVP called **Autonomous News Reel Generator**, a full-stack application that automatically generates short-form vertical news videos (TikTok, Instagram Reels, YouTube Shorts) from a user-provided topic.

The system follows a simple, code-first architecture and does **not** use Make.com, n8n, Zapier, or any external workflow orchestration platform. All business logic and workflow orchestration should be handled directly within the FastAPI backend.

The goal is to create a reliable, asynchronous, production-oriented pipeline that can generate videos without blocking API requests.

---

## Core Workflow

1. User enters a topic from the Next.js dashboard.
2. Frontend sends a request to FastAPI.
3. FastAPI immediately creates a campaign record in PostgreSQL/Supabase with a `pending` status.
4. FastAPI instantly returns a `202 Accepted` response to avoid request timeouts.
5. A background worker starts processing the campaign.
6. The worker sends the topic to Google Gemini.
7. Gemini returns a structured JSON script containing scenes, narration text, and search keywords.
8. The worker searches the Pexels API using the generated keywords.
9. Relevant vertical stock videos are downloaded.
10. Narration text is converted into speech using `edge-tts`.
11. MoviePy stitches video clips and voiceover into a final vertical MP4.
12. The generated video is uploaded to Supabase Storage.
13. The campaign status is updated to `completed`.
14. The frontend periodically polls the backend and displays the final video once available.

---

## Technology Stack

### Frontend

* Next.js
* React
* Tailwind CSS
* Video Player Component
* Dashboard UI

### Backend

* FastAPI
* SQLAlchemy
* PostgreSQL / Supabase
* Alembic Migrations
* Background Tasks / Worker Layer

### AI

* Google Gemini API
* Structured JSON output only

### Media Processing

* edge-tts (Text-to-Speech)
* MoviePy (Video Rendering)
* Pexels API (Stock Video Source)

### Storage

* Supabase Storage

---

## Architecture

User
→ Next.js Dashboard
→ FastAPI API
→ PostgreSQL/Supabase

Background Worker:
→ Google Gemini
→ Pexels API
→ edge-tts
→ MoviePy
→ Supabase Storage

Frontend Polling:
→ FastAPI
→ Campaign Status
→ Video URL

---

## Important Engineering Rules

### Rule 1: Non-Blocking API

The API must never wait for:
/stop


* Gemini responses
* Pexels requests
* Voice generation
* Video rendering

Generation requests should always:

1. Create a database record.
2. Queue/start background processing.
3. Return `202 Accepted` immediately.

### Rule 2: Structured AI Output

Gemini must return strict JSON.

Example:

```json
{
  "title": "AI News Today",
  "scenes": [
    {
      "narration": "OpenAI released a major update.",
      "search_term": "artificial intelligence"
    }
  ]
}
```

No free-form text responses should be used.

### Rule 3: Stock-Stitch Method Only

Do not build or integrate custom AI video generation systems.

The video creation pipeline is:

Topic
→ Gemini Script
→ Pexels Stock Videos
→ edge-tts Voiceover
→ MoviePy Stitching
→ MP4 Output

### Rule 4: Database-Driven State Management

Campaign statuses:

* pending
* processing
* rendering
* completed
* failed

Every stage must update the campaign status in the database.

---

## Initial MVP Features

### Campaign Creation

* Create campaign from topic
* Store metadata
* Trigger background processing

### Campaign Tracking

* View all campaigns
* View status
* View creation timestamps

### Video Generation

* Generate script
* Fetch stock footage
* Generate narration
* Render video
* Upload final MP4

### Video Playback

* Display completed video
* Play directly from Supabase Storage URL

---

## Development Approach

Build in this order:

1. FastAPI project setup
2. Database models
3. Campaign APIs
4. Background worker
5. Gemini integration
6. Pexels integration
7. edge-tts integration
8. MoviePy rendering pipeline
9. Supabase Storage upload
10. Next.js dashboard
11. End-to-end testing

The architecture should remain modular, maintainable, and production-ready, with clear separation between API routes, services, database models, worker logic, and rendering components.
