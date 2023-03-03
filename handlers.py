import datetime
import http.client
import urllib

import src.startgg as startgg
import src.streambrain as streambrain
import src.twitch_chat as twitch_chat

from typing import Dict, List

def safe_api_call(decorated: callable) -> callable:
    def decorated_made_safe(*args, **kwargs) -> callable:
        try:
            return decorated(*args, **kwargs)
        except http.client.IncompleteRead:
            print("Non-critical: safe_api_call IncompleteRead. Passing.")
        except TimeoutError:
            print("Non-critical: safe_api_call TimeoutError. Passing.")
        except urllib.error.URLError as e:
            if "10060" in e.reason:
                print(
                        "Non-critical: safe_api_call URLError "
                        "[WinError 10060]. Passing.")
            else:
                raise
    return decorated_made_safe


@safe_api_call
def get_startgg_league_events(
        access_token: str, league_slug: str) -> List[Dict]:
    return startgg.get_league_events(access_token, league_slug)


@safe_api_call
def get_startgg_league_standings(
        access_token: str, league_slug: str) -> List[Dict]:
    return startgg.get_league_standings(access_token, league_slug)


class TwitchChatCommandHandler(streambrain.Handler):
    def __init__(
            self, twitch_chat_send, twitch_chat_join, twitch_chat_part,
            joined_channels, current_channels_path,
            event_promo_optouts_path, startgg_access_token):
        super().__init__(twitch_chat.PrivateMessageEvent)
        self._twitch_chat_send = twitch_chat_send
        self._twitch_chat_join = twitch_chat_join
        self._twitch_chat_part = twitch_chat_part
        self._joined_channels = joined_channels
        self._current_channels_path = current_channels_path
        self._event_promo_optouts_path = event_promo_optouts_path
        self._startgg_access_token = startgg_access_token

    def handle(self, streambrain_event):
        chat_message_body = streambrain_event.message.message_body
        sender = streambrain_event.message.display_name.lower().strip()
        channel = streambrain_event.message.channel
        first_word = chat_message_body.lower().split()[0]
        if first_word == "!jazzyevents":
            self.command_jazzyevents(channel)
        elif first_word == "!beep":
            self.command_beep(channel)
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

    def command_jazzyevents(self, channel):
        events = get_startgg_league_events(
                self._startgg_access_token, "the-jazzy-circuit-4")
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
            with open(self._current_channels_path, "w") as channels_file:
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
            with open(self._current_channels_path, "w") as channels_file:
                channels_file.write("\n".join(self._joined_channels))

    def command_jazzy(self, channel):
        self._twitch_chat_send(
                channel,
                "Love 3rd Strike? Follow twitter.com/thejazzycircuit and "
                "get info about upcoming events and more at "
                "http://jazzycircuit.org !")

    def command_jazzypromosoff(self, channel, sender):
        with open(self._event_promo_optouts_path) as optouts_file:
            optouts = optouts_file.read().split()
        if sender not in optouts:
            optouts.append(sender)
            changes_made = True
        else:
            changes_made = False
        if changes_made:
            optouts_str = ""
            for optout in optouts:
                optouts_str += optout + "\n"
            with open(self._event_promo_optouts_path, "w") as optouts_file:
                optouts_file.write(optouts_str)
        self._twitch_chat_send(
                channel,
                f"Automatic upcoming event promos will no longer be "
                f"sent to the {sender} chat. Use !jazzypromoson to "
                f"receive them again.")

    def command_jazzypromoson(self, channel, sender):
        with open(self._event_promo_optouts_path) as optouts_file:
            optouts = optouts_file.read().split()
        try:
            optouts.remove(sender)
            changes_made = True
        except ValueError:
            changes_made = False
        if changes_made:
            optouts_str = ""
            for optout in optouts:
                optouts_str += optout + "\n"
            with open(self._event_promo_optouts_path, "w") as optouts_file:
                optouts_file.write(optouts_str)
        self._twitch_chat_send(
                channel,
                f"Automatic upcoming event promos will now be "
                f"sent to the {sender} chat if JazzyCircuitBot is there. "
                f"Use !jazzypromosoff to opt-out of them again. Use "
                f"!jazzybot to invite JazzyCircuitBot to your channel's "
                f"chat (must be modded first).")

    def command_jazzystandings(self, channel):
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
        self._twitch_chat_send(channel, top_players_str)


class LeaveIfNotModdedHandler(streambrain.Handler):
    def __init__(
            self, twitch_chat_send, twitch_chat_part, joined_channels,
            current_channels_path):
        super().__init__(twitch_chat.UserstateEvent)
        self._twitch_chat_send = twitch_chat_send
        self._twitch_chat_part = twitch_chat_part
        self._joined_channels = joined_channels
        self._current_channels_path = current_channels_path

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
                with open(self._current_channels_path, "w") as channels_file:
                    channels_file.write("\n".join(self._joined_channels))
                self._twitch_chat_send(
                        channel, "I need to be a mod so that my messages aren't rate-limited so drastically. Unfortunately, that means I need to leave! Give me moderator status and invite me back, if you want!")


class PingHandler(streambrain.Handler):
    def __init__(self, twitch_chat_direct_interface_pong):
        super().__init__(twitch_chat.PingEvent)
        self._pong = twitch_chat_direct_interface_pong

    def handle(self, streambrain_event):
        self._pong(streambrain_event.message)
