import datetime
import json
import time
import typing

import handlers
import src.startgg as startgg
import src.streambrain as streambrain
import src.twitch as twitch
import src.twitch_chat as twitch_chat

JAZZYCIRCUITBOT_CHANNELS_PATH = "jazzycircuitbot_channels.txt"


class TwitchChatReconnector:
    def __init__(
            self, twitch_username: str, twitch_access_token: str,
            twitch_chat_interface_setup: callable,
            twitch_chat_join: callable, interval_seconds: int=60,
            max_attempts: int=0, new_connection_timeout_sec: int=5) -> None:
        self._twitch_username = twitch_username
        self._twitch_access_token = twitch_access_token
        self._twitch_chat_interface_setup = twitch_chat_interface_setup
        self._twitch_chat_join = twitch_chat_join
        self._interval_seconds = interval_seconds
        self._max_attempts = max_attempts
        self._new_connection_timeout_sec = new_connection_timeout_sec

    def reconnect(self) -> None:
        attempts = 0
        while self._max_attempts <= 0 or attempts < self._max_attempts:
            attempts += 1
            # diagnostic
            diag_str = f"Twitch chat reconnect attempt #{attempts}"
            if self._max_attempts > 0:
                diag_str += f" of {self._max_attempts}"
            print(diag_str)
            try:
                self._twitch_chat_interface_setup(
                        self._twitch_username, self._twitch_access_token,
                        self._new_connection_timeout_sec)
            except twitch_chat.TwitchChatDisconnectedError:
                print(
                        "Reconnection failed. Trying again in "
                        f"{self._interval_seconds} seconds.") 
                time.sleep(self._interval_seconds)
                continue
            else:
                break
        with open(JAZZYCIRCUITBOT_CHANNELS_PATH) as channels_file:
            joined_channels = channels_file.read().split()
        for channel in joined_channels:
            self._twitch_chat_join(channel)


# Load credentials
twitch_username = "botvencabot"
with open("credentials.json") as credentials_file:
    credentials = json.loads(credentials_file.read())
twitch_access_token = credentials["twitch_access_token"]
startgg_access_token = credentials["startgg_access_token"]
twitch_client_id = credentials["twitch_client_id"]

# Set up direct_twitch_chat_interface
twitch_chat_interface = twitch_chat.DirectInterface()
twitch_chat_interface.setup(twitch_username, twitch_access_token)
with open(JAZZYCIRCUITBOT_CHANNELS_PATH) as channels_file:
    joined_channels = channels_file.read().split()
for channel in joined_channels:
    twitch_chat_interface.join_channel(channel)

# Set up startgg_interface
startgg_interface = startgg.StartGGInterface(startgg_access_token)

# Set up Twitch interface
twitch_interface = twitch.TwitchInterface(
        twitch_access_token, twitch_client_id)

# Set up other interfaces
read_twitch_chat = twitch_chat_interface.read
send_twitch_privmsg = twitch_chat_interface.send
join_twitch_channel = twitch_chat_interface.join_channel
part_twitch_channel = twitch_chat_interface.part_channel
send_twitch_pong = twitch_chat_interface.pong
send_twitch_ping = twitch_chat_interface.ping
twitch_chat_reconnector = TwitchChatReconnector(
        twitch_username, twitch_access_token, twitch_chat_interface.setup,
        join_twitch_channel, 10)

# Set up listeners
twitch_chat_listener = twitch_chat.DirectInterfaceListener(
        read_twitch_chat, send_twitch_ping,
        twitch_chat_reconnector.reconnect)

# Set up handlers
twitch_chat_command_handler = handlers.TwitchChatCommandHandler(
        send_twitch_privmsg, join_twitch_channel, part_twitch_channel,
        joined_channels, startgg_interface)
leave_if_not_modded_handler = handlers.LeaveIfNotModdedHandler(
        send_twitch_privmsg, part_twitch_channel, joined_channels)
ping_handler = handlers.PingHandler(send_twitch_pong)

# Create StreamBrain
jazzycircuitbot_brain = streambrain.StreamBrain()
jazzycircuitbot_brain.activate_handler(twitch_chat_command_handler)
jazzycircuitbot_brain.activate_handler(leave_if_not_modded_handler)
jazzycircuitbot_brain.activate_handler(ping_handler)

# Main loop
#print(twitch_interface.get_streams(user_logins=["vencabot"]))
jazzycircuitbot_brain.start_listening(twitch_chat_listener)
#twitch_chat_interface.send("vencabot", "o shit lol")
#input()
#twitch_chat_interface.send("vencabot", "thisll never get sent lol")
input()
jazzycircuitbot_brain.stop()
