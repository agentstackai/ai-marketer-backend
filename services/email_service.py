import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content, HtmlContent

sg = None

def get_client():
    global sg
    if sg is None:
        sg = SendGridAPIClient(os.getenv("SENDGRID_API_KEY"))
    return sg

def send_campaign_emails(recipients: list, subject: str, html_body: str, text_body: str, personalize_fn=None) -> dict:
    """
    Send campaign emails to a list of recipients.
    recipients: [{"name": str, "email": str, ...}]
    """
    client = get_client()
    from_email = Email(os.getenv("SENDGRID_FROM_EMAIL"), os.getenv("SENDGRID_FROM_NAME", "AI Marketer"))

    results = {"sent": 0, "failed": 0, "errors": []}

    for recipient in recipients:
        try:
            body_html = personalize_fn(html_body, recipient) if personalize_fn else html_body
            body_text = text_body

            message = Mail(
                from_email=from_email,
                to_emails=To(recipient["email"], recipient.get("name", "")),
                subject=subject,
                plain_text_content=body_text,
                html_content=body_html
            )

            response = client.send(message)
            if response.status_code in (200, 202):
                results["sent"] += 1
            else:
                results["failed"] += 1
                results["errors"].append(f"{recipient['email']}: HTTP {response.status_code}")
        except Exception as e:
            results["failed"] += 1
            results["errors"].append(f"{recipient['email']}: {str(e)}")

    return results


def test_connection() -> dict:
    try:
        client = get_client()
        # Validate key by calling the API suppressions endpoint
        response = client.client.suppression.bounces.get()
        return {"ok": True, "status": response.status_code}
    except Exception as e:
        return {"ok": False, "error": str(e)}
