"""Survey API — collect responses, generate PDF, send email with attachment."""

import base64
import json
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core.deps import require_role
from app.core.security import TokenPayload, UserRole
from app.services.email_service import send_survey_email
from app.services.survey_pdf_service import generate_survey_pdf

router = APIRouter()

SURVEY_DIR = Path(__file__).parent.parent.parent.parent / "survey_responses"


class SurveySubmission(BaseModel):
    """Survey data with optional PDF attachment."""

    company_name: str = ""
    contact_name: str = ""
    email: str = ""
    phone: str = ""
    summary: str = ""
    pdf_base64: str = ""
    raw_data: dict = {}


@router.post("/")
async def submit_survey(request: Request):
    """Receive survey submission, save to disk, and send email with PDF."""
    data = await request.json()
    data["submitted_at"] = datetime.now(UTC).isoformat()
    data["ip"] = request.client.host if request.client else "unknown"

    # Save to file
    SURVEY_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    company = data.get("company_name", "unknown").replace(" ", "_")[:30]
    filename = f"{timestamp}_{company}.json"

    # Don't save PDF base64 to JSON (too large)
    save_data = {k: v for k, v in data.items() if k != "pdf_base64"}
    with open(SURVEY_DIR / filename, "w") as f:
        json.dump(save_data, f, indent=2, ensure_ascii=False)

    # Generate PDF server-side (ignore client-sent pdf_base64)
    raw = data.get("raw_data", data)
    try:
        pdf_bytes = generate_survey_pdf(raw)
        pdf_b64 = base64.b64encode(pdf_bytes).decode()
    except Exception:
        pdf_b64 = data.get("pdf_base64", "")  # fallback to client PDF

    # Send email with PDF attachment
    from app.services.email_service import email_delivery_enabled

    email_result = {"skipped": "Email provider not configured"}
    if email_delivery_enabled():
        email_result = await send_survey_email(
            to_email="wuqxmark@gmail.com",
            company_name=data.get("company_name", "Unknown"),
            contact_name=data.get("contact_name", "Unknown"),
            contact_email=data.get("email", ""),
            summary=data.get("summary", ""),
            pdf_base64=pdf_b64,
        )

    return JSONResponse(
        {
            "status": "received",
            "id": filename,
            "email": email_result,
        }
    )


@router.get("/responses")
async def list_responses(
    current_user: TokenPayload = Depends(require_role(UserRole.PLATFORM_ADMIN)),
):
    """List all survey responses. Platform admin only."""
    if not SURVEY_DIR.exists():
        return []

    responses = []
    for f in sorted(SURVEY_DIR.glob("*.json"), reverse=True):
        with open(f) as fh:
            data = json.load(fh)
            responses.append(
                {
                    "file": f.name,
                    "company": data.get("company_name", "?"),
                    "email": data.get("email", "?"),
                    "business_type": data.get("business_type", "?"),
                    "timeline": data.get("timeline", "?"),
                    "submitted_at": data.get("submitted_at", "?"),
                }
            )
    return responses
