import dataclasses
import json
import urllib.parse
import urllib.request

from typing import List, Tuple, Union

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

def get_transactions(api_key: str) -> List[Transaction]:
    query_params = [("scope", "null")]
    response_data = _call_api(api_key, "transactions", query_params)
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
        gs = data["giving_space"]
        giving_space = GivingSpace(
                gs["id"], gs["name"], gs["amount"], gs["message"])
        transactions.append(Transaction(currency, giving_space))
    return transactions

def _call_api(
        api_key: str, endpoint: str,
        query_parameters: List[Tuple[str, Union[int, str]]]):
    encoded_parameters = urllib.parse.urlencode(query_parameters)
    request_url = f"{API_URL}{endpoint}?{encoded_parameters}"
    # Givebutter bug: API requests fail without a User-Agent header.
    request_headers = {
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "Fuck You."}
    request = urllib.request.Request(request_url, None, request_headers)
    with urllib.request.urlopen(request) as response:
        response_data = json.load(response)
    if not "links" in response_data:
        return [response_data]
    # We have multiple pages of data.
    total_data = response_data["data"]
    while response_data["links"]["next"]:
        request_url = response_data["links"]["next"]
        request = urllib.request.Request(request_url, None, request_headers)
        with urllib.request.urlopen(request) as response:
            response_data = json.load(response)
        total_data += response_data["data"]
    return total_data
