import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("COC_API_KEY")
CLAN_TAG = os.getenv("CLAN_TAG").replace("#", "%23")

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Accept": "application/json"
}

def save_json(filename, data):
    with open(filename, "w") as f:
        json.dump(data, f, indent=2)

def main():
    clan_url = f"https://api.clashofclans.com/v1/clans/{CLAN_TAG}"
    war_url = f"https://api.clashofclans.com/v1/clans/{CLAN_TAG}/currentwar"

    clan = requests.get(clan_url, headers=headers).json()
    war = requests.get(war_url, headers=headers).json()

    save_json("./data/clan.json", clan)
    save_json("./data/currentWar.json", war)

    print("Saved clan.json and currentWar.json")

if __name__ == "__main__":
    main()
