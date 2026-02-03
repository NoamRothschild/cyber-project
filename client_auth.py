import socket

IP = '127.0.0.1'
PORT = 9999
BYTES_TO_DECODE = 1024

def login_or_register(username, password):
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        client.connect((IP, PORT))

        credentials = f"{username}:{password}"
        client.send(credentials.encode())

        response = client.recv(BYTES_TO_DECODE).decode()
        if response == "AUTH_SUCCESS":
            print("Success! Data pushed to database.")
        else:
            print("Failed to push data.")
    except ConnectionRefusedError:
        print("Server is offline.")
    finally:
        client.close()

login_or_register(input(), int(input()))
