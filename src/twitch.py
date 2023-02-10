import dataclasses
import json
import urllib.parse
import urllib.request

from typing import List
from typing import Optional


API_URL = "https://api.twitch.tv/helix/"
REFRESH_URL = "https://id.twitch.tv/oauth2/token"


class InvalidRefreshTokenError(Exception):
    pass


class TwitchHTTPError(Exception):
    def __init__(self, code: int, reasons: List[str]=[]) -> None:
        self.code = code
        self.reasons = reasons
        super().__init__()


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
    tags: List[str]
    viewer_count: int
    # TO-DO: convert this to a datetime
    started_at: str
    language: str
    thumbnail_url: str
    is_mature: bool


def _call_api(
        access_token: str, client_id: str, endpoint: str,
        query_parameters: List[tuple],
        request_limit: Optional[int]=None) -> dict:
    total_data = []
    total_parameters = query_parameters
    request_counter = 0
    while request_counter < request_limit if request_limit else True:
        encoded_parameters = urllib.parse.urlencode(total_parameters)
        request_url = f"{API_URL}{endpoint}?{encoded_parameters}"
        request_headers = {
                "Authorization": f"Bearer {access_token}",
                "Client-Id": client_id}
        request = urllib.request.Request(request_url, None, request_headers)
        try:
            with urllib.request.urlopen(request) as response:
                response_data = json.load(response)
        except urllib.error.HTTPError as e:
            raise TwitchHTTPError(e.code, [e.reason])
        request_counter += 1
        try:
            total_data += response_data["data"]
        except KeyError:
            total_data = response_data
        if not "pagination" in response_data:
            break
        if response_data["pagination"]:
            cursor = response_data["pagination"]["cursor"]
            total_parameters = query_parameters + [("after", cursor)]
        else:
            break
    return total_data


def _construct_streams_query_parameters(
        user_ids: List[int], user_logins: List[str],
        game_ids: List[int], stream_type: Optional[str],
        language: Optional[str], max_results: Optional[int]) -> List[tuple]:
    query_parameters = []
    query_parameters += [("user_id", x) for x in user_ids]
    query_parameters += [("user_login", x) for x in user_logins]
    query_parameters += [("game_id", x) for x in game_ids]
    if stream_type is not None:
        query_parameters.append(("type", stream_type))
    if language is not None:
        query_parameters.append(("language", language))
    if max_results is not None:
        query_parameters.append(("first", max_results))
    return query_parameters
 

def get_streams(
        access_token: str, client_id: str, user_ids: List[int]=[],
        user_logins: List[str]=[], game_ids: List[int]=[],
        stream_type: Optional[str]=None, language: Optional[str]=None,
        max_results: Optional[int]=None,
        request_limit: Optional[int]=None) -> List[TwitchStreamData]:
    parameters = _construct_streams_query_parameters(
            user_ids, user_logins, game_ids, stream_type, language,
            max_results)
    streams_data = _call_api(
            access_token, client_id, "streams", parameters,
            request_limit)
    streams = []
    for stream_data in streams_data:
        # rename attributes away from protected words
        stream_data["stream_id"] = stream_data["id"]
        del stream_data["id"]
        stream_data["stream_type"] = stream_data["type"]
        del stream_data["type"]
        # tag_ids is deprecated
        try:
            del stream_data["tag_ids"]
        except KeyError:
            pass
        streams.append(TwitchStreamData(**stream_data))
    return streams


def refresh_access_token(
        client_id: str, client_secret: str, refresh_token: str) -> str:
    parameters = {
            "client_id": client_id, "client_secret": client_secret,
            "grant_type": "refresh_token", "refresh_token": refresh_token}
    refresh_data = bytes(urllib.parse.urlencode(parameters), "ASCII")
    request = urllib.request.Request(REFRESH_URL, refresh_data)
    with urllib.request.urlopen(request) as response:
        response_data = json.load(response)
    if "error" in response_data:
        if response_data["message"] == "Invalid refresh token":
            raise InvalidRefreshTokenError(refresh_token)
    return response_data["access_token"]
