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
    # Determine our side and opponent
    clan = war_json.get("clan", {})
    opponent = war_json.get("opponent", {})

    if clan.get("name") == CLAN_NAME:
        opp_name = opponent.get("name", "UnknownOpponent")
        opp_tag = opponent.get("tag", "UnknownTag")
    else:
        # In case API flips sides
        opp_name = clan.get("name", "UnknownOpponent")
        opp_tag = clan.get("tag", "UnknownTag")

    opp_name_clean = sanitize_name(opp_name)
    start_time = war_json.get("startTime") or war_json.get("preparationStartTime")
    if start_time:
        # API time format: 20260101T000000.000Z
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

    # CWL season folder
    season_dir = CWL_DIR / season
    season_dir.mkdir(parents=True, exist_ok=True)
    group_path = season_dir / "group.json"

    # Determine CWL day if present
    round_index = None
    if "rounds" in cwl_group:
        # Try to match this war by opponent tag
        our_tag = normalize_tag(CLAN_TAG)
        clan = war_json.get("clan", {})
        opponent = war_json.get("opponent", {})
        if clan.get("tag") and normalize_tag(clan["tag"]) == our_tag:
            opp_tag = opponent.get("tag")
        else:
            opp_tag = clan.get("tag")

        if opp_tag:
            opp_tag_norm = normalize_tag(opp_tag)
            for i, rnd in enumerate(cwl_group["rounds"], start=1):
                for war_tag in rnd.get("warTags", []):
                    # We can’t resolve warTags to wars here without extra calls,
                    # so for Phase 1 we just store war_key and day if we know it.
                    # If you want, we can later enhance this with more API calls.
                    pass
            # For now, we’ll just not set day if we can’t infer it cleanly.
    # Load existing group file
    if group_path.exists():
        with group_path.open("r", encoding="utf-8") as f:
            group_data = json.load(f)
    else:
        group_data = {"season": season, "rounds": []}

    # Avoid duplicates
    if not any(r.get("war_key") == war_key for r in group_data["rounds"]):
        entry = {"war_key": war_key}
        if round_index is not None:
            entry["day"] = round_index
        group_data["rounds"].append(entry)

    with group_path.open("w", encoding="utf-8") as f:
        json.dump(group_data, f, ensure_ascii=False, indent=2)
    print(f"Updated CWL group: {group_path}")


def update_member_histories(war_json: dict, war_key: str, is_cwl: bool, season: str | None = None):
    # Determine our side
    clan = war_json.get("clan", {})
    opponent = war_json.get("opponent", {})
    if clan.get("name") == CLAN_NAME:
        our_side = clan
        opp_name = opponent.get("name", "UnknownOpponent")
    else:
        our_side = opponent
        opp_name = clan.get("name", "UnknownOpponent")

    members_by_tag = {}
    for m in our_side.get("members", []):
        tag = m.get("tag")
        if tag:
            members_by_tag[normalize_tag(tag)] = m

    # Collect attacks from our side only
    for m in our_side.get("members", []):
        player_tag = m.get("tag")
        if not player_tag:
            continue
        player_tag_norm = normalize_tag(player_tag)
        attacks = m.get("attacks", [])

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

        for atk in attacks:
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
            # Avoid duplicates (same war_key + order)
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

    # Only save finished wars
    if state != "warEnded":
        print("No ended war to save.")
        return

    # Check if CWL is active
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
