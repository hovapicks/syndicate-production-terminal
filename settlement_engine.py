import os
import re
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

ESPN_ENDPOINTS = {
    "NFL": "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard",
    "CFB": "https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard",
    "NHL": "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard",
    "WNBA": "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard"
}

def american_to_implied(odds):
    if odds == 0: return 0.5
    return (100.0 / (odds + 100.0)) if odds > 0 else (abs(odds) / (abs(odds) + 100.0))

def calculate_clv(book_odds, closing_odds):
    if not book_odds or not closing_odds:
        return 0.0
    p_book = american_to_implied(book_odds)
    p_close = american_to_implied(closing_odds)
    if p_book == 0: return 0.0
    # Beat-the-close edge formula
    clv = ((p_close / p_book) - 1.0) * 100.0
    return round(clv, 2)

def fetch_espn_scores(sport):
    url = ESPN_ENDPOINTS.get(sport)
    if not url: return {}
    try:
        r = requests.get(url, timeout=10)
        if r.status_code != 200: return {}
        data = r.json()
        results = {}
        for ev in data.get("events", []):
            comp = ev.get("competitions", [{}])[0]
            status_desc = comp.get("status", {}).get("type", {}).get("name", "")
            completed = comp.get("status", {}).get("type", {}).get("completed", False)
            
            competitors = comp.get("competitors", [])
            if len(competitors) < 2: continue
            
            home_team, away_team = None, None
            home_score, away_score = 0, 0
            
            for c in competitors:
                team_name = c.get("team", {}).get("name", "")
                team_abbrev = c.get("team", {}).get("abbreviation", "")
                score = float(c.get("score", 0))
                if c.get("homeAway") == "home":
                    home_team = team_abbrev or team_name
                    home_score = score
                else:
                    away_team = team_abbrev or team_name
                    away_score = score

            results[f"{away_team}@{home_team}"] = {
                "completed": completed,
                "status": status_desc,
                "home_team": home_team,
                "away_team": away_team,
                "home_score": home_score,
                "away_score": away_score
            }
        return results
    except Exception:
        return {}

def grade_wager(entry, game_result):
    market = entry.get("market")
    pick = entry.get("pick", "")
    stake = float(entry.get("stake_units", 1.0))
    odds = int(entry.get("odds", -110))
    
    h_score = game_result["home_score"]
    a_score = game_result["away_score"]
    total_score = h_score + a_score
    score_str = f"{game_result['away_team']} {int(a_score)} - {game_result['home_team']} {int(h_score)}"

    # Multiplier for calculating profit
    dec_payout = (odds / 100.0) if odds > 0 else (100.0 / abs(odds))

    if market == "Moneyline":
        # Check team in pick
        home_win = h_score > a_score
        away_win = a_score > h_score
        if h_score == a_score:
            return "PUSH", 0.0, score_str

        # Match team name/abbreviation
        is_home_pick = game_result["home_team"] in pick
        if (is_home_pick and home_win) or (not is_home_pick and away_win):
            return "WON", round(stake * dec_payout, 2), score_str
        else:
            return "LOST", -stake, score_str

    elif market in ["Spread", "Puck Line"]:
        # Extract spread number (e.g., +3.0, -1.5)
        m = re.search(r"([+-]?\d+(?:\.\d+)?)", pick)
        if not m: return "OPEN", 0.0, ""
        spread_val = float(m.group(1))
        is_home = game_result["home_team"] in pick
        
        diff = (h_score - a_score) if is_home else (a_score - h_score)
        covered = diff + spread_val
        
        if covered > 0:
            return "WON", round(stake * dec_payout, 2), score_str
        elif covered < 0:
            return "LOST", -stake, score_str
        else:
            return "PUSH", 0.0, score_str

    elif market == "Total":
        m = re.search(r"(\d+(?:\.\d+)?)", pick)
        if not m: return "OPEN", 0.0, ""
        line = float(m.group(1))
        is_over = "OVER" in pick.upper()
        
        if total_score == line:
            return "PUSH", 0.0, score_str
        elif (is_over and total_score > line) or (not is_over and total_score < line):
            return "WON", round(stake * dec_payout, 2), score_str
        else:
            return "LOST", -stake, score_str

    return "OPEN", 0.0, ""

def run_settlement():
    print("[*] Running Syndicate Settlement & CLV Audit Engine...")
    r = requests.get(f"{SUPABASE_URL}/rest/v1/ledger_entries?status=eq.OPEN", headers=HEADERS, timeout=8)
    if r.status_code != 200 or not r.json():
        print("[✓] No open wagers pending settlement.")
        return

    open_bets = r.json()
    sports_needed = list(set([b["sport"] for b in open_bets]))
    score_registry = {}
    for sp in sports_needed:
        score_registry[sp] = fetch_espn_scores(sp)

    settled_count = 0
    for bet in open_bets:
        sp = bet["sport"]
        matchup = bet["matchup"].replace(" ", "").replace("@", "@")
        scores = score_registry.get(sp, {})
        
        # Match game
        target_game = None
        for k, v in scores.items():
            if v["home_team"] in bet["matchup"] and v["away_team"] in bet["matchup"]:
                target_game = v
                break
        
        if target_game and target_game["completed"]:
            status, net_units, score_str = grade_wager(bet, target_game)
            if status != "OPEN":
                update_payload = {
                    "status": status,
                    "net_units": net_units,
                    "result_score": score_str,
                    "settled_at": datetime.now(timezone.utc).isoformat()
                }
                patch_r = requests.patch(
                    f"{SUPABASE_URL}/rest/v1/ledger_entries?id=eq.{bet['id']}",
                    headers=HEADERS,
                    json=update_payload
                )
                if patch_r.status_code in [200, 204]:
                    print(f"[✓] Settled Bet {bet['id']}: {bet['pick']} -> {status} ({net_units:+}u) [{score_str}]")
                    settled_count += 1

    print(f"[*] Settlement complete. {settled_count} wagers reconciled.")

if __name__ == "__main__":
    run_settlement()
