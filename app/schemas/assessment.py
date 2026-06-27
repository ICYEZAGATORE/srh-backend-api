"""
app/schemas/assessment.py — Request schema for the /assessment endpoint.
"""

from pydantic import BaseModel, Field


class AssessmentSubmit(BaseModel):
    session_id: str = Field(..., description="Anonymous session UUID.")
    type: str = Field(..., description="Assessment type: 'pre' or 'post'.")
    responses: list[dict] = Field(
        ...,
        description="List of answers, e.g. [{'question_id': 'q1', 'answer': 'B'}].",
    )
