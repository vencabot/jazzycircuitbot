import src.startgg as startgg

from datetime import datetime
from http.client import IncompleteRead, RemoteDisconnected
from typing import Dict, List
from urllib.error import URLError

from src.irc_client import IRCClient
from src.irc_client_listener import IRCClientPrivateMessageEvent
from src.streambrain import Handler


def safe_api_call(decorated: callable) -> callable:
    def decorated_made_safe(*args, **kwargs) -> callable:
        try:
            return decorated(*args, **kwargs)
        except (
                IncompleteRead, RemoteDisconnected, TimeoutError,
                URLError) as e:
            if type(e) == URLError and e.errno != 10065:
                raise
            print(f"Non-critical: safe_api_call {e}: {e.message}. Passing.")
    return decorated_made_safe


@safe_api_call
def get_startgg_league_events(
        access_token: str, league_slug: str) -> List[Dict]:
    return startgg.get_league_events(access_token, league_slug)


@safe_api_call
def get_startgg_league_standings(
        access_token: str, league_slug: str) -> List[Dict]:
    return startgg.get_league_standings(access_token, league_slug)


class TwitchChatCommandHandler(Handler):
    def __init__(
            self, irc_client: IRCClient, current_channels_path: str,
            event_promo_optouts_path: str,
            startgg_access_token: str) -> None:
        super().__init__(IRCClientPrivateMessageEvent)
        self._irc_client = irc_client
        self._current_channels_path = current_channels_path
        self._event_promo_optouts_path = event_promo_optouts_path
        self._startgg_access_token = startgg_access_token

    def handle(
            self, irc_client_event: IRCClientPrivateMessageEvent) -> None:
        if irc_client_event.irc_client is not self._irc_client:
            return
        irc_tags = irc_client_event.irc_message.tags
        irc_parameters = irc_client_event.irc_message.parameters
        # is this really who 'sender' is? Check IRC protocol
        sender = irc_tags["display-name"].lower().strip()
        channel = irc_parameters[0][1:]
        chat_message_body = irc_parameters[1]
        first_word = chat_message_body.lower().split()[0]
        if first_word == "!jazzyevents":
            self.command_jazzyevents(channel)
        elif first_word == "!jazzybot":
            self.command_jazzybot(channel, sender)
        elif first_word == "!ggsjazzy":
            self.command_ggsjazzy(channel, sender)
        elif first_word == "!jazzy":
            self.command_jazzy(channel)
        elif first_word == "!jazzypromosoff":
            self.command_jazzypromosoff(channel, sender)
        elif first_word == "!jazzypromoson":
            self.command_jazzypromoson(channel, sender)
        elif first_word == "!jazzystandings":
            self.command_jazzystandings(channel)

    def command_jazzyevents(self, channel: str) -> None:
        events = get_startgg_league_events(
                self._startgg_access_token, "the-jazzy-circuit-4")
        now = datetime.now().timestamp()
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
        self._irc_client.private_message(channel, reply_str)

    def command_jazzybot(self, channel: str, sender: str) -> None:
        if sender not in self._irc_client.channels:
            self._irc_client.join(sender)
            with open(self._current_channels_path, "w") as channels_file:
                channels_file.write("\n".join(self._irc_client.channels))
            self._irc_client.private_message(
                    channel,
                    f"@{sender} I joined your chat! If I don't respond "
                    "there, make sure I have the Moderator role and invite "
                    "me again! :D")
            self._irc_client.private_message(
                    sender, "Thanks for inviting me!")
        else:
            self._irc_client.private_message(
                    channel,
                    f"@{sender} I'm already listening to your chat, I "
                    "believe! If I'm not responding there, let Vencabot "
                    "know so he can have a look! 💪")

    def command_ggsjazzy(self, channel: str, sender: str) -> None:
        if sender in self._irc_client.channels:
            self._irc_client.private_message(channel, "GGs!")
            self._irc_client.part(sender)
            with open(self._current_channels_path, "w") as channels_file:
                channels_file.write("\n".join(self._irc_client.channels))

    def command_jazzy(self, channel: str) -> None:
        self._irc_client.private_message(
                channel,
                "Love 3rd Strike? Follow twitter.com/thejazzycircuit and "
                "get info about upcoming events and more at "
                "http://jazzycircuit.org !")

    def command_jazzypromosoff(self, channel: str, sender: str) -> None:
        with open(self._event_promo_optouts_path) as optouts_file:
            optouts = optouts_file.read().split()
        if sender not in optouts:
            optouts.append(sender)
            with open(self._event_promo_optouts_path, "w") as optouts_file:
                optouts_file.write("\n".join(optouts))
        self._irc_client.private_message(
                channel,
                "Automatic upcoming event promos will no longer be sent to "
                f"the {sender} chat. Use !jazzypromoson to receive them "
                "again.")

    def command_jazzypromoson(self, channel: str, sender: str) -> None:
        with open(self._event_promo_optouts_path) as optouts_file:
            optouts = optouts_file.read().split()
        try:
            optouts.remove(sender)
        except ValueError:
            pass
        else:
            with open(self._event_promo_optouts_path, "w") as optouts_file:
                optouts_file.write("\n".join(optouts))
        self._irc_client.private_message(
                channel,
                "Automatic upcoming event promos will now be sent to the "
                f"{sender} chat if JazzyCircuitBot is there. Use "
                "!jazzypromosoff to opt-out of them. Use !jazzybot to "
                "invite JazzyCircuitBot to your channel's chat (must be "
                "modded first).")

    def command_jazzystandings(self, channel: str) -> None:
        standings = get_startgg_league_standings(
                self._startgg_access_token, "the-jazzy-circuit-4")
        top_players = []
        for standing in standings[:6]:
            gamer_tag = standing["player"]["gamerTag"]
            total_points = standing["totalPoints"]
            top_players.append((gamer_tag, total_points))
        for standing in standings[6:]:
            if standing["totalPoints"] == standings[5]["totalPoints"]:
                gamer_tag = standing["player"]["gamerTag"]
                total_points = standing["totalPoints"]
                top_players.append((gamer_tag, total_points))
            else:
                break
        top_players_str = "The top-ranked players in Jazzy Season 4 are "
        for player_tuple in top_players:
            top_players_str += f"{player_tuple[0]} ({player_tuple[1]})"
            player_index = top_players.index(player_tuple)
            if player_index < len(top_players) - 2:
                top_players_str += ", "
            elif player_index == len(top_players) - 2:
                top_players_str += ", and "
        top_players_str += " -- but only the TOP 5 players will compete in the Jazzy Finale! See more at start.gg/thejazzycircuit/standings ."
        self._irc_client.private_message(channel, top_players_str)
