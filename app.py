# app.py
import os
import secrets
import datetime as dt
import mysql.connector
from flask import Flask, request, render_template, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from email.message import EmailMessage
import smtplib

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "dev-secret-change-me")

# ----- Config DB (Railway) -----
def get_db():
    cfg = dict(
        host=os.getenv("QR_DB_HOST", "mysql.railway.internal"),
        user=os.getenv("QR_DB_USER", "root"),
        password=os.getenv("QR_DB_PASSWORD", ""),
        database=os.getenv("QR_DB_NAME", os.getenv("QR_DB_DATABASE", "railway")),
        port=int(os.getenv("QR_DB_PORT", "3306")),
        autocommit=True
    )
    return mysql.connector.connect(**cfg)

# helpers de password
def make_password(pwd: str) -> str:
    return generate_password_hash(pwd)

def check_password(pwd: str, ph: str) -> bool:
    if not ph:
        return False
    return check_password_hash(ph, pwd)

# helper de mail
def send_mail(to_email: str, subject: str, html: str, text: str = ""):
    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER")
    pwd  = os.getenv("SMTP_PASS")
    sender = os.getenv("SMTP_FROM", user or "noreply@example.com")

    if not host or not user or not pwd:
        # sin SMTP: imprimir para pruebas
        print(f"[MAIL-FAKE]\nTo: {to_email}\nSubject: {subject}\n{text}\n----HTML----\n{html}\n")
        return

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(text or "Abrí este correo en un cliente compatible con HTML.")
    msg.add_alternative(html, subtype="html")
    with smtplib.SMTP(host, port) as s:
        s.starttls()
        s.login(user, pwd)
        s.send_message(msg)

# ---------- RUTAS ----------

@app.route("/")
def index():
    # landing simple (podés cambiarla luego)
    return redirect(url_for("login"))

# --- LOGIN con mensajes diferenciados
@app.route("/login", methods=["GET", "POST"])
def login():
    next_url = request.args.get("next") or url_for("panel")
    error = None
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        cnx = get_db()
        cur = cnx.cursor(dictionary=True)
        cur.execute("SELECT id, email, password_hash FROM users WHERE email=%s", (email,))
        row = cur.fetchone()
        cur.close(); cnx.close()
        if not row:
            error = "Usuario inexistente"
        else:
            if not check_password(password, row["password_hash"]):
                error = "Contraseña inválida"
            else:
                session["uid"] = row["id"]
                return redirect(next_url)
    return render_template("login.html", error=error, next=next_url)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# --- Panel del usuario (lista sus QR)
@app.route("/panel")
def panel():
    uid = session.get("uid")
    if not uid:
        return redirect(url_for("login", next=url_for("panel")))
    cnx = get_db(); cur = cnx.cursor(dictionary=True)
    cur.execute("""SELECT id, public_code, COALESCE(qr_code_string,'') AS qr_code_string
                   FROM qr_codes WHERE user_id=%s ORDER BY id DESC""", (uid,))
    qrs = cur.fetchall()
    cur.close(); cnx.close()
    return render_template("panel.html", qrs=qrs)

# --- Vista pública por código
@app.route("/v/<code>")
def view_public(code):
    cnx = get_db(); cur = cnx.cursor(dictionary=True)
    cur.execute("SELECT id, user_id FROM qr_codes WHERE public_code=%s", (code,))
    row = cur.fetchone()
    cur.close(); cnx.close()
    if not row:
        return "Código inexistente", 404
    if not row["user_id"]:
        # no reclamado: llevar al claim
        return redirect(url_for("claim_code", code=code))
    # si está reclamado, redirige a la ficha actual /emergencia/<id>
    return redirect(url_for("emergencia", qr_id=row["id"]))

# --- Reclamar código (requiere login)
@app.route("/claim/<code>")
def claim_code(code):
    uid = session.get("uid")
    if not uid:
        return redirect(url_for("login", next=url_for("claim_code", code=code)))
    cnx = get_db(); cur = cnx.cursor(dictionary=True)
    # asegura que existe y no tiene dueño
    cur.execute("SELECT id, user_id FROM qr_codes WHERE public_code=%s", (code,))
    row = cur.fetchone()
    if not row:
        cur.close(); cnx.close()
        return "Código inexistente.", 404
    if row["user_id"]:
        cur.close(); cnx.close()
        return redirect(url_for("panel"))

    cur.execute("UPDATE qr_codes SET user_id=%s, claimed_at=NOW() WHERE id=%s", (uid, row["id"]))
    cnx.commit()
    cur.close(); cnx.close()
    flash("Tu QR fue activado y vinculado a tu cuenta.", "ok")
    return redirect(url_for("panel"))

# --- Emergencia (ficha pública por id)
@app.route("/emergencia/<int:qr_id>")
def emergencia(qr_id):
    # renderiza la ficha; acá solo demo mínima
    cnx = get_db(); cur = cnx.cursor(dictionary=True)
    # en tu proyecto usás más datos; aquí dejamos lo esencial
    cur.execute("""SELECT qc.id, u.email
                   FROM qr_codes qc
                   LEFT JOIN users u ON u.id = qc.user_id
                   WHERE qc.id=%s""", (qr_id,))
    row = cur.fetchone()
    cur.close(); cnx.close()
    if not row:
        return "QR no encontrado", 404
    # reutilizo tu template existente de ficha
    return render_template("emergencia.html", data=row)

# --- Recupero: solicitar email
@app.route("/forgot", methods=["GET", "POST"])
def forgot():
    sent = False
    msg  = None
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        if email:
            cnx = get_db(); cur = cnx.cursor(dictionary=True)
            cur.execute("SELECT id FROM users WHERE email=%s", (email,))
            u = cur.fetchone()
            if u:
                token = secrets.token_urlsafe(32)
                expires = dt.datetime.utcnow() + dt.timedelta(hours=1)
                cur.execute("UPDATE users SET reset_token=%s, reset_expires=%s WHERE id=%s",
                            (token, expires, u["id"]))
                cnx.commit()
                base = os.getenv("BASE_PUBLIC_URL", request.url_root.rstrip("/"))
                link = f"{base}/reset/{token}"
                html = f"""
                <p>Para blanquear tu contraseña, hacé clic en el siguiente enlace (vence en 1 hora):</p>
                <p><a href="{link}">{link}</a></p>
                """
                send_mail(email, "Blanquear contraseña - QR Emergencias", html, link)
            cur.close(); cnx.close()
            sent = True
            msg = "Si el email existe, enviamos un enlace para blanquear la contraseña."
    return render_template("forgot_password.html", sent=sent, msg=msg)

# --- Recupero: setear nueva contraseña
@app.route("/reset/<token>", methods=["GET", "POST"])
def reset_token(token):
    cnx = get_db(); cur = cnx.cursor(dictionary=True)
    cur.execute("SELECT id, reset_expires FROM users WHERE reset_token=%s", (token,))
    u = cur.fetchone()

    invalid = False
    if not u:
        invalid = True
    else:
        if not u["reset_expires"] or u["reset_expires"] < dt.datetime.utcnow():
            invalid = True

    if request.method == "POST" and not invalid:
        pwd = request.form.get("password") or ""
        pwd2 = request.form.get("password2") or ""
        if len(pwd) < 6:
            flash("La contraseña debe tener al menos 6 caracteres.", "error")
        elif pwd != pwd2:
            flash("Las contraseñas no coinciden.", "error")
        else:
            ph = make_password(pwd)
            cur.execute("""UPDATE users SET password_hash=%s, reset_token=NULL, reset_expires=NULL
                           WHERE id=%s""", (ph, u["id"]))
            cnx.commit()
            cur.close(); cnx.close()
            flash("Contraseña actualizada. Ya podés iniciar sesión.", "ok")
            return redirect(url_for("login"))

    cur.close(); cnx.close()
    return render_template("reset_password.html", invalid=invalid)

# --- Salud
@app.route("/db_ping")
def db_ping():
    try:
        cnx = get_db()
        cur = cnx.cursor()
        cur.execute("SELECT DATABASE()")
        db = cur.fetchone()[0]
        cur.close(); cnx.close()
        return jsonify(status="db_ok", db_name=db)
    except Exception as e:
        return jsonify(status="db_error", error=str(e)), 500

if __name__ == "__main__":
    app.run(debug=True, port=5000)
