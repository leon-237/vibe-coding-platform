from app.services.documents import chunk_text, extract_text, EmptyDocument, UnsupportedFile

from conftest import auth, register, update_user


def test_register_normalises_country_and_returns_free_plan(client):
    body = register(client, country="cm")
    assert body["user"]["country"] == "CM"
    assert body["user"]["plan"] == "free"
    assert body["access_token"]


def test_duplicate_email_is_rejected(client):
    register(client)
    response = client.post("/auth/register", json={
        "email": "etudiant@example.com", "password": "motdepasse123",
        "first_name": "A", "last_name": "B", "country": "SN",
    })
    assert response.status_code == 409


def test_unsupported_country_is_rejected(client):
    response = client.post("/auth/register", json={
        "email": "x@example.com", "password": "motdepasse123",
        "first_name": "A", "last_name": "B", "country": "FR",
    })
    assert response.status_code == 422


def test_wrong_password_and_missing_token(client):
    register(client)
    assert client.post("/auth/login", json={"email": "etudiant@example.com", "password": "mauvais"}).status_code == 401
    assert client.get("/me").status_code == 401


def test_profile_update_and_account_deletion(client):
    token = register(client)["access_token"]
    response = client.patch("/me", json={"language": "en", "filiere": "Informatique"}, headers=auth(token))
    assert response.json()["language"] == "en"
    assert client.request("DELETE", "/me", json={"password": "faux"}, headers=auth(token)).status_code == 403
    assert client.request("DELETE", "/me", json={"password": "motdepasse123"}, headers=auth(token)).status_code == 204
    assert client.post("/auth/login", json={"email": "etudiant@example.com", "password": "motdepasse123"}).status_code == 401


def test_free_plan_limits_subjects_to_three(client):
    token = register(client)["access_token"]
    for i in range(3):
        assert client.post("/subjects", json={"name": f"M{i}"}, headers=auth(token)).status_code == 201
    response = client.post("/subjects", json={"name": "M4"}, headers=auth(token))
    assert response.status_code == 402


def test_student_plan_has_no_subject_limit(client):
    from datetime import datetime, timedelta

    token = register(client)["access_token"]
    update_user("etudiant@example.com", plan="etudiant", plan_expires_at=datetime.utcnow() + timedelta(days=10))
    for i in range(5):
        assert client.post("/subjects", json={"name": f"M{i}"}, headers=auth(token)).status_code == 201


def test_expired_plan_falls_back_to_free(client):
    from datetime import datetime, timedelta

    token = register(client)["access_token"]
    update_user("etudiant@example.com", plan="premium", plan_expires_at=datetime.utcnow() - timedelta(days=1))
    me = client.get("/me", headers=auth(token)).json()
    assert me["plan"] == "free"


def test_upload_text_document_creates_chunks(client, student):
    text = ("Une dérivée mesure la variation d'une fonction. " * 60).encode()
    response = client.post(
        "/documents",
        files={"file": ("cours.txt", text, "text/plain")},
        data={"subject_id": student["subject_id"], "chapter_id": student["chapter_id"]},
        headers=auth(student["token"]),
    )
    assert response.status_code == 201, response.text
    assert response.json()["chunks"] >= 2


def test_upload_rejects_unsupported_and_empty_files(client, student):
    headers = auth(student["token"])
    data = {"subject_id": student["subject_id"]}
    bad = client.post("/documents", files={"file": ("x.exe", b"MZ", "application/octet-stream")}, data=data, headers=headers)
    assert bad.status_code == 422
    empty = client.post("/documents", files={"file": ("vide.txt", b"   \n  ", "text/plain")}, data=data, headers=headers)
    assert empty.status_code == 422


def test_document_analysis_is_premium_only(client, student, ai):
    text = b"Cours sur les limites et la continuite des fonctions."
    doc = client.post(
        "/documents", files={"file": ("c.txt", text, "text/plain")},
        data={"subject_id": student["subject_id"]}, headers=auth(student["token"]),
    ).json()
    assert client.post(f"/documents/{doc['id']}/analyze", headers=auth(student["token"])).status_code == 402

    update_user("etudiant@example.com", plan="premium")
    from datetime import datetime, timedelta
    update_user("etudiant@example.com", plan_expires_at=datetime.utcnow() + timedelta(days=5))
    response = client.post(f"/documents/{doc['id']}/analyze", headers=auth(student["token"]))
    assert response.status_code == 200
    assert "analysis" in response.json()


def test_other_users_cannot_see_subjects(client, student):
    other = register(client, email="autre@example.com")["access_token"]
    response = client.get(f"/subjects/{student['subject_id']}", headers=auth(other))
    assert response.status_code == 404


def test_chunk_text_respects_size():
    text = "\n\n".join(f"Paragraphe numero {i} " + "mot " * 80 for i in range(20))
    chunks = chunk_text(text, size=500, overlap=50)
    assert chunks
    assert all(len(c) <= 500 for c in chunks)


def test_extract_text_errors():
    import pytest

    with pytest.raises(UnsupportedFile):
        extract_text("a.xyz", b"data")
    with pytest.raises(EmptyDocument):
        extract_text("a.txt", b"   ")
