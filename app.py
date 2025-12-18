import json
import os
from datetime import datetime
from io import BytesIO

import qrcode
from flask import (
    Flask, render_template, request, redirect, url_for, session,
    send_file, jsonify
)

from sqlalchemy import (
    create_engine, Column, BigInteger, Integer, String, Boolean,
    DateTime, ForeignKey, func
)
from sqlalchemy.orm import sessionmaker, declarative_base


# -----------------------------
# Flask
# -----------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")


# -----------------------------
# DB (Postgres via DATABASE_URL) - robusto per Render
# -----------------------------
DATABASE_URL = os.getenv("DATABASE_URL")

# pulizia (evita virgolette/spazi messi per sbaglio su Render)
if DATABASE_URL:
    DATABASE_URL = DATABASE_URL.strip().strip('"').strip("'")

# compatibilità (alcuni provider danno postgres://)
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

Base = declarative_base()


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    group_code = Column(String, nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class QuizAnswer(Base):
    __tablename__ = "quiz_answers"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    attempt_id = Column(BigInteger, ForeignKey("quiz_attempts.id"), nullable=False)
    group_code = Column(String, nullable=False)
    question_id = Column(Integer, nullable=False)
    selected_index = Column(Integer, nullable=False)
    is_correct = Column(Boolean, nullable=False)
    answered_at = Column(DateTime, default=datetime.utcnow, nullable=False)


engine = None
SessionDB = None

try:
    if DATABASE_URL:
        # come nel tuo progetto “che funziona”
        engine = create_engine(DATABASE_URL)
        Base.metadata.create_all(engine)
        SessionDB = sessionmaker(bind=engine)
except Exception as e:
    # Non facciamo morire l'app: parte senza stats
    print("❌ DB init error. Controlla DATABASE_URL su Render.")
    print("❌ DATABASE_URL prefix:", (DATABASE_URL or "")[:30] + "...")
    print("❌ Exception:", repr(e))
    engine = None
    SessionDB = None


# -----------------------------
# Questions + Groups
# -----------------------------
def load_questions():
    with open("questions.json", "r", encoding="utf-8") as f:
        return json.load(f)


QUESTIONS = load_questions()

GROUPS = {
    "tamburi": [1, 2],
    "chiarine": [3, 4, 5, 6, 7, 8, 9],
    "tamburi_giudizioGrande": [10, 11, 12],
    "chiarine_giudizioGrande": [13, 14, 15],
    "coreografia": [16, 17, 18],
}

QMAP = {int(q["id"]): q for q in QUESTIONS}


# -----------------------------
# Helpers DB
# -----------------------------
def create_attempt(group_code: str):
    """Crea un tentativo e ritorna attempt_id (o None se DB non configurato)."""
    if not SessionDB:
        return None
    db = SessionDB()
    try:
        a = QuizAttempt(group_code=group_code)
        db.add(a)
        db.commit()
        db.refresh(a)
        return a.id
    finally:
        db.close()


def save_answer(attempt_id: int, group_code: str, question_id: int, selected_index: int, is_correct: bool):
    """Salva una risposta (no-op se DB non configurato o attempt_id None)."""
    if not SessionDB or attempt_id is None:
        return
    db = SessionDB()
    try:
        row = QuizAnswer(
            attempt_id=attempt_id,
            group_code=group_code,
            question_id=question_id,
            selected_index=selected_index,
            is_correct=is_correct,
        )
        db.add(row)
        db.commit()
    finally:
        db.close()


# -----------------------------
# Routes: Home + Full quiz
# -----------------------------
@app.get("/")
def index():
    return render_template("index.html", total=len(QUESTIONS))


@app.post("/start")
def start():
    session.clear()
    session["q_ids"] = [int(q["id"]) for q in QUESTIONS]
    session["idx"] = 0
    session["score"] = 0
    session["wrong"] = []
    session["group_code"] = "full"
    session["attempt_id"] = create_attempt("full")
    return redirect(url_for("quiz"))


# -----------------------------
# Routes: Group landing + start
# -----------------------------
@app.get("/g/<group_code>")
def group_landing(group_code):
    if group_code not in GROUPS:
        return "Gruppo non valido", 404

    q_ids = GROUPS[group_code]
    title = f"Quiz Regolamento {group_code.replace('_', ' ').capitalize()}"
    return render_template("group.html", title=title, total=len(q_ids), group_code=group_code)


@app.post("/g/<group_code>/start")
def start_group(group_code):
    if group_code not in GROUPS:
        return "Gruppo non valido", 404

    session.clear()
    session["q_ids"] = GROUPS[group_code]
    session["idx"] = 0
    session["score"] = 0
    session["wrong"] = []
    session["group_code"] = group_code
    session["attempt_id"] = create_attempt(group_code)

    return redirect(url_for("quiz"))


# -----------------------------
# Routes: QR (dinamici)
# -----------------------------
@app.get("/qr/<group_code>.png")
def qr_png(group_code):
    if group_code not in GROUPS:
        return "Gruppo non valido", 404

    base = request.host_url.rstrip("/")
    target = f"{base}/g/{group_code}"

    img = qrcode.make(target)
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


@app.get("/qr/<group_code>")
def qr_page(group_code):
    if group_code not in GROUPS:
        return "Gruppo non valido", 404

    base = request.host_url.rstrip("/")
    target = f"{base}/g/{group_code}"

    return f"""
    <!doctype html>
    <html>
    <head><meta name="viewport" content="width=device-width, initial-scale=1"></head>
    <body style="margin:0;display:flex;align-items:center;justify-content:center;min-height:100vh;font-family:Arial;background:#111;color:#fff;">
      <div style="text-align:center;padding:24px;">
        <h1 style="margin:0 0 16px 0;">{group_code.upper()}</h1>
        <img src="/qr/{group_code}.png" style="width:360px;max-width:90vw;background:#fff;padding:12px;border-radius:16px;">
        <p style="opacity:.85;margin-top:16px;">Link dentro al QR:</p>
        <p style="word-break:break-all;opacity:.9;margin-top:6px;">{target}</p>
      </div>
    </body>
    </html>
    """


# -----------------------------
# Routes: Quiz flow
# -----------------------------
@app.get("/quiz")
def quiz():
    q_ids = session.get("q_ids")
    if not q_ids:
        return redirect(url_for("index"))

    idx = session.get("idx", 0)
    if idx >= len(q_ids):
        return redirect(url_for("result"))

    q = QMAP[int(q_ids[idx])]
    feedback = session.pop("feedback", None)
    return render_template("quiz.html", q=q, idx=idx, total=len(q_ids), feedback=feedback)


@app.post("/answer")
def answer():
    q_ids = session.get("q_ids")
    if not q_ids:
        return redirect(url_for("index"))

    idx = session.get("idx", 0)
    if idx >= len(q_ids):
        return redirect(url_for("result"))

    q = QMAP[int(q_ids[idx])]

    selected = request.form.get("choice")
    if selected is None:
        session["feedback"] = {"ok": False, "msg": "Seleziona una risposta."}
        return redirect(url_for("quiz"))

    selected = int(selected)
    ok = (selected == int(q["answer_index"]))

    if ok:
        session["score"] = session.get("score", 0) + 1
    else:
        wrong = session.get("wrong", [])
        wrong.append(int(q["id"]))
        session["wrong"] = wrong

    # salva in DB
    save_answer(
        attempt_id=session.get("attempt_id"),
        group_code=session.get("group_code", "unknown"),
        question_id=int(q["id"]),
        selected_index=selected,
        is_correct=ok,
    )

    session["feedback"] = {
        "ok": ok,
        "correct": int(q["answer_index"]),
        "explanation": q.get("explanation", "")
    }

    return redirect(url_for("quiz"))


@app.post("/next")
def next_q():
    session["idx"] = session.get("idx", 0) + 1
    return redirect(url_for("quiz"))


@app.get("/result")
def result():
    q_ids = session.get("q_ids", [])
    score = session.get("score", 0)
    wrong_ids = set(session.get("wrong", []))
    wrong_qs = [QMAP[int(qid)] for qid in q_ids if int(qid) in wrong_ids]

    return render_template(
        "result.html",
        score=score,
        total=len(q_ids),
        wrong_qs=wrong_qs
    )


@app.post("/reset")
def reset():
    session.clear()
    return redirect(url_for("index"))


# -----------------------------
# Stats: API + Page
# -----------------------------
@app.get("/api/stats/<group_code>")
def api_stats(group_code):
    if group_code not in GROUPS:
        return jsonify({"error": "Gruppo non valido"}), 404
    if not SessionDB:
        return jsonify({"error": "DB non configurato"}), 500

    db = SessionDB()
    try:
        rows = (
            db.query(QuizAnswer.question_id, QuizAnswer.selected_index, func.count().label("n"))
              .filter(QuizAnswer.group_code == group_code)
              .group_by(QuizAnswer.question_id, QuizAnswer.selected_index)
              .all()
        )

        out = {}
        for qid, sel, n in rows:
            qid = int(qid)
            out.setdefault(qid, {})[int(sel)] = int(n)

        payload = []
        for qid in GROUPS[group_code]:
            qobj = QMAP.get(int(qid))
            if not qobj:
                continue
            counts = [out.get(int(qid), {}).get(i, 0) for i in range(len(qobj["choices"]))]
            payload.append({
                "question_id": int(qid),
                "question": qobj["question"],
                "choices": qobj["choices"],
                "counts": counts,
                "answer_index": int(qobj["answer_index"]),
            })

        return jsonify({"group": group_code, "items": payload})
    finally:
        db.close()


@app.get("/stats/<group_code>")
def stats(group_code):
    if group_code not in GROUPS:
        return "Gruppo non valido", 404
    return render_template("stats.html", group_code=group_code)


# -----------------------------
# Run (Render)
# -----------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
