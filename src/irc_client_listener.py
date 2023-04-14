from socket import timeout as SocketTimeoutError
from typing import List, Optional

from .streambrain import Event, Listener
from .irc_client import IRCMessage, IRCClient


class IRCClientMessageEvent(Event):
    def __init__(
            self, irc_client: IRCClient, irc_message: IRCMessage) -> None:
        super().__init__(None)
        self.irc_client = irc_client
        self.irc_message = irc_message


class IRCClientPrivateMessageEvent(IRCClientMessageEvent):
    def __init__(
            self, irc_client: IRCClient, irc_message: IRCMessage) -> None:
        super().__init__(irc_client, irc_message)


class IRCClientPingEvent(IRCClientMessageEvent):
    def __init__(
            self, irc_client: IRCClient, irc_message: IRCMessage) -> None:
        super().__init__(irc_client, irc_message)


class IRCClientJoinEvent(IRCClientMessageEvent):
    def __init__(
            self, irc_client: IRCClient, irc_message: IRCMessage) -> None:
        super().__init__(irc_client, irc_message)


class IRCClientUserstateEvent(IRCClientMessageEvent):
    def __init__(
            self, irc_client: IRCClient, irc_message: IRCMessage) -> None:
        super().__init__(irc_client, irc_message)


class IRCClientNoticeEvent(IRCClientMessageEvent):
    def __init__(
            self, irc_client: IRCClient, irc_message: IRCMessage) -> None:
        super().__init__(irc_client, irc_message)


class IRCClientTimeoutEvent(Event):
    def __init__(self, irc_client: IRCClient) -> None:
        super().__init__(None)
        self.irc_client = irc_client


IRC_COMMAND_EVENT_MAP = {
        "PRIVMSG": IRCClientPrivateMessageEvent, "PING": IRCClientPingEvent,
        "JOIN": IRCClientJoinEvent, "USERSTATE": IRCClientUserstateEvent,
        "NOTICE": IRCClientNoticeEvent}


class IRCClientListener(Listener):
    def __init__(
            self, irc_client: IRCClient, sleep_sec: int = 0) -> None:
        super().__init__(sleep_sec)
        self._irc_client = irc_client

    def listen(self) -> List[Event]:
        try:
            new_messages = self._irc_client.read_messages()
        except SocketTimeoutError as e:
            return [IRCClientTimeoutEvent(self._irc_client)]
        events = []
        for irc_message in new_messages:
            try:
                event_type = IRC_COMMAND_EVENT_MAP[irc_message.command]
            except KeyError:
                continue
            else:
                events.append(event_type(self._irc_client, irc_message))
        return events
