import socket
import sqlite3

DB_NAME = 'Auth.db'
PORT = 9999
IP = '127.0.0.1'
BYTES_TO_DECODE = 1024
connection = sqlite3.connect(DB_NAME)


def create_table():
    cursor = connection.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS DATABASE
        (user_ID INTEGER PRIMARY KEY AUTOINCREMENT, 
         username TEXT UNIQUE NOT NULL, 
         password TEXT NOT NULL)
            """)
    connection.commit()

def add_user_to_db(username, password):
    try:
        cursor = connection.cursor()
        cursor.execute("INSERT INTO DATABASE (username, password) VALUES (?, ?)", (username, str(password)))
        connection.commit()
        connection.close()
        return True

    except Exception as e:
        print(f"Database Error: {e}")
        return False


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

                if add_user_to_db(username, password):
                    print(f"User {username} successfully registered/pushed!")
                    client_socket.send("AUTH_SUCCESS".encode())
                else:
                    client_socket.send("AUTH_FAILED".encode())
        finally:
            client_socket.close()


if __name__ == "__main__":
    run_server()