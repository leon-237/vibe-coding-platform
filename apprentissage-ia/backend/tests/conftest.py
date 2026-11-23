import os
import sys
import tempfile
from pathlib import Path

# Configure the environment BEFORE the app is imported.
_TMP = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP}/test.db"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["DAILY_AI_SPEND_CAP_USD"] = "1000"
os.environ["PUBLIC_APP_URL"] = "https://app.test"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.ai.client import FakeAIClient, set_ai_client  # noqa: E402
from app.db import Base, create_all, get_engine, init_engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User  # noqa: E402
from app.payments import set_payment_provider  # noqa: E402
from app.payments.sandbox import SandboxProvider  # noqa: E402

QCM_JSON = json.dumps({
    "questions": [
        {
            "question": "Quelle est la capitale du Cameroun ?",
            "choices": ["Douala", "Yaoundé", "Garoua", "Bafoussam"],
            "answer_index": 1,
            "explanation": "Yaoundé est la capitale politique.",
            "difficulty": "facile",
        },
        {
            "question": "Combien font 2 + 2 ?",
            "choices": ["3", "4", "5", "6"],
            "answer_index": 1,
            "explanation": "2 + 2 = 4.",
            "difficulty": "facile",
        },
        {  # invalid: only three choices -> must be dropped
            "question": "Question invalide ?",
            "choices": ["a", "b", "c"],
            "answer_index": 0,
            "explanation": "x",
        },
    ]
})


def default_responder(system: str, user: str) -> str:
    if "QCM" in system:
        return "Voici les questions :\n" + QCM_JSON
    return f"Explication de test pour : {user[-40:]}"


@pytest.fixture
def ai():
    fake = FakeAIClient(responder=default_responder)
    set_ai_client(fake)
    yield fake
    set_ai_client(None)


@pytest.fixture
def sandbox():
    provider = SandboxProvider()
    set_payment_provider(provider)
    yield provider
    set_payment_provider(None)


@pytest.fixture
def client(ai, sandbox):
    init_engine()
    Base.metadata.drop_all(get_engine())
    create_all()
    with TestClient(app) as c:
        yield c


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def register(client, email="etudiant@example.com", country="CM", **extra) -> dict:
    body = {
        "email": email,
        "password": "motdepasse123",
        "first_name": "Awa",
        "last_name": "Diallo",
        "country": country,
        **extra,
    }
    response = client.post("/auth/register", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def login_token(client, email="etudiant@example.com") -> str:
    response = client.post("/auth/login", json={"email": email, "password": "motdepasse123"})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def update_user(email: str, **fields) -> None:
    with Session(get_engine()) as db:
        user = db.scalar(select(User).where(User.email == email))
        for key, value in fields.items():
            setattr(user, key, value)
        db.commit()


def user_row(email: str) -> User:
    with Session(get_engine()) as db:
        return db.scalar(select(User).where(User.email == email))


@pytest.fixture
def student(client):
    """A registered free-plan student with a ready chapter."""
    info = register(client)
    token = info["access_token"]
    subject = client.post("/subjects", json={"name": "Maths", "semester": 1}, headers=auth(token)).json()
    chapter = client.post(
        f"/subjects/{subject['id']}/chapters", json={"title": "Dérivées"}, headers=auth(token)
    ).json()
    return {"token": token, "subject_id": subject["id"], "chapter_id": chapter["id"], "email": "etudiant@example.com"}
