import os
import json
import requests
from datetime import datetime
from pathlib import Path

API_TOKEN = os.getenv("COC_API_TOKEN")
CLAN_TAG = os.getenv("CLAN_TAG")  # e.g. #XXXXXXX
CLAN_NAME = "JustAnotherClan"

BASE_URL = "https://api.clashofclans.com/v1"

DATA_DIR = Path("data")
WARS_DIR = DATA_DIR / "wars"
CWL_DIR = DATA_DIR / "cwl"
MEMBERS_DIR = DATA_DIR / "members"


def coc_get(path: str):
    headers = {"Authorization": f"Bearer {API_TOKEN}"}
    url = f"{BASE_URL}{path}"
    resp = requests.get(url, headers=headers, timeout=15)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def normalize_tag(tag: str) -> str:
    return tag.upper().replace("O", "0")


def sanitize_name(name: str) -> str:
    return "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in name.strip()) or "Unknown"


def get_current_war():
    tag = normalize_tag(CLAN_TAG).replace("#", "%23")
    return coc_get(f"/clans/{tag}/currentwar")


def get_cwl_group():
    tag = normalize_tag(CLAN_TAG).replace("#", "%23")
    return coc_get(f"/clans/{tag}/currentwar/leaguegroup")


def ensure_dirs():
    WARS_DIR.mkdir(parents=True, exist_ok=True)
    CWL_DIR.mkdir(parents=True, exist_ok=True)
    MEMBERS_DIR.mkdir(parents=True, exist_ok=True)


def build_war_key(war_json: dict) -> str:
    clan = war_json.get("clan", {})
    opponent = war_json.get("opponent", {})

    if clan.get("name") == CLAN_NAME:
        opp_name = opponent.get("name", "UnknownOpponent")
    else:
        opp_name = clan.get("name", "UnknownOpponent")

    opp_name_clean = sanitize_name(opp_name)

    start_time = war_json.get("startTime") or war_json.get("preparationStartTime")
    if start_time:
        dt = datetime.strptime(start_time.split(".")[0], "%Y%m%dT%H%M%S")
        date_str = dt.strftime("%Y-%m-%d")
    else:
        date_str = datetime.utcnow().strftime("%Y-%m-%d")

    return f"{date_str}_{opp_name_clean}"


def save_war(war_json: dict, war_key: str):
    path = WARS_DIR / f"{war_key}.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(war_json, f, ensure_ascii=False, indent=2)
    print(f"Saved war: {path}")


def update_cwl_group(war_json: dict, war_key: str, cwl_group: dict | None):
    if not cwl_group:
        return

    season = cwl_group.get("season")
    if not season:
        return

    season_dir = CWL_DIR / season
    season_dir.mkdir(parents=True, exist_ok=True)
    group_path = season_dir / "group.json"

    if group_path.exists():
        with group_path.open("r", encoding="utf-8") as f:
            group_data = json.load(f)
    else:
        group_data = {"season": season, "rounds": []}

    if not any(r.get("war_key") == war_key for r in group_data["rounds"]):
        group_data["rounds"].append({"war_key": war_key})

    with group_path.open("w", encoding="utf-8") as f:
        json.dump(group_data, f, ensure_ascii=False, indent=2)

    print(f"Updated CWL group: {group_path}")


def update_member_histories(war_json: dict, war_key: str, is_cwl: bool, season: str | None = None):
    clan = war_json.get("clan", {})
    opponent = war_json.get("opponent", {})

    if clan.get("name") == CLAN_NAME:
        our_side = clan
        opp_name = opponent.get("name", "UnknownOpponent")
    else:
        our_side = opponent
        opp_name = clan.get("name", "UnknownOpponent")

    for m in our_side.get("members", []):
        player_tag = m.get("tag")
        if not player_tag:
            continue

        player_tag_norm = normalize_tag(player_tag)
        member_path = MEMBERS_DIR / f"{player_tag_norm}.json"

        if member_path.exists():
            with member_path.open("r", encoding="utf-8") as f:
                member_data = json.load(f)
        else:
            member_data = {
                "playerTag": player_tag_norm,
                "name": m.get("name", "Unknown"),
                "history": []
            }

        for atk in m.get("attacks", []):
            entry = {
                "war_key": war_key,
                "type": "CWL" if is_cwl else "NORMAL",
                "season": season,
                "opponent": opp_name,
                "stars": atk.get("stars"),
                "destruction": atk.get("destructionPercentage"),
                "order": atk.get("order"),
                "defenderTag": atk.get("defenderTag"),
            }

            if not any(h.get("war_key") == war_key and h.get("order") == entry["order"]
                       for h in member_data["history"]):
                member_data["history"].append(entry)

        with member_path.open("w", encoding="utf-8") as f:
            json.dump(member_data, f, ensure_ascii=False, indent=2)

        print(f"Updated member history: {member_path}")


def main():
    ensure_dirs()

    war = get_current_war()
    if not war:
        print("War state: None")
        print("No ended war to save.")
        return

    state = war.get("state")
    print(f"War state: {state}")

    if state != "warEnded":
        print("No ended war to save.")
        return

    cwl_group = get_cwl_group()
    is_cwl = cwl_group is not None
    season = cwl_group.get("season") if cwl_group else None

    war_key = build_war_key(war)
    save_war(war, war_key)

    if is_cwl:
        update_cwl_group(war, war_key, cwl_group)

    update_member_histories(war, war_key, is_cwl=is_cwl, season=season)


if __name__ == "__main__":
    main()
