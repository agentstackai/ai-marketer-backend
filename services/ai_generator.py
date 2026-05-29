import anthropic
import json
import os

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

SYSTEM_PROMPT = """You are an expert AI digital marketing strategist. Given a campaign prompt,
you generate high-converting, platform-optimized marketing content. Always return valid JSON only."""

def generate_campaign_content(prompt: str, brand_name: str = "AgentStack") -> dict:
    user_message = f"""
Create a complete marketing campaign for the following brief:

CAMPAIGN BRIEF: {prompt}
BRAND: {brand_name}

Generate all of the following content and return as a single JSON object:

{{
  "campaign_name": "Short descriptive name for this campaign",
  "email": {{
    "subject": "Compelling email subject line (max 60 chars)",
    "preview_text": "Email preview text (max 90 chars)",
    "body_html": "Full HTML email body with inline styles, professional layout, compelling CTA button",
    "body_text": "Plain text version of the email"
  }},
  "sms": {{
    "message": "SMS message (max 160 chars, include opt-out: Reply STOP to unsubscribe)"
  }},
  "linkedin": {{
    "post": "LinkedIn post (max 1300 chars, professional tone, include 3-5 relevant hashtags)",
    "image_prompt": "Description of ideal image to accompany this LinkedIn post"
  }},
  "instagram": {{
    "caption": "Instagram caption (engaging, includes 10-15 hashtags at the end)",
    "image_prompt": "Description of ideal image/visual for this Instagram post"
  }},
  "youtube": {{
    "title": "YouTube video title (SEO optimized, max 70 chars)",
    "description": "YouTube video description (300-500 words, include timestamps, links placeholder)",
    "tags": ["tag1", "tag2", "tag3", "...up to 10 tags"],
    "thumbnail_prompt": "Description of ideal YouTube thumbnail"
  }},
  "video_script": {{
    "hook": "Opening 5-second attention grabber",
    "intro": "10-second brand introduction",
    "main_content": "60-second main value proposition and key points",
    "cta": "15-second call to action and outro",
    "full_script": "Complete word-for-word script for the AI presenter to read"
  }},
  "summary": "One-paragraph summary of this campaign strategy"
}}

Make all content compelling, on-brand, and platform-appropriate. Return ONLY the JSON object, no other text."""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}]
    )

    raw = message.content[0].text.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    return json.loads(raw)


def personalize_email(template_html: str, recipient: dict) -> str:
    """Replace {{name}}, {{company}} placeholders in email HTML."""
    result = template_html
    result = result.replace("{{name}}", recipient.get("name", "there"))
    result = result.replace("{{first_name}}", recipient.get("name", "there").split()[0])
    result = result.replace("{{company}}", recipient.get("company", "your company"))
    result = result.replace("{{email}}", recipient.get("email", ""))
    return result


def personalize_sms(template: str, recipient: dict) -> str:
    result = template
    result = result.replace("{{name}}", recipient.get("name", "there").split()[0])
    result = result.replace("{{company}}", recipient.get("company", ""))
    return result
