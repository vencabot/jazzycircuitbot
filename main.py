import dataclasses
import datetime
import json
import typing
import urllib.parse
import urllib.request

import src.startgg as startgg
import src.streambrain as streambrain
import src.twitch_chat as twitch_chat

JAZZYCIRCUITBOT_CHANNELS_PATH = "jazzycircuitbot_channels.txt"

@dataclasses.dataclass
class TwitchStreamData:
    stream_id: str
    user_id: str
    user_login: str
    user_name: str
    game_id: str
    game_name: str
    stream_type: str
    title: str
    viewer_count: int
    # TO-DO: convert this to a datetime
    started_at: str
    language: str
    thumbnail_url: str
    tag_ids: str
    is_mature: bool


class TwitchInterface:
    def __init__(self, access_token: str, client_id: str):
        self._access_token = access_token
        self._client_id = client_id

    def get_streams(
            self, user_ids: typing.List[str]=[],
            user_logins: typing.List[str]=[],
            game_ids: typing.List[str]=[],
            stream_type: str=None, language: str=None,
            max_results: int=None):
        query_parameters = []
        for user_id in user_ids:
            query_parameters.append(("user_id", user_id))
        for user_login in user_logins:
            query_parameters.append(("user_login", user_login))
        for game_id in game_ids:
            query_parameters.append(("game_id", game_id))
        if stream_type is not None:
            query_parameters.append(("type", stream_type))
        if language is not None:
            query_parameters.append(("language", language))
        if max_results is not None:
            query_parameters.append(("first", max_results))
        streams_data = self._make_request("streams", query_parameters)
        streams = []
        for stream_data in streams_data["data"]:
            stream_data["stream_id"] = stream_data["id"]
            stream_data["stream_type"] = stream_data["type"]
            del stream_data["id"]
            del stream_data["type"]
            streams.append(TwitchStreamData(**stream_data))
        return streams

    def _make_request(
            self, endpoint: str, query_parameters: typing.List[tuple]):
        api_url = "https://api.twitch.tv/helix/"
        encoded_parameters = urllib.parse.urlencode(query_parameters)
        request_url = f"{api_url}{endpoint}?{encoded_parameters}"
        request_headers = {
                "Authorization": f"Bearer {self._access_token}",
                "Client-Id": self._client_id}
        twitch_request = urllib.request.Request(
                request_url, None, request_headers)
        with urllib.request.urlopen(twitch_request) as twitch_response:
            response_data = json.load(twitch_response)
        return response_data


class DemoCommandHandler(streambrain.Handler):
    def __init__(
            self, twitch_chat_send, twitch_chat_join, twitch_chat_part,
            joined_channels, startgg_interface):
        super().__init__(twitch_chat.PrivateMessageEvent)
        self._twitch_chat_send = twitch_chat_send
        self._twitch_chat_join = twitch_chat_join
        self._twitch_chat_part = twitch_chat_part
        self._joined_channels = joined_channels
        self._startgg_interface = startgg_interface

    def handle(self, streambrain_event):
        chat_message_body = streambrain_event.message.message_body
        sender = streambrain_event.message.display_name.lower().strip()
        channel = streambrain_event.message.channel
        first_word = chat_message_body.lower().split()[0]
        if first_word == "!events":
            self.command_events(channel)
        elif first_word == "!beep":
            self.command_beep(channel)
        elif first_word == "!jazzybot":
            self.command_jazzybot(channel, sender)
        elif first_word == "!ggsjazzy":
            self.command_ggsjazzy(channel, sender)
        elif first_word == "!jazzy":
            self.command_jazzy(channel)

    def command_events(self, channel):
        events = startgg.get_events(self._startgg_interface)
        now = datetime.datetime.now().timestamp()
        upcoming_events = []
        for event in events:
            if event["startAt"] > now:
                upcoming_events.append(event)
        registrations = 0
        for event in upcoming_events:
            try:
                registrations += event["numEntrants"]
            except TypeError:
                if event["numEntrants"] is None:
                    # The tournament's entrants is set to private
                    pass
                else:
                    raise
        reply_str = (
                f"There are currently {len(upcoming_events)} upcoming "
                f"events in Jazzy Season 4 with a total of {registrations} "
                "registrations. Learn more and sign up at "
                "start.gg/thejazzycircuit/schedule !")
        self._twitch_chat_send(channel, reply_str)

    def command_beep(self, channel):
        self._twitch_chat_send(channel, "boop")
        print("GOT BEEP")

    def command_jazzybot(self, channel, sender):
        if sender not in self._joined_channels:
            self._twitch_chat_join(sender)
            self._joined_channels.append(sender)
            with open(JAZZYCIRCUITBOT_CHANNELS_PATH, "w") as channels_file:
                channels_file.write("\n".join(self._joined_channels))
            self._twitch_chat_send(
                    channel,
                    f"@{sender} I joined your chat! If I don't respond "
                    "there, make sure I have the Moderator role and invite "
                    "me again! :D")
            self._twitch_chat_send(sender, "Thanks for inviting me!")
        else:
            self._twitch_chat_send(
                    channel,
                    f"@{sender} I'm already listening to your chat, I "
                    "believe! If I'm not responding there, let Vencabot "
                    "know so he can have a look! 💪")

    def command_ggsjazzy(self, channel, sender):
        if sender in self._joined_channels:
            self._twitch_chat_send(channel, "GGs!")
            self._twitch_chat_part(sender)
            self._joined_channels.remove(sender)
            with open(JAZZYCIRCUITBOT_CHANNELS_PATH, "w") as channels_file:
                channels_file.write("\n".join(self._joined_channels))

    def command_jazzy(self, channel):
        self._twitch_chat_send(
                channel,
                "Love 3rd Strike? Follow twitter.com/thejazzycircuit and "
                "get info about upcoming events and more at "
                "http://jazzycircuit.org !")


class LeaveIfNotModdedHandler(streambrain.Handler):
    def __init__(
            self, twitch_chat_send, twitch_chat_part, joined_channels):
        super().__init__(twitch_chat.UserstateEvent)
        self._twitch_chat_send = twitch_chat_send
        self._twitch_chat_part = twitch_chat_part
        self._joined_channels = joined_channels

    def handle(self, streambrain_event):
        irc_message = streambrain_event.message
        user = irc_message.tags["display-name"]
        channel = irc_message.parameters[0][1:]
        if user == "JazzyCircuitBot":
            if (
                    not irc_message.tags["user-type"] == "mod"
                    and channel in self._joined_channels):
                self._twitch_chat_part(channel)
                self._joined_channels.remove(channel)
                with open(JAZZYCIRCUITBOT_CHANNELS_PATH, "w") as channels_file:
                    channels_file.write("\n".join(self._joined_channels))
                self._twitch_chat_send(
                        channel, "I need to be a mod so that my messages aren't rate-limited so drastically. Unfortunately, that means I need to leave! Give me moderator status and invite me back, if you want!")


class PingHandler(streambrain.Handler):
    def __init__(self, twitch_chat_direct_interface_pong):
        super().__init__(twitch_chat.PingEvent)
        self._pong = twitch_chat_direct_interface_pong

    def handle(self, streambrain_event):
        self._pong(streambrain_event.message)


# Load credentials
with open("credentials.json") as credentials_file:
    credentials = json.loads(credentials_file.read())
twitch_access_token = credentials["twitch_access_token"]
startgg_access_token = credentials["startgg_access_token"]
twitch_client_id = credentials["twitch_client_id"]

# Set up direct_twitch_chat_interface
twitch_chat_direct_interface = twitch_chat.DirectInterface()
twitch_chat_direct_interface.setup("botvencabot", twitch_access_token)
with open(JAZZYCIRCUITBOT_CHANNELS_PATH) as channels_file:
    joined_channels = channels_file.read().split()
for channel in joined_channels:
    twitch_chat_direct_interface.join_channel(channel)

# Set up startgg_interface
startgg_interface = startgg.StartGGInterface(startgg_access_token)

# Set up Twitch interface
twitch_interface = TwitchInterface(twitch_access_token, twitch_client_id)

# Set up other interfaces
read_twitch_chat = twitch_chat_direct_interface.read
send_twitch_privmsg = twitch_chat_direct_interface.send
join_twitch_channel = twitch_chat_direct_interface.join_channel
part_twitch_channel = twitch_chat_direct_interface.part_channel
send_twitch_pong = twitch_chat_direct_interface.pong

# Set up listeners
twitch_chat_listener = twitch_chat.DirectInterfaceListener(read_twitch_chat)

# Set up handlers
demo_command_handler = DemoCommandHandler(
        send_twitch_privmsg, join_twitch_channel, part_twitch_channel,
        joined_channels, startgg_interface)
leave_if_not_modded_handler = LeaveIfNotModdedHandler(
        send_twitch_privmsg, part_twitch_channel, joined_channels)
ping_handler = PingHandler(send_twitch_pong)

# Create StreamBrain
demo_brain = streambrain.StreamBrain()
demo_brain.activate_handler(demo_command_handler)
demo_brain.activate_handler(leave_if_not_modded_handler)
demo_brain.activate_handler(ping_handler)

# Main loop
#print(twitch_interface.get_streams(user_logins=["vencabot"]))
demo_brain.start_listening(twitch_chat_listener)
input()
demo_brain.stop()
