import dataclasses
import json
import typing
import urllib.parse
import urllib.request


class InvalidRefreshTokenError(Exception):
    pass


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
    viewer_count: int
    # TO-DO: convert this to a datetime
    started_at: str
    language: str
    thumbnail_url: str
    tag_ids: str
    is_mature: bool


class TwitchInterface:
    def __init__(self, access_token: str, client_id: str):
        self._access_token = access_token
        self._client_id = client_id

    def get_streams(
            self, user_ids: typing.List[str]=[],
            user_logins: typing.List[str]=[],
            game_ids: typing.List[str]=[],
            stream_type: str=None, language: str=None,
            max_results: int=None):
        query_parameters = []
        for user_id in user_ids:
            query_parameters.append(("user_id", user_id))
        for user_login in user_logins:
            query_parameters.append(("user_login", user_login))
        for game_id in game_ids:
            query_parameters.append(("game_id", game_id))
        if stream_type is not None:
            query_parameters.append(("type", stream_type))
        if language is not None:
            query_parameters.append(("language", language))
        if max_results is not None:
            query_parameters.append(("first", max_results))
        streams_data = self._make_request("streams", query_parameters)
        streams = []
        for stream_data in streams_data["data"]:
            stream_data["stream_id"] = stream_data["id"]
            stream_data["stream_type"] = stream_data["type"]
            del stream_data["id"]
            del stream_data["type"]
            streams.append(TwitchStreamData(**stream_data))
        return streams

    def _make_request(
            self, endpoint: str, query_parameters: typing.List[tuple]):
        api_url = "https://api.twitch.tv/helix/"
        encoded_parameters = urllib.parse.urlencode(query_parameters)
        request_url = f"{api_url}{endpoint}?{encoded_parameters}"
        request_headers = {
                "Authorization": f"Bearer {self._access_token}",
                "Client-Id": self._client_id}
        twitch_request = urllib.request.Request(
                request_url, None, request_headers)
        with urllib.request.urlopen(twitch_request) as twitch_response:
            response_data = json.load(twitch_response)
        return response_data


def get_refreshed_access_token(
        refresh_token: str, client_id: str, client_secret: str) -> str:
    refresh_url = "https://id.twitch.tv/oauth2/token"
    refresh_parameters = {
            "client_id": client_id, "client_secret": client_secret,
            "grant_type": "refresh_token", "refresh_token": refresh_token}
    refresh_parameters_encoded = urllib.parse.urlencode(refresh_parameters)
    refresh_data = bytes(refresh_parameters_encoded, "ASCII")
    refresh_request = urllib.request.Request(refresh_url, refresh_data)
    with urllib.request.urlopen(refresh_request) as refresh_response:
        response_data = json.load(refresh_response)
    if "error" in response_data:
        if response_data["message"] == "Invalid refresh token":
            raise InvalidRefreshTokenError(refresh_token)
    return response_data
