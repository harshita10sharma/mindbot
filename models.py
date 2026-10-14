from typing import List, Optional

from pydantic import BaseModel, Field


class StartRequest(BaseModel):
    session_id: str = Field(..., max_length=100)


class ChatRequest(BaseModel):
    session_id: str = Field(..., max_length=100)
    query: str = Field(..., max_length=4000)


class AssessmentRequest(BaseModel):
    session_id: str = Field(..., max_length=100)
    answers: List[int]


class MoodRequest(BaseModel):
    session_id: str = Field(..., max_length=100)
    score: int = Field(..., ge=1, le=10, description="1 = very low, 10 = very good")
    note: Optional[str] = Field(None, max_length=500)


class SafetyPlan(BaseModel):
    warning_signs: List[str] = []
    coping_strategies: List[str] = []
    distraction_people_places: List[str] = []
    people_to_ask_for_help: List[str] = []
    professionals: List[str] = []
    safe_environment: List[str] = []
    reasons_for_living: List[str] = []
