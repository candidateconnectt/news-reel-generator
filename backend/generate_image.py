from __future__ import annotations

import asyncio
import base64
import json
import sys
import uuid
import os
from pathlib import Path

from typing import List
from dataclasses import dataclass, asdict
from datetime import datetime
from io import BytesIO
from google import genai
from google.genai import types

import httpx
from PIL import Image
from dotenv import load_dotenv

load_dotenv()

try:
    GEMINI_SDK_AVAILABLE = True
except ImportError:
    GEMINI_SDK_AVAILABLE = False

try:
    from openai import OpenAI
    OPENAI_SDK_AVAILABLE = True
except ImportError:
    OPENAI_SDK_AVAILABLE = False

try:
    from zai import ZaiClient
    ZAI_SDK_AVAILABLE = True
except ImportError:
    ZAI_SDK_AVAILABLE = False

@dataclass
class DesignSpecs:
    enhanced_prompt: str
    style: str
    color_theme: str
    font_style: str
    font_size: str
    layout: str
    mood: str
    target_audience: str
    key_elements: List[str]
    
    def to_dict(self) -> dict:
        return asdict(self)

class GeminiImageGenerator:
    @staticmethod
    async def generate(prompt: str, api_key: str, aspect_ratio: str = "1:1", model: str = "gemini-2.5-flash-image") -> bytes:
        if not GEMINI_SDK_AVAILABLE:
            raise RuntimeError("Google Gemini SDK not installed. Run: pip install google-generativeai")
        
        loop = asyncio.get_event_loop()
        image_bytes = await loop.run_in_executor(
            None,
            GeminiImageGenerator._sync_generate,
            prompt, api_key, aspect_ratio, model
        )
        return image_bytes
    
    @staticmethod
    def _sync_generate(prompt: str, api_key: str, aspect_ratio: str = "1:1", model: str = "gemini-2.5-flash-image") -> bytes:
        try:
            client = genai.Client(api_key=api_key)
            
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=1.0,
                    top_p=0.95,
                    response_modalities=["IMAGE"],
                    image_config=types.ImageConfig(
                        aspect_ratio=aspect_ratio
                    )
                )
            )
                        
            if hasattr(response, 'candidates') and response.candidates:
                for candidate in response.candidates:
                    if hasattr(candidate, 'content') and candidate.content:
                        for part in candidate.content.parts:
                            if hasattr(part, 'inline_data') and part.inline_data:
                                return part.inline_data.data
            
            raise RuntimeError("No image data found in Gemini response")
        except Exception as e:
            raise RuntimeError(f"Gemini SDK error: {str(e)}")

class OpenAIImageGenerator:
    @staticmethod
    async def generate(prompt: str, api_key: str, aspect_ratio: str = "1:1") -> bytes:
        if not OPENAI_SDK_AVAILABLE:
            raise RuntimeError("OpenAI SDK not installed. Run: pip install openai")
        
        loop = asyncio.get_event_loop()
        image_bytes = await loop.run_in_executor(
            None,
            OpenAIImageGenerator._sync_generate,
            prompt, api_key, aspect_ratio
        )
        return image_bytes
    
    @staticmethod
    def _sync_generate(prompt: str, api_key: str, aspect_ratio: str = "1:1") -> bytes:
        try:
            client = OpenAI(api_key=api_key)
            
            size_prompt = ""
            if aspect_ratio == "16:9":
                size_prompt = " (landscape format, wide aspect ratio 16:9)"
            elif aspect_ratio == "3:4":
                size_prompt = " (portrait format, 3:4 aspect ratio)"
            else:
                size_prompt = " (square format, 1:1 aspect ratio)"
            
            full_prompt = prompt + size_prompt
            
            response = client.responses.create(
                model="gpt-5.5",
                input=full_prompt,
                tools=[{"type": "image_generation"}],
            )
            
            image_data = [
                output.result
                for output in response.output
                if output.type == "image_generation_call"
            ]
            
            if image_data:
                image_base64 = image_data[0]
                return base64.b64decode(image_base64)
            else:
                raise RuntimeError("No image data found in response")
                
        except Exception as e:
            raise RuntimeError(f"OpenAI API error: {str(e)}")

class MiniMaxGenerator:
    @staticmethod
    async def generate(prompt: str, api_key: str, aspect_ratio: str = "1:1") -> bytes:
        url = "https://api.minimax.io/v1/image_generation"
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "image-01",
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "response_format": "url",
        }
        
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            
            if resp.status_code != 200:
                raise RuntimeError(f"MiniMax API Error {resp.status_code}: {resp.text[:200]}")
            
            data = resp.json()
            base_resp = data.get("base_resp", {})
            if base_resp.get("status_code", 0) != 0:
                raise RuntimeError(f"MiniMax error: {base_resp.get('status_msg', 'Unknown error')}")
            
            urls = data.get("data", {}).get("image_urls", [])
            if not urls:
                raise RuntimeError("No image URL returned")
            
            img_resp = await client.get(urls[0])
            img_resp.raise_for_status()
            return img_resp.content

class ZAIImageGenerator:
    @staticmethod
    async def generate(prompt: str, api_key: str, aspect_ratio: str = "1:1") -> bytes:
        if not ZAI_SDK_AVAILABLE:
            raise RuntimeError("Z.AI SDK not installed. Run: pip install zai-sdk")
        
        loop = asyncio.get_event_loop()
        image_bytes = await loop.run_in_executor(
            None,
            ZAIImageGenerator._sync_generate,
            prompt, api_key, aspect_ratio
        )
        return image_bytes
    
    @staticmethod
    def _sync_generate(prompt: str, api_key: str, aspect_ratio: str = "1:1") -> bytes:
        try:
            client = ZaiClient(api_key=api_key)
            
            response = client.images.generations(
                model="glm-image",
                prompt=prompt,
            )
            
            if response.data and len(response.data) > 0 and response.data[0].url:
                import requests
                img_response = requests.get(response.data[0].url, timeout=60)
                img_response.raise_for_status()
                return img_response.content
            else:
                raise RuntimeError("No image URL found in response")
                
        except Exception as e:
            raise RuntimeError(f"Z.AI API error: {str(e)}")

class OpenRouterImageGenerator:
    @staticmethod
    async def generate(prompt: str, api_key: str, model: str, aspect_ratio: str = "1:1") -> bytes:
        loop = asyncio.get_event_loop()
        image_bytes = await loop.run_in_executor(
            None,
            OpenRouterImageGenerator._sync_generate,
            prompt, api_key, model, aspect_ratio
        )
        return image_bytes
    
    @staticmethod
    def _sync_generate(prompt: str, api_key: str, model: str, aspect_ratio: str = "1:1") -> bytes:
        try:
            url = "https://openrouter.ai/api/v1/chat/completions"
            
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": model,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "modalities": ["image"]
            }
            
            import requests
            response = requests.post(url, headers=headers, json=payload, timeout=120)
            response.raise_for_status()
            
            result = response.json()
            
            if result.get("choices"):
                message = result["choices"][0]["message"]
                if message.get("images"):
                    for image in message["images"]:
                        image_url = image["image_url"]["url"]
                        if image_url.startswith("data:image"):
                            base64_data = image_url.split(",")[1]
                            return base64.b64decode(base64_data)
                        else:
                            img_response = requests.get(image_url, timeout=60)
                            img_response.raise_for_status()
                            return img_response.content
            
            raise RuntimeError("No image data found in OpenRouter response")
                
        except Exception as e:
            raise RuntimeError(f"OpenRouter API error: {str(e)}")

async def deepseek_brain_analyze(user_prompt: str, api_key: str, context: str = "social media post") -> DesignSpecs:
    system_prompt = """You are an expert design strategist and creative director. 
    Analyze the user's request and provide comprehensive design specifications for image generation.
    
    Return ONLY valid JSON with this exact structure:
    {
        "enhanced_prompt": "Detailed, professional image generation prompt",
        "style": "Art style (e.g., Modern, Minimalist, Corporate, Playful)",
        "color_theme": "Color scheme (e.g., '#1E3A8A and #F59E0B')",
        "font_style": "Font recommendation (e.g., Sans-serif bold, Elegant serif)",
        "font_size": "Hierarchy suggestion (e.g., Headline 72pt, body 24pt)",
        "layout": "Composition layout (e.g., Centered, Split screen)",
        "mood": "Emotional tone (e.g., Professional, Energetic, Festive)",
        "target_audience": "Who this is for",
        "key_elements": ["List", "of", "key", "elements"]
    }"""
    
    user_message = f"""Create detailed design specifications for a {context} with this request:
    
    "{user_prompt}"
    
    Consider cultural context, professional branding, and platform requirements."""
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                "temperature": 0.7
            }
        )
        
        if resp.status_code != 200:
            raise RuntimeError(f"DeepSeek API Error {resp.status_code}")
        
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        
        try:
            import re
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                specs_dict = json.loads(json_match.group())
            else:
                specs_dict = json.loads(content)
                
            return DesignSpecs(
                enhanced_prompt=specs_dict.get("enhanced_prompt", user_prompt),
                style=specs_dict.get("style", "Modern professional"),
                color_theme=specs_dict.get("color_theme", "Professional blue"),
                font_style=specs_dict.get("font_style", "Sans-serif"),
                font_size=specs_dict.get("font_size", "Standard hierarchy"),
                layout=specs_dict.get("layout", "Balanced composition"),
                mood=specs_dict.get("mood", "Professional"),
                target_audience=specs_dict.get("target_audience", "General"),
                key_elements=specs_dict.get("key_elements", ["relevant imagery"])
            )
        except Exception:
            return DesignSpecs(
                enhanced_prompt=user_prompt,
                style="Modern professional",
                color_theme="Professional branding",
                font_style="Sans-serif",
                font_size="Standard",
                layout="Balanced",
                mood="Professional",
                target_audience="General",
                key_elements=["relevant imagery"]
            )

def build_enhanced_prompt(specs: DesignSpecs) -> str:
    return f"{specs.style} {specs.mood} design with {specs.color_theme} colors. {specs.layout} composition. Include: {', '.join(specs.key_elements[:5])}. Main content: {specs.enhanced_prompt}"

async def display_design_specs(specs: DesignSpecs):
    print("\n" + "="*60)
    print("🎨 DESIGN SPECIFICATIONS")
    print("="*60)
    print(f"📝 Prompt: {specs.enhanced_prompt[:200]}...")
    print(f"🎭 Style: {specs.style}")
    print(f"🎨 Colors: {specs.color_theme}")
    print(f"📝 Font: {specs.font_style} ({specs.font_size})")
    print(f"📐 Layout: {specs.layout}")
    print(f"😊 Mood: {specs.mood}")
    print(f"👥 Audience: {specs.target_audience}")
    print("="*60)

async def main():
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_API_KEY2 = os.getenv("GEMINI_API_KEY2", "")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY", "")
    ZAI_API_KEY = os.getenv("ZAI_API_KEY", "")
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
    
    print("\n" + "="*60)
    print("🎨 AI IMAGE GENERATION SYSTEM")
    print("="*60)
    print("\n📌 SUPPORTED PROVIDERS:")
    print("   ✓ Gemini")
    print("   ✓ OpenAI (Responses API - gpt-5.5)")
    print("   ✓ MiniMax")
    print("   ✓ Z.AI (GLM-Image)")
    print("   ✓ OpenRouter (Multiple Models)")
    print("="*60)
    
    print("\n📡 SELECT IMAGE GENERATION PROVIDER:")
    print("-"*50)
    print("1. Gemini")
    print("2. OpenAI (Responses API)")
    print("3. MiniMax")
    print("4. Z.AI (GLM-Image)")
    print("5. OpenRouter")
    print("-"*50)
    
    provider_choice = input("\nYour choice [1-5] (default 1): ").strip() or "1"
    
    # Gemini key selection (only if provider 1 is chosen)
    if provider_choice == "1":
        print("\n🔑 SELECT GEMINI API KEY:")
        print("-"*50)
        print("1. Primary API Key")
        print("2. Secondary API Key")
        print("-"*50)
        
        gemini_key_choice = input("\nYour choice [1-2] (default 1): ").strip() or "1"
        
        if gemini_key_choice == "1":
            api_key = GEMINI_API_KEY
            key_name = "Primary"
        else:
            api_key = GEMINI_API_KEY2
            key_name = "Secondary"
        
        if not api_key:
            print(f"❌ {key_name} GEMINI_API_KEY not found in .env")
            return
        
        print(f"\n✅ Using {key_name} Gemini API Key")
    
    # OpenRouter model selection (only if provider 5 is chosen)
    openrouter_model = None
    if provider_choice == "5":
        print("\n🤖 SELECT OPENROUTER IMAGE MODEL:")
        print("-"*50)
        print("1. google/gemini-2.5-flash-image (Nano Banana)")
        print("2. google/gemini-3.1-flash-image-preview (Nano Banana 2)")
        print("3. openai/gpt-5.4-image-2")
        print("4. black-forest-labs/flux.2-pro")
        print("5. recraft/recraft-v4.1-pro")
        print("-"*50)
        
        model_choice = input("\nYour choice [1-5] (default 1): ").strip() or "1"
        
        model_map = {
            "1": "google/gemini-2.5-flash-image",
            "2": "google/gemini-3.1-flash-image-preview",
            "3": "openai/gpt-5.4-image-2",
            "4": "black-forest-labs/flux.2-pro",
            "5": "recraft/recraft-v4.1-pro"
        }
        openrouter_model = model_map.get(model_choice, "google/gemini-2.5-flash-image")
        print(f"\n✅ Using OpenRouter model: {openrouter_model}")
    
    print("\n📝 DESCRIBE WHAT YOU WANT TO CREATE:")
    print("Example: 'Generate a Bakra Eid LinkedIn post for IT software company'")
    
    try:
        user_prompt = input("\nYour request: ").strip()
    except EOFError:
        print("\n❌ No input received. Please try again and enter your prompt.")
        return
    
    if not user_prompt:
        print("❌ No prompt entered")
        return
    
    use_deepseek = DEEPSEEK_API_KEY and input("\n🧠 Use DeepSeek for design strategy? (y/n, default y): ").strip().lower() != 'n'
    
    if use_deepseek:
        print("\n🧠 Consulting DeepSeek Brain...")
        try:
            specs = await deepseek_brain_analyze(user_prompt, DEEPSEEK_API_KEY)
            await display_design_specs(specs)
            final_prompt = build_enhanced_prompt(specs)
        except Exception as e:
            print(f"⚠️ DeepSeek failed: {e}")
            final_prompt = user_prompt
            specs = None
    else:
        final_prompt = user_prompt
        specs = None
    
    print("\n📐 ASPECT RATIO:")
    print("1. 1:1 (Square)")
    print("2. 3:4 (Portrait)")
    print("3. 16:9 (Landscape)")
    ratio_choice = input("\nChoose [1-3] (default 1): ").strip() or "1"
    
    ratio_map = {"1": "1:1", "2": "3:4", "3": "16:9"}
    aspect_ratio = ratio_map.get(ratio_choice, "1:1")
    
    print(f"\n🎨 GENERATING IMAGE...")
    print(f"📐 Aspect Ratio: {aspect_ratio}")
    
    out_dir = Path(__file__).parent / "generated_images"
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"image_{timestamp}_{uuid.uuid4().hex[:6]}.png"
    out_path = out_dir / filename
    
    try:
        if provider_choice == "1":
            print(f"🖼️ Using Gemini with {key_name} key...")
            image_bytes = await GeminiImageGenerator.generate(final_prompt, api_key, aspect_ratio)
            provider_name = f"Gemini ({key_name} Key)"
                    
        elif provider_choice == "2":
            if not OPENAI_API_KEY:
                print("❌ OPENAI_API_KEY not found in .env")
                return
            
            if not OPENAI_SDK_AVAILABLE:
                print("❌ OpenAI SDK not installed. Run: pip install openai")
                return
            
            print("🖼️ Using OpenAI Responses API with gpt-5.5...")
            image_bytes = await OpenAIImageGenerator.generate(final_prompt, OPENAI_API_KEY, aspect_ratio)
            provider_name = "OpenAI (Responses API - gpt-5.5)"
            
        elif provider_choice == "3":
            if not MINIMAX_API_KEY:
                print("❌ MINIMAX_API_KEY not found in .env")
                return
            
            print("🖼️ Using MiniMax...")
            image_bytes = await MiniMaxGenerator.generate(final_prompt, MINIMAX_API_KEY, aspect_ratio)
            provider_name = "MiniMax"
        
        elif provider_choice == "4":
            if not ZAI_API_KEY:
                print("❌ ZAI_API_KEY not found in .env")
                return
            
            if not ZAI_SDK_AVAILABLE:
                print("❌ Z.AI SDK not installed. Run: pip install zai-sdk")
                return
            
            print("🖼️ Using Z.AI GLM-Image...")
            image_bytes = await ZAIImageGenerator.generate(final_prompt, ZAI_API_KEY, aspect_ratio)
            provider_name = "Z.AI (GLM-Image)"
        
        elif provider_choice == "5":
            if not OPENROUTER_API_KEY:
                print("❌ OPENROUTER_API_KEY not found in .env")
                return
            
            print(f"🖼️ Using OpenRouter with {openrouter_model}...")
            image_bytes = await OpenRouterImageGenerator.generate(final_prompt, OPENROUTER_API_KEY, openrouter_model, aspect_ratio)
            provider_name = f"OpenRouter ({openrouter_model})"
            
        else:
            print("❌ Invalid choice")
            return
        
        out_path.write_bytes(image_bytes)
        
        try:
            img = Image.open(BytesIO(image_bytes))
            print(f"✅ Image verified: {img.size[0]}x{img.size[1]} pixels")
        except:
            pass
        
        print("\n" + "="*60)
        print("✨ SUCCESS! Image Generated ✨")
        print("="*60)
        print(f"🎨 Provider: {provider_name}")
        print(f"📁 Saved: {out_path}")
        print(f"📏 Size: {len(image_bytes):,} bytes ({len(image_bytes)/1024:.1f} KB)")
        print(f"📐 Ratio: {aspect_ratio}")
        
        if specs:
            print("\n💡 Design Specifications Used:")
            print(f"   Style: {specs.style}")
            print(f"   Colors: {specs.color_theme}")
            print(f"   Font: {specs.font_style}")
        
        print("="*60)
        
    except Exception as e:
        print(f"\n❌ Generation Failed: {str(e)}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️ Cancelled by user")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()