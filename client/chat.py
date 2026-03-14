import pygame
from game import Game
import socket
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend

import protobuf.chat_net_pb2 as chat_net
import auth_crypto
import threading

# הגדרות בסיסיות
width, height = 300, 400

_CLIENT_DIR = Path(__file__).resolve().parent


def _get_chat_client_key_pair():
    """Generate or return cached client RSA key pair for chat (created at first use)."""
    if not hasattr(_get_chat_client_key_pair, "_cached"):
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend(),
        )
        _get_chat_client_key_pair._cached = (private_key, private_key.public_key())
    return _get_chat_client_key_pair._cached


class Chat(pygame.sprite.Sprite):
    def __init__(self, ssid: int, host: str="127.0.0.1", reliable_port: int = 8888):
        super().__init__()
        self.rect = pygame.Rect(0, 80, width, height)
        self.screen = pygame.display.get_surface()
        self.is_open = False  # שיניתי ל-is_open כדי לא להתנגש עם פונקציות
        self.font = pygame.font.SysFont('Arial', 18)

        self.messages = []
        self.current_typing = ""  # מה שהמשתמש כותב כרגע
        self.reliable_conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.session_id = ssid
        self.host = host
        self.reliable_port = reliable_port
        self.user_idc=self.open_reliable_conn()


    def add_external_message(self, text):

        self.messages.append(text)

        if len(self.messages) > 18:
            self.messages.pop(0)

    def handle_event(self, event):

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_c and not self.is_open:
                self.is_open = True
                return

            if self.is_open:
                if event.key == pygame.K_ESCAPE:
                    self.is_open = False
                elif event.key == pygame.K_RETURN:
                    if self.current_typing:
                        self.add_external_message(f"You: {self.current_typing}")
                        self.try_send_mas(str(self.current_typing))
                        self.current_typing = ""

                elif event.key == pygame.K_BACKSPACE:
                    self.current_typing = self.current_typing[:-1]
                else:

                    if event.unicode.isprintable():
                        self.current_typing += event.unicode

    def draw(self):
        if not self.is_open:
            return


        overlay = pygame.Surface((width, height))
        overlay.set_alpha(180)
        overlay.fill((20, 20, 20))
        self.screen.blit(overlay, (0, 80))

        # ציור ההודעות
        for i, msg in enumerate(self.messages):
            msg_surf = self.font.render(msg, True, (255, 255, 255))
            self.screen.blit(msg_surf, (10, 10 + i * 20+80))

        # ציור מה שהמשתמש מקליד כרגע (בתחתית)
        input_text = self.font.render(f"> {self.current_typing}", True, (0, 255, 0))
        self.screen.blit(input_text, (10, height+80 - 30))

    def open_reliable_conn(self):
        """opens the TCP conn and returns the user id. can throw"""
        self.reliable_conn.connect((self.host, self.reliable_port))
        client_private_key, client_public_key = _get_chat_client_key_pair()
        chat_server_public_key = auth_crypto.load_public_key_from_dir(_CLIENT_DIR, "chat_server_public.pem")
        self._client_private_key = client_private_key
        self._chat_server_public_key = chat_server_public_key

        handshake = chat_net.HandshakeStart()
        handshake.kind = handshake.LOGIN
        handshake.session_id = self.session_id
        handshake.client_public_key = auth_crypto.public_key_to_bytes(client_public_key)
        self.reliable_conn.sendall(
            auth_crypto.encrypt_and_prefix(handshake.SerializeToString(), chat_server_public_key)
        )
        plaintext = auth_crypto.receive_and_decrypt(self.reliable_conn.recv, client_private_key)
        login_resp = chat_net.HandshakeStart()
        login_resp.ParseFromString(plaintext)
        if login_resp.kind != login_resp.SERVER_OK:
            raise RuntimeError("failed connecting to zone: invalid session id")
        listener = threading.Thread(target=server_listener, args=(self,))
        listener.start()
        return login_resp.user_id

    def try_send_mas(self, mas: str) -> None:
        update = chat_net.ChatMessage()
        update.message = mas
        self.reliable_conn.sendall(
            auth_crypto.encrypt_and_prefix(
                update.SerializeToString(), self._chat_server_public_key
            )
        )

def server_listener(chat: Chat):
        """
        Start this one in another thread
        Assumes a connection has already been established in `game.chat_conn`
        """
        first = True
        while True:
            try:
                plaintext = auth_crypto.receive_and_decrypt(
                    chat.reliable_conn.recv, chat._client_private_key
                )
            except ValueError:
                break
            parsed = chat_net.ChatMessage()
            parsed.ParseFromString(plaintext)
            print(f"received: {parsed}")

            payload_type = parsed.WhichOneof("mas")
            print(f'{payload_type=}')
            if payload_type == "message":
                if(first):
                    first=False
                    break_starting_mas(chat, parsed.message)
                    continue
                msg = parsed.message
                chat.add_external_message(f"{msg}")


def break_starting_mas(chat: Chat, mas: str):
    for m in mas.split("\r\n"):
        chat.add_external_message(m)


