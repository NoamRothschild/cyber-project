import socket
import protobuf.auth_net_pb2 as auth_net

IP = '127.0.0.1'
PORT = 9999
BYTES_TO_DECODE = 1024


def connect(username, password, command):
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        client.connect((IP, PORT))

        answer = auth_net.RequestLogin()
        if command == "REG":
            answer.mode = auth_net.Mode.REGISTER
        elif command == "LOG":
            answer.mode = auth_net.Mode.LOGIN

        answer.username = username
        answer.password = password

        client.sendall(answer.SerializeToString())
        raw_response = client.recv(BYTES_TO_DECODE)
        response = auth_net.SendAnswer()
        response.ParseFromString(raw_response)

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