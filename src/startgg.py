import urllib.request
import json

from typing import Any, Dict


START_GG_API_URL = "https://api.start.gg/gql/alpha"


def _call_api(access_token: str, query_string: str) -> Dict[str, Any]:
    query = json.dumps({"query": query_string}).encode("utf-8")
    request_headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}"}
    request = urllib.request.Request(
            START_GG_API_URL, query, request_headers)
    # diagnostic
    print("request instantiated successfully")
    with urllib.request.urlopen(request) as response:
        body = json.loads(response.read().decode("utf-8"))
    return body


def get_league_events(access_token: str, league_slug: str):
    # bug: this only fetches the first 500 events
    query_string = (
            '''
            query LeagueQuery {
                league(slug: "''' + league_slug + '''"){
                    events(query: { 
                        page: 1,
                        perPage: 500
                    }){
                        nodes { 
                            id 
                            name 
                            startAt 
                            numEntrants
                            slug
                            tournament {
                                id
                                name
                                city
                                addrState
                                countryCode
                                slug
                            }
                        }
                    }
                }
            }
            ''')
    league_data = _call_api(access_token, query_string)
    return league_data["data"]["league"]["events"]["nodes"]
        

def get_league_standings(access_token: str, league_slug: str):
    query_string_raw = (
            '''
            query LeagueStandings {
                league(slug: "''' + league_slug + '''") {
                    id
                    name
                    standings (query: {
                        page: PAGE_NUMBER,
                        perPage: 500
                    }) {
                        pageInfo {
                            totalPages
                            total
                        }
                        nodes {
                            id
                            placement
                            totalPoints
                            player {
                                id
                                gamerTag
                            }
                        }
                    }
                }
            }
            ''')
    standings = []
    current_page = 1
    while True:
        query_string = query_string_raw.replace(
                "PAGE_NUMBER", str(current_page))
        query_response = _call_api(access_token, query_string)
        standings_data = query_response["data"]["league"]["standings"]
        standings.extend(standings_data["nodes"])
        total_pages = standings_data["pageInfo"]["totalPages"]
        if current_page == total_pages:
            break
    return standings
