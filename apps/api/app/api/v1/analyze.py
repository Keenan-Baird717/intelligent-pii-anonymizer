from fastapi import APIRouter

from app.schemas.analyze import AnalyzeTextRequest, AnalyzeTextResponse
from app.services.analysis import analyze_pasted_text

router = APIRouter()


@router.post("/analyze/text", response_model=AnalyzeTextResponse)
def analyze_text_endpoint(request: AnalyzeTextRequest) -> AnalyzeTextResponse:
    return analyze_pasted_text(request)
