import os
import sys
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

ODDS_API_KEYS = [
    os.getenv("ODDS_API_KEY_1", "b57a9742abb4c32ac9bd245ea8ca47ff"),
    os.getenv("ODDS_API_KEY_2", "6c404361bcf2dcf77c92b9b0598674c6"),
    os.getenv("ODDS_API_KEY_3", "9137cefef71eb58610901407cf582c8b"),
    os.getenv("ODDS_API_KEY_4", "0546f5420442d0179ff437806ddd3b6d")
]

SPORT_KEYS = {
    "nhl": "icehockey_nhl",
    "nfl": "americanfootball_nfl",
    "mlb": "baseball_mlb",
    "cfb": "americanfootball_ncaaf"
}

def decimal_to_american(dec):
    if dec <= 1.0: return -110
    return int(round((dec - 1.0) * 100)) if dec >= 2.0 else int(round(-100 / (dec - 1.0)))

def calc_cents_delta(ret_odds, sharp_odds):
    # Accurate cents difference accounting for the +100/-100 boundary
    if ret_odds > 0 and sharp_odds > 0:
        return ret_odds - sharp_odds
    elif ret_odds < 0 and sharp_odds < 0:
        return abs(sharp_odds) - abs(ret_odds)
    elif ret_odds > 0 and sharp_odds < 0:
        return (ret_odds - 100) + (100 - abs(sharp_odds))
    else:
        return (abs(ret_odds) - 100) + (100 - sharp_odds)

def send_steam_alert(sport, matchup, pick, sharp_price, stale_book, stale_price, edge_cents):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID: return
    text = (
        f"🚨 *STALE LINE DISCREPANCY DETECTED*\n\n"
        f"🏆 *Sport:* {sport.upper()}\n"
        f"⚔️ *Matchup:* {matchup}\n"
        f"🎯 *Target:* {pick}\n"
        f"⚡ *Sharp Benchmark:* {sharp_price:+d}\n"
        f"🏦 *Stale Book:* {stale_book.upper()} offering *{stale_price:+d}*\n"
        f"💎 *Delta:* +{edge_cents} cents stale edge\n\n"
        f"⏰ {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
    )
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}, timeout=5)
    except Exception:
        pass

def run_scan(sport_input="nhl", market_input="h2h"):
    sport_key = SPORT_KEYS.get(sport_input.lower(), "icehockey_nhl")
    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds/"
    params = {
        "regions": "us",
        "markets": market_input,
        "oddsFormat": "decimal"
    }

    events = None
    active_key = None
    remaining_credits = "N/A"

    for k in ODDS_API_KEYS:
        if not k: continue
        params["apiKey"] = k
        try:
            r = requests.get(url, params=params, timeout=8)
            if r.status_code == 200:
                events = r.json()
                active_key = k[:6]
                remaining_credits = r.headers.get("x-requests-remaining", "N/A")
                break
        except Exception:
            continue

    if not events:
        print(f"[!] Failed to pull odds for {sport_input}. Verify API connectivity.")
        return

    print(f"\n========================================================")
    print(f" HOVA SYNDICATE STALE LINE SCANNER: {sport_input.upper()} ({market_input})")
    print(f" Cost: 1 Credit | Key: {active_key}... | Remaining: {remaining_credits}")
    print(f"========================================================\n")

    discrepancies_found = 0

    for ev in events:
        h_team = ev.get("home_team")
        a_team = ev.get("away_team")
        matchup = f"{a_team} @ {h_team}"

        sharp_prices = {}
        retail_quotes = {}

        for bm in ev.get("bookmakers", []):
            b_key = bm.get("key")
            is_sharp = b_key in ["pinnacle", "circa", "lowvig"]

            for mkt in bm.get("markets", []):
                if mkt.get("key") == market_input:
                    for out in mkt.get("outcomes", []):
                        name = out.get("name")
                        point = out.get("point")
                        label = f"{name} ({point:+g})" if point is not None else name
                        amer_odds = decimal_to_american(out.get("price"))

                        if is_sharp:
                            sharp_prices[label] = amer_odds
                        else:
                            if label not in retail_quotes: retail_quotes[label] = []
                            retail_quotes[label].append((b_key, amer_odds))

        for target, sharp_val in sharp_prices.items():
            for ret_book, ret_val in retail_quotes.get(target, []):
                delta = calc_cents_delta(ret_val, sharp_val)
                # Strict 15+ cents discrepancy hurdle rate
                if delta >= 15:
                    discrepancies_found += 1
                    print(f"[*] ALERT: {matchup} -> {target}")
                    print(f"    Sharp: {sharp_val:+d} | Stale: {ret_book.upper()} at {ret_val:+d} (+{delta}c edge)")
                    send_steam_alert(sport_input, matchup, target, sharp_val, ret_book, ret_val, delta)

    if discrepancies_found == 0:
        print("[✓] Scan complete: Sharp markets and retail books are currently in parity.")
    else:
        print(f"\n[✓] Scan complete: Dispatched {discrepancies_found} stale line alert(s) to Telegram.")

if __name__ == "__main__":
    sport_arg = sys.argv[1] if len(sys.argv) > 1 else "nhl"
    mkt_arg = sys.argv[2] if len(sys.argv) > 2 else "h2h"
    run_scan(sport_arg, mkt_arg)
