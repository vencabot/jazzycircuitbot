from src.irc_client import IRCClient
from src.irc_client_listener import (
        IRCClientNoticeEvent, IRCClientUserstateEvent, IRCClientPingEvent,
        IRCClientTimeoutEvent)
from src.streambrain import Handler
from src.twitch import TwitchOauthManager


FAILED_LOGIN_IRC_PARAMS = ["*", "Login authentication failed"]


class ReportTimeoutHandler(Handler):
    def __init__(self) -> None:
        super().__init__(IRCClientTimeoutEvent)

    def handle(
            self, irc_client_timeout_event: IRCClientTimeoutEvent) -> None:
        print(f"{irc_client_timeout_event.irc_client} timed out.")


class LeaveIfNotModdedHandler(Handler):
    def __init__(
            self, irc_client: IRCClient,
            current_channels_path: str) -> None:
        super().__init__(IRCClientUserstateEvent)
        self._irc_client = irc_client
        self._current_channels_path = current_channels_path

    def handle(self, userstate_event: IRCClientUserstateEvent) -> None:
        if userstate_event.irc_client is not self._irc_client:
            return
        user = userstate_event.irc_message.tags["display-name"]
        channel = userstate_event.irc_message.parameters[0][1:]
        user_type = userstate_event.irc_message.tags["user-type"]
        if user == "JazzyCircuitBot" and user_type != "mod":
            self._irc_client.part(channel)
            with open(self._current_channels_path, "w") as channels_file:
                channels_file.write("\n".join(self._irc_client.channels))
            self._irc_client.private_message(
                    channel,
                    "I need to be a mod so that my messages aren't rate-"
                    "limited so drastically. Unfortunately, that means I "
                    "need to leave! Give me moderator status and invite me "
                    "back, if you want!")


class PongIfPingedHandler(Handler):
    def __init__(self, irc_client: IRCClient) -> None:
        super().__init__(IRCClientPingEvent)
        self._irc_client = irc_client

    def handle(self, irc_client_ping_event: IRCClientPingEvent) -> None:
        if irc_client_ping_event.irc_client is not self._irc_client:
            return
        # diagnostic
        print("Got ping. Sending pong.")
        self._irc_client.pong(irc_client_ping_event.irc_message.parameters)


class TwitchChatLoginFailedHandler(Handler):
    def __init__(
            self, irc_client: IRCClient,
            twitch_oauth_manager: TwitchOauthManager) -> None:
        super().__init__(IRCClientNoticeEvent)
        self._irc_client = irc_client
        self._twitch_oauth_manager = twitch_oauth_manager

    def handle(self, irc_client_notice_event: IRCClientNoticeEvent) -> None:
        notice_client = irc_client_notice_event.irc_client
        notice_parameters = irc_client_notice_event.irc_message.parameters
        login_failed = notice_parameters == FAILED_LOGIN_IRC_PARAMS
        if notice_client is not self._irc_client or not login_failed:
            return
        new_password = f"oauth:{self._twitch_oauth_manager.access_token}"
        if self._irc_client.saved_password == new_password:
            self._twitch_oauth_manager.refresh()
            access_token = self._twitch_oauth_manager.access_token
            new_password = f"oauth:{access_token}"
        self.relogin_with_new_password(up_to_date_password)

    def relogin_with_new_password(self, new_password: str):
        self._irc_client.disconnect()
        self._irc_client.connect(
                self._irc_client.saved_host_name,
                self._irc_client.saved_host_port,
                self._irc_client.saved_timeout_seconds)
        self._irc_client.login(
                new_password, self._irc_client.saved_nickname,
                self._irc_client.saved_username)
        for channel_name in self._irc_client.channels:
            self._irc_client.join(channel_name)
