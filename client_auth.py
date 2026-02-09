import socket

IP = '127.0.0.1'
PORT = 9999
BYTES_TO_DECODE = 1024


def connect(username, password, command):
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        client.connect((IP, PORT))

        credentials = f"{command}:{username}:{password}"
        client.send(credentials.encode())

        response = client.recv(BYTES_TO_DECODE).decode()

        return response

    except ConnectionRefusedError:
        return "SERVER_OFFLINE"
    except socket.timeout:
        return "TIMEOUT"
    except socket.error as e:
        # Catches other network errors like BrokenPipe
        return f"NET_ERROR: {e}"
    finally:
        client.close()