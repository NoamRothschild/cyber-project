import pygame
from game import Game
import socket
from config import CHAT_HOST, CHAT_PORT
import protobuf.region_net_pb2 as region_net
import threading

# הגדרות בסיסיות
width, height = 300, 400
BUFF_SIZE = 1024


class Chat(pygame.sprite.Sprite):
    def __init__(self, ssid: int, host: str=CHAT_HOST, reliable_port: int = CHAT_PORT):
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
        handshake = region_net.HandshakeStart()
        handshake.session_id = self.session_id
        handshake.kind = handshake.LOGIN

        self.reliable_conn.sendall(handshake.SerializeToString())
        login_resp_raw = self.reliable_conn.recv(BUFF_SIZE)
        login_resp = region_net.HandshakeStart()
        login_resp.ParseFromString(login_resp_raw)
        if login_resp.kind != login_resp.SERVER_OK:
            raise RuntimeError("failed connecting to zone: invalid session id")
        listener = threading.Thread(target=server_listener, args=(self,))
        listener.start()
        return login_resp.user_id

    def try_send_mas(self, mas: str ) -> None:

        update = region_net.ChatMessage()
        update.message = mas
        self.reliable_conn.sendall(update.SerializeToString())

def server_listener(chat: Chat):
        """
        Start this one in another thread
        Assumes a connection has already been established in `game.region_conn`
        """
        first= True
        while True:
            server_raw = chat.reliable_conn.recv(BUFF_SIZE)
            if not server_raw:
                continue
            parsed = region_net.ChatMessage()
            parsed.ParseFromString(server_raw)
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


