from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from pymongo import MongoClient
from bson import ObjectId
import os, csv, io, json, datetime, threading

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

    return jsonify(results)


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "AI Marketer Backend"})


if __name__ == "__main__":
    app.run(debug=True, port=5001)
