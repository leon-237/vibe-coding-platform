"""Create a demo account with courses, questions and quiz history, for local review only.

It uses a fake AI client (no network, no key). Never run it against production.

    DATABASE_URL=sqlite:////tmp/demo.db python scripts/seed_demo.py
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("SECRET_KEY", "demo-secret")

from fastapi.testclient import TestClient  # noqa: E402

from app.ai.client import FakeAIClient, set_ai_client  # noqa: E402
from app.db import Base, create_all, get_engine, init_engine  # noqa: E402
from app.main import app  # noqa: E402

EMAIL = "demo@example.com"
PASSWORD = "demo-parcours"

SUBJECTS = {
    "Mathématiques": ["Dérivées", "Intégrales", "Suites numériques"],
    "Physique": ["Mécanique du point", "Électricité"],
    "Chimie": ["Liaisons chimiques"],
}


def qcm_for(system: str, user: str) -> str:
    # Build plausible questions from the chapter name found in the prompt.
    chapter = user.split("Chapitre : ")[1].split("\n")[0] if "Chapitre : " in user else "le chapitre"
    items = []
    for i in range(3):
        items.append({
            "question": f"Question {i + 1} sur {chapter} : quelle affirmation est exacte ?",
            "choices": [f"Proposition {c} ({chapter})" for c in "ABCD"],
            "answer_index": i % 4,
            "explanation": f"La proposition {'ABCD'[i % 4]} correspond au cours sur {chapter}.",
            "difficulty": "moyen",
        })
    return json.dumps({"questions": items})


def main() -> None:
    init_engine()
    Base.metadata.drop_all(get_engine())
    create_all()
    set_ai_client(FakeAIClient(responder=lambda system, user: qcm_for(system, user)
                               if "QCM" in system else "Explication de démonstration."))

    with TestClient(app) as c:
        token = c.post("/auth/register", json={
            "email": EMAIL, "password": PASSWORD, "first_name": "Leonnel", "last_name": "Mbarga",
            "country": "CM", "establishment": "Université de démonstration",
            "level": "Licence 2", "filiere": "Informatique", "academic_year": "2026-2027",
        }).json()["access_token"]
        h = {"Authorization": f"Bearer {token}"}

        # The demo account is Premium so the daily AI quota never blocks the seeding.
        from datetime import datetime, timedelta
        from sqlalchemy import select
        from sqlalchemy.orm import Session
        from app.models import User
        with Session(get_engine()) as db:
            user = db.scalar(select(User).where(User.email == EMAIL))
            user.plan = "premium"
            user.plan_expires_at = datetime.utcnow() + timedelta(days=365)
            db.commit()


        for name, chapters in SUBJECTS.items():
            subject = c.post("/subjects", json={"name": name, "semester": 1}, headers=h).json()
            for pos, title in enumerate(chapters):
                chapter = c.post(f"/subjects/{subject['id']}/chapters",
                                 json={"title": title, "position": pos}, headers=h).json()
                c.post(f"/chapters/{chapter['id']}/exercises/generate",
                       json={"count": 3, "difficulty": "moyen"}, headers=h)

                # One finished quiz per chapter: alternate correct and wrong answers.
                quiz = c.post("/quizzes", json={"chapter_id": chapter["id"], "count": 3}, headers=h).json()
                if quiz.get("questions"):
                    answers = [{"exercise_id": q["id"], "choice": 0 if i != 1 else 3}
                               for i, q in enumerate(quiz["questions"])]
                    c.post(f"/quizzes/{quiz['session_id']}/submit", json={"answers": answers}, headers=h)

    print(f"Compte de démonstration : {EMAIL} / {PASSWORD}")


if __name__ == "__main__":
    main()
