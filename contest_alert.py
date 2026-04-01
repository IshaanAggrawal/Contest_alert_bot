import os
import requests
import json
from datetime import datetime, timezone, timedelta

# ── ENV VARS ────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

# ── CONFIG ──────────────────────────────────────────────────────────────────
ALERT_MIN = timedelta(minutes=100)   # safer window
ALERT_MAX = timedelta(minutes=130)

SENT_FILE = "sent.json"


# ── SENT STORAGE (PREVENT DUPLICATES) ───────────────────────────────────────
def load_sent():
    if os.path.exists(SENT_FILE):
        with open(SENT_FILE, "r") as f:
            return set(json.load(f))
    return set()


def save_sent(sent):
    with open(SENT_FILE, "w") as f:
        json.dump(list(sent), f)


# ── TELEGRAM ────────────────────────────────────────────────────────────────
def send_alert(contest):
    now = datetime.now(timezone.utc)
    mins_left = int((contest["start"] - now).total_seconds() / 60)

    icons = {"Codeforces": "🔵", "LeetCode": "🟡", "CodeChef": "🟠"}
    icon = icons.get(contest["platform"], "🏆")

    msg = (
        f"⏰ Contest Alert — {mins_left} mins left!\n\n"
        f"{icon} {contest['name']}\n"
        f"📌 Platform: {contest['platform']}\n"
        f"🕐 Starts: {contest['start'].strftime('%d %b %Y %H:%M UTC')}\n"
        f"🔗 {contest['url']}"
    )

    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": msg},
            timeout=10,
        )
        resp.raise_for_status()
        print(f"  ✅ Alert sent: {contest['name']}")
    except Exception as e:
        print(f"  ❌ Telegram error: {e}")


# ── HELPERS ─────────────────────────────────────────────────────────────────
def in_window(start: datetime, now: datetime) -> bool:
    diff = start - now
    return ALERT_MIN <= diff <= ALERT_MAX


# ── CODEFORCES ──────────────────────────────────────────────────────────────
def get_codeforces(now):
    print("Fetching Codeforces…")
    try:
        r = requests.get("https://codeforces.com/api/contest.list", timeout=15)
        r.raise_for_status()
        data = r.json()

        contests = []
        for c in data.get("result", []):
            if c.get("phase") != "BEFORE":
                continue

            start = datetime.fromtimestamp(c["startTimeSeconds"], tz=timezone.utc)

            if in_window(start, now):
                contests.append({
                    "id": f"cf_{c['id']}",
                    "name": c["name"],
                    "platform": "Codeforces",
                    "start": start,
                    "url": f"https://codeforces.com/contest/{c['id']}",
                })

        print(f"  Found {len(contests)} contest(s).")
        return contests

    except Exception as e:
        print(f"  ❌ Codeforces error: {e}")
        return []


# ── LEETCODE ────────────────────────────────────────────────────────────────
def get_leetcode(now):
    print("Fetching LeetCode…")

    query = "{ allContests { title startTime titleSlug } }"

    try:
        r = requests.post(
            "https://leetcode.com/graphql",
            json={"query": query},
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        r.raise_for_status()

        contests = []
        all_c = r.json().get("data", {}).get("allContests", [])

        for c in all_c:
            start = datetime.fromtimestamp(c["startTime"], tz=timezone.utc)

            if start <= now:
                continue

            if in_window(start, now):
                contests.append({
                    "id": f"lc_{c['titleSlug']}",
                    "name": c["title"],
                    "platform": "LeetCode",
                    "start": start,
                    "url": f"https://leetcode.com/contest/{c['titleSlug']}",
                })

        print(f"  Found {len(contests)} contest(s).")
        return contests

    except Exception as e:
        print(f"  ❌ LeetCode error: {e}")
        return []


# ── CODECHEF ────────────────────────────────────────────────────────────────
def get_codechef(now):
    print("Fetching CodeChef…")

    try:
        r = requests.get(
            "https://www.codechef.com/api/list/contests/all",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
        )
        r.raise_for_status()

        data = r.json()
        contests = []

        for section in ("future_contests", "present_contests"):
            for c in data.get(section, []):
                start_str = c.get("contest_start_date_iso")
                if not start_str:
                    continue

                try:
                    start = datetime.fromisoformat(start_str)
                    start = start.astimezone(timezone.utc)
                except Exception:
                    continue

                if in_window(start, now):
                    code = c.get("contest_code", "")

                    contests.append({
                        "id": f"cc_{code}",
                        "name": c.get("contest_name", code),
                        "platform": "CodeChef",
                        "start": start,
                        "url": f"https://www.codechef.com/{code}",
                    })

        print(f"  Found {len(contests)} contest(s).")
        return contests

    except Exception as e:
        print(f"  ❌ CodeChef error: {e}")
        return []


# ── MAIN ────────────────────────────────────────────────────────────────────
def main():
    now = datetime.now(timezone.utc)

    print(f"\n🔍 Checking at {now.strftime('%Y-%m-%d %H:%M UTC')}")
    print("   Window: 100–130 mins before start\n")

    sent = load_sent()
    new_sent = set(sent)

    all_contests = []
    all_contests += get_codeforces(now)
    all_contests += get_leetcode(now)
    all_contests += get_codechef(now)

    print(f"\n📬 Total found: {len(all_contests)}")

    for c in all_contests:
        if c["id"] in sent:
            continue

        send_alert(c)
        new_sent.add(c["id"])

    save_sent(new_sent)

    if not all_contests:
        print("No contests found.")

    print("\n✅ Done.\n")


if __name__ == "__main__":
    main()
