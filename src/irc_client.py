import re
import socket
import time

from typing import List, Optional


IRC_MESSAGE_REGEX = re.compile(
        "^(@(?P<tags>.*?) )?(:(?P<prefix>.*?) )?(?P<command>.*?)"
        "( (?P<parameters>.*?))?$")

DISCONNECTION_OSERROR_ERRNOS = {
        10053: "ConnectionAbortedError",
        10054: "ConnectionResetError",
        10065: "A socket operation was attempted to an unreachable host."}


class IRCClientAlreadyConnectedError(Exception):
    pass


class IRCClientNotConnectedError(Exception):
    pass


class RemoteConnectionClosedError(Exception):
    pass


class IRCClientDisconnectedError(Exception):
    def __init__(self, disconnected_client: "IRCClient"):
        self.client = disconnected_client
        super().__init__()

# diagnostic
def _create_retry_error_message_for(irc_client: "IRCClient") -> str:
    host_str = f"{irc_client.saved_host_name}:{irc_client.saved_host_port}"
    return (
            f"{irc_client} disconnected from {host_str}. Sleeping for "
            f"{irc_client.retry_seconds} seconds and retrying request.")


def method_require_not_connected(to_decorate: callable) -> callable:
    def decorated(self, *args, **kwargs):
        if self._connection is not None:
            raise IRCClientAlreadyConnectedError
        return to_decorate(self, *args, **kwargs)
    return decorated


def method_require_connection(to_decorate: callable) -> callable:
    def decorated(self, *args, **kwargs):
        if self._connection is not None:
            return to_decorate(self, *args, **kwargs)
        else:
            raise IRCClientNotConnectedError
    return decorated


def method_raise_disconnected_error(to_decorate: callable) -> callable:
    def decorated(self, *args, **kwargs):
        try:
            return to_decorate(self, *args, **kwargs)
        except (
                OSError, RemoteConnectionClosedError) as e:
            if (
                    isinstance(e, OSError)
                    and e.errno not in DISCONNECTION_OSERROR_ERRNOS.keys()):
                raise
            #diagnostic
            print("Caught an IRC Client method connection error:")
            print(repr(e))
            print("Raising IRCClientDisconnectedError.")
            raise IRCClientDisconnectedError(self)
    return decorated


def method_retry_on_disconnect(to_decorate: callable) -> callable:
    def decorated(self, *args, **kwargs):
        while True:
            error_message = _create_retry_error_message_for(self)
            try:
                return_value = to_decorate(self, *args, **kwargs)
            except IRCClientDisconnectedError:
                print(error_message)
                time.sleep(self.retry_seconds)
                self.retry_seconds = self.retry_seconds * 2
            else:
                self.retry_seconds = self.default_retry_seconds
                return return_value
    return decorated


def method_reconnect_and_retry(to_decorate: callable) -> callable:
    def decorated(self, *args, **kwargs):
        while True:
            error_message = _create_retry_error_message_for(self)
            try:
                return_value = to_decorate(self, *args, **kwargs)
            except IRCClientDisconnectedError:
                #diagnostic
                print(error_message)
                time.sleep(self.retry_seconds)
                self.retry_seconds = self.retry_seconds * 2
                self.disconnect()
                self.connect(
                        self.saved_host_name, self.saved_host_port,
                        self.saved_timeout_seconds)
                self.login(
                        self.saved_password, self.saved_nickname,
                        self.saved_username)
                for capability_name in self.requested_capabilities:
                    self.request_capability(capability_name)
                for channel_name in self.channels:
                    self.join(channel_name)
            else:
                self.retry_seconds = self.default_retry_seconds
                return return_value
    return decorated


class IRCMessage:
    def __init__(self, raw_message: str) -> None:
        match = IRC_MESSAGE_REGEX.fullmatch(raw_message)
        self.command = match.group("command")
        self.tags = {}
        if match.group("tags"):
            for tag in match.group("tags").split(";"):
                tag_key, tag_value = tag.split("=", 1)
                self.tags[tag_key] = tag_value
        self.prefix = match.group("prefix")
        if match.group("parameters"):
            param_colon_split = match.group("parameters").split(":")
            self.parameters = param_colon_split[0].split()
            if len(param_colon_split) > 1:
                self.parameters.append(":".join(param_colon_split[1:]))
        else:
            self.parameters = []


class IRCClient:
    def __init__(self, default_retry_seconds: float=.5) -> None:
        self.default_retry_seconds = default_retry_seconds
        self.retry_seconds = default_retry_seconds
        self._connection = None
        self.saved_host_name = None
        self.saved_host_port = None
        self.saved_timeout_seconds = None
        self.saved_password = None
        self.saved_nickname = None
        self.saved_username = None
        self.requested_capabilities = []
        self.channels = []

    @method_require_not_connected
    def connect(
            self, host_name: str, host_port: int=6667,
            timeout_seconds: Optional[float] = None):
        self.saved_host_name = host_name
        self.saved_host_port = host_port
        self.saved_timeout_seconds = timeout_seconds
        self._connection = socket.create_connection((host_name, host_port))
        if timeout_seconds is not None:
            self._connection.settimeout(timeout_seconds)

    @method_retry_on_disconnect
    @method_raise_disconnected_error
    @method_require_connection
    def login(
            self, password: Optional[str], nickname: Optional[str],
            username: Optional[str]) -> None:
        self.saved_password = password
        self.saved_nickname = nickname
        self.saved_username = username
        if password is not None:
            self._connection.send(f"PASS {password}\r\n".encode())
        if nickname is not None:
            self._connection.send(f"NICK {nickname}\r\n".encode())
        if username is not None:
            self._connection.send(f"USER {username}\r\n".encode())

    @method_require_connection
    def disconnect(self) -> None:
        connection = self._connection
        self._connection = None
        connection.close()

    @method_reconnect_and_retry
    @method_raise_disconnected_error
    @method_require_connection
    def request_capability(self, capability_name: str) -> None:
        self._connection.send(f"CAP REQ :{capability_name}\r\n".encode())
        if capability_name not in self.requested_capabilities:
            self.requested_capabilities.append(capability_name)

    @method_reconnect_and_retry
    @method_raise_disconnected_error
    @method_require_connection
    def pong(self, parameters: List[str]) -> None:
        parameters_str = ""
        for parameter in parameters:
            if not parameter.count(" "):
                if not parameter.startswith(":"):
                    parameters_str += f" {parameter}"
                else:
                    parameters_str += f" :{parameter}"
            else:
                parameters_str += f" :{parameter}"
        self._connection.send(f"PONG {parameters_str}\r\n".encode())

    @method_reconnect_and_retry
    @method_raise_disconnected_error
    @method_require_connection
    def join(self, channel_name: str) -> None:
        self._connection.send(f"JOIN #{channel_name}\r\n".encode())
        if channel_name not in self.channels:
            self.channels.append(channel_name)

    @method_reconnect_and_retry
    @method_raise_disconnected_error
    @method_require_connection
    def part(self, channel_name: str) -> None:
        self._connection.send(f"PART #{channel_name}\r\n".encode())
        try:
            self.channels.remove(channel_name)
        except ValueError:
            pass

    @method_reconnect_and_retry
    @method_raise_disconnected_error
    @method_require_connection
    def private_message(
            self, channel_name: str, message_str: str) -> None:
        irc_message = f"PRIVMSG #{channel_name} :{message_str}\r\n"
        self._connection.send(irc_message.encode())

    @method_reconnect_and_retry
    @method_raise_disconnected_error
    @method_require_connection
    def read_messages(self) -> List[IRCMessage]:
        recv_str = ""
        while True:
            recv_bytes = self._connection.recv(1024)
            recv_str += recv_bytes.decode("utf-8", "replace")
            if recv_str.endswith("\r\n"):
                break
        if recv_str == "":
            raise RemoteConnectionClosed
        raw_messages = [line for line in recv_str.split("\r\n") if line]
        return [IRCMessage(raw_message) for raw_message in raw_messages]
