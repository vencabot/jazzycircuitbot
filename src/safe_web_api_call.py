from http.client import IncompleteRead, RemoteDisconnected
from time import sleep
from urllib.error import HTTPError, URLError


DEFAULT_RETRY_SECONDS = 2
SAFE_HTTPERRORS = [500, 503, 524]
SAFE_URLERRORS = [10060, 10065]
WEB_API_ERRORS = (
        TimeoutError, IncompleteRead, RemoteDisconnected, URLError)


def safe_web_api_call(to_decorate: callable) -> callable:
    def decorated(*args, **kwargs):
        retry_attempt = 0
        retry_seconds = DEFAULT_RETRY_SECONDS
        while True:
            try:
                return to_decorate(*args, **kwargs)
            except WEB_API_ERRORS as e:
                if type(e) == URLError and e.errno not in SAFE_URLERRORS:
                    raise
                if type(e) == HTTPError and e.code not in SAFE_HTTPERRORS:
                    raise
                retry_attempt += 1
                # diagnostic
                print(
                        f"Non-critical: safe_web_api_call {e}: {e.message}."
                        f"Retry #{retry_attempt} in {retry_seconds} "
                        "seconds.")
                sleep(retry_seconds)
                retry_seconds = retry_seconds * 2
                # diagnostic
                print(
                        f"safe_web_abi_call: Slept for {retry_seconds} "
                        "seconds. Retry #{retry_attempt}.")
            else:
                break
    return decorated
