# inspect_code.py
import sys, getpass
import urllib.parse as up
import mysql.connector

def parse_mysql_url(url: str):
    p = up.urlparse(url)
    user = p.username
    pwd = p.password
    host = p.hostname
    port = p.port or 3306
    db   = (p.path or "/").lstrip("/")
    return host, port, db, user, pwd

def main():
    if len(sys.argv) < 2:
        print("Uso: python inspect_code.py <PUBLIC_CODE> [--unclaim]")
        sys.exit(1)

    code = sys.argv[1].strip()
    do_unclaim = ("--unclaim" in sys.argv)

    mysql_url = input("Pegá tu MYSQL_PUBLIC_URL: ").strip()
    host, port, db, user, pwd = parse_mysql_url(mysql_url)

    print(f"→ Conectando a {host}:{port} / db={db} user={user} …")
    cnx = mysql.connector.connect(host=host, port=port, user=user, password=pwd, database=db, autocommit=True)
    cur = cnx.cursor(dictionary=True)

    cur.execute("""
      SELECT q.id, q.public_code, q.user_id, q.claimed_at, u.email
      FROM qr_codes q
      LEFT JOIN users u ON u.id=q.user_id
      WHERE q.public_code=%s
    """, (code,))
    row = cur.fetchone()
    if not row:
        print("❌ No existe ese public_code.")
        return

    print("\nEstado actual:")
    print(f"  id={row['id']}  public_code={row['public_code']}  user_id={row['user_id']}  claimed_at={row['claimed_at']}  email={row.get('email')}")

    if do_unclaim:
        cur.execute("UPDATE qr_codes SET user_id=NULL, claimed_at=NULL WHERE id=%s", (row["id"],))
        print("→ Hecho: se dejó virgen (user_id=NULL, claimed_at=NULL).")

    cur.close()
    cnx.close()

if __name__ == "__main__":
    main()
