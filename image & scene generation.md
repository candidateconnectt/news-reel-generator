# Image & Scene Generation Guidelines

## Objective

The purpose of this document is to standardize image generation across both:

1. Social Media Post Generation
2. Reel Generation

All generated assets must maintain brand consistency, visual quality, and a professional appearance suitable for agency-level content production.

---

# Core Principle

The system must NEVER generate random or unrelated images.

Every generated asset must inherit:

* Brand identity
* Brand colors
* Typography style
* Visual language
* Industry context
* Campaign objective

The AI must think like a creative designer, not merely an image generator.

---

# Brand Context

Before generating any image, the following brand information must be loaded:

* Company Name
* Industry
* Primary Color
* Secondary Color
* Accent Color
* Typography Style
* Logo
* Tone of Voice
* Visual Style

Example:

{
"company": "Salesflo",
"industry": "AI Automation",
"primaryColor": "#0057FF",
"secondaryColor": "#FFFFFF",
"fontStyle": "Inter",
"tone": "Professional",
"visualStyle": "Modern SaaS"
}

All image prompts must inherit these brand settings.

---

# Post Generation Workflow

## Step 1: Determine Post Type

Supported types:

* Hiring
* Event
* Achievement
* Promotion
* Announcement
* Case Study
* Festival
* Partnership
* Product Launch

---

## Step 2: Generate Content Structure

Generate:

* Headline
* Supporting Text
* CTA
* Design Direction

Example:

Headline:
"We Are Hiring"

Supporting Text:
"Join our growing development team."

CTA:
"Apply Today"

---

## Step 3: Generate Image Prompt

The prompt must include:

* Brand style
* Company context
* Industry context
* Layout requirements
* Color palette

Prompt Example:

Modern SaaS hiring campaign,
clean corporate design,
blue and white color palette,
professional workspace,
high-quality social media graphic,
minimalistic composition,
Instagram post format,
premium agency quality

---

# Reel Generation Workflow

## Critical Rule

Reels must NOT generate random images independently.

All reel scenes must belong to the same visual world.

Visual consistency is mandatory.

---

## Step 1: Generate Script

Example:

Hook:
"We Are Hiring"

Body:
"Join our engineering team"

CTA:
"Apply Now"

---

## Step 2: Generate Storyboard

Convert script into scenes.

Example:

Scene 1:
"We Are Hiring"

Scene 2:
"Looking for Full Stack Developers"

Scene 3:
"Remote Friendly"

Scene 4:
"Apply Today"

---

## Step 3: Generate Scene Prompts

Each scene receives its own image prompt.

However every prompt must inherit:

* Same visual style
* Same lighting
* Same color palette
* Same brand identity
* Same composition rules

Example:

Scene 1:
Modern SaaS office environment,
blue corporate palette,
clean professional atmosphere,
vertical reel format

Scene 2:
Modern SaaS office environment,
blue corporate palette,
clean professional atmosphere,
vertical reel format

Scene 3:
Modern SaaS office environment,
blue corporate palette,
clean professional atmosphere,
vertical reel format

---

# Image Requirements

Required:

* High Quality
* 9:16 for reels
* 1:1 or 4:5 for posts
* Professional composition
* Consistent visual language
* Brand aligned

Avoid:

* Random styles
* Mixed aesthetics
* Cartoon-like outputs unless requested
* Inconsistent colors
* Unrelated objects

---

# Output Structure

The generation service must return:

{
"brand_context": {},
"campaign_type": "",
"post_type": "",
"script": {},
"storyboard": [],
"image_prompts": [],
"generated_assets": []
}

This structure will later be consumed by the rendering pipeline.
        