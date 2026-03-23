import socket
import sqlite3
import hashlib
import uuid
import json
import threading
from pathlib import Path

import protobuf.auth_net_pb2 as auth_net
import redis
import auth_crypto
import data_db_handler as db
import rate_limiter

DB_NAME = 'Auth.db'
PORT = 9999
# Default 0.0.0.0 so Docker -p and LAN work; override with AUTH_BIND=127.0.0.1 for local-only.
BIND_ADDRESS = __import__('os').environ.get('AUTH_BIND', '0.0.0.0')
BYTES_TO_DECODE = 8192

_AUTH_SERVER_DIR = Path(__file__).resolve().parent

REDIS_PORT = 6379
CACHE_TIME = 86400 # in seconds

# --- קבועים חדשים למניעת פריצה ---
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_TIME = 600  # 10 דקות בשניות

def _redis_conn_params():
    """
    Host and password for redis.Redis.

    password=None means redis-py will not send AUTH — required when Redis has no
    requirepass (e.g. default redis:latest on the host). If you use a password
    in compose (--requirepass), set REDIS_PASSWORD to match or rely on config.json.

    Env REDIS_PASSWORD may be set to empty (e.g. -e REDIS_PASSWORD=) to force no AUTH
    even when config.json defines a password.
    """
    import os
    from config import REDIS_HOST as _cfg_host
    _cfg_pwd = os.environ.get("REDIS_PASSWORD", "36f52b82c90c161f0")

    host = (os.environ.get("REDIS_HOST") or "").strip() or _cfg_host or "127.0.0.1"

    if "REDIS_PASSWORD" in os.environ:
        raw_pwd = os.environ["REDIS_PASSWORD"]
    else:
        raw_pwd = _cfg_pwd
    if isinstance(raw_pwd, str):
        raw_pwd = raw_pwd.strip()
    password = raw_pwd if raw_pwd else None

    return host, password


_rhost, _rpass = _redis_conn_params()
r = redis.Redis(host=_rhost, port=REDIS_PORT, password=_rpass, decode_responses=True)
print(
    f"[auth] Redis client init: host={_rhost!r} port={REDIS_PORT} "
    f"password={'set len=' + str(len(_rpass)) if _rpass else 'none (no AUTH)'}",
    flush=True,
)
try:
    r.ping()
    print("[auth] Redis PING ok at module load", flush=True)
except redis.RedisError as ex:
    print(f"[auth] Redis PING failed at module load: {ex!r}", flush=True)


def get_db_connection():
    """Creates a fresh database connection."""
    return sqlite3.connect(DB_NAME)


def get_hashed_password(username, password):
    """Hashes the password with the username as a salt."""
    hashed_object = hashlib.sha256((username + password).encode("utf-8"))
    return hashed_object.hexdigest()


def create_table():
    """Initializes the database tables."""
    try:
        with get_db_connection() as connection:
            cursor = connection.cursor()
            cursor.execute("""
                   CREATE TABLE IF NOT EXISTS USERS
                   (
                       user_ID INTEGER PRIMARY KEY AUTOINCREMENT,
                       username TEXT UNIQUE NOT NULL,
                       password TEXT NOT NULL
                   )
                   """)
            cursor.execute("""
                   CREATE TABLE IF NOT EXISTS SESSIONS
                   (
                       session_id INTEGER PRIMARY KEY, 
                       user_id INTEGER, FOREIGN KEY(user_id) REFERENCES USERS(user_ID)
                   )
                   """)
            connection.commit()
            print("Database initialized successfully.")
    except sqlite3.Error as e:
        print(f"Error creating tables: {e}")


def cache_player_stats_in_redis(user_id: int) -> None:
    """
    Cache the player's persistent stats in Redis under keys like:
    client:USER_ID:health, client:USER_ID:money, client:USER_ID:weapons, ...
    """
    stats = db.load_player(user_id)
    if not stats:
        stats = {
            "health": 400,
            "money": 0,
            "weapons": [1, 2, 3, 4, 5, 0, 0, 0, 0, 0],
            "ammo":    [15, 3, 1000, 30, 10, 0, 0, 0, 0, 0],
            "potions": [1, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            "spawn_x": 74010,
            "spawn_y": 32605,
        }

    prefix = f"client:{user_id}:"
    r.set(prefix + "health", stats["health"])
    r.set(prefix + "money", stats["money"])
    r.set(prefix + "spawn_x", stats["spawn_x"])
    r.set(prefix + "spawn_y", stats["spawn_y"])

    # Store parallel lists as comma‑separated strings
    r.set(prefix + "weapons", ",".join(str(w) for w in stats["weapons"]))
    r.set(prefix + "ammo", ",".join(str(a) for a in stats["ammo"]))
    r.set(prefix + "potions", ",".join(str(p) for p in stats["potions"]))


SCALAR_FIELDS = {"health", "money", "spawn_x", "spawn_y"}
LIST_FIELDS = {"weapons": "weapon", "ammo": "ammo", "potions": "potion"}


def handle_auth_update(conn: sqlite3.Connection, raw_data: str) -> None:
    try:
        data = json.loads(raw_data)
    except json.JSONDecodeError as e:
        print(f"[auth-update] bad JSON: {e}")
        return

    user_id = data.get("user_id")
    if user_id is None:
        print("[auth-update] missing user_id, ignoring")
        return

    # Region server publishes here when the client disconnects — always drop the
    # login lock so they can log in again (otherwise active_user:* lasts CACHE_TIME).
    try:
        r.delete(f"active_user:{user_id}")
    except redis.RedisError as re:
        print(f"[auth-update] failed to clear active_user:{user_id}: {re}")

    set_clauses = []
    params = []

    for field in SCALAR_FIELDS:
        if field in data:
            set_clauses.append(f"{field} = ?")
            params.append(data[field])

    for json_key, col_prefix in LIST_FIELDS.items():
        if json_key in data:
            for i, val in enumerate(data[json_key], start=1):
                set_clauses.append(f"{col_prefix}{i} = ?")
                params.append(val)

    if not set_clauses:
        return

    params.append(user_id)
    query = f"UPDATE INVENTORY SET {', '.join(set_clauses)} WHERE Player_id = ?"
    try:
        conn.execute(query, params)
        conn.commit()
        print(f"[auth-update] saved stats for user {user_id}")
    except sqlite3.Error as e:
        print(f"[auth-update] DB error for user {user_id}: {e}")


def auth_update_listener() -> None:
    conn = sqlite3.connect(db.DB_PATH)
    _rhost, _rpass = _redis_conn_params()
    sub = redis.Redis(host=_rhost, port=REDIS_PORT, password=_rpass, decode_responses=True)
    ps = sub.pubsub()
    ps.subscribe("auth-update")
    print("[auth-update] listening on channel 'auth-update'")
    for message in ps.listen():
        if message["type"] != "message":
            continue
        handle_auth_update(conn, message["data"])


def handle_register(username, password):
    """
    Registers a new user.
    Returns: "REGISTER_SUCCESS" or "REGISTER_FAILED"
    """
    print(
        f"[auth][register] handle_register enter username={username!r} "
        f"username_len={len(username)} password_len={len(password)}",
        flush=True,
    )
    try:
        with get_db_connection() as connection:
            print("[auth][register] SQLite connection acquired", flush=True)
            cursor = connection.cursor()

            cursor.execute("SELECT 1 FROM USERS WHERE username = ?", (username,))
            exists = cursor.fetchone()
            print(f"[auth][register] username lookup done exists={bool(exists)}", flush=True)

            if exists:
                print(f"[auth][register] returning REGISTER_TAKEN for {username!r}", flush=True)
                return "REGISTER_TAKEN"

            hashed_pw = get_hashed_password(username, password)
            print(f"[auth][register] password hashed hash_len={len(hashed_pw)}", flush=True)
            cursor.execute("INSERT INTO USERS (username, password) VALUES (?, ?)",
                           (username, hashed_pw))

            connection.commit()
            print(f"[auth][register] INSERT committed; {username!r} registered successfully.", flush=True)
            return "REGISTER_SUCCESS"

    except sqlite3.Error as e:
        print(f"[auth][register] sqlite error -> REGISTER_FAILED: {e!r}", flush=True)
        return "REGISTER_FAILED"


def handle_login(username, password):

    # מפתח ייחודי ב-Redis עבור ניסיונות ההתחברות של המשתמש
    attempts_key = f"login_attempts:{username}"

    # 1. בדיקה אם המשתמש חסום כרגע
    current_attempts = r.get(attempts_key)
    if current_attempts and int(current_attempts) >= MAX_LOGIN_ATTEMPTS:
        print(f"[SECURITY] User {username} is currently locked out.")
        return "LOGIN_LOCKED"

    try:
        with get_db_connection() as connection:
            cursor = connection.cursor()
            hashed_pw = get_hashed_password(username, password)
            cursor.execute("SELECT user_ID FROM USERS WHERE username = ? and password = ?", (username, hashed_pw))

            result = cursor.fetchone()
            if result:
                user_id_from_db = result[0]

                # --- NEW: Session Concurrency Check ---
                active_user_key = f"active_user:{user_id_from_db}"
                existing_session = r.get(active_user_key)

                if existing_session:
                    print(f"[SECURITY] Denied login for {username} (ID: {user_id_from_db}): Already connected.")
                    return "ALREADY_LOGGED_IN"
                # --------------------------------------

                # כניסה מוצלחת! מוחקים את מונה הניסיונות
                r.delete(attempts_key)

                session_id = int(uuid.uuid4()) & (2 ** 63 - 1)

                cursor.execute("DELETE FROM SESSIONS WHERE user_id = ?", (user_id_from_db,))
                cursor.execute("INSERT INTO SESSIONS (session_id, user_id) VALUES (?, ?)",
                               (session_id, user_id_from_db))

                # creating an "instance" in the game data db
                db.create_new_player(user_id_from_db)

                # cache the fresh player stats in Redis
                cache_player_stats_in_redis(user_id_from_db)

                connection.commit()

                # Session + lock in Redis only after DB commit succeeds (avoids "already in use"
                # when login failed mid-way but active_user was already set).
                # Key = session id, Value = user id
                r.setex(f"session:{session_id}", CACHE_TIME, user_id_from_db)
                r.setex(f"session:{session_id}:username", CACHE_TIME, username)
                r.setex(active_user_key, CACHE_TIME, session_id)
                return f"LOGIN_SUCCESS:{session_id}"
            else:
                # סיסמה שגויה - מעלים את המונה ב-Redis
                # INCR יוצר את המפתח אם הוא לא קיים ומחזיר את הערך החדש
                new_attempts = r.incr(attempts_key)
                if new_attempts == 1:
                    # אם זה הניסיון הכושל הראשון, קובעים זמן תפוגה למונה
                    r.expire(attempts_key, LOCKOUT_TIME)

                print(f"[SECURITY] Failed login for {username}. Attempt {new_attempts}/{MAX_LOGIN_ATTEMPTS}")
                return "LOGIN_FAILED"
    except sqlite3.Error as e:
        print(f"Error registering user: {e}")
        return "LOGIN_FAILED"



def run_server():
     import os
     bind_addr = os.environ.get("AUTH_BIND", "0.0.0.0")
     server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
     server_socket.bind((bind_addr, PORT))
     server_socket.listen()
     print(
         f"[auth] TCP listening on {bind_addr!r}:{PORT} (override with AUTH_BIND)",
         flush=True,
     )

     server_private_key = auth_crypto.load_private_key_from_dir(_AUTH_SERVER_DIR)
     print("[auth] Loaded auth server RSA private key from disk", flush=True)
     create_table()
     while True:
         (client_socket, client_address) = server_socket.accept()
         peer = f"{client_address[0]}:{client_address[1]}"
         print(f"[auth] accept from {peer}", flush=True)
         if not rate_limiter.should_continue(client_address):
             client_socket.close()
             print(f"[auth] rate_limiter blocked {peer}", flush=True)
             continue

         try:
             try:
                 print(f"[auth] {peer} reading length-prefixed ciphertext (decrypt with server private key)...", flush=True)
                 plaintext = auth_crypto.receive_and_decrypt(client_socket.recv, server_private_key)
                 print(
                     f"[auth] {peer} decrypt OK plaintext_len={len(plaintext)}",
                     flush=True,
                 )
             except ValueError as e:
                 print(f"[auth] {peer} Decrypt/read failed (key mismatch or truncated?): {e!r}", flush=True)
                 continue
             data = auth_net.RequestLogin()
             try:
                 data.ParseFromString(plaintext)
             except Exception as ex:
                 print(f"[auth] {peer} protobuf ParseFromString failed: {ex!r}", flush=True)
                 continue

             try:
                 mode_name = auth_net.Mode.Name(data.mode)
             except ValueError:
                 mode_name = f"<unknown {data.mode!r}>"
             print(
                 f"[auth] {peer} RequestLogin mode={mode_name} username={data.username!r} "
                 f"username_len={len(data.username)} password_len={len(data.password)} "
                 f"client_public_key_len={len(data.client_public_key)}",
                 flush=True,
             )

             if not data.client_public_key:
                 print(f"[auth] {peer} missing client_public_key; closing", flush=True)
                 client_socket.close()
                 continue
             try:
                 client_public_key = auth_crypto.public_key_from_bytes(data.client_public_key)
                 print(f"[auth] {peer} parsed client RSA public key OK", flush=True)
             except Exception as ex:
                 print(f"[auth] {peer} public_key_from_bytes failed: {ex!r}", flush=True)
                 continue

             command = data.mode

             if command == auth_net.Mode.REGISTER:
                print(f"[auth] {peer} REGISTER route start", flush=True)
                result = handle_register(data.username, data.password)
                print(f"[auth] {peer} handle_register returned {result!r}", flush=True)
                if result == "REGISTER_SUCCESS":
                    answer = auth_net.SendAnswer()
                    answer.status = auth_net.Status.SUCCESS
                    payload = answer.SerializeToString()
                    out = auth_crypto.encrypt_and_prefix(payload, client_public_key)
                    print(
                        f"[auth] {peer} sending REGISTER SUCCESS encrypted reply total_send_len={len(out)} "
                        f"inner_proto_len={len(payload)}",
                        flush=True,
                    )
                    client_socket.sendall(out)
                elif result == "REGISTER_TAKEN":
                    answer = auth_net.SendAnswer()
                    answer.status = auth_net.Status.TAKEN
                    payload = answer.SerializeToString()
                    out = auth_crypto.encrypt_and_prefix(payload, client_public_key)
                    print(
                        f"[auth] {peer} sending REGISTER TAKEN encrypted reply total_send_len={len(out)}",
                        flush=True,
                    )
                    client_socket.sendall(out)
                else:
                    answer = auth_net.SendAnswer()
                    answer.status = auth_net.Status.FAILURE
                    payload = answer.SerializeToString()
                    out = auth_crypto.encrypt_and_prefix(payload, client_public_key)
                    print(
                        f"[auth] {peer} sending REGISTER FAILURE encrypted reply total_send_len={len(out)}",
                        flush=True,
                    )
                    client_socket.sendall(out)

             elif command == auth_net.Mode.LOGIN:
                result = handle_login(data.username, data.password)

                if result.startswith("LOGIN_SUCCESS"):
                    answer = auth_net.SendAnswer()
                    answer.status = auth_net.Status.SUCCESS
                    answer.session_id = int(result.split(":")[1])
                    print(f"User {data.username} logged in.")
                    client_socket.sendall(auth_crypto.encrypt_and_prefix(answer.SerializeToString(), client_public_key))

                elif result == "ALREADY_LOGGED_IN":
                    answer = auth_net.SendAnswer()
                    answer.status = auth_net.Status.ALREADY_LOGGED_IN
                    print(f"Login rejected: {data.username} is already active.")
                    client_socket.sendall(auth_crypto.encrypt_and_prefix(answer.SerializeToString(), client_public_key))

                elif result == "LOGIN_LOCKED":
                    answer = auth_net.SendAnswer()
                    answer.status = auth_net.Status.LOCKED
                    print(f"User {data.username} rejected due to lockout.")
                    client_socket.sendall(auth_crypto.encrypt_and_prefix(answer.SerializeToString(), client_public_key))

                elif result == "LOGIN_FAILED":
                    answer = auth_net.SendAnswer()
                    answer.status = auth_net.Status.FAILURE
                    client_socket.sendall(auth_crypto.encrypt_and_prefix(answer.SerializeToString(), client_public_key))
             else:
                 print(
                     f"[auth] {peer} unknown mode={command!r} ({mode_name}); no reply sent",
                     flush=True,
                 )
         finally:
            print(f"[auth] {peer} client_socket.close() in finally", flush=True)
            client_socket.close()


if __name__ == "__main__":
    db.create_table()
    threading.Thread(target=auth_update_listener, daemon=True).start()
    run_server()
