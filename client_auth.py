import socket

IP = '127.0.0.1'
PORT = 9999
BYTES_TO_DECODE = 1024


def get_connection_protocol():
    command = input("Enter Mode : REG for register and LOG for login ")
    if command == "REG":
        return "REG"
    elif command == "LOG":
        return "LOG"
    return None


def connect():
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        client.connect((IP, PORT))

        command = get_connection_protocol()
        username = input("Enter Username : ")
        password = input("Enter Password : ")

        credentials = f"{command}:{username}:{password}"
        client.send(credentials.encode())

        response = client.recv(BYTES_TO_DECODE).decode()
        if response == "AUTH_SUCCESS":
            print("Success! Data pushed to database.")
        elif response == "LOGIN_SUCCESS":
            print("Login successful.")
        elif response == "LOGIN_FAILED":
            print("Login failed.")
        elif response == "AUTH_TAKEN":
            print("Username is already taken.")
        else:
            print(f"Server returned: {response}")
    except ConnectionRefusedError:
        print("Server is offline.")
    finally:
        client.close()


connect()