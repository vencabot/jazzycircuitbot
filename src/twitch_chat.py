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


class PrivateMessage:
    def __init__(
            self,
            badge_info: dict,           # 'Badge' : 'badge info' pairs
            badges: dict,               # Also 'badge' : 'badge info' pairs
            color: Optional[str],       # User-set name color, if they did
            display_name: str,          # Username including capitalization
            emotes: str,   # FIX THIS   # Character range : image name pairs
            first_msg: bool,            # Is this a first-time chatter?
            message_id: str,            # No clue how this is used
            mod: bool,                  # Is a moderator (not broadcaster)?
            returning_chatter: bool,    # Is this a second-time chatter?
            room_id: int,               # No clue how this is used
            subscriber: bool,           # Is user a channel subscriber?
            tmi_sent_ts: int, #FIX THIS # Message timestamp
            turbo: bool,                # Is user paying for Twitch Turbo?
            user_id: int,               # Backend ID for sender
            user_type: str,             # "", "admin", "global_mod", "staff"
            vip: bool,                  # Is user a VIP in this channel?
            channel: str,               # Twitch chat message was sent to
            message_body: str,          # The body text of the message
            bits: int = None,           # The amount of bits cheered w/ msg
            reply_parent_msg_id: str = None, # The message replied to
            reply_parent_user_login: str = None, # Login username of replied
            reply_parent_display_name: str = None, # Shown name of replied
            reply_parent_msg_body: str = None # Message text replied to
            ) -> None:
        self.badge_info = badge_info
        self.badges = badges
        self.color = color
        self.display_name = display_name
        self.emotes = emotes
        self.first_msg = first_msg
        self.message_id = message_id
        self.mod = mod
        self.returning_chatter = returning_chatter
        self.room_id = room_id
        self.subscriber = subscriber
        self.tmi_sent_ts = tmi_sent_ts
        self.turbo = turbo
        self.user_id = user_id
        self.user_type = user_type
        self.vip = vip
        self.channel = channel
        self.message_body = message_body
        self.bits = bits
        self.reply_parent_msg_id = reply_parent_msg_id
        self.reply_parent_user_login = reply_parent_user_login
        self.reply_parent_display_name = reply_parent_display_name
        self.reply_parent_msg_body = reply_parent_msg_body


class PrivateMessageEvent(Event):
    def __init__(self, twitch_private_message: PrivateMessage):
        super().__init__(twitch_private_message)

class PingEvent(Event):
    def __init__(self, ping_message_parameters: List[str]):
        super().__init__(ping_message_parameters)

class PongEvent(Event):
    def __init__(self, pong_message_parameters: List[str]):
        super().__init__(pong_message_parameters)

class JoinEvent(Event):
    def __init__(self, twitch_irc_message):
        super().__init__(twitch_irc_message)

class UserstateEvent(Event):
    def __init__(self, twitch_irc_message):
        super().__init__(twitch_irc_message)

class DirectInterfaceListener(Listener):
    def __init__(
            self, twitch_chat_read: callable, twitch_chat_ping: callable,
            twitch_chat_reconnect: callable, sleep_sec: int = 0) -> None:
        super().__init__(sleep_sec)
        self._twitch_chat_read = twitch_chat_read
        self._twitch_chat_ping = twitch_chat_ping
        self._twitch_chat_reconnect = twitch_chat_reconnect
        self._waiting_for_pong = False

    def listen(self) -> List[Event]:
        try:
            new_messages = self._twitch_chat_read()
        except socket.timeout:
            print("diag got timeout")
            if self._waiting_for_pong:
                # We timed out while waiting for our pong.
                self._waiting_for_pong = False
                self._twitch_chat_reconnect()
            else:
                try:
                    self._twitch_chat_ping()
                    self._waiting_for_pong = True
                except TwitchChatDisconnectedError:
                    self._twitch_chat_reconnect()
            return []
        except TwitchChatDisconnectedError:
            self._twitch_chat_reconnect()
            return []
        events = []
        for irc_message in new_messages:
            if irc_message.command == "PRIVMSG":
                message = create_private_message_object_from(irc_message)
                event = PrivateMessageEvent(message)
                events.append(event)
            elif irc_message.command == "PING":
                events.append(PingEvent(irc_message.parameters))
            elif irc_message.command == "PONG":
                self._waiting_for_pong = False
                events.append(PongEvent(irc_message.parameters))
            elif irc_message.command == "JOIN":
                events.append(JoinEvent(irc_message))
            elif irc_message.command == "USERSTATE":
                events.append(UserstateEvent(irc_message))
            if irc_message.command == "NOTICE":
                if irc_message.parameters == (
                        ["*", "Login authentication failed"]):
                    print("Login authenticationed failed! Boooo! T_T")
                    self._twitch_chat_reconnect(True)
        return events


# These keys will only situationally appear in a PRIVMSG's 'tags' field.
OPTIONAL_PRIVMSG_TAGS = [
        "bits", "reply_parent_msg_id", "reply_parent_user_login",
        "reply_parent_display_name", "reply_parent_msg_body", "vip"]


def irc_badge_pairs_to_dict(raw_badge_str: str) -> dict:
    badge_pair_strings = raw_badge_str.split(",")
    badges = {}
    for pair_str in badge_pair_strings:
        pair = pair_str.split("/")
        if pair[0]:
            badges[pair[0]] = pair[1]
    return badges


def create_private_message_object_from(
        twitch_irc_message: TwitchIRCMessage) -> PrivateMessageEvent:
    tags = twitch_irc_message.tags
    for optional_tag in OPTIONAL_PRIVMSG_TAGS:
        if optional_tag not in tags:
            tags[optional_tag] = None
    badge_info = irc_badge_pairs_to_dict(tags["badge-info"])
    badges = irc_badge_pairs_to_dict(tags["badges"])
    color = tags["color"] if tags["color"] else None
    display_name = tags["display-name"]
    emotes = tags["emotes"]
    first_msg = bool(int(tags["first-msg"]))
    message_id = tags["id"]
    mod = bool(int(tags["mod"]))
    returning_chatter = bool(int(tags["returning-chatter"]))
    room_id = int(tags["room-id"])
    subscriber = bool(int(tags["subscriber"]))
    # CONVERT THIS TO DATETIME
    tmi_sent_ts = int(tags["tmi-sent-ts"])
    turbo = bool(int(tags["turbo"]))
    user_id = int(tags["user-id"])
    user_type = tags["user-type"]
    channel = twitch_irc_message.parameters[0][1:]
    message_body = twitch_irc_message.parameters[1]
    bits = int(tags["bits"]) if tags["bits"] is not None else None
    reply_parent_msg_id = tags["reply_parent_msg_id"]
    reply_parent_user_login = tags["reply_parent_user_login"]
    reply_parent_display_name = tags["reply_parent_display_name"]
    reply_parent_msg_body = tags["reply_parent_msg_body"]
    vip = bool(int(tags["vip"])) if tags["vip"] is not None else None
    return PrivateMessage(
            badge_info, badges, color, display_name, emotes, first_msg,
            message_id, mod, returning_chatter, room_id, subscriber,
            tmi_sent_ts, turbo, user_id, user_type, vip, channel,
            message_body, bits, reply_parent_msg_id,
            reply_parent_user_login, reply_parent_display_name,
            reply_parent_msg_body)
