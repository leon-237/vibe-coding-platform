
from app.services.quiz import parse_qcm, sm2_next

from conftest import QCM_JSON, auth, register


def _generate(client, student, count=2):
    response = client.post(
        f"/chapters/{student['chapter_id']}/exercises/generate",
        json={"count": count, "difficulty": "facile"},
        headers=auth(student["token"]),
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_parse_qcm_drops_invalid_questions():
    items = parse_qcm("bla " + QCM_JSON + " fin")
    assert len(items) == 2
    assert all(len(i.choices) == 4 for i in items)


def test_parse_qcm_rejects_garbage():
    assert parse_qcm("pas du json") == []
    assert parse_qcm('{"questions": "nope"}') == []


def test_sm2_schedule():
    ease, interval, reps = sm2_next(2.5, 0, 0, True)
    assert (interval, reps) == (1, 1)
    ease, interval, reps = sm2_next(ease, interval, reps, True)
    assert (interval, reps) == (6, 2)
    ease, interval, reps = sm2_next(ease, interval, reps, False)
    assert (interval, reps) == (1, 0)
    assert ease >= 1.3


def test_generate_then_quiz_then_correction(client, student):
    created = _generate(client, student, count=2)
    assert created["created"] == 2

    quiz = client.post("/quizzes", json={"chapter_id": student["chapter_id"], "count": 2},
                       headers=auth(student["token"])).json()
    assert len(quiz["questions"]) == 2
    assert "answer_index" not in quiz["questions"][0]  # answers are never sent before submission

    answers = []
    for q in quiz["questions"]:
        # the first question's correct answer is index 1 in the fixture
        choice = 1 if "capitale" in q["question"] else 0
        answers.append({"exercise_id": q["id"], "choice": choice})
    result = client.post(f"/quizzes/{quiz['session_id']}/submit", json={"answers": answers},
                         headers=auth(student["token"])).json()

    assert result["total"] == 2
    assert result["correct"] == 1
    assert result["score_percent"] == 50
    assert result["xp_gained"] == 10 + 2
    wrong = [r for r in result["results"] if not r["is_correct"]]
    assert wrong and wrong[0]["explanation"]

    # a wrong answer is queued for review straight away
    due = client.get("/reviews/due", headers=auth(student["token"])).json()
    assert due["due_count"] == 1

    # submitting twice is refused
    again = client.post(f"/quizzes/{quiz['session_id']}/submit", json={"answers": answers},
                        headers=auth(student["token"]))
    assert again.status_code == 409


def test_submit_rejects_foreign_question(client, student):
    _generate(client, student, count=2)
    quiz = client.post("/quizzes", json={"chapter_id": student["chapter_id"], "count": 1},
                       headers=auth(student["token"])).json()
    response = client.post(
        f"/quizzes/{quiz['session_id']}/submit",
        json={"answers": [{"exercise_id": 99999, "choice": 0}]},
        headers=auth(student["token"]),
    )
    assert response.status_code == 422


def test_quiz_without_questions_is_a_conflict(client, student):
    response = client.post("/quizzes", json={"chapter_id": student["chapter_id"]}, headers=auth(student["token"]))
    assert response.status_code == 409


def test_review_answer_reschedules_item(client, student):
    _generate(client, student, count=2)
    quiz = client.post("/quizzes", json={"chapter_id": student["chapter_id"], "count": 2},
                       headers=auth(student["token"])).json()
    client.post(f"/quizzes/{quiz['session_id']}/submit",
                json={"answers": [{"exercise_id": q["id"], "choice": 3} for q in quiz["questions"]]},
                headers=auth(student["token"]))
    due = client.get("/reviews/due", headers=auth(student["token"])).json()["questions"]
    exercise_id = due[0]["id"]
    answer = client.post(f"/reviews/{exercise_id}/answer", json={"choice": 0}, headers=auth(student["token"])).json()
    assert answer["is_correct"] in (True, False)
    assert answer["interval_days"] >= 1
    # answered items leave the due list until their next date
    remaining = client.get("/reviews/due", headers=auth(student["token"])).json()["due_count"]
    assert remaining == 1


def test_evaluation_weekly_limit_for_free_plan(client, student):
    _generate(client, student, count=2)
    body = {"kind": "evaluation", "subject_id": student["subject_id"], "count": 2}
    assert client.post("/quizzes", json=body, headers=auth(student["token"])).status_code == 201
    assert client.post("/quizzes", json=body, headers=auth(student["token"])).status_code == 402


def test_explain_is_cached_and_counts_quota_once(client, student, ai):
    question = "Qu'est-ce qu'une dérivée ?"
    first = client.post("/ai/explain", json={"question": question, "chapter_id": student["chapter_id"]},
                        headers=auth(student["token"])).json()
    second = client.post("/ai/explain", json={"question": question, "chapter_id": student["chapter_id"]},
                         headers=auth(student["token"])).json()
    assert first["cached"] is False
    assert second["cached"] is True
    assert second["answer"] == first["answer"]
    assert len(ai.calls) == 1


def test_free_daily_quota_then_429(client, student):
    for i in range(5):
        r = client.post("/ai/explain", json={"question": f"Question numéro {i} ?"},
                        headers=auth(student["token"]))
        assert r.status_code == 200, r.text
    r = client.post("/ai/explain", json={"question": "Question de trop ?"}, headers=auth(student["token"]))
    assert r.status_code == 429


def test_failed_ai_call_is_not_charged(client, student, ai):
    ai.fail = True
    r = client.post("/ai/explain", json={"question": "Une question qui échoue ?"}, headers=auth(student["token"]))
    assert r.status_code == 503
    ai.fail = False
    for i in range(5):  # full free quota is still available
        assert client.post("/ai/explain", json={"question": f"Autre question {i} ?"},
                           headers=auth(student["token"])).status_code == 200


def test_spend_cap_pauses_ai(client, student, monkeypatch):
    monkeypatch.setenv("DAILY_AI_SPEND_CAP_USD", "0")
    r = client.post("/ai/explain", json={"question": "Quelque chose ?"}, headers=auth(student["token"]))
    assert r.status_code == 503


def test_dashboard_structure(client, student):
    _generate(client, student, count=2)
    quiz = client.post("/quizzes", json={"chapter_id": student["chapter_id"], "count": 2},
                       headers=auth(student["token"])).json()
    client.post(f"/quizzes/{quiz['session_id']}/submit",
                json={"answers": [{"exercise_id": q["id"], "choice": 1} for q in quiz["questions"]]},
                headers=auth(student["token"]))
    dash = client.get("/dashboard", headers=auth(student["token"])).json()
    assert dash["streak_days"] == 1
    assert dash["xp"] > 0
    assert dash["subjects"][0]["questions"] == 2
    assert dash["subjects"][0]["covered_percent"] == 100
    assert "recommendation" in dash


def test_student_cannot_use_another_students_chapter(client, student):
    other = register(client, email="autre@example.com")["access_token"]
    response = client.post(f"/subjects/{student['subject_id']}/chapters", json={"title": "Piratage"},
                           headers=auth(other))
    assert response.status_code == 404
    response = client.post(f"/chapters/{student['chapter_id']}/exercises/generate", json={},
                           headers=auth(other))
    assert response.status_code == 404
