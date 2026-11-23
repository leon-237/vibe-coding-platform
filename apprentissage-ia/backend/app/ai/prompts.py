"""Prompt builders. Answers are requested in the student's language."""
from __future__ import annotations

LANGUAGE_NAMES = {"fr": "français", "en": "English"}


def _lang(code: str) -> str:
    return LANGUAGE_NAMES.get(code, "français")


def explain_prompt(language: str, question: str, context: list[str]) -> tuple[str, str]:
    system = (
        "Tu es un tuteur pédagogique. Explique clairement, reformule si besoin, donne un exemple. "
        f"Réponds en {_lang(language)}. Si le contexte ne suffit pas, dis-le et réponds prudemment. "
        "Ne donne pas de réponse qui ne se base pas sur le cours fourni quand il existe."
    )
    if context:
        ctx = "\n\n---\n\n".join(context)
        user = f"Extraits du cours de l'étudiant :\n{ctx}\n\nQuestion : {question}"
    else:
        user = (
            "Aucun document de cours n'a été fourni par l'étudiant pour cette question.\n\n"
            f"Question : {question}"
        )
    return system, user


def qcm_prompt(
    language: str,
    subject: str,
    chapter: str,
    context: str,
    count: int,
    difficulty: str,
) -> tuple[str, str]:
    system = (
        "Tu rédiges des QCM d'entraînement fiables. Chaque question a exactement quatre choix, "
        "une seule bonne réponse, et une explication courte de la bonne réponse. "
        f"Réponds en {_lang(language)}. Réponds UNIQUEMENT avec un objet JSON de la forme "
        '{"questions":[{"question":"...","choices":["...","...","...","..."],'
        '"answer_index":0,"explanation":"...","difficulty":"facile|moyen|difficile"}]}'
    )
    source = context.strip() or "(pas de document fourni : utilise le programme standard du chapitre)"
    user = (
        f"Matière : {subject}\nChapitre : {chapter}\nDifficulté visée : {difficulty}\n"
        f"Nombre de questions : {count}\n\nSource :\n{source}"
    )
    return system, user


def analysis_prompt(language: str, text: str) -> tuple[str, str]:
    system = (
        "Tu analyses un cours pour un étudiant : plan, notions clés, points à réviser, "
        f"et questions d'approfondissement. Réponds en {_lang(language)}, sous forme de Markdown."
    )
    return system, f"Document :\n{text}"
