import json

from conftest import auth, register, update_user, user_row

from app.catalog import price_for


def _checkout(client, token, product="etudiant_monthly", promo=None):
    body = {"product": product}
    if promo:
        body["promo_code"] = promo
    response = client.post("/billing/checkout", json=body, headers=auth(token))
    assert response.status_code == 201, response.text
    return response.json()


def _webhook(client, sandbox, tx_ref, *, valid=True):
    body = json.dumps({"event": "charge.completed", "data": {"tx_ref": tx_ref}}).encode()
    signature = sandbox.sign(body) if valid else "mauvaise-signature"
    return client.post(
        "/billing/webhooks/sandbox",
        content=body,
        headers={"content-type": "application/json", "x-sandbox-signature": signature},
    )


def test_prices_are_per_country_and_in_local_currency(client):
    token = register(client, country="CM")["access_token"]
    cm = client.get("/billing/catalog", headers=auth(token)).json()
    assert cm["currency"] == "XAF"
    sn = client.get("/billing/catalog?country=SN", headers=auth(token)).json()
    assert sn["currency"] == "XOF"
    prices = {p["code"]: p["price"] for p in cm["products"]}
    assert prices["etudiant_monthly"] == 3500
    assert prices["etudiant_annual"] == 16500
    assert prices["premium_monthly"] == 7000
    assert price_for("SN", "etudiant_monthly") == 3500


def test_checkout_then_signed_webhook_activates_plan_once(client, sandbox):
    token = register(client)["access_token"]
    checkout = _checkout(client, token, "etudiant_monthly")
    assert checkout["payment_link"].startswith("https://")
    assert checkout["currency"] == "XAF"

    # the provider reports the payment as successful
    sandbox.simulate_payment(checkout["tx_ref"])
    response = _webhook(client, sandbox, checkout["tx_ref"])
    assert response.status_code == 200
    assert response.json()["status"] == "succeeded"

    sub = client.get("/billing/subscription", headers=auth(token)).json()
    assert sub["plan"] == "etudiant"
    assert sub["expires_at"] is not None

    # replaying the same notification changes nothing
    _webhook(client, sandbox, checkout["tx_ref"])
    assert client.get("/billing/subscription", headers=auth(token)).json()["plan"] == "etudiant"


def test_webhook_with_bad_signature_is_refused(client, sandbox):
    token = register(client)["access_token"]
    checkout = _checkout(client, token)
    sandbox.simulate_payment(checkout["tx_ref"])
    assert _webhook(client, sandbox, checkout["tx_ref"], valid=False).status_code == 401
    assert user_row("etudiant@example.com").plan == "free"


def test_pending_payment_is_not_granted(client, sandbox):
    token = register(client)["access_token"]
    checkout = _checkout(client, token)
    status = client.get(f"/billing/payments/{checkout['tx_ref']}", headers=auth(token)).json()
    assert status["status"] == "pending"
    assert user_row("etudiant@example.com").plan == "free"


def test_polling_reconciles_without_webhook(client, sandbox):
    token = register(client)["access_token"]
    checkout = _checkout(client, token, "premium_monthly")
    sandbox.simulate_payment(checkout["tx_ref"])
    status = client.get(f"/billing/payments/{checkout['tx_ref']}", headers=auth(token)).json()
    assert status["status"] == "succeeded"
    assert status["subscription"]["plan"] == "premium"


def test_amount_mismatch_is_never_granted(client, sandbox):
    token = register(client)["access_token"]
    checkout = _checkout(client, token, "etudiant_monthly")
    tx = sandbox.transactions[checkout["tx_ref"]]
    sandbox.transactions[checkout["tx_ref"]] = type(tx)("successful", 100, tx.currency, tx.provider_tx_id)
    status = client.get(f"/billing/payments/{checkout['tx_ref']}", headers=auth(token)).json()
    assert status["status"] == "failed"
    assert user_row("etudiant@example.com").plan == "free"


def test_credit_pack_grants_credits_and_unlocks_ai_after_quota(client, sandbox, student):
    for i in range(5):  # use up the free quota
        assert client.post("/ai/explain", json={"question": f"Question {i} ?"},
                           headers=auth(student["token"])).status_code == 200
    assert client.post("/ai/explain", json={"question": "Bloquée ?"},
                       headers=auth(student["token"])).status_code == 429

    checkout = _checkout(client, student["token"], "credits_100")
    sandbox.simulate_payment(checkout["tx_ref"])
    client.get(f"/billing/payments/{checkout['tx_ref']}", headers=auth(student["token"]))
    assert user_row("etudiant@example.com").ai_credits == 100

    assert client.post("/ai/explain", json={"question": "Maintenant ok ?"},
                       headers=auth(student["token"])).status_code == 200
    assert user_row("etudiant@example.com").ai_credits == 99


def test_promo_code_applies_discount_and_is_counted(client, sandbox):
    admin_token = register(client, email="admin@example.com")["access_token"]
    update_user("admin@example.com", is_admin=True)
    promo = client.post("/admin/promo-codes", json={"code": "rentree10", "percent_off": 10},
                        headers=auth(admin_token))
    assert promo.status_code == 201

    token = register(client)["access_token"]
    checkout = _checkout(client, token, "credits_100", promo="RENTREE10")
    assert checkout["discount"] == 100
    assert checkout["amount"] == 900

    sandbox.simulate_payment(checkout["tx_ref"])
    client.get(f"/billing/payments/{checkout['tx_ref']}", headers=auth(token))
    listing = client.get("/admin/summary", headers=auth(admin_token)).json()
    assert listing["revenue"][0]["amount"] == 900


def test_invalid_promo_code_is_refused(client):
    token = register(client)["access_token"]
    response = client.post("/billing/checkout", json={"product": "etudiant_monthly", "promo_code": "NOPE"},
                           headers=auth(token))
    assert response.status_code == 422


def test_admin_endpoints_are_restricted(client):
    token = register(client)["access_token"]
    assert client.get("/admin/summary", headers=auth(token)).status_code == 403


def test_admin_summary_and_suspension(client, sandbox):
    admin_token = register(client, email="admin@example.com")["access_token"]
    update_user("admin@example.com", is_admin=True)
    student_token = register(client)["access_token"]

    summary = client.get("/admin/summary", headers=auth(admin_token)).json()
    assert summary["users_by_plan"]["free"] == 2
    assert "estimated_margin_before_fees_fcfa" in summary

    student_id = user_row("etudiant@example.com").id
    client.post(f"/admin/users/{student_id}/suspend", json={"suspended": True}, headers=auth(admin_token))
    assert client.get("/me", headers=auth(student_token)).status_code == 403
    assert client.post("/auth/login", json={"email": "etudiant@example.com", "password": "motdepasse123"}).status_code == 403
