from typing import List

from src.givebutter import Transaction
from src.givebutter_listeners import GivebutterDonationEvent
from src.irc_client import IRCClient
from src.safe_web_api_call import safe_web_api_call
from src.streambrain import Handler
from src.twitch import (
        TwitchHTTPError, TwitchStreamData, TwitchOauthManager, get_streams)


@safe_web_api_call
def get_twitch_user_login_streams(
        twitch_oauth_manager: TwitchOauthManager,
        user_logins: List[str]=[]) -> List[TwitchStreamData]:
    try:
        twitch_streams_data, cursor = get_streams(
                twitch_oauth_manager.access_token,
                twitch_oauth_manager.client_id,
                user_logins = user_logins)
        return twitch_streams_data
    except TwitchHTTPError as e:
        if e.code != 401:
            raise
        # diagnostic
        print("Couldn't get live streams. Invalid access token.")
        print("Refreshing access token and trying again.")
        twitch_oauth_manager.refresh()
        twitch_streams_data, cursor = get_streams(
                twitch_oauth_manager.access_token,
                twitch_oauth_manager.client_id, user_logins = user_logins)
        return twitch_streams_data
 

def build_thank_you_message(transaction: Transaction) -> str:
    gs = transaction.giving_space
    thank_you_message = f"Thank you to {gs.donor_name} for their "
    if gs.amount:
            thank_you_message += f"{gs.amount} {transaction.currency} "
    thank_you_message += (
            "donation to the Jazzy Givebutter @ givebutter.com/jazzy3s !")
    if gs.message:
        thank_you_message += f" {gs.donor_name} says: \"{gs.message}\""
    return thank_you_message


class GivebutterDonationHandler(Handler):
    def __init__(
            self, twitch_oauth_manager: TwitchOauthManager,
            irc_client: IRCClient,
            processed_giving_space_ids_path: str) -> None:
        self._twitch_oauth_manager = twitch_oauth_manager
        self._irc_client = irc_client
        self._processed_giving_space_ids_path = (
                processed_giving_space_ids_path)
        super().__init__(GivebutterDonationEvent)

    def handle(
            self,
            givebutter_donation_event: GivebutterDonationEvent) -> None:
        # diagnostic
        print("Got new donation.")
        transaction = givebutter_donation_event.message
        self.send_thank_you_messages(transaction)
        giving_space_id = transaction.giving_space.giving_space_id
        self.update_processed_giving_space_ids_file(giving_space_id)

    def send_thank_you_messages(self, transaction):
        print("Checking if Twitch streams are online.")
        live_jazzybot_streams = get_twitch_user_login_streams(
                self._twitch_oauth_manager, self._irc_client.channels)
        thank_you_message = build_thank_you_message(transaction)
        for stream in live_jazzybot_streams:
            self._irc_client.private_message(
                    stream.user_login, thank_you_message)

    def update_processed_giving_space_ids_file(self, giving_space_id):
        with open(self._processed_giving_space_ids_path, "a") as f:
            f.write(f"{str(giving_space_id)}\n")
