from pydantic import BaseModel, Field


class TranslationRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5_000)
    source_language: str = Field(default="auto", pattern=r"^(auto|[a-z]{2,3}(?:-[A-Z]{2})?)$")
    target_language: str = Field(pattern=r"^[a-z]{2,3}(?:-[A-Z]{2})?$")


class TranslationResponse(BaseModel):
    translated_text: str
    source_language: str
    target_language: str
    provider: str
    is_mock: bool
    latency_ms: float = Field(default=0, ge=0)


class Language(BaseModel):
    code: str
    name: str
