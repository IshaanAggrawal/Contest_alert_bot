import os
import requests
from datetime import datetime, timezone, timedelta

# ── ENV VARS (set these in GitHub Secrets) ──────────────────────────────────
TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID        = os.environ["TELEGRAM_CHAT_ID"]

# Alert window: contests starting between 1h 50m and 2h 10m from now
# GitHub Actions runs every 15 min → at most one run catches each contest
ALERT_MIN = timedelta(hours=1, minutes=50)
ALERT_MAX = timedelta(hours=2, minutes=10)

# ── TELEGRAM ────────────────────────────────────────────────────────────────
def send_alert(contest):
    now = datetime.now(timezone.utc)
    mins_left = int((contest["start"] - now).total_seconds() / 60)

    icons = {"Codeforces": "🔵", "LeetCode": "🟡", "CodeChef": "🟠"}
    icon = icons.get(contest["platform"], "🏆")

    msg = (
        f"⏰ *Contest Alert — {mins_left} mins left!*\n\n"
        f"{icon} *{contest['name']}*\n"
        f"📌 Platform: `{contest['platform']}`\n"
        f"🕐 Starts: `{contest['start'].strftime('%d %b %Y  %H:%M UTC')}`\n"
        f"🔗 [Open Contest]({contest['url']})"
    )
    resp = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"},
        timeout=10,
    )
    resp.raise_for_status()
    print(f"  ✅ Alert sent: {contest['name']}")


# ── HELPERS ─────────────────────────────────────────────────────────────────
def in_window(start: datetime) -> bool:
    diff = start - datetime.now(timezone.utc)
    return ALERT_MIN <= diff <= ALERT_MAX


# ── CODEFORCES ──────────────────────────────────────────────────────────────
def get_codeforces():
    print("Fetching Codeforces…")
    try:
        r = requests.get("https://codeforces.com/api/contest.list", timeout=15)
        r.raise_for_status()
        data = r.json()
        if data["status"] != "OK":
            print("  ⚠️  Codeforces API error")
            return []

        contests = []
        for c in data["result"]:
            if c["phase"] != "BEFORE":
                continue
            start = datetime.fromtimestamp(c["startTimeSeconds"], tz=timezone.utc)
            if in_window(start):
                contests.append({
                    "name":     c["name"],
                    "platform": "Codeforces",
                    "start":    start,
                    "url":      f"https://codeforces.com/contest/{c['id']}",
                })
        print(f"  Found {len(contests)} contest(s) in window.")
        return contests
    except Exception as e:
        print(f"  ❌ Codeforces error: {e}")
        return []


# ── LEETCODE ────────────────────────────────────────────────────────────────
def get_leetcode():
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
        all_c = r.json().get("data", {}).get("allContests", [])

        contests = []
        now = datetime.now(timezone.utc)
        for c in all_c:
            start = datetime.fromtimestamp(c["startTime"], tz=timezone.utc)
            if start <= now:
                continue
            if in_window(start):
                contests.append({
                    "name":     c["title"],
                    "platform": "LeetCode",
                    "start":    start,
                    "url":      f"https://leetcode.com/contest/{c['titleSlug']}",
                })
        print(f"  Found {len(contests)} contest(s) in window.")
        return contests
    except Exception as e:
        print(f"  ❌ LeetCode error: {e}")
        return []


# ── CODECHEF ────────────────────────────────────────────────────────────────
def get_codechef():
    print("Fetching CodeChef…")
    try:
        r = requests.get(
            "https://www.codechef.com/api/list/contests/all",
            params={"sort_by": "START", "sorting_order": "asc", "offset": 0, "mode": "all"},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()

        contests = []
        for section in ("future_contests", "present_contests"):
            for c in data.get(section, []):
                # CodeChef returns IST (UTC+5:30); convert properly
                start_str = c.get("contest_start_date_iso") or c.get("contest_start_date")
                if not start_str:
                    continue
                try:
                    # ISO format with offset e.g. "2024-11-02T14:30:00+05:30"
                    from datetime import datetime
                    start = datetime.fromisoformat(start_str)
                    if start.tzinfo is None:
                        # Assume IST if no tz info
                        start = start.replace(tzinfo=timezone(timedelta(hours=5, minutes=30)))
                    start = start.astimezone(timezone.utc)
                except Exception:
                    continue

                if in_window(start):
                    code = c.get("contest_code", "")
                    contests.append({
                        "name":     c.get("contest_name", code),
                        "platform": "CodeChef",
                        "start":    start,
                        "url":      f"https://www.codechef.com/{code}",
                    })
        print(f"  Found {len(contests)} contest(s) in window.")
        return contests
    except Exception as e:
        print(f"  ❌ CodeChef error: {e}")
        return []


# ── MAIN ────────────────────────────────────────────────────────────────────
def main():
    print(f"\n🔍 Checking contests at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"   Alert window: contests starting in 1h 50m – 2h 10m\n")

    all_contests = []
    all_contests.extend(get_codeforces())
    all_contests.extend(get_leetcode())
    all_contests.extend(get_codechef())

    print(f"\n📬 Total alerts to send: {len(all_contests)}")
    for c in all_contests:
        send_alert(c)

    if not all_contests:
        print("   No contests starting in ~2 hours. Nothing sent.")

    print("\n✅ Done.\n")


if __name__ == "__main__":
    main()
