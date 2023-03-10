import datetime
import re
import socket
import time

from .streambrain import Event, Listener

from threading import Lock, Thread
from typing import List, Optional


TWITCH_SERVER_HOST = "irc.chat.twitch.tv"
TWITCH_SERVER_PORT = 6667


class LoginAuthenticationFailedError(Exception):
    pass


class CapabilityRequestDeniedError(Exception):
    pass


class TwitchChatDisconnectedError(Exception):
    pass


class TwitchIRCMessage:
    TWITCH_IRC_RE = re.compile(
            r"^(@(?P<tags>.*?) )?"
            r"(:(?P<prefix>.*?) )?"
            r"(?P<command>.*?)"
            r"( (?P<parameters>.*?))?$")

    def __init__(self, message_line: str) -> "TwitchIRCMessage":
        match = self.TWITCH_IRC_RE.fullmatch(message_line)
        self.command = match.group("command")
        self.tags = {}
        if match.group("tags"):
            for tag in match.group("tags").split(";"):
                self.tags.update([tag.split("=", 1)])
        self.prefix = match.group("prefix")
        if match.group("parameters"):
            param_colon_split = match.group("parameters").split(":")
            self.parameters = param_colon_split[0].split()
            if len(param_colon_split) > 1:
                self.parameters.append(":".join(param_colon_split[1:]))
        else:
            self.parameters = []


class DirectInterface:
    def __init__(self):
        self._connection = None
        self._is_setting_up = False

    # Create a method for reporting what Twitch channels we're currently in.

    def _connect(self, timeout_seconds: int = 150) -> socket.socket:
        twitch_address = (TWITCH_SERVER_HOST, TWITCH_SERVER_PORT)
        self._connection = socket.create_connection(twitch_address)
        self._connection.settimeout(timeout_seconds)

    def _send_authentication(
            self, username: str, access_token: str) -> None:
        self._connection.send(f"PASS oauth:{access_token}\r\n".encode())
        self._connection.send(f"NICK {username}\r\n".encode())

    def _verify_authentication(self) -> None:
        # We don't use this method any more (?).
        # This is done in the Listener.
        try:
            response_messages = self.read()
        except socket.timeout:
            # diagnostic
            print("Twitch IRC server did not respond to authentication.")
            self._is_setting_up = False
            raise
        first_command = response_messages[0].command
        first_params = response_messages[0].parameters
        if (
                first_command == "NOTICE"
                and first_params == ["*", "Login authentication failed"]):
            error_message = (
                    "Twitch IRC server did not accept oauth access token.")
            self._is_setting_up = False
            raise LoginAuthenticationFailedError(error_message)

    def _request_capability(self, capability_name: str) -> None:
        self._connection.send(f"CAP REQ :{capability_name}\r\n".encode())

    def setup(
            self, username: str, access_token: str,
            timeout_seconds: int = 5) -> None:
        if self._is_setting_up:
            # diagnostic
            print(
                    "TwitchChatDirectInterface 'setup' was called while it "
                    "was already being set up.")
            return
        self._is_setting_up = True
        identifier = f"Chatbot '{username}'"
        # diagnostic
        try:
            print(f"{identifier} connecting.")
            self._connect(timeout_seconds)
            # diagnostic
            print(f"{identifier} authenticating.")
            self._send_authentication(username, access_token)
            # We will now verify authentication through the Listener (?)
            #self._verify_authentication()
            # diagnostic
            print(f"{identifier} requesting IRC capabilities.")
            self._request_capability("twitch.tv/membership")
            self._request_capability("twitch.tv/tags")
            self._request_capability("twitch.tv/commands")
        except (ConnectionResetError, socket.gaierror) as e:
            self._is_setting_up = False
            print("Excepted error: ", e)
            raise TwitchChatDisconnectedError()
        except OSError as e:
            if e.errno == 10065:
                # a socket operation was attempted to an unreachable host
                self._is_setting_up = False
                print("Excepted error: OSError 10065")
                raise TwitchChatDisconnectedError()
            else:
                print(e.errno)
                raise
        # We should read a few messages to verify successful set-up.
        # diagnostic
        print(f"{identifier} finished setting up.")
        self._is_setting_up = False

    def join_channel(self, channel: str) -> None:
        diag_str = f"{self} joining channel '{channel}'."
        # diagnostic
        print(diag_str)
        try:
            self._connection.send(f"JOIN #{channel}\r\n".encode())
        except ConnectionResetError:
            raise TwitchChatDisconnectedError()
       # Should we read a message to see if it was a success?

    def part_channel(self, channel:str) -> None:
        diag_str = f"{self} parting channel '{channel}'."
        # diagnostic
        print(diag_str)
        try:
            self._connection.send(f"PART #{channel}\r\n".encode())
        except ConnectionResetError:
            raise TwitchChatDisconnectedError()
 
    def read(self) -> List[TwitchIRCMessage]:
        recv_str = ""
        while True:
            try:
                recv_str += self._connection.recv(1024).decode()
            except ConnectionResetError as e:
                print("Excepted error: ", e)
                raise TwitchChatDisconnectedError()
            except ConnectionAbortedError as e:
                print("Excepted error: ", e)
                raise TwitchChatDisconnectedError()
            except UnicodeDecodeError:
                # DIAGNOSTIC
                print(
                        "Caught UnicodeDecodeError. I think this happens "
                        "when people do ASCII art stuff. If you see this "
                        "error, investigate it more.")
            if recv_str.endswith("\r\n"):
                break
        # diagnostic
        print(f"read got: {recv_str}")
        if recv_str == "":
            # If 'read' returns nothing, then the remote server closed the
            # connection.
            raise TwitchChatDisconnectedError()
        server_messages = [line for line in recv_str.split("\r\n") if line]
        return [TwitchIRCMessage(message) for message in server_messages]

    def send(self, channel: str, message: str) -> None:
        send_data = f"PRIVMSG #{channel} :{message}\r\n".encode()
        try:
            bytes_sent = self._connection.send(send_data)
        except ConnectionResetError:
            raise TwitchChatDisconnectedError()
        print(bytes_sent)
        if bytes_sent == 0:
            raise TwitchChatDisconnectedError()

    def pong(self, parameters):
        message = f"PONG :{' '.join(parameters)}\r\n"
        # diagnostic
        try:
            self._connection.send(message.encode())
        except ConnectionResetError:
            raise TwitchChatDisconnectedError()
        print(f"sent: {message}")

    def ping(self):
        message = "PING :tmi.twitch.tv\r\n"
        try:
            self._connection.send(message.encode())
        except ConnectionResetError:
            raise TwitchChatDisconnectedError()
        print(f"sent: {message}")
