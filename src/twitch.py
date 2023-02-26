import dataclasses
import datetime
import json
import urllib.parse
import urllib.request

from typing import List
from typing import Optional
from typing import Tuple
from typing import Union


API_ENDPOINT_REFERENCE_ANCHOR_MAP = {
        "schedule": "get-channel-stream-schedule",
        "streams": "get-streams",
        "users": "get-users"}
API_REFERENCE_URL = "https://dev.twitch.tv/docs/api/reference/"
API_URL = "https://api.twitch.tv/helix/"
REFRESH_URL = "https://id.twitch.tv/oauth2/token"
TWITCH_DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


class InvalidRefreshTokenError(Exception):
    pass


class TwitchHTTPError(Exception):
    def __init__(
            self, http_error: urllib.error.HTTPError, endpoint: str,
            query_parameters: List[Tuple[str, Union[int, str]]]) -> None:
        self.endpoint = endpoint
        self.query_parameters = query_parameters
        self.code = http_error.code
        self.headers = http_error.headers
        self.reason = http_error.reason
        super().__init__()

    def __str__(self):
        encoded_query = urllib.parse.urlencode(self.query_parameters)
        api_url_str = f"{API_URL}{self.endpoint}?{encoded_query}"
        try:
            anchor = f"#{API_ENDPOINT_REFERENCE_ANCHOR_MAP[self.endpoint]}"
        except KeyError:
            anchor = None
        reference_url_str = f"{API_REFERENCE_URL}{anchor}"
        return (
                f"Request to {api_url_str} failed with HTTP error "
                f"{self.code}. More details at {reference_url_str} .")


@dataclasses.dataclass
class TwitchScheduleSegment:
    segment_id: str
    start_time: datetime.datetime
    end_time: datetime.datetime
    title: str
    canceled_until: Optional[datetime.datetime]
    category_id: int
    category_name: str
    is_recurring: bool


@dataclasses.dataclass
class TwitchStreamData:
    stream_id: int
    user_id: int
    user_login: str
    user_name: str
    game_id: int
    game_name: str
    stream_type: str
    title: str
    tags: List[str]
    viewer_count: int
    started_at: datetime.datetime
    language: str
    thumbnail_url: str
    is_mature: bool


@dataclasses.dataclass
class TwitchUser:
    user_id: int
    login: str
    display_name: str
    user_type: str
    broadcaster_type: str
    description: str
    profile_image_url: str
    offline_image_url: str
    view_count: int
    created_at: datetime.datetime


def _call_api(
        access_token: str, client_id: str, endpoint: str,
        query_parameters: List[Tuple[str, Union[int, str]]]) -> dict:
    encoded_parameters = urllib.parse.urlencode(query_parameters)
    request_url = f"{API_URL}{endpoint}?{encoded_parameters}"
    request_headers = {
            "Authorization": f"Bearer {access_token}",
            "Client-Id": client_id}
    request = urllib.request.Request(request_url, None, request_headers)
    try:
        with urllib.request.urlopen(request) as response:
            return json.load(response)
    except urllib.error.HTTPError as e:
        raise TwitchHTTPError(e, endpoint, query_parameters)


def _call_api_paginated(
        access_token: str, client_id: str, endpoint: str,
        query_parameters: List[Tuple[str, Union[int, str]]],
        paginated_key: Optional[str]=None, page_size: Optional[int]=None,
        max_pages: Optional[int]=None,
        after: Optional[str]=None) -> Tuple[list, dict, str]:
    total_data = []
    total_parameters = query_parameters
    if after:
        total_parameters.append(("after", after))
    page_counter = 0
    while page_counter < max_pages if max_pages else True:
        response_data = _call_api(
                access_token, client_id, endpoint, total_parameters)
        page_counter += 1
        if paginated_key:
            total_data += response_data["data"][paginated_key]
        else:
            total_data += response_data["data"]
        if response_data["pagination"]:
            cursor = response_data["pagination"]["cursor"]
            total_parameters = query_parameters + [("after", cursor)]
        else:
            cursor = None
            break
    if paginated_key:
        del response_data["data"][paginated_key]
        metadata = response_data["data"]
    else:
        metadata = {}
    return total_data, metadata, cursor


def _construct_schedule_segment_from_raw_dict(
        segment_data: dict) -> TwitchScheduleSegment:
    segment_data["segment_id"] = segment_data["id"]
    del segment_data["id"]
    segment_data["start_time"] = datetime.datetime.strptime(
            segment_data["start_time"], TWITCH_DATETIME_FORMAT)
    segment_data["end_time"] = datetime.datetime.strptime(
            segment_data["end_time"], TWITCH_DATETIME_FORMAT)
    segment_data["category_id"] = segment_data["category"]["id"]
    segment_data["category_name"] = segment_data["category"]["name"]
    del segment_data["category"]
    if segment_data["canceled_until"] is not None:
        segment_data["canceled_until"] = datetime.datetime.strptime(
                segment_data["canceled_until"], TWITCH_DATETIME_FORMAT)
    return TwitchScheduleSegment(**segment_data)


def _construct_stream_data_from_raw_dict(
        stream_data: dict) -> TwitchStreamData:
    stream_data["stream_id"] = int(stream_data["id"])
    del stream_data["id"]
    stream_data["user_id"] = int(stream_data["user_id"])
    stream_data["game_id"] = int(stream_data["game_id"])
    stream_data["stream_type"] = stream_data["type"]
    del stream_data["type"]
    stream_data["started_at"] = datetime.datetime.strptime(
            stream_data["started_at"], TWITCH_DATETIME_FORMAT)
    # tag_ids is deprecated
    try:
        del stream_data["tag_ids"]
    except KeyError:
        pass
    return TwitchStreamData(**stream_data)
 

def _construct_streams_query_parameters(
        user_ids: List[int], user_logins: List[str],
        game_ids: List[int], stream_type: Optional[str],
        language: Optional[str], page_size: Optional[int]) -> List[tuple]:
    query_parameters = []
    query_parameters += [("user_id", x) for x in user_ids]
    query_parameters += [("user_login", x) for x in user_logins]
    query_parameters += [("game_id", x) for x in game_ids]
    if stream_type is not None:
        query_parameters.append(("type", stream_type))
    if language is not None:
        query_parameters.append(("language", language))
    if page_size is not None:
        query_parameters.append(("first", page_size))
    return query_parameters


def _construct_user_from_raw_dict(user_data: dict) -> TwitchUser:
    user_data["user_id"] = int(user_data["id"])
    del user_data["id"]
    user_data["user_type"] = user_data["type"]
    del user_data["type"]
    user_data["created_at"] = datetime.datetime.strptime(
            user_data["created_at"], TWITCH_DATETIME_FORMAT)
    return TwitchUser(**user_data)


def get_channel_stream_schedule(
        access_token: str, client_id: str, broadcaster_id: int,
        segment_ids: List[str]=[], start_time: Optional[str]=None,
        page_size: Optional[int]=None, max_pages: Optional[int]=None,
        after: Optional[str]=None) -> dict:
    parameters = [("broadcaster_id", broadcaster_id)]
    for segment_id in segment_ids:
        parameters.append(("id", segment_id))
    if start_time:
        parameters.append(("start_time", start_time))
    segments_data, metadata, cursor = _call_api_paginated(
            access_token, client_id, "schedule", parameters, "segments",
            page_size, max_pages, after)
    segments = []
    for segment_data in segments_data:
        segment = _construct_schedule_segment_from_raw_dict(segment_data)
        segments.append(segment)
    return segments, metadata, cursor


def get_streams(
        access_token: str, client_id: str, user_ids: List[int]=[],
        user_logins: List[str]=[], game_ids: List[int]=[],
        stream_type: Optional[str]=None, language: Optional[str]=None,
        page_size: Optional[int]=None, max_pages: Optional[int]=None,
        after: Optional[str]=None) -> Tuple[List[TwitchStreamData], str]:
    query_parameters = _construct_streams_query_parameters(
            user_ids, user_logins, game_ids, stream_type, language,
            page_size)
    streams_data, metadata, cursor = _call_api_paginated(
            access_token, client_id, "streams", query_parameters, None,
            page_size, max_pages, after)
    streams = []
    for stream_data in streams_data:
        stream_data = _construct_stream_data_from_raw_dict(stream_data)
        streams.append(stream_data)
    return streams, cursor


def get_users(
        access_token: str, client_id: str, user_ids: List[int]=[],
        logins: List[str]=[]) -> dict:
    parameters = []
    for user_id in user_ids:
        parameters.append(("id", user_id))
    for login in logins:
        parameters.append(("login", login))
    users_data = _call_api(
            access_token, client_id, "users", parameters)
    users = []
    for user_data in users_data["data"]:
        users.append(_construct_user_from_raw_dict(user_data))
    return users


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
