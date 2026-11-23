"""Operator commands. Usage (from the backend folder):

    python -m app.cli make-admin admin@example.com
    python -m app.cli create-tables
"""
from __future__ import annotations

import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import create_all, get_engine
from .models import User


def make_admin(email: str) -> None:
    with Session(get_engine()) as db:
        user = db.scalar(select(User).where(User.email == email.lower()))
        if user is None:
            raise SystemExit(f"Aucun utilisateur avec l'e-mail {email}")
        user.is_admin = True
        db.commit()
        print(f"{email} est maintenant administrateur")


def main(argv: list[str]) -> None:
    if len(argv) >= 2 and argv[0] == "make-admin":
        make_admin(argv[1])
    elif argv == ["create-tables"]:
        create_all()
        print("Tables créées")
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
