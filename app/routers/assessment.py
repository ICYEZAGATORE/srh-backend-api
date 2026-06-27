"""
app/routers/assessment.py — Pre/post SRH knowledge assessment submission.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session as SASession

from app.database import get_db
from app.models.assessment import Assessment
from app.models.session import Session
from app.schemas.assessment import AssessmentSubmit

router = APIRouter(prefix="/assessment", tags=["Assessment"])

VALID_TYPES = {"pre", "post"}


@router.post("/submit")
def submit_assessment(
    body: AssessmentSubmit, db: SASession = Depends(get_db)
) -> dict:
    if body.type not in VALID_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="type must be 'pre' or 'post'.",
        )

    # Link to the session only if it is a valid, existing UUID.
    session_id = None
    try:
        sid = uuid.UUID(str(body.session_id))
        if db.get(Session, sid) is not None:
            session_id = sid
    except (ValueError, AttributeError, TypeError):
        session_id = None

    assessment = Assessment(
        session_id=session_id,
        type=body.type,
        responses=body.responses,
    )
    db.add(assessment)
    db.commit()

    return {"status": "submitted"}
