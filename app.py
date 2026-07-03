from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS
from dotenv import load_dotenv
from pymongo import MongoClient
from bson import ObjectId
import os, csv, io, json, datetime, threading, queue as queue_module

load_dotenv()

app = Flask(__name__)
CORS(app, origins=["http://localhost:5174", "http://localhost:3000", "https://marketer.agentstacktech.com"])

# MongoDB
mongo = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"))
db = mongo["ai_marketer"]
campaigns_col = db["campaigns"]
audiences_col = db["audiences"]
jobs_col = db["broadcast_jobs"]

# ─── Helpers ────────────────────────────────────────────────────────────────

def oid(doc):
    doc["id"] = str(doc.pop("_id"))
    return doc

def now():
    return datetime.datetime.utcnow().isoformat()

# ─── Campaign Routes ─────────────────────────────────────────────────────────

@app.route("/api/campaign/generate", methods=["POST"])
def generate_campaign():
    """Step 1: Given a prompt, generate all campaign content via Claude."""
    data = request.json or {}
    prompt = data.get("prompt", "").strip()
    brand = data.get("brand_name", "AgentStack")

    if not prompt:
        return jsonify({"error": "prompt is required"}), 400

    try:
        from services.ai_generator import generate_campaign_content
        content = generate_campaign_content(prompt, brand)

        campaign = {
            "prompt": prompt,
            "brand_name": brand,
            "status": "draft",
            "content": content,
            "campaign_name": content.get("campaign_name", "Untitled Campaign"),
            "audience_list_id": None,
            "channels": [],
            "broadcast_results": {},
            "created_at": now(),
            "sent_at": None
        }
        result = campaigns_col.insert_one(campaign)
        campaign["id"] = str(result.inserted_id)
        campaign.pop("_id", None)
        return jsonify(campaign), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/campaign/<campaign_id>", methods=["GET"])
def get_campaign(campaign_id):
    doc = campaigns_col.find_one({"_id": ObjectId(campaign_id)})
    if not doc:
        return jsonify({"error": "not found"}), 404
    return jsonify(oid(doc))


@app.route("/api/campaign/list", methods=["GET"])
def list_campaigns():
    docs = list(campaigns_col.find().sort("created_at", -1).limit(50))
    return jsonify([oid(d) for d in docs])


@app.route("/api/campaign/<campaign_id>", methods=["PATCH"])
def update_campaign(campaign_id):
    """Update campaign content or settings before broadcast."""
    data = request.json or {}
    allowed = ["content", "audience_list_id", "channels", "campaign_name"]
    update = {k: data[k] for k in allowed if k in data}
    if not update:
        return jsonify({"error": "nothing to update"}), 400

    campaigns_col.update_one({"_id": ObjectId(campaign_id)}, {"$set": update})
    doc = campaigns_col.find_one({"_id": ObjectId(campaign_id)})
    return jsonify(oid(doc))


@app.route("/api/campaign/<campaign_id>/broadcast", methods=["POST"])
def broadcast_campaign(campaign_id):
    """Step 3: Broadcast campaign to selected channels."""
    data = request.json or {}
    channels = data.get("channels", [])  # ["email","sms","linkedin","instagram","youtube"]
    audience_list_id = data.get("audience_list_id")

    doc = campaigns_col.find_one({"_id": ObjectId(campaign_id)})
    if not doc:
        return jsonify({"error": "campaign not found"}), 404

    content = doc.get("content", {})

    # Create a broadcast job for async tracking
    job = {
        "campaign_id": campaign_id,
        "channels": channels,
        "audience_list_id": audience_list_id,
        "status": "running",
        "results": {},
        "started_at": now(),
        "finished_at": None
    }
    job_result = jobs_col.insert_one(job)
    job_id = str(job_result.inserted_id)

    # Run broadcast in background thread
    def run_broadcast():
        results = {}

        # Load audience if needed
        audience = []
        if audience_list_id:
            aud_doc = audiences_col.find_one({"_id": ObjectId(audience_list_id)})
            if aud_doc:
                audience = aud_doc.get("records", [])

        # --- Email ---
        if "email" in channels and audience:
            try:
                from services.email_service import send_campaign_emails
                from services.ai_generator import personalize_email
                email_data = content.get("email", {})
                res = send_campaign_emails(
                    recipients=audience,
                    subject=email_data.get("subject", ""),
                    html_body=email_data.get("body_html", ""),
                    text_body=email_data.get("body_text", ""),
                    personalize_fn=personalize_email
                )
                results["email"] = res
            except Exception as e:
                results["email"] = {"error": str(e)}

        # --- SMS ---
        if "sms" in channels and audience:
            try:
                from services.sms_service import send_campaign_sms
                from services.ai_generator import personalize_sms
                sms_data = content.get("sms", {})
                res = send_campaign_sms(
                    recipients=audience,
                    message_template=sms_data.get("message", ""),
                    personalize_fn=personalize_sms
                )
                results["sms"] = res
            except Exception as e:
                results["sms"] = {"error": str(e)}

        # --- LinkedIn ---
        if "linkedin" in channels:
            try:
                from services.linkedin_service import post_text
                li_data = content.get("linkedin", {})
                res = post_text(li_data.get("post", ""))
                results["linkedin"] = res
            except Exception as e:
                results["linkedin"] = {"error": str(e)}

        # --- Instagram ---
        if "instagram" in channels:
            try:
                from services.instagram_service import post_image
                ig_data = content.get("instagram", {})
                # Use a placeholder image if no real image URL is provided
                image_url = data.get("instagram_image_url", "")
                if image_url:
                    res = post_image(image_url, ig_data.get("caption", ""))
                    results["instagram"] = res
                else:
                    results["instagram"] = {"error": "No image URL provided for Instagram post"}
            except Exception as e:
                results["instagram"] = {"error": str(e)}

        # --- Video Generation (D-ID) + YouTube ---
        if "youtube" in channels or "video" in channels:
            try:
                from services.video_service import create_video, wait_for_video
                video_script = content.get("video_script", {})
                full_script = video_script.get("full_script", "")
                if full_script:
                    talk = create_video(full_script)
                    talk_id = talk.get("talk_id")
                    final = wait_for_video(talk_id)
                    results["video"] = final

                    # Upload to YouTube if ready
                    if "youtube" in channels and final.get("result_url"):
                        from services.youtube_service import upload_video_from_url
                        yt_data = content.get("youtube", {})
                        yt_res = upload_video_from_url(
                            video_url=final["result_url"],
                            title=yt_data.get("title", ""),
                            description=yt_data.get("description", ""),
                            tags=yt_data.get("tags", [])
                        )
                        results["youtube"] = yt_res
                else:
                    results["video"] = {"error": "No video script available"}
            except Exception as e:
                results["video"] = {"error": str(e)}
                results["youtube"] = {"error": str(e)}

        # --- Twitter/X ---
        if "twitter" in channels:
            try:
                from services.twitter_service import post_tweet, post_thread
                tw_data = content.get("twitter", {})
                use_thread = data.get("twitter_thread", False)
                if use_thread and tw_data.get("thread"):
                    res = post_thread(tw_data["thread"])
                else:
                    res = post_tweet(tw_data.get("tweet", ""))
                results["twitter"] = res
            except Exception as e:
                results["twitter"] = {"error": str(e)}

        # --- WhatsApp Business ---
        if "whatsapp" in channels and audience:
            try:
                from services.whatsapp_service import send_campaign_messages
                from services.ai_generator import personalize_whatsapp
                wa_data = content.get("whatsapp", {})
                res = send_campaign_messages(
                    recipients=audience,
                    message_template=wa_data.get("message", ""),
                    personalize_fn=personalize_whatsapp
                )
                results["whatsapp"] = res
            except Exception as e:
                results["whatsapp"] = {"error": str(e)}

        # --- Facebook Page ---
        if "facebook" in channels:
            try:
                from services.facebook_service import post_text as fb_post_text
                fb_data = content.get("facebook", {})
                res = fb_post_text(fb_data.get("post", ""))
                results["facebook"] = res
            except Exception as e:
                results["facebook"] = {"error": str(e)}

        # --- Telegram Channel ---
        if "telegram" in channels:
            try:
                from services.telegram_service import send_message as tg_send
                tg_data = content.get("telegram", {})
                res = tg_send(tg_data.get("message", ""))
                results["telegram"] = res
            except Exception as e:
                results["telegram"] = {"error": str(e)}

        # Update job and campaign
        jobs_col.update_one(
            {"_id": ObjectId(job_id)},
            {"$set": {"status": "completed", "results": results, "finished_at": now()}}
        )
        campaigns_col.update_one(
            {"_id": ObjectId(campaign_id)},
            {"$set": {"status": "sent", "broadcast_results": results, "sent_at": now()}}
        )

    thread = threading.Thread(target=run_broadcast, daemon=True)
    thread.start()

    return jsonify({"job_id": job_id, "status": "running", "message": "Broadcast started"}), 202


@app.route("/api/job/<job_id>", methods=["GET"])
def get_job(job_id):
    doc = jobs_col.find_one({"_id": ObjectId(job_id)})
    if not doc:
        return jsonify({"error": "not found"}), 404
    return jsonify(oid(doc))


# ─── Audience Routes ──────────────────────────────────────────────────────────

@app.route("/api/audience/upload", methods=["POST"])
def upload_audience():
    """Upload a CSV audience list. Columns: name, email, phone, company (optional)."""
    name = request.form.get("name", "Audience List")
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "CSV file required"}), 400

    content_str = file.read().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content_str))
    records = []
    for row in reader:
        # Normalize column names
        record = {k.strip().lower(): v.strip() for k, v in row.items()}
        records.append(record)

    doc = {
        "name": name,
        "records": records,
        "count": len(records),
        "created_at": now()
    }
    result = audiences_col.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    doc.pop("_id", None)
    return jsonify(doc), 201


@app.route("/api/audience/list", methods=["GET"])
def list_audiences():
    docs = list(audiences_col.find({}, {"records": 0}).sort("created_at", -1))
    return jsonify([oid(d) for d in docs])


@app.route("/api/audience/<audience_id>", methods=["GET"])
def get_audience(audience_id):
    doc = audiences_col.find_one({"_id": ObjectId(audience_id)})
    if not doc:
        return jsonify({"error": "not found"}), 404
    return jsonify(oid(doc))


@app.route("/api/audience/<audience_id>", methods=["DELETE"])
def delete_audience(audience_id):
    audiences_col.delete_one({"_id": ObjectId(audience_id)})
    return jsonify({"ok": True})


# ─── Integration Test Routes ──────────────────────────────────────────────────

@app.route("/api/integrations/test", methods=["GET"])
def test_all_integrations():
    results = {}
    try:
        from services.email_service import test_connection as email_test
        results["sendgrid"] = email_test()
    except Exception as e:
        results["sendgrid"] = {"ok": False, "error": str(e)}

    try:
        from services.sms_service import test_connection as sms_test
        results["twilio"] = sms_test()
    except Exception as e:
        results["twilio"] = {"ok": False, "error": str(e)}

    try:
        from services.video_service import test_connection as vid_test
        results["did"] = vid_test()
    except Exception as e:
        results["did"] = {"ok": False, "error": str(e)}

    try:
        from services.linkedin_service import test_connection as li_test
        results["linkedin"] = li_test()
    except Exception as e:
        results["linkedin"] = {"ok": False, "error": str(e)}

    try:
        from services.instagram_service import test_connection as ig_test
        results["instagram"] = ig_test()
    except Exception as e:
        results["instagram"] = {"ok": False, "error": str(e)}

    try:
        from services.youtube_service import test_connection as yt_test
        results["youtube"] = yt_test()
    except Exception as e:
        results["youtube"] = {"ok": False, "error": str(e)}

    try:
        from services.twitter_service import test_connection as tw_test
        results["twitter"] = tw_test()
    except Exception as e:
        results["twitter"] = {"ok": False, "error": str(e)}

    try:
        from services.whatsapp_service import test_connection as wa_test
        results["whatsapp"] = wa_test()
    except Exception as e:
        results["whatsapp"] = {"ok": False, "error": str(e)}

    try:
        from services.facebook_service import test_connection as fb_test
        results["facebook"] = fb_test()
    except Exception as e:
        results["facebook"] = {"ok": False, "error": str(e)}

    try:
        from services.telegram_service import test_connection as tg_test
        results["telegram"] = tg_test()
    except Exception as e:
        results["telegram"] = {"ok": False, "error": str(e)}

    return jsonify(results)


# ─── AI Agent Routes ─────────────────────────────────────────────────────────

_agent_queues: dict[str, queue_module.Queue] = {}


@app.route("/api/agent/run", methods=["POST"])
def run_agent():
    data = request.json or {}
    prompt = data.get("prompt", "").strip()
    brand_name = data.get("brand_name", "AgentStack")
    channels = data.get("channels", [])
    audience_id = data.get("audience_id", "")

    if not prompt:
        return jsonify({"error": "prompt is required"}), 400
    if not channels:
        return jsonify({"error": "select at least one channel"}), 400

    audience = []
    if audience_id:
        aud_doc = audiences_col.find_one({"_id": ObjectId(audience_id)})
        if aud_doc:
            audience = aud_doc.get("records", [])

    job_id = str(ObjectId())
    q: queue_module.Queue = queue_module.Queue()
    _agent_queues[job_id] = q

    jobs_col.insert_one({
        "_id": ObjectId(job_id),
        "type": "agent",
        "prompt": prompt,
        "brand_name": brand_name,
        "channels": channels,
        "audience_id": audience_id,
        "status": "running",
        "events": [],
        "started_at": now(),
    })

    def emit(event_type: str, event_data: dict):
        event = {"type": event_type, "data": event_data, "ts": now()}
        q.put(event)
        jobs_col.update_one(
            {"_id": ObjectId(job_id)},
            {"$push": {"events": event}}
        )

    def run():
        try:
            from services.ai_agent import run_campaign_agent
            run_campaign_agent(prompt, brand_name, channels, audience, emit)
        except Exception as exc:
            emit("error", {"message": str(exc)})
        finally:
            q.put(None)  # sentinel — closes the SSE stream
            jobs_col.update_one(
                {"_id": ObjectId(job_id)},
                {"$set": {"status": "completed", "finished_at": now()}}
            )

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"job_id": job_id}), 202


@app.route("/api/agent/stream/<job_id>")
def stream_agent(job_id):
    q = _agent_queues.get(job_id)

    def generate():
        if q is None:
            # Job already done — replay from DB
            job = jobs_col.find_one({"_id": ObjectId(job_id)})
            if job:
                for ev in job.get("events", []):
                    yield f"data: {json.dumps(ev)}\n\n"
            yield 'data: {"type":"end"}\n\n'
            return

        while True:
            try:
                event = q.get(timeout=30)
                if event is None:
                    yield 'data: {"type":"end"}\n\n'
                    _agent_queues.pop(job_id, None)
                    break
                yield f"data: {json.dumps(event)}\n\n"
            except queue_module.Empty:
                yield ": keepalive\n\n"

    return Response(
        stream_with_context(generate()),
        content_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/api/agent/job/<job_id>")
def get_agent_job(job_id):
    job = jobs_col.find_one({"_id": ObjectId(job_id)})
    if not job:
        return jsonify({"error": "not found"}), 404
    job["id"] = str(job.pop("_id"))
    return jsonify(job)


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "AI Marketer Backend"})


if __name__ == "__main__":
    app.run(debug=True, port=5001)
