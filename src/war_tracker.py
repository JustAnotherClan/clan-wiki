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

LAST_SAVED_FILE = "./data/last_saved_war.txt"

def get_current_war():
    url = f"https://api.clashofclans.com/v1/clans/{CLAN_TAG}/currentwar"
    response = requests.get(url, headers=headers)
    return response.json()

def save_war(war_data):
    end_time = war_data.get("endTime")
    if not end_time:
        return False

    safe_time = end_time.replace(":", "-").replace(".", "-")

    filename = f"./data/wars/{safe_time}.json"
    with open(filename, "w") as f:
        json.dump(war_data, f, indent=2)

    with open(LAST_SAVED_FILE, "w") as f:
        f.write(end_time)

    print(f"Saved war: {filename}")
    return True

def get_last_saved_endtime():
    if not os.path.exists(LAST_SAVED_FILE):
        return None
    with open(LAST_SAVED_FILE, "r") as f:
        return f.read().strip()

def main():
    war = get_current_war()
    state = war.get("state")
    end_time = war.get("endTime")

    print(f"War state: {state}")

    if state == "warEnded" and end_time:
        last_saved = get_last_saved_endtime()
        if last_saved != end_time:
            save_war(war)
        else:
            print("War already saved.")
    else:
        print("No ended war to save.")

if __name__ == "__main__":
    main()
