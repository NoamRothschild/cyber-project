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
BIND_ADDRESS = __import__('os').environ.get('AUTH_BIND', '127.0.0.1')
BYTES_TO_DECODE = 8192

_AUTH_SERVER_DIR = Path(__file__).resolve().parent

REDIS_PORT = 6379
CACHE_TIME = 86400 # in seconds

def _redis_host():
    import os
    from config import REDIS_PASSWORD as _p
    return os.environ.get("REDIS_HOST", "127.0.0.1"), _p

_rhost, _rpass = _redis_host()
r = redis.Redis(host=_rhost, port=REDIS_PORT, password=_rpass, decode_responses=True)


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
    _rhost, _rpass = _redis_host()
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
    try:
        with get_db_connection() as connection:
            cursor = connection.cursor()

            cursor.execute("SELECT 1 FROM USERS WHERE username = ?", (username,))

            if cursor.fetchone():
                return "REGISTER_TAKEN"

            hashed_pw = get_hashed_password(username, password)
            cursor.execute("INSERT INTO USERS (username, password) VALUES (?, ?)",
                           (username, hashed_pw))

            connection.commit()
            print(f"User {username} registered successfully.")
            return "REGISTER_SUCCESS"


    except sqlite3.Error as e:
        print(f"Error registering user: {e}")
        return "REGISTER_FAILED"


def handle_login(username, password):
    try :
        with get_db_connection() as connection:
            cursor = connection.cursor()
            hashed_pw = get_hashed_password(username, password)
            cursor.execute("SELECT user_ID FROM USERS WHERE username = ? and password = ?", (username,hashed_pw))

            result = cursor.fetchone()
            if result:
                user_id_from_db = result[0]
                session_id = int(uuid.uuid4()) & (2 ** 63 - 1)

                cursor.execute("DELETE FROM SESSIONS WHERE user_id = ?", (user_id_from_db,))
                cursor.execute("INSERT INTO SESSIONS (session_id, user_id) VALUES (?, ?)",
                               (session_id, user_id_from_db))

                # creating an "instance" in the game data db
                db.create_new_player(user_id_from_db)

                # cache the fresh player stats in Redis
                cache_player_stats_in_redis(user_id_from_db)

                # set data to redis db for 24h
                # Key = session id, Value = user id
                r.setex(f"session:{session_id}", CACHE_TIME, user_id_from_db)
                r.setex(f"session:{session_id}:username", CACHE_TIME, username)
                connection.commit()
                return f"LOGIN_SUCCESS:{session_id}"
            else:
                print("You are not logged in. you need to register first.")
                return "LOGIN_FAILED"
    except sqlite3.Error as e:
        print(f"Error registering user: {e}")
        return "LOGIN_FAILED"



def run_server():
     import os
     bind_addr = os.environ.get("AUTH_BIND", "127.0.0.1")
     server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
     server_socket.bind((bind_addr, PORT))
     server_socket.listen()
     print("Server is running and waiting to register users...")

     server_private_key = auth_crypto.load_private_key_from_dir(_AUTH_SERVER_DIR)
     create_table()
     while True:
         (client_socket, client_address) = server_socket.accept()
         if not rate_limiter.should_continue(client_address):
             client_socket.close()
             print("[INFO] ignoring possible DOS attempt from a user")
             continue

         try:
             try:
                 plaintext = auth_crypto.receive_and_decrypt(client_socket.recv, server_private_key)
             except ValueError as e:
                 print(f"[auth] Decrypt failed (key mismatch?): {e}")
                 continue
             data = auth_net.RequestLogin()
             data.ParseFromString(plaintext)

             if not data.client_public_key:
                 client_socket.close()
                 continue
             client_public_key = auth_crypto.public_key_from_bytes(data.client_public_key)

             command = data.mode

             if command == auth_net.Mode.REGISTER:
                result = handle_register(data.username, data.password)
                if result == "REGISTER_SUCCESS":
                    answer = auth_net.SendAnswer()
                    answer.status = auth_net.Status.SUCCESS
                    print(f"User {data.username} successfully registered/pushed!")
                    client_socket.sendall(auth_crypto.encrypt_and_prefix(answer.SerializeToString(), client_public_key))
                elif result == "REGISTER_TAKEN":
                    answer = auth_net.SendAnswer()
                    answer.status = auth_net.Status.TAKEN
                    print(f"User {data.username} tried to register but already exists.")
                    client_socket.sendall(auth_crypto.encrypt_and_prefix(answer.SerializeToString(), client_public_key))
                else:
                    answer = auth_net.SendAnswer()
                    answer.status = auth_net.Status.FAILURE
                    print("Database error occurred.")
                    client_socket.sendall(auth_crypto.encrypt_and_prefix(answer.SerializeToString(), client_public_key))

             elif command == auth_net.Mode.LOGIN:
                result = handle_login(data.username, data.password)

                if result.startswith("LOGIN_SUCCESS"):
                    answer = auth_net.SendAnswer()
                    answer.status = auth_net.Status.SUCCESS
                    answer.session_id = int(result.split(":")[1])
                    print(f"User {data.username} logged in.")
                    client_socket.sendall(auth_crypto.encrypt_and_prefix(answer.SerializeToString(), client_public_key))
                elif result == "LOGIN_FAILED":
                    answer = auth_net.SendAnswer()
                    answer.status = auth_net.Status.FAILURE
                    client_socket.sendall(auth_crypto.encrypt_and_prefix(answer.SerializeToString(), client_public_key))
         finally:
            client_socket.close()


if __name__ == "__main__":
    db.create_table()
    threading.Thread(target=auth_update_listener, daemon=True).start()
    run_server()
