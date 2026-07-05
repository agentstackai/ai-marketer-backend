"""
Claude-powered campaign agent.
Orchestrates content generation + delivery across all channels via tool use.
"""
import anthropic
import json
import os

def _client():
    return anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

TOOLS = [
    {
        "name": "generate_channel_content",
        "description": (
            "Generate AI marketing content optimized for a specific channel. "
            "Call this once per channel before sending."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "channel": {
                    "type": "string",
                    "enum": ["email", "sms", "linkedin", "instagram", "youtube",
                             "twitter", "whatsapp", "facebook", "telegram"],
                    "description": "Target channel"
                },
                "prompt": {"type": "string", "description": "Campaign brief"},
                "brand_name": {"type": "string", "description": "Brand name"}
            },
            "required": ["channel", "prompt", "brand_name"]
        }
    },
    {
        "name": "create_ai_video",
        "description": (
            "Create an AI presenter video from a script using D-ID. "
            "Returns a result_url when ready. Call before post_to_social for youtube."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "script": {"type": "string", "description": "Full word-for-word script"}
            },
            "required": ["script"]
        }
    },
    {
        "name": "send_emails",
        "description": "Send personalized marketing emails to all audience contacts via SendGrid.",
        "input_schema": {
            "type": "object",
            "properties": {
                "subject": {"type": "string"},
                "body_html": {"type": "string", "description": "Full HTML email body with inline styles"},
                "body_text": {"type": "string", "description": "Plain text fallback"}
            },
            "required": ["subject", "body_html", "body_text"]
        }
    },
    {
        "name": "send_sms",
        "description": "Send SMS messages to all audience contacts via Twilio (max 160 chars).",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "SMS body (max 160 chars, include STOP opt-out)"}
            },
            "required": ["message"]
        }
    },
    {
        "name": "send_whatsapp",
        "description": "Send WhatsApp messages to all audience contacts via Meta Business API.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "WhatsApp message (max 300 chars, emoji ok)"}
            },
            "required": ["message"]
        }
    },
    {
        "name": "post_to_social",
        "description": "Post content to a social media platform (LinkedIn, Instagram, Twitter/X, Facebook, Telegram, YouTube).",
        "input_schema": {
            "type": "object",
            "properties": {
                "platform": {
                    "type": "string",
                    "enum": ["linkedin", "instagram", "twitter", "facebook", "telegram", "youtube"]
                },
                "content": {"type": "string", "description": "Post text / caption"},
                "thread": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Array of tweet strings for a Twitter thread (optional)"
                },
                "video_url": {"type": "string", "description": "Video URL (required for YouTube)"},
                "title": {"type": "string", "description": "Video title (YouTube)"},
                "description": {"type": "string", "description": "Video description (YouTube)"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Video tags (YouTube)"},
                "image_url": {"type": "string", "description": "Image URL (Instagram)"}
            },
            "required": ["platform", "content"]
        }
    }
]

SYSTEM_PROMPT = """You are an AI marketing campaign orchestrator. Execute a full multi-channel campaign end-to-end.

Workflow:
1. Call generate_channel_content for EACH selected channel (one call per channel)
2. If 'youtube' is a channel, call create_ai_video with the full_script from the youtube content
3. Send/post to every channel:
   - email → send_emails (pass subject, body_html, body_text from generated content)
   - sms → send_sms (pass the message)
   - whatsapp → send_whatsapp (pass the message)
   - linkedin → post_to_social platform=linkedin (pass the post text)
   - instagram → post_to_social platform=instagram (pass caption; image_url optional)
   - twitter → post_to_social platform=twitter (pass content + thread array for threading)
   - facebook → post_to_social platform=facebook (pass the post text)
   - telegram → post_to_social platform=telegram (pass the message)
   - youtube → post_to_social platform=youtube (pass video_url from create_ai_video, plus title/description/tags)
4. End with a concise summary of what was sent to each channel.

Cover every selected channel. Do not skip any."""


def _generate_single_channel(channel: str, prompt: str, brand_name: str) -> dict:
    """Secondary Claude call to generate focused per-channel content."""
    specs = {
        "email": 'Return JSON: {"subject":"...","preview_text":"...","body_html":"full HTML with inline styles and CTA","body_text":"plain text version"}',
        "sms": 'Return JSON: {"message":"max 160 chars, include: Reply STOP to unsubscribe"}',
        "linkedin": 'Return JSON: {"post":"professional, max 1300 chars, 3-5 hashtags","image_prompt":"visual description"}',
        "instagram": 'Return JSON: {"caption":"engaging, 10-15 hashtags at end","image_prompt":"visual description"}',
        "youtube": 'Return JSON: {"title":"SEO title max 70 chars","description":"300 words with timestamps","tags":["tag1","tag2"],"video_script":{"hook":"5s opener","intro":"10s intro","main_content":"60s value prop","cta":"15s outro","full_script":"complete word-for-word script"}}',
        "twitter": 'Return JSON: {"tweet":"max 280 chars, 2-3 hashtags","thread":["tweet 1 hook","tweet 2 value","tweet 3 CTA with hashtags"]}',
        "whatsapp": 'Return JSON: {"message":"conversational, emoji ok, max 300 chars, no markdown bold"}',
        "facebook": 'Return JSON: {"post":"story-led 2-3 paragraphs, 3-5 hashtags at end","image_prompt":"visual description"}',
        "telegram": 'Return JSON: {"message":"Markdown ok (*bold*), bullet points with -, max 500 chars, end with [Learn more](URL)"}',
    }

    resp = _client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        messages=[{
            "role": "user",
            "content": (
                f"Generate {channel.upper()} marketing content.\n\n"
                f"BRIEF: {prompt}\nBRAND: {brand_name}\n\n"
                f"{specs.get(channel, 'Return JSON with appropriate content.')}\n\n"
                "Return ONLY valid JSON, no markdown fences."
            )
        }]
    )

    raw = resp.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


def _execute_tool(name: str, inp: dict, audience: list, video_cache: dict) -> dict:
    if name == "generate_channel_content":
        return _generate_single_channel(inp["channel"], inp["prompt"], inp.get("brand_name", "AgentStack"))

    if name == "create_ai_video":
        from services.video_service import create_video, wait_for_video
        result = create_video(inp["script"])
        talk_id = result.get("talk_id")
        if not talk_id:
            return result
        final = wait_for_video(talk_id, max_wait=180)
        if final.get("result_url"):
            video_cache["url"] = final["result_url"]
        return final

    if name == "send_emails":
        if not audience:
            return {"sent": 0, "failed": 0, "note": "No audience list loaded"}
        from services.email_service import send_campaign_emails
        from services.ai_generator import personalize_email
        return send_campaign_emails(
            recipients=audience,
            subject=inp["subject"],
            html_body=inp["body_html"],
            text_body=inp.get("body_text", ""),
            personalize_fn=personalize_email,
        )

    if name == "send_sms":
        if not audience:
            return {"sent": 0, "failed": 0, "note": "No audience list loaded"}
        from services.sms_service import send_campaign_sms
        from services.ai_generator import personalize_sms
        return send_campaign_sms(
            recipients=audience,
            message_template=inp["message"],
            personalize_fn=personalize_sms,
        )

    if name == "send_whatsapp":
        if not audience:
            return {"sent": 0, "failed": 0, "note": "No audience list loaded"}
        from services.whatsapp_service import send_campaign_messages
        from services.ai_generator import personalize_whatsapp
        return send_campaign_messages(
            recipients=audience,
            message_template=inp["message"],
            personalize_fn=personalize_whatsapp,
        )

    if name == "post_to_social":
        platform = inp["platform"]
        content = inp["content"]

        if platform == "linkedin":
            from services.linkedin_service import post_text
            return post_text(content)

        if platform == "instagram":
            from services.instagram_service import post_image
            image_url = inp.get("image_url", "")
            if not image_url:
                return {"ok": False, "note": "No image URL — Instagram post skipped. Provide image_url to publish."}
            return post_image(image_url, content)

        if platform == "twitter":
            from services.twitter_service import post_tweet, post_thread
            thread = inp.get("thread")
            if thread and len(thread) > 1:
                return post_thread(thread)
            return post_tweet(content)

        if platform == "facebook":
            from services.facebook_service import post_text as fb_post
            return fb_post(content)

        if platform == "telegram":
            from services.telegram_service import send_message
            return send_message(content)

        if platform == "youtube":
            video_url = inp.get("video_url") or video_cache.get("url")
            if not video_url:
                return {"ok": False, "note": "No video URL. Call create_ai_video first."}
            from services.youtube_service import upload_video_from_url
            return upload_video_from_url(
                video_url=video_url,
                title=inp.get("title", content[:70]),
                description=inp.get("description", content),
                tags=inp.get("tags", []),
            )

        return {"error": f"Unknown platform: {platform}"}

    return {"error": f"Unknown tool: {name}"}


def run_campaign_agent(prompt: str, brand_name: str, channels: list, audience: list, emit):
    """
    Run the Claude campaign agent synchronously.
    Call from a background thread. emit(event_type, data) is called for each event.
    """
    video_cache = {}
    audience_note = f"{len(audience)} contacts" if audience else "no audience (social channels only)"

    messages = [{
        "role": "user",
        "content": (
            f"Launch a complete marketing campaign.\n\n"
            f"BRIEF: {prompt}\n"
            f"BRAND: {brand_name}\n"
            f"CHANNELS: {', '.join(channels)}\n"
            f"AUDIENCE: {audience_note}\n\n"
            "Generate channel-specific content and execute the full campaign now."
        )
    }]

    emit("start", {"message": f"Agent starting — {len(channels)} channels: {', '.join(channels)}"})

    for _ in range(25):  # max iterations guard
        response = _client().messages.create(
            model="claude-sonnet-4-6",
            max_tokens=8096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        messages.append({"role": "assistant", "content": response.content})

        for block in response.content:
            if getattr(block, "type", None) == "text" and block.text.strip():
                emit("thought", {"message": block.text.strip()})

        if response.stop_reason == "end_turn":
            emit("done", {"message": "Campaign launched successfully across all channels!"})
            return

        if response.stop_reason != "tool_use":
            emit("done", {"message": f"Agent finished: {response.stop_reason}"})
            return

        tool_results = []
        for block in response.content:
            if getattr(block, "type", None) != "tool_use":
                continue

            emit("tool_start", {"tool": block.name, "input": block.input})

            try:
                result = _execute_tool(block.name, block.input, audience, video_cache)
                emit("tool_done", {"tool": block.name, "result": result})
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result),
                })
            except Exception as exc:
                emit("tool_error", {"tool": block.name, "error": str(exc)})
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps({"error": str(exc)}),
                    "is_error": True,
                })

        messages.append({"role": "user", "content": tool_results})

    emit("done", {"message": "Agent reached max iterations — check results above."})
