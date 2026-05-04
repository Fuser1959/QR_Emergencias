# generate_unclaimed_qr.py
import mysql.connector
from urllib.parse import urlparse
from secrets import choice
import string
from datetime import datetime

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sin 0/O/I/1
CODE_LEN = 10
COUNT = 50  # cantidad de etiquetas a crear

def parse_mysql_public_url(url: str):
    p = urlparse(url)
    if p.scheme != "mysql":
        raise ValueError("MYSQL_PUBLIC_URL inválida (debe empezar con mysql://)")
    return {
        "host": p.hostname,
        "port": p.port or 3306,
        "user": p.username or "root",
        "password": p.password or "",
        "database": (p.path or "/railway").lstrip("/") or "railway",
    }

def gen_code(n=CODE_LEN):
    return "".join(choice(ALPHABET) for _ in range(n))

def unique_code(conn):
    cur = conn.cursor()
    while True:
        code = gen_code()
        cur.execute("SELECT 1 FROM qr_codes WHERE public_code=%s LIMIT 1", (code,))
        if cur.fetchone() is None:
            cur.close()
            return code

def main():
    print("Pegá tu MYSQL_PUBLIC_URL (Railway → MySQL → Variables):")
    url = input("MYSQL_PUBLIC_URL: ").strip()
    cfg = parse_mysql_public_url(url)

    conn = mysql.connector.connect(**cfg)
    cur = conn.cursor()

    created = []
    for _ in range(COUNT):
        code = unique_code(conn)
        # qr_code_string opcional: ayuda para debug interno
        cur.execute("SELECT COALESCE(MAX(id),0)+1 FROM qr_codes")
        next_id = cur.fetchone()[0]
        qr_code_string = f"QR{next_id:03d}"

        cur2 = conn.cursor()
        cur2.execute("""
            INSERT INTO qr_codes (id, qr_code_string, public_code, user_id, claimed_at)
            VALUES (%s, %s, %s, NULL, NULL)
        """, (next_id, qr_code_string, code))
        cur2.close()
        created.append((next_id, code))

        if len(created) % 25 == 0:
            conn.commit()
    conn.commit()

    cur.close()
    conn.close()

    print("\nListo ✅ — creadas {} etiquetas vírgenes:".format(len(created)))
    for (qid, code) in created:
        print(f"  id={qid}  public_code={code}  URL=/v/{code}")

if __name__ == "__main__":
    main()
