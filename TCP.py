import socket
import sqlite3
import hashlib

DB_NAME = 'Auth.db'
PORT = 9999
IP = '127.0.0.1'
BYTES_TO_DECODE = 1024

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
                       session_id TEXT PRIMARY KEY, 
                       user_id INTEGER, FOREIGN KEY(user_id) REFERENCES USERS(user_ID)
                   )
                   """)
            connection.commit()
            print("Database initialized successfully.")
    except sqlite3.Error as e:
        print(f"Error creating tables: {e}")


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

def run_server():
     server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
     server_socket.bind((IP, PORT))
     server_socket.listen()
     print("Server is running and waiting to register users...")

     create_table()
     while True:
         (client_socket, client_address) = server_socket.accept()
         try:
             data = client_socket.recv(BYTES_TO_DECODE).decode('utf-8')
             if ":" in data:
                 username, password = data.split(":")

                 result = handle_register(username, password)

                 if result == "REGISTER_SUCCESS":
                     print(f"User {username} successfully registered/pushed!")
                     client_socket.send("AUTH_SUCCESS".encode())
                 elif result == "REGISTER_TAKEN":
                     print(f"User {username} tried to register but already exists.")
                     client_socket.send("AUTH_TAKEN".encode())
                 else:
                    print("Database error occurred.")
                    client_socket.send("AUTH_FAILED".encode())
         finally:
             client_socket.close()


if __name__ == "__main__":
    run_server()
