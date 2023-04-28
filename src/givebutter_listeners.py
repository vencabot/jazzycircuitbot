import src.givebutter as givebutter

from typing import List

from src.safe_web_api_call import safe_web_api_call
from src.streambrain import Event, Listener


def get_givebutter_transactions(
        givebutter_api_key: str) -> List[givebutter.Transaction]:
    return givebutter.get_transactions(givebutter_api_key)


class GivebutterDonationEvent(Event):
    pass


class GivebutterListener(Listener):
    def __init__(
            self, givebutter_api_key: str,
            processed_giving_space_ids: List[int],
            sleep_sec: int = 10) -> None:
        self._givebutter_api_key = givebutter_api_key
        self._processed_giving_space_ids = processed_giving_space_ids
        super().__init__(sleep_sec)

    def listen(self) -> List[Event]:
        # diagnostic
        print("Checking for new donations.")
        new_donations = []
        for transaction in get_givebutter_transactions(
                self._givebutter_api_key):
            giving_space_id = transaction.giving_space.giving_space_id
            if giving_space_id not in self._processed_giving_space_ids:
                new_donations.append(transaction)
                self._processed_giving_space_ids.append(giving_space_id)
        return [GivebutterDonationEvent(x) for x in new_donations]
