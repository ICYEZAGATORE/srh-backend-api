"""
assess.py — GET /api/v1/assess/questions  |  POST /api/v1/assess/submit
Pre- and post-intervention SRH knowledge assessment.
Used to measure knowledge change as per the research design (Objective 3).
"""

from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
import uuid

from app.routers.auth import get_current_user_optional

router = APIRouter(prefix="/assess")


# ── Static question bank ──────────────────────────────────────────────────────
# In production these come from the database; for the demo they are hardcoded.

QUESTIONS = [
    {
        "id": "q1",
        "topic": "contraception",
        "question_en": "Which of the following methods ALSO protects against STIs?",
        "question_rw": "Ni ibuhe buryo bwirinda no kwandura STI?",
        "options_en": ["Contraceptive pill", "Condom", "IUD", "Injection"],
        "options_rw": ["Ibinini byo guturinda", "Kondomu", "IUD", "Urushinge"],
        "correct_index": 1,
    },
    {
        "id": "q2",
        "topic": "reproductive_rights",
        "question_en": "What is the legal age of consent in Rwanda?",
        "question_rw": "Imyaka yo kwemera imibonano mpuzabitsina mu Rwanda ni ingahe?",
        "options_en": ["16", "17", "18", "21"],
        "options_rw": ["16", "17", "18", "21"],
        "correct_index": 2,
    },
    {
        "id": "q3",
        "topic": "STIs",
        "question_en": "How is HIV transmitted?",
        "question_rw": "HIV yandurira ate?",
        "options_en": [
            "Through hugging an infected person",
            "Through sharing food",
            "Through unprotected sex and sharing needles",
            "Through mosquito bites",
        ],
        "options_rw": [
            "Gukurana n'umuntu ufite HIV",
            "Gusangira indyo",
            "Imibonano mpuzabitsina itaborerwa no gukorana imisumari",
            "Kuryamwa n'inzige",
        ],
        "correct_index": 2,
    },
    {
        "id": "q4",
        "topic": "reproductive_rights",
        "question_en": "What does consent mean in a sexual relationship?",
        "question_rw": "Kwemera mu mibonano mpuzabitsina bisobanura iki?",
        "options_en": [
            "Agreement given once is valid forever",
            "A clear and ongoing agreement that can be withdrawn at any time",
            "Silence means yes",
            "Only relevant before marriage",
        ],
        "options_rw": [
            "Kwemera inshuro imwe biryamye igihe cyose",
            "Ivugurura ryeruye kandi rihoraho rishobora gukurwaho igihe cyose",
            "Guceceka bisobanura yego",
            "Bireberana gusa mbere y'ubukwe",
        ],
        "correct_index": 1,
    },
    {
        "id": "q5",
        "topic": "contraception",
        "question_en": "Emergency contraception works best if taken within how many hours?",
        "question_rw": "Gukumira inda y'acil nzira bikora neza niba bifashwe mu masaha angahe?",
        "options_en": ["12 hours", "48 hours", "72 hours", "96 hours"],
        "options_rw": ["Amasaha 12", "Amasaha 48", "Amasaha 72", "Amasaha 96"],
        "correct_index": 2,
    },
]


# ── Schemas ───────────────────────────────────────────────────────────────────

class QuestionOut(BaseModel):
    id: str
    topic: str
    question_en: str
    question_rw: str
    options_en: list[str]
    options_rw: list[str]


class AssessmentSubmit(BaseModel):
    assessment_type: str = Field(
        description="pre | post",
        examples=["pre"],
    )
    answers: dict[str, int] = Field(
        description="Map of question_id to selected option index (0-based).",
        examples=[{"q1": 1, "q2": 2, "q3": 2, "q4": 1, "q5": 2}],
    )
    language: str = Field(default="en", description="en | rw")


class AssessmentResult(BaseModel):
    submission_id: str
    assessment_type: str
    score: int
    total: int
    percentage: float
    correct_answers: dict[str, bool]
    topic_breakdown: dict[str, dict]
    timestamp: str
    message_en: str
    message_rw: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get(
    "/questions",
    response_model=list[QuestionOut],
    summary="Get SRH assessment questions",
    description=(
        "Returns the bilingual SRH knowledge assessment questions. "
        "Call before the intervention (pre-test) and after (post-test) to measure learning."
    ),
)
async def get_questions():
    return [QuestionOut(**{k: v for k, v in q.items() if k != "correct_index"})
            for q in QUESTIONS]


@router.post(
    "/submit",
    response_model=AssessmentResult,
    summary="Submit assessment answers",
    description=(
        "Submit answers to the SRH knowledge assessment. "
        "Returns score, percentage, and per-topic breakdown. "
        "Used to measure pre- vs post-intervention knowledge change (Objective 3)."
    ),
)
async def submit_assessment(
    body: AssessmentSubmit,
    current_user=Depends(get_current_user_optional),
):
    if body.assessment_type not in ("pre", "post"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="assessment_type must be 'pre' or 'post'.",
        )

    correct_map = {q["id"]: q["correct_index"] for q in QUESTIONS}
    topic_map = {q["id"]: q["topic"] for q in QUESTIONS}

    correct_answers = {}
    topic_scores: dict[str, dict] = {}

    for q_id, selected in body.answers.items():
        if q_id not in correct_map:
            continue
        is_correct = selected == correct_map[q_id]
        correct_answers[q_id] = is_correct

        topic = topic_map[q_id]
        if topic not in topic_scores:
            topic_scores[topic] = {"correct": 0, "total": 0}
        topic_scores[topic]["total"] += 1
        if is_correct:
            topic_scores[topic]["correct"] += 1

    score = sum(correct_answers.values())
    total = len(QUESTIONS)
    pct = round(score / total * 100, 1)

    # Add percentage to topic breakdown
    for t in topic_scores.values():
        t["percentage"] = round(t["correct"] / t["total"] * 100, 1)

    if pct >= 80:
        msg_en = "Excellent! You have a strong understanding of SRH topics."
        msg_rw = "Byiza cyane! Ufite ubumenyi bwiza ku bibazo by'ubuzima bw'imororokano."
    elif pct >= 60:
        msg_en = "Good work! Review the topics where you scored lower."
        msg_rw = "Akazi keza! Subiramo ibisubizo ufite amakosa."
    else:
        msg_en = "Keep learning! The platform is here to help you improve."
        msg_rw = "Komeza kwiga! Urubuga ruri hano kugufasha kunoza ubumenyi bwawe."

    return AssessmentResult(
        submission_id=str(uuid.uuid4()),
        assessment_type=body.assessment_type,
        score=score,
        total=total,
        percentage=pct,
        correct_answers=correct_answers,
        topic_breakdown=topic_scores,
        timestamp=datetime.utcnow().isoformat() + "Z",
        message_en=msg_en,
        message_rw=msg_rw,
    )
