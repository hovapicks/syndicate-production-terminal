import os
import re
import requests
from datetime import datetime, timezone, timedelta
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
    "MLB": "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard",
    "NHL": "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard",
    "NCAAF": "https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard",
    "EPL": "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard"
}

TEAM_ALIASES = {
    "ARS": "ARS", "ARSENAL": "ARS",
    "MCI": "MCI", "MAN CITY": "MCI", "MANCHESTER CITY": "MCI",
    "LIV": "LIV", "LIVERPOOL": "LIV",
    "CHE": "CHE", "CHELSEA": "CHE",
    "MUN": "MUN", "MAN UTD": "MUN", "MANCHESTER UNITED": "MUN",
    "TOT": "TOT", "SPURS": "TOT", "TOTTENHAM": "TOT",
    "NEW": "NEW", "NEWCASTLE": "NEW", "NEWCASTLE UNITED": "NEW",
    "AVL": "AVL", "ASTON VILLA": "AVL",
    "BHA": "BHA", "BRIGHTON": "BHA",
    "WHU": "WHU", "WEST HAM": "WHU",
    "EVE": "EVE", "EVERTON": "EVE",
    "FUL": "FUL", "FULHAM": "FUL",
    "CRY": "CRY", "PALACE": "CRY", "CRYSTAL PALACE": "CRY",
    "DRAW": "DRAW", "TIE": "DRAW"
}

def normalize_token(text):
    clean = re.sub(r"[^A-Za-z0-9]", "", str(text)).upper()
    return TEAM_ALIASES.get(clean, clean)

def fetch_espn_scores(sport, days_back=2):
    endpoint = ESPN_ENDPOINTS.get(sport)
    if not endpoint: return []

    final_events = []
    base_dt = datetime.now(timezone.utc)
    for d_offset in range(days_back + 1):
        target_date = (base_dt - timedelta(days=d_offset)).strftime("%Y%m%d")
        try:
            r = requests.get(f"{endpoint}?dates={target_date}", timeout=6)
            if r.status_code == 200:
                events = r.json().get("events", [])
                for ev in events:
                    if ev.get("status", {}).get("type", {}).get("state") == "post":
                        final_events.append(ev)
        except Exception:
            continue
    return final_events

def parse_wager(pick_str, market_str):
    raw = str(pick_str).strip()
    
    if "DRAW" in raw.upper() or "TIE" in raw.upper():
        return "DRAW", "DRAW", 0.0

    line_match = re.search(r"([+-]?\d+\.?\d*)", raw)
    if line_match and any(char in raw for char in ["+", "-"]):
        spread_val = float(line_match.group(1))
        team_part = raw[:line_match.start()].strip()
        return "SPREAD", normalize_token(team_part), spread_val

    if "OVER" in raw.upper():
        total_val = float(re.search(r"(\d+\.?\d*)", raw).group(1))
        return "OVER", None, total_val
    if "UNDER" in raw.upper():
        total_val = float(re.search(r"(\d+\.?\d*)", raw).group(1))
        return "UNDER", None, total_val

    team_clean = raw.upper().replace("MONEYLINE", "").replace("MATCH RESULT", "").replace("ML", "").strip()
    return "ML", normalize_token(team_clean), 0.0

def evaluate_ticket(event, bet_type, target_team, line_value):
    comps = event.get("competitions", [{}])[0].get("competitors", [])
    if len(comps) != 2: return None, None

    team_a = comps[0]
    team_b = comps[1]

    abbr_a = team_a.get("team", {}).get("abbreviation", "").upper()
    name_a = team_a.get("team", {}).get("name", "").upper()
    score_a = float(team_a.get("score", 0))

    abbr_b = team_b.get("team", {}).get("abbreviation", "").upper()
    name_b = team_b.get("team", {}).get("name", "").upper()
    score_b = float(team_b.get("score", 0))

    score_str = f"{abbr_a} {int(score_a)} - {abbr_b} {int(score_b)}"

    if bet_type == "DRAW":
        return ("WON" if score_a == score_b else "LOST"), score_str

    if bet_type == "ML":
        if target_team in [abbr_a, name_a, normalize_token(name_a)]:
            picked_score, opp_score = score_a, score_b
        elif target_team in [abbr_b, name_b, normalize_token(name_b)]:
            picked_score, opp_score = score_b, score_a
        else:
            return None, None

        if picked_score > opp_score: return "WON", score_str
        elif picked_score < opp_score: return "LOST", score_str
        else: return "LOST", score_str  # In 3-way markets, a draw results in a loss for moneyline bets

    elif bet_type == "SPREAD":
        if target_team in [abbr_a, name_a, normalize_token(name_a)]:
            picked_score, opp_score = score_a, score_b
        elif target_team in [abbr_b, name_b, normalize_token(name_b)]:
            picked_score, opp_score = score_b, score_a
        else:
            return None, None

        margin = (picked_score + line_value) - opp_score
        if margin > 0: return "WON", score_str
        elif margin < 0: return "LOST", score_str
        else: return "PUSH", score_str

    elif bet_type in ["OVER", "UNDER"]:
        tot = score_a + score_b
        if bet_type == "OVER":
            if tot > line_value: return "WON", score_str
            elif tot < line_value: return "LOST", score_str
            else: return "PUSH", score_str
        else:
            if tot < line_value: return "WON", score_str
            elif tot > line_value: return "LOST", score_str
            else: return "PUSH", score_str

    return None, None

def run_settlement():
    print("[*] Polling OPEN tickets from Supabase ledger...")
    r = requests.get(f"{SUPABASE_URL}/rest/v1/ledger_entries?status=eq.OPEN&select=*", headers=HEADERS, timeout=8)
    if r.status_code != 200:
        print(f"[-] Supabase query error: {r.status_code}")
        return

    open_bets = r.json()
    if not open_bets:
        print("[✓] Zero OPEN bets pending audit.")
        return

    print(f"[*] Auditing {len(open_bets)} pending wagers against ESPN final box scores...")

    espn_cache = {
        sport: fetch_espn_scores(sport) for sport in ESPN_ENDPOINTS.keys()
    }

    settled_count = 0

    for bet in open_bets:
        bet_id = bet.get("id")
        sport = bet.get("sport")
        matchup = bet.get("matchup", "")
        pick = bet.get("pick", "")
        market = bet.get("market", "")
        odds = int(bet.get("odds", -110))
        stake = float(bet.get("stake_units", 1.0))

        bet_type, target_team, line_val = parse_wager(pick, market)
        events = espn_cache.get(sport, [])

        matched_event = None
        for ev in events:
            ev_name = ev.get("name", "").upper()
            ev_short = ev.get("shortName", "").upper()
            m_tokens = [normalize_token(t) for t in re.split(r"[@vV\s]+", matchup) if t]
            if any(t in ev_name or t in ev_short for t in m_tokens):
                matched_event = ev
                break

        if not matched_event:
            continue

        result_status, score_str = evaluate_ticket(matched_event, bet_type, target_team, line_val)
        if not result_status:
            continue

        if result_status == "WON":
            net_profit = stake * (odds / 100.0) if odds > 0 else stake * (100.0 / abs(odds))
        elif result_status == "LOST":
            net_profit = -stake
        else:
            net_profit = 0.0

        update_payload = {
            "status": result_status,
            "net_units": round(net_profit, 2),
            "result_score": score_str
        }

        patch_res = requests.patch(f"{SUPABASE_URL}/rest/v1/ledger_entries?id=eq.{bet_id}", headers=HEADERS, json=update_payload, timeout=8)
        if patch_res.status_code in [200, 204]:
            settled_count += 1
            print(f"  [✓] Settled: {matchup} | {pick} -> {result_status} ({net_profit:+.2f}u) [{score_str}]")

    print(f"[✓] Settlement completed. Graded {settled_count} tickets.")

if __name__ == "__main__":
    run_settlement()
