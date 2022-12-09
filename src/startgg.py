import urllib.request
import typing
import json

class StartGGInterface:
    START_GG_API_URL = "https://api.start.gg/gql/alpha"
    HTTP_POST_REQUEST_HEADERS = {
        "Content-Type": "application/json"
    }

    def __init__(self, token: str):
        self.HTTP_POST_REQUEST_HEADERS["Authorization"] = f"Bearer {token}" 
    
    def get_query(self, query_string: str) -> typing.Dict[str, typing.Any]:
        query = {"query": query_string}
        jsonified_query = json.dumps(query)
        post_query = jsonified_query.encode("utf-8")

        req = urllib.request.Request(
                self.START_GG_API_URL, data=post_query,
                headers=self.HTTP_POST_REQUEST_HEADERS)
        print("request instantiated successfully")
        with urllib.request.urlopen(req) as resp:
            body = json.loads(resp.read().decode('utf-8'))
            return body

    def get_league_events(self):
        return self.get_query('''
            query LeagueQuery {
                league(slug: "the-jazzy-circuit-4"){
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

# Kenny's old code.        
#def get_events(
#        interface: typing.Type[StartGGInterface]) -> typing.List[str]:
#    events_data = interface.get_league_events()["data"]["league"]["events"]["nodes"]
#    events = []
#    for event in events_data:
#        events.append(f'{event["name"]} ({event["id"]}) starts at {event["startAt"]}. It currently has {event["numEntrants"] if event["numEntrants"] else 0} entrants.')
#    return events

def get_events(interface: StartGGInterface) -> typing.List[dict]:
    return interface.get_league_events()["data"]["league"]["events"]["nodes"]
