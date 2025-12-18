import json
import os
import qrcode
from io import BytesIO
from flask import Flask, render_template, request, redirect, url_for, session, send_file


app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")

def load_questions():
    with open("questions.json", "r", encoding="utf-8") as f:
        return json.load(f)

QUESTIONS = load_questions()

# Gruppi attivabili via QR (metti qui gli ID reali delle domande)
GROUPS = {
    "tamburi": [1, 2],
    "chiarine": [3, 4, 5],  # <-- metti qui gli ID delle domande per chiarine
}

QMAP = {int(q["id"]): q for q in QUESTIONS}


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
    return redirect(url_for("quiz"))

@app.get("/qr/<group_code>.png")
def qr_png(group_code):
    if group_code not in GROUPS:
        return "Gruppo non valido", 404

    # IMPORTANTISSIMO: genera l'URL usando l'host con cui stai aprendo il sito
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

@app.get("/quiz")
def quiz():
    q_ids = session.get("q_ids")
    if not q_ids:
        return redirect(url_for("index"))

    idx = session.get("idx", 0)
    if idx >= len(q_ids):
        return redirect(url_for("result"))

    q = QMAP[q_ids[idx]]
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

    q = QMAP[q_ids[idx]]

    selected = request.form.get("choice")
    if selected is None:
        session["feedback"] = {"ok": False, "msg": "Seleziona una risposta."}
        return redirect(url_for("quiz"))

    selected = int(selected)
    ok = (selected == q["answer_index"])

    if ok:
        session["score"] = session.get("score", 0) + 1
    else:
        wrong = session.get("wrong", [])
        wrong.append(q["id"])
        session["wrong"] = wrong

    session["feedback"] = {
        "ok": ok,
        "correct": q["answer_index"],
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
    wrong_qs = [QMAP[qid] for qid in q_ids if qid in wrong_ids]

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
@app.get("/g/<group_code>")
def group_landing(group_code):
    if group_code not in GROUPS:
        return "Gruppo non valido", 404

    q_ids = GROUPS[group_code]
    title = f"Quiz Regolamento {group_code.capitalize()}"
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

    return redirect(url_for("quiz"))



if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
