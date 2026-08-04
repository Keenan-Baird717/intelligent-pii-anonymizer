from fastapi import APIRouter

from app.schemas.anonymize import AnonymizeTextRequest, AnonymizeTextResponse
from app.services.anonymization import anonymize_pasted_text

router = APIRouter()


@router.post("/anonymize/text", response_model=AnonymizeTextResponse)
def anonymize_text_endpoint(request: AnonymizeTextRequest) -> AnonymizeTextResponse:
    return anonymize_pasted_text(request)
