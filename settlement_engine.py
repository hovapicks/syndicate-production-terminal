import os
import requests
import pandas as pd
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://btzzkdjnijzzdqvjnomr.supabase.co").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

ESPN_LEAGUE_MAP = {
    "NFL": "football/nfl",
    "CFB": "football/college-football",
    "NHL": "hockey/nhl",
    "MLB": "baseball/mlb",
    "WNBA": "basketball/wnba"
}

def american_to_prob(amer):
    if amer > 0:
        return 100.0 / (amer + 100.0)
    else:
        return abs(amer) / (abs(amer) + 100.0)

def calculate_clv(booked_odds, closing_odds):
    if not booked_odds or not closing_odds:
        return 0.0
    try:
        b_prob = american_to_prob(float(booked_odds))
        c_prob = american_to_prob(float(closing_odds))
        return round(((c_prob / b_prob) - 1.0) * 100.0, 2)
    except Exception:
        return 0.0

def fetch_espn_scoreboard(sport):
    path = ESPN_LEAGUE_MAP.get(sport.upper())
    if not path: return []
    url = f"https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard"
    try:
        r = requests.get(url, timeout=8)
        if r.status_code == 200:
            return r.json().get("events", [])
    except Exception:
        pass
    return []

def extract_closing_odds(competition, market):
    odds_items = competition.get("odds", [])
    if not odds_items:
        return -110
    obj = odds_items[0]
    if market.lower() in ["moneyline", "h2h"]:
        away_ml = obj.get("awayTeamOdds", {}).get("moneyLine")
        if away_ml: return int(away_ml)
    return -110

def run_settlement():
    print("[*] Reconciling ledger with ESPN final scores and closing line benchmarks...")
    r = requests.get(f"{SUPABASE_URL}/rest/v1/ledger_entries?select=*", headers=HEADERS, timeout=8)
    if r.status_code != 200 or not r.json():
        print("[-] Ledger is empty or unreachable.")
        return

    tickets = r.json()
    for t in tickets:
        if t.get("status") not in ["OPEN", "WON", "LOST", "PUSH"]:
            continue

        sport = t.get("sport", "NFL")
        matchup = t.get("matchup", "")
        booked_odds = t.get("odds")
        stake = float(t.get("stake_units", 1.0))

        events = fetch_espn_scoreboard(sport)
        for ev in events:
            short_name = ev.get("shortName", "")
            status_name = ev.get("status", {}).get("type", {}).get("name", "")

            if matchup.upper() in short_name.upper() or short_name.upper() in matchup.upper():
                competitions = ev.get("competitions", [{}])[0]
                competitors = competitions.get("competitors", [])

                if status_name == "STATUS_FINAL" and len(competitors) == 2:
                    h_team = competitors[0] if competitors[0].get("homeAway") == "home" else competitors[1]
                    a_team = competitors[1] if competitors[0].get("homeAway") == "home" else competitors[0]
                    h_score = int(h_team.get("score", 0))
                    a_score = int(a_team.get("score", 0))
                    final_score_str = f"{a_team.get('team',{}).get('abbreviation','AWAY')} {a_score} - {h_team.get('team',{}).get('abbreviation','HOME')} {h_score}"

                    closing_odds = extract_closing_odds(competitions, t.get("market", "spread"))
                    clv_pct = calculate_clv(booked_odds, closing_odds)

                    update_payload = {
                        "result_score": final_score_str,
                        "clv_percent": clv_pct
                    }

                    if t.get("status") == "OPEN":
                        profit = round(stake * (booked_odds / 100.0) if booked_odds > 0 else stake * (100.0 / abs(booked_odds)), 2)
                        update_payload["status"] = "WON"
                        update_payload["net_units"] = profit

                    requests.patch(f"{SUPABASE_URL}/rest/v1/ledger_entries?id=eq.{t['id']}", headers=HEADERS, json=update_payload, timeout=8)
                    print(f"[✓] Reconciled ticket {t['id']} | Result: {final_score_str} | CLV: {clv_pct}%")
                    break

if __name__ == "__main__":
    run_settlement()
