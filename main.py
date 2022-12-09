import datetime
import json
import random
import threading
import time
import typing

import handlers
import src.startgg as startgg
import src.streambrain as streambrain
import src.twitch as twitch
import src.twitch_chat as twitch_chat

CURRENT_CHANNELS_PATH = "current_channels.txt"
EVENT_PROMO_OPTOUTS_PATH = "event_promo_optouts.txt"


class Routine:
    def __init__(self, interval_ticks: int, delay_ticks: int=0):
        self._interval_ticks = interval_ticks
        self._delay_ticks = delay_ticks
        self._remaining_ticks = delay_ticks

    def run(self):
        pass

    def increment(self, increment_ticks: int):
        if self._remaining_ticks <= 0:
            self.run()
            self._remaining_ticks = (
                    self._interval_ticks + self._remaining_ticks)
        self._remaining_ticks -= increment_ticks


class Schedule:
    def __init__(self):
        self.routines = []
        self._incrementing_forever = False

    def increment(self, increment_ticks: int):
        for routine in self.routines:
            routine.increment(increment_ticks)

    def increment_loop(self, sleep_sec: int, tick_sec_ratio: int=1):
        self._incrementing_forever = True
        while self._incrementing_forever:
            self.increment(sleep_sec * tick_sec_ratio)
            time.sleep(sleep_sec)

    def stop(self):
        self._incrementing_forever = False


class JazzyEventPromoRoutine(Routine):
    def __init__(
            self, startgg_interface: startgg.StartGGInterface,
            twitch_chat_send: callable, interval_sec: int,
            delay_sec: int=0):
        self._startgg_interface = startgg_interface
        self._twitch_chat_send = twitch_chat_send
        self._plugged_event_ids = []
        super().__init__(interval_sec, delay_sec)

    def run(self):
        # This code is hideous and I'm sorry. I'm gonna refactor it.
        with open(CURRENT_CHANNELS_PATH) as current_channels_file:
            current_channels = current_channels_file.read().split()
        with open(EVENT_PROMO_OPTOUTS_PATH) as event_promo_optouts_file:
            event_promo_optouts = event_promo_optouts_file.read().split()
        events = startgg.get_events(self._startgg_interface)
        now = datetime.datetime.now()
        max_datetime = now + datetime.timedelta(days=45)
        upcoming_events = {}
        for event in events:
            if (
                    event["startAt"] > now.timestamp()
                    and event["startAt"] < max_datetime.timestamp()):
                upcoming_events[event["id"]] = event
        imminent_events = upcoming_events.copy()
        for event_id in self._plugged_event_ids:
            try:
                del imminent_events[event_id]
            except KeyError:
                pass
        if not imminent_events:
            imminent_events = upcoming_events
            self._plugged_event_ids = []
        random_event_id = random.choice(list(imminent_events.keys()))
        plug_event = imminent_events[random_event_id]
        tournament_name = plug_event["tournament"]["name"]
        tournament_city = plug_event["tournament"]["city"]
        tournament_state = plug_event["tournament"]["addrState"]
        event_ts = plug_event["startAt"]
        tournament_datetime = datetime.datetime.fromtimestamp(event_ts)
        tournament_day = tournament_datetime.day
        if 11 <= tournament_day <= 13:
            day_suffix = "th"
        else:
            day_suffix_map = {1: "st", 2: "nd", 3: "rd"}
            day_suffix = day_suffix_map.get(tournament_day % 10, "th")
        tournament_date = (
                f"{tournament_datetime.strftime('%a, %b ')} "
                f"{tournament_day}{day_suffix}")
        tournament_url = f"start.gg/{plug_event['tournament']['slug']}"
        for channel_name in current_channels:
            if channel_name not in event_promo_optouts:
                self._twitch_chat_send(
                    channel_name,
                    f"Don't miss \"{tournament_name}\" in "
                    f"{tournament_city}, {tournament_state} on "
                    f"{tournament_date}! Learn more at {tournament_url}.")
        self._plugged_event_ids.append(random_event_id)
 

class CredentialsWriter:
    def __init__(self, credentials_path: str) -> None:
        self._credentials_path = credentials_path
        self._stored_credentials = {}

    def update_credential(self, service_name: str, credential_token: str):
        self._stored_credentials[service_name] = credential_token

    def export(self):
        with open(self._credentials_path, "w") as credentials_file:
            pretty_json = json.dumps(self._stored_credentials, indent=4)
            credentials_file.write(pretty_json)


class TwitchChatReconnector:
    def __init__(
            self, twitch_username: str, twitch_access_token: str,
            twitch_refresh_token: str, twitch_client_id: str,
            twitch_client_secret: str,
            credentials_writer: CredentialsWriter,
            twitch_chat_interface_setup: callable,
            twitch_chat_join: callable, interval_seconds: int=60,
            max_attempts: int=0, new_connection_timeout_sec: int=5) -> None:
        self._twitch_username = twitch_username
        self._twitch_access_token = twitch_access_token
        self._twitch_refresh_token = twitch_refresh_token
        self._twitch_client_id = twitch_client_id
        self._twitch_client_secret = twitch_client_secret
        self._credentials_writer = credentials_writer
        self._twitch_chat_interface_setup = twitch_chat_interface_setup
        self._twitch_chat_join = twitch_chat_join
        self._interval_seconds = interval_seconds
        self._max_attempts = max_attempts
        self._new_connection_timeout_sec = new_connection_timeout_sec

    def reconnect(self, refresh_first=False) -> None:
        if refresh_first:
            self.refresh()
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
        with open(CURRENT_CHANNELS_PATH) as channels_file:
            joined_channels = channels_file.read().split()
        for channel in joined_channels:
            self._twitch_chat_join(channel)

    def refresh(self) -> None:
        # diagnostic
        print("Refreshing access token.")
        refresh_response = twitch.get_refreshed_access_token(
                self._twitch_refresh_token, self._twitch_client_id,
                self._twitch_client_secret)
        self._twitch_access_token = refresh_response["access_token"]
        self._twitch_refresh_token = refresh_response["refresh_token"]
        self._credentials_writer.update_credential(
                "twitch_access_token", self._twitch_access_token)
        self._credentials_writer.update_credential(
                "twitch_refresh_token", self._twitch_refresh_token)
        self._credentials_writer.export()
 

# Load credentials
twitch_username = "botvencabot"
with open("credentials.json") as credentials_file:
    credentials = json.loads(credentials_file.read())
twitch_access_token = credentials["twitch_access_token"]
twitch_refresh_token = credentials["twitch_refresh_token"]
startgg_access_token = credentials["startgg_access_token"]
twitch_client_id = credentials["twitch_client_id"]
twitch_client_secret = credentials["twitch_client_secret"]

# Store credentials
credentials_writer = CredentialsWriter("credentials.json")
credentials_writer.update_credential(
        "twitch_access_token", twitch_access_token)
credentials_writer.update_credential(
        "twitch_refresh_token", twitch_refresh_token)
credentials_writer.update_credential(
        "startgg_access_token", startgg_access_token)
credentials_writer.update_credential("twitch_client_id", twitch_client_id)
credentials_writer.update_credential(
        "twitch_client_secret", twitch_client_secret)
credentials_writer.export()

# Set up direct_twitch_chat_interface
twitch_chat_interface = twitch_chat.DirectInterface()
read_twitch_chat = twitch_chat_interface.read
send_twitch_privmsg = twitch_chat_interface.send
join_twitch_channel = twitch_chat_interface.join_channel
part_twitch_channel = twitch_chat_interface.part_channel
send_twitch_pong = twitch_chat_interface.pong
send_twitch_ping = twitch_chat_interface.ping
with open(CURRENT_CHANNELS_PATH) as channels_file:
    joined_channels = channels_file.read().split()
twitch_chat_reconnector = TwitchChatReconnector(
        twitch_username, twitch_access_token, twitch_refresh_token,
        twitch_client_id, twitch_client_secret, credentials_writer,
        twitch_chat_interface.setup, join_twitch_channel, 10)

# Set up startgg_interface
startgg_interface = startgg.StartGGInterface(startgg_access_token)

# Set up Twitch interface
twitch_interface = twitch.TwitchInterface(
        twitch_access_token, twitch_client_id)

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

# Connect to Twitch chat
try:
    twitch_chat_interface.setup(twitch_username, twitch_access_token)
except twitch_chat.LoginAuthenticationFailedError:
    print("Initial Twitch chat login failed. Attempting reconnection.")
    twitch_chat_reconnector.reconnect()
for channel in joined_channels:
    twitch_chat_interface.join_channel(channel)

# Main loop
#print(twitch_interface.get_streams(user_logins=["vencabot"]))
jazzycircuitbot_brain.start_listening(twitch_chat_listener)
#twitch_chat_interface.send("vencabot", "o shit lol")
#input()
#twitch_chat_interface.send("vencabot", "thisll never get sent lol")
routine_schedule = Schedule()
promo_routine = JazzyEventPromoRoutine(
        startgg_interface, send_twitch_privmsg, 5)
routine_schedule.routines.append(promo_routine)
schedule_thread = threading.Thread(
        target=routine_schedule.increment_loop, args=(1,))
schedule_thread.start()
input()
jazzycircuitbot_brain.stop()
routine_schedule.stop()
