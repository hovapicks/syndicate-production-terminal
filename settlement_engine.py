import os
import re
import unicodedata
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

def strip_accents(text):
    return ''.join(c for c in unicodedata.normalize('NFD', str(text)) if unicodedata.category(c) != 'Mn')

def clean_alphanumeric(text):
    return re.sub(r"[^A-Za-z0-9]", "", strip_accents(text)).upper()

def fetch_espn_scores(sport, days_back=2):
    endpoint = ESPN_ENDPOINTS.get(sport)
    if not endpoint: return []

    final_events = []
    base_dt = datetime.now(timezone.utc)
    for d_offset in range(days_back + 1):
        target_date = (base_dt - timedelta(days=d_offset)).strftime("%Y%m%d")
        try:
            r = requests.get(f"{endpoint}?dates={target_date}", timeout=8)
            if r.status_code == 200:
                events = r.json().get("events", [])
                for ev in events:
                    state = ev.get("status", {}).get("type", {}).get("state")
                    if state == "post":
                        final_events.append(ev)
        except Exception:
            continue
    return final_events

def parse_wager(pick_str, market_str):
    raw = strip_accents(str(pick_str).strip())
    
    if "DRAW" in raw.upper() or "TIE" in raw.upper():
        return "DRAW", "DRAW", 0.0

    line_match = re.search(r"([+-]?\d+\.?\d*)", raw)
    if line_match and any(char in raw for char in ["+", "-"]):
        spread_val = float(line_match.group(1))
        team_part = raw[:line_match.start()].strip()
        team_part = re.sub(r"\s*\([^)]*\)", "", team_part).strip()
        return "SPREAD", clean_alphanumeric(team_part), spread_val

    if "OVER" in raw.upper():
        total_val = float(re.search(r"(\d+\.?\d*)", raw).group(1))
        return "OVER", None, total_val
    if "UNDER" in raw.upper():
        total_val = float(re.search(r"(\d+\.?\d*)", raw).group(1))
        return "UNDER", None, total_val

    team_clean = raw.upper().replace("MONEYLINE", "").replace("MATCH RESULT", "").replace("ML", "").strip()
    team_clean = re.sub(r"\s*\([^)]*\)", "", team_clean).strip()
    return "ML", clean_alphanumeric(team_clean), 0.0

def matches_team(target_clean, comp_team):
    candidates = [
        comp_team.get("name", ""),
        comp_team.get("location", ""),
        comp_team.get("displayName", ""),
        comp_team.get("shortDisplayName", ""),
        comp_team.get("abbreviation", "")
    ]
    cleaned_candidates = [clean_alphanumeric(c) for c in candidates if c]
    for c in cleaned_candidates:
        if target_clean in c or c in target_clean:
            return True
    return False

def evaluate_ticket(event, bet_type, target_clean, line_value):
    comps = event.get("competitions", [{}])[0].get("competitors", [])
    if len(comps) != 2: return None, None

    team_a = comps[0]
    team_b = comps[1]

    score_a = float(team_a.get("score", 0))
    score_b = float(team_b.get("score", 0))

    name_a = team_a.get("team", {}).get("shortDisplayName", team_a.get("team", {}).get("name", "Team A"))
    name_b = team_b.get("team", {}).get("shortDisplayName", team_b.get("team", {}).get("name", "Team B"))
    score_str = f"{name_a} {int(score_a)} - {name_b} {int(score_b)}"

    if bet_type == "DRAW":
        return ("WON" if score_a == score_b else "LOST"), score_str

    is_a = matches_team(target_clean, team_a.get("team", {}))
    is_b = matches_team(target_clean, team_b.get("team", {}))

    if not is_a and not is_b:
        return None, None

    picked_score = score_a if is_a else score_b
    opp_score = score_b if is_a else score_a

    if bet_type == "ML":
        if picked_score > opp_score: return "WON", score_str
        elif picked_score < opp_score: return "LOST", score_str
        else: return "LOST", score_str

    elif bet_type == "SPREAD":
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
        sport: fetch_espn_scores(sport, days_back=2) for sport in ESPN_ENDPOINTS.keys()
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
        created_at_str = bet.get("created_at")

        # Parse ticket placement timestamp
        bet_dt = None
        if created_at_str:
            try:
                bet_dt = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
            except Exception:
                pass

        bet_type, target_clean, line_val = parse_wager(pick, market)
        events = espn_cache.get(sport, [])

        matched_event = None
        for ev in events:
            ev_date_str = ev.get("date")
            if ev_date_str and bet_dt:
                try:
                    ev_dt = datetime.fromisoformat(ev_date_str.replace("Z", "+00:00"))
                    # The game must have started AFTER or within 4 hours prior to bet creation
                    # (Strictly rejects yesterday's game in a multi-game series)
                    time_diff = (ev_dt - bet_dt).total_seconds()
                    if time_diff < -14400:  # Event started >4 hours before the bet was even created
                        continue
                except Exception:
                    pass

            ev_name = clean_alphanumeric(ev.get("name", ""))
            ev_short = clean_alphanumeric(ev.get("shortName", ""))
            
            teams_in_matchup = [clean_alphanumeric(t) for t in re.split(r"[@vV]+", matchup) if t.strip()]
            if any(t in ev_name or t in ev_short for t in teams_in_matchup):
                matched_event = ev
                break

        if not matched_event:
            continue

        result_status, score_str = evaluate_ticket(matched_event, bet_type, target_clean, line_val)
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
