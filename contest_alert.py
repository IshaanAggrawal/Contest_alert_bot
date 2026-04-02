import os
import json
import requests
from datetime import datetime, timezone, timedelta

# ── ENV ─────────────────────────────────────────────────────────────────────
TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

STATE_FILE = "state.json"

# ── WINDOWS ─────────────────────────────────────────────────────────────────
TWO_HOUR_MIN = timedelta(minutes=100)
TWO_HOUR_MAX = timedelta(minutes=130)

DAY_ALERT_MAX = timedelta(days=30)

# ── STATE ───────────────────────────────────────────────────────────────────
def load_state():
    if os.path.exists(STATE_FILE):
        return json.load(open(STATE_FILE))
    return {"two_hour": [], "day_alert": []}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


# ── TELEGRAM ────────────────────────────────────────────────────────────────
def send(msg):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": msg},
            timeout=10
        )
    except Exception as e:
        print("Telegram error:", e)


# ── HELPERS ─────────────────────────────────────────────────────────────────
def now():
    return datetime.now(timezone.utc)


def in_2hr_window(start):
    diff = start - now()
    return TWO_HOUR_MIN <= diff <= TWO_HOUR_MAX


def in_day_window(start):
    diff = start - now()
    return timedelta(0) < diff <= DAY_ALERT_MAX


# ── FETCH ALL CONTESTS ──────────────────────────────────────────────────────
def get_all_contests():
    contests = []

    # 🔵 Codeforces
    try:
        r = requests.get("https://codeforces.com/api/contest.list", timeout=10)
        for c in r.json()["result"]:
            if c["phase"] != "BEFORE":
                continue
            contests.append({
                "id": f"cf_{c['id']}",
                "name": c["name"],
                "platform": "Codeforces",
                "start": datetime.fromtimestamp(c["startTimeSeconds"], tz=timezone.utc),
                "url": f"https://codeforces.com/contest/{c['id']}"
            })
    except Exception as e:
        print("CF error:", e)

    # 🟡 LeetCode
    try:
        r = requests.post(
            "https://leetcode.com/graphql",
            json={"query": "{ allContests { title startTime titleSlug } }"},
            timeout=10
        )
        for c in r.json()["data"]["allContests"]:
            start = datetime.fromtimestamp(c["startTime"], tz=timezone.utc)
            if start > now():
                contests.append({
                    "id": f"lc_{c['titleSlug']}",
                    "name": c["title"],
                    "platform": "LeetCode",
                    "start": start,
                    "url": f"https://leetcode.com/contest/{c['titleSlug']}"
                })
    except Exception as e:
        print("LC error:", e)

    # 🟠 CodeChef
    try:
        r = requests.get(
            "https://www.codechef.com/api/list/contests/all",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10
        )
        data = r.json()

        for section in ("future_contests", "present_contests"):
            for c in data.get(section, []):
                start_str = c.get("contest_start_date_iso")
                if not start_str:
                    continue

                try:
                    start = datetime.fromisoformat(start_str).astimezone(timezone.utc)
                except:
                    continue

                if start > now():
                    contests.append({
                        "id": f"cc_{c.get('contest_code','')}",
                        "name": c.get("contest_name", ""),
                        "platform": "CodeChef",
                        "start": start,
                        "url": f"https://www.codechef.com/{c.get('contest_code','')}"
                    })
    except Exception as e:
        print("CC error:", e)

    return contests


# ── MAIN ────────────────────────────────────────────────────────────────────
def main():
    print("🔍 Running bot...\n")

    state = load_state()
    new_state = {
        "two_hour": state["two_hour"][:],
        "day_alert": state["day_alert"][:]
    }

    contests = get_all_contests()

    if not contests:
        print("❌ No contests fetched")
        return

    contests.sort(key=lambda x: x["start"])

    # ── 📅 DAY ALERT (PER PLATFORM) ──────────────────────────────────────────
    platform_map = {}

    for c in contests:
        if c["platform"] not in platform_map:
            platform_map[c["platform"]] = c

    for platform, c in platform_map.items():
        if c["id"] in state["day_alert"]:
            continue

        if in_day_window(c["start"]):
            days = (c["start"] - now()).days

            msg = (
                f"📅 Next {platform} Contest\n\n"
                f"{c['name']}\n"
                f"Starts in: {days} day(s)\n"
                f"{c['url']}"
            )

            send(msg)
            new_state["day_alert"].append(c["id"])
            print(f"✅ Day alert: {platform}")

    # ── ⏰ 2-HOUR ALERT ─────────────────────────────────────────────────────
    for c in contests:
        if c["id"] in state["two_hour"]:
            continue

        if in_2hr_window(c["start"]):
            mins = int((c["start"] - now()).total_seconds() / 60)

            msg = (
                f"⏰ Contest in {mins} mins!\n\n"
                f"{c['name']}\n"
                f"{c['platform']}\n"
                f"{c['url']}"
            )

            send(msg)
            new_state["two_hour"].append(c["id"])
            print(f"✅ 2hr alert: {c['name']}")

    save_state(new_state)
    print("\n✅ Done\n")


if __name__ == "__main__":
    main()
