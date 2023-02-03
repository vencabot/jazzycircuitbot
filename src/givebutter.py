import dataclasses
import typing
import json
import urllib.parse
import urllib.request

API_URL = "https://api.givebutter.com/v1/"

@dataclasses.dataclass
class GivingSpace:
    giving_space_id: int
    donor_name: str
    amount: int
    message: str

@dataclasses.dataclass
class Transaction:
    currency: str
    giving_space: GivingSpace

class GivebutterInterface:
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def get_transactions(self) -> None:
        query_params = [("scope", "null")]
        response_data = self._make_request("transactions", query_params)
        transactions = []
        for data in response_data:
            currency = data["currency"]
            # diagnostic
            if not data["giving_space"]:
                # This is a bug I've experienced rarely. Sometimes,
                # especially immediately following a donation, a transaction
                # may be served up by the API which has 'None' for the
                # giving_space object. Because this bug is rare and I'd like
                # to diagnose it, we should capture it.
                # For now, let's just not return transactions until (?) they
                # have a giving_space.
                continue
            gs_id = data["giving_space"]["id"]
            gs_name = data["giving_space"]["name"]
            gs_amount = data["giving_space"]["amount"]
            gs_msg = data["giving_space"]["message"]
            giving_space = GivingSpace(gs_id, gs_name, gs_amount, gs_msg)
            transactions.append(Transaction(currency, giving_space))
        return transactions

    def _make_request(
            self, endpoint: str, query_parameters: typing.List[tuple]):
        encoded_parameters = urllib.parse.urlencode(query_parameters)
        request_url = f"{API_URL}{endpoint}"
        # For some ungodly fucking reason, the request fails if a
        # User-Agent header is not supplied.
        request_headers = {
                "Authorization": f"Bearer {self._api_key}",
                "User-Agent": "Fuck You."}
        request = urllib.request.Request(request_url, None, request_headers)
        try:
            with urllib.request.urlopen(request) as response:
                response_data = json.load(response)
        except urllib.error.HTTPError as e:
            raise
        if not "links" in response_data:
            return [response_data]
        # We have multiple pages of data.
        total_data = response_data["data"]
        while response_data["links"]["next"]:
            request_url = response_data["links"]["next"]
            request = urllib.request.Request(
                    request_url, None, request_headers)
            try:
                with urllib.request.urlopen(request) as response:
                    response_data = json.load(response)
            except urllib.error.HTTPError as e:
                raise
            total_data += response_data["data"]
        return total_data
