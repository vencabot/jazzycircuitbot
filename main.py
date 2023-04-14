import datetime
import http.client
import json
import random
import sys
import threading
import typing
import urllib.error

import src.givebutter as givebutter
import src.startgg as startgg
import src.irc_client_listener as irc_client_listener

from time import sleep
from typing import Dict, List, Optional, Tuple

from src.irc_client import IRCClient
from src.irc_client_handlers import (
        ReportTimeoutHandler, LeaveIfNotModdedHandler, PongIfPingedHandler,
        TwitchChatLoginFailedHandler)
from src.streambrain import StreamBrain
from src.twitch import (
        TwitchHTTPError, TwitchStreamData, TwitchOauthManager, get_streams)
from src.twitch_chat_command_handler import TwitchChatCommandHandler

CURRENT_CHANNELS_PATH = "current_channels.txt"
EVENT_PROMO_OPTOUTS_PATH = "event_promo_optouts.txt"


def safe_api_call(decorated: callable) -> callable:
    def decorated_made_safe(*args, **kwargs) -> callable:
        try:
            return decorated(*args, **kwargs)
        except http.client.IncompleteRead:
            print("Non-critical: safe_api_call IncompleteRead. Passing.")
        except http.client.RemoteDisconnected:
            print(
                    "Non-critical: safe_api_call RemoteDisconnected. "
                    "Passing.")
        except TimeoutError:
            print("Non-critical: safe_api_call TimeoutError. Passing.")
        except urllib.error.URLError as e:
            if "10060" in e.reason:
                print(
                        "Non-critical: safe_api_call URLError "
                        "[WinError 10060]. Passing.")
            else:
                raise
        except urllib.error.HTTPError as e:
            if e.code == 524:
                print(
                        "Non-critical: safe_api_call HTTPError code 524. "
                        "Passing.")
            else:
                raise
    return decorated_made_safe


@safe_api_call
def get_givebutter_transactions(
        api_key: str) -> List[givebutter.Transaction]:
    return givebutter.get_transactions(api_key)


@safe_api_call
def get_twitch_streams(
        twitch_oauth_manager: TwitchOauthManager, user_ids: List[int]=[],
        user_logins: List[str]=[], game_ids: List[int]=[],
        stream_type: Optional[str]=None, language: Optional[str]=None,
        page_size: Optional[int]=None, max_pages: Optional[int]=None,
        after: Optional[str]=None) -> Tuple[List[TwitchStreamData], str]:
    already_failed = False
    while True:
        try:
            return get_streams(
                    twitch_oauth_manager.access_token,
                    twitch_oauth_manager.client_id, user_ids, user_logins,
                    game_ids, stream_type, language, page_size, max_pages,
                    after)
        except TwitchHTTPError as e:
            if e.code != 401:
                raise
            if already_failed:
                raise Exception(
                        "get_twitch_streams: Twitch API key is invalid.")
            print("Couldn't get live streams. Invalid access token.")
            print("Refreshing access token and trying again.")
            twitch_oauth_manager.refresh()
            already_failed = True


@safe_api_call
def get_startgg_league_events(
        access_token: str, league_slug: str) -> List[Dict]:
    return startgg.get_league_events(access_token, league_slug)


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
            # diagnostic
            try:
                routine.increment(increment_ticks)
            except Exception as e:
                exc_type, exc_object, exc_traceback = sys.exc_info()
                exc_filename = exc_traceback.tb_frame.f_code.co_filename
                exc_line_no = exc_traceback.tb_lineno
                with open("error_that_killed_me.txt", "w") as crashlog_file:
                    crashlog_file.write(
                            f"{exc_type.__name__} in {exc_filename} at "
                            f"line {exc_line_no}: {exc_object}")
                raise

    def increment_loop(self, sleep_sec: int, tick_sec_ratio: int=1):
        self._incrementing_forever = True
        while self._incrementing_forever:
            self.increment(sleep_sec * tick_sec_ratio)
            sleep(sleep_sec)

    def stop(self):
        self._incrementing_forever = False


class GivebutterThankingRoutine(Routine):
    def __init__(
            self, givebutter_api_key: str,
            twitch_oauth_manager: TwitchOauthManager, irc_client: IRCClient,
            processed_giving_space_ids: typing.List[int], interval_sec: int,
            delay_sec: int=0) -> None:
        self.givebutter_api_key = givebutter_api_key
        self.twitch_oauth_manager = twitch_oauth_manager
        self.irc_client = irc_client
        self.processed_giving_space_ids = processed_giving_space_ids
        super().__init__(interval_sec, delay_sec)

    def run(self):
        # diagnostic
        print("Checking for new donations.")
        new_donations = []
        try:
            gb_transactions = get_givebutter_transactions(
                    self.givebutter_api_key)
        except Exception as e:
            # We might run into urllib.error.HTTPError or some OSError.
            # I would like to narrow this down to the exact Exceptions that
            # we'll be running into at some point.
            # diagnostic
            print("Exception while getting Givebutter transactions.")
            print(e)
            raise
        for transaction in gb_transactions:
            giving_space_id = transaction.giving_space.giving_space_id
            if giving_space_id not in self.processed_giving_space_ids:
                new_donations.append(transaction)
        if not new_donations:
            # diagnostic
            print("No new donations.")
            return
        # diagnostic
        print("Got new donations", new_donations)
        print("Checking if Twitch streams are online.")
        live_jazzybot_streams = get_twitch_streams(
                self.twitch_oauth_manager,
                user_logins=self.irc_client.channels)[0]
        for transaction in new_donations:
            giving_space_id = transaction.giving_space.giving_space_id
            currency = transaction.currency
            donor_name = transaction.giving_space.donor_name
            amount = transaction.giving_space.amount
            message = transaction.giving_space.message
            chat_message = f"Thank you to {donor_name} for the "
            if amount:
                if currency == "USD":
                    chat_message += f"${amount} "
                else:
                    chat_message += f"{amount} {currency} "
            chat_message += (
                    "donation to the Jazzy Givebutter @ "
                    "givebutter.com/jazzy3s!")
            if message:
                chat_message += f" {donor_name} says: \"{message}\""
            for stream in live_jazzybot_streams:
                self.irc_client.private_message(
                        stream.user_login, chat_message)
            self.processed_giving_space_ids.append(giving_space_id)


class JazzyEventPromoRoutine(Routine):
    def __init__(
            self, startgg_access_token: str,
            twitch_oauth_manager: TwitchOauthManager, irc_client: IRCClient,
            interval_sec: int, delay_sec: int=0):
        self._startgg_access_token = startgg_access_token
        self._twitch_oauth_manager = twitch_oauth_manager
        self._irc_client = irc_client
        self._plugged_event_ids = []
        super().__init__(interval_sec, delay_sec)

    def run(self):
        # This code is hideous and I'm sorry. I'm gonna refactor it.
        with open(EVENT_PROMO_OPTOUTS_PATH) as event_promo_optouts_file:
            optouts = event_promo_optouts_file.read().split()
        # diagnostic
        print("Getting startgg events.")
        events = get_startgg_league_events(
                self._startgg_access_token, "the-jazzy-circuit-4")
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
        promo_channels = []
        for channel_name in self._irc_client.channels:
            if channel_name not in optouts:
                promo_channels.append(channel_name)
        # diagnostic
        print("Checking if Twitch streams are online.")
        live_jazzybot_streams = get_twitch_streams(
                self._twitch_oauth_manager,
                user_logins=self._irc_client.channels)[0]
        for stream in live_jazzybot_streams:
            self._irc_client.private_message(
                stream.user_login,
                f"Don't miss \"{tournament_name}\" in "
                f"{tournament_city}, {tournament_state} on "
                f"{tournament_date}! Learn more at {tournament_url} .")
        self._plugged_event_ids.append(random_event_id)
 

# Load credentials
twitch_username = "botvencabot"
with open("credentials.json") as credentials_file:
    credentials = json.loads(credentials_file.read())
twitch_refresh_token = credentials["twitch_refresh_token"]
startgg_access_token = credentials["startgg_access_token"]
twitch_client_id = credentials["twitch_client_id"]
twitch_client_secret = credentials["twitch_client_secret"]
givebutter_api_key = credentials["givebutter_api_key"]
twitch_oauth_manager = TwitchOauthManager(
        twitch_client_id, twitch_client_secret, twitch_refresh_token)
twitch_oauth_manager.refresh()

# Set up Twitch chat
twitch_chat = IRCClient()
twitch_chat.connect("irc.chat.twitch.tv")

# Set up listeners
twitch_chat_listener = irc_client_listener.IRCClientListener(twitch_chat)

# Set up handlers
twitch_chat_command_handler = TwitchChatCommandHandler(
        twitch_chat, CURRENT_CHANNELS_PATH, EVENT_PROMO_OPTOUTS_PATH,
        startgg_access_token)
leave_if_not_modded_handler = LeaveIfNotModdedHandler(
        twitch_chat, CURRENT_CHANNELS_PATH)
pong_if_pinged_handler = PongIfPingedHandler(twitch_chat)
twitch_chat_login_failed_handler = TwitchChatLoginFailedHandler(
        twitch_chat, twitch_oauth_manager)
report_timeout_handler = ReportTimeoutHandler()

# Create StreamBrain
jazzycircuitbot_brain = StreamBrain()
jazzycircuitbot_brain.activate_handler(twitch_chat_command_handler)
jazzycircuitbot_brain.activate_handler(leave_if_not_modded_handler)
jazzycircuitbot_brain.activate_handler(pong_if_pinged_handler)
jazzycircuitbot_brain.activate_handler(twitch_chat_login_failed_handler)
jazzycircuitbot_brain.activate_handler(report_timeout_handler)

# Login to Twitch chat
twitch_password = f"oauth:{twitch_oauth_manager.access_token}"
twitch_chat.login(twitch_password, twitch_username, None)
twitch_chat.request_capability("twitch.tv/tags")
twitch_chat.request_capability("twitch.tv/membership")
twitch_chat.request_capability("twitch.tv/commands")
with open(CURRENT_CHANNELS_PATH) as current_channels_file:
    raw_channel_lines = current_channels_file.readlines()
for raw_channel_line in raw_channel_lines:
    twitch_chat.join(raw_channel_line.strip())

# Givebutter stuff
with open("processed_giving_space_ids.txt") as giving_space_ids_file:
    raw_giving_space_id_strs = giving_space_ids_file.readlines()
processed_giving_space_ids = []
for raw_giving_space_id_str in raw_giving_space_id_strs:
    giving_space_id_str = raw_giving_space_id_str.strip()
    if giving_space_id_str:
        processed_giving_space_ids.append(int(giving_space_id_str))
givebutter_thanking_routine = GivebutterThankingRoutine(
        givebutter_api_key, twitch_oauth_manager, twitch_chat,
        processed_giving_space_ids, 10)

# Main loop
jazzycircuitbot_brain.start_listening(twitch_chat_listener)
routine_schedule = Schedule()
promo_routine = JazzyEventPromoRoutine(
        startgg_access_token, twitch_oauth_manager, twitch_chat, 1800)
routine_schedule.routines.append(promo_routine)
routine_schedule.routines.append(givebutter_thanking_routine)
schedule_thread = threading.Thread(
        target=routine_schedule.increment_loop, args=(1,))
schedule_thread.start()
input()
jazzycircuitbot_brain.stop()
routine_schedule.stop()

# Save processed giving space IDs to an output file.
processed_giving_space_ids_output_str = ""
for gs_id in givebutter_thanking_routine.processed_giving_space_ids:
    processed_giving_space_ids_output_str += f"{gs_id}\n"
with open("processed_giving_space_ids.txt", "w") as giving_space_ids_file:
    giving_space_ids_file.write(processed_giving_space_ids_output_str)

# We should also save our new Twitch Refresh Token.
