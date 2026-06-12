# Product Architecture & Workflow

## Product Vision

Build an agency-grade AI Content Generation Platform capable of producing:

* Social Media Posts
* Reels
* Campaign Assets

while maintaining complete brand consistency across all outputs.

The platform should function as a content operating system for agencies and internal marketing teams.

---

# Technology Stack

Frontend:

* Next.js

Backend:

* FastAPI

Database:

* Supabase PostgreSQL

Storage:

* Supabase Storage

Authentication:

* Supabase Auth

Queue:

* Celery + Redis

Image Generation:

* MiniMax

LLMs:

* Gemini
* DeepSeek

Video Processing:

* FFmpeg

Deployment:

* Railway

---

# Core Product Modules

## Brand Management

Stores:

* Company Name
* Colors
* Fonts
* Logos
* Tone of Voice
* Visual Style

This becomes the source of truth for all generated content.

---

## Template Management

Supported Templates:

* Hiring
* Event
* Promotion
* Announcement
* Achievement
* Product Launch
* Festival
* Case Study

Templates define layout and content structure.

---

## Post Generation Engine

Workflow:

User Input
→ Campaign Analysis
→ Content Generation
→ Prompt Generation
→ Image Generation
→ Asset Storage
→ Final Post

Output:

* Image
* Caption
* Metadata

---

## Reel Generation Engine

Workflow:

User Input
→ Script Generation
→ Storyboard Generation
→ Scene Planning
→ Image Generation
→ Motion Effects
→ Caption Timeline
→ Audio Processing
→ FFmpeg Rendering
→ Storage Upload

Output:

* Final Reel
* Captions
* Assets
* Metadata

---

# Reel Rendering Pipeline

## Step 1

Generate campaign script.

---

## Step 2

Generate storyboard scenes.

---

## Step 3

Generate image prompts.

---

## Step 4

Generate images.

---

## Step 5

Apply motion effects.

Supported effects:

* Zoom In
* Zoom Out
* Pan Left
* Pan Right
* Slow Push
* Fade

---

## Step 6

Generate caption timeline.

Example:

[
{
"start": 0,
"end": 2,
"text": "We Are Hiring"
}
]

---

## Step 7

Generate audio.

Modes:

* Music Only
* Voiceover + Music

---

## Step 8

Render reel using FFmpeg.

---

## Step 9

Upload final assets to Supabase Storage.

---

# Queue Architecture

Rendering must NEVER happen inside the API request.

Correct flow:

User Request
→ Create Job
→ Store Job
→ Queue
→ Worker
→ Processing
→ Upload
→ Complete

Status Values:

* Pending
* Processing
* Completed
* Failed

---

# Database Structure

Tables:

brands

templates

campaigns

posts

reels

assets

jobs

users

---

# Storage Structure

brands/

campaigns/

posts/

reels/

temp/

Every generated asset must be uploaded to Supabase Storage.

Local storage must only be used temporarily during processing.

---

# Scalability Requirements

The architecture must support:

* Multiple Clients
* Multiple Brands
* Multiple Campaigns
* Concurrent Reel Rendering
* Future SaaS Expansion

Avoid solutions that tightly couple generation logic with rendering logic.

Each module should remain independently scalable.

---

# Product Goal

The platform should allow a user to:

Select Brand
→ Select Content Type
→ Enter Topic
→ Generate Content

without manually designing graphics or editing videos.

The system should automatically maintain branding, visual consistency, captions, audio, and rendering quality across all generated content.
