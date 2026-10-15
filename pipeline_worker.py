import os
import requests
import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://btzzkdjnijzzdqvjnomr.supabase.co").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
MAX_DAILY_EXPOSURE_UNITS = float(os.getenv("MAX_DAILY_EXPOSURE_UNITS", "6.0"))

# Support comma-separated secret OR individual numbered env vars
raw_keys = os.getenv("ODDS_API_KEYS", "")
if raw_keys:
    ODDS_API_KEYS = [k.strip() for k in raw_keys.split(",") if k.strip()]
else:
    ODDS_API_KEYS = [
        val for k, val in sorted(os.environ.items(), key=lambda x: int(x[0].split('_')[-1]) if x[0].split('_')[-1].isdigit() else 99)
        if k.startswith("ODDS_API_KEY_") and val
    ]

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

def decimal_to_american(dec):
    if dec <= 1.0: return -110
    return int(round((dec - 1.0) * 100)) if dec >= 2.0 else int(round(-100 / (dec - 1.0)))

def fetch_market_odds(sport_key):
    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds/"
    params = {"regions": "us", "markets": "h2h,spreads,totals", "oddsFormat": "decimal"}

    for key in ODDS_API_KEYS:
        if not key: continue
        params["apiKey"] = key
        try:
            r = requests.get(url, params=params, timeout=10)
            if r.status_code == 200:
                data = r.json()
                print(f"[✓] Retrieved {sport_key} ({len(data)} events)")
                return data
            elif r.status_code in [401, 429]:
                continue
        except Exception:
            continue
    return []

def extract_all_recommendations():
    recommendations = []
    
    sports_map = {
        "NHL": "icehockey_nhl",
        # "MLB": "baseball_mlb",
        # "NFL": "americanfootball_nfl",
        # "NCAAF": "americanfootball_ncaaf",
        # "EPL": "soccer_epl"
    }

    now_utc = datetime.now(timezone.utc)
    # Strictly lock window to tonight's games (next 10 hours)
    cutoff_today = now_utc + timedelta(hours=18)

    for sport_label, sport_key in sports_map.items():
        events = fetch_market_odds(sport_key)
        for ev in events:
            h_team = ev.get("home_team")
            a_team = ev.get("away_team")
            commence_time_str = ev.get("commence_time")

            if commence_time_str:
                try:
                    c_dt = datetime.fromisoformat(commence_time_str.replace("Z", "+00:00"))
                    # Drop completed or in-progress games, and skip tomorrow's games entirely
                    if c_dt <= now_utc or c_dt > cutoff_today:
                        continue
                except Exception:
                    continue

            matchup = f"{a_team} @ {h_team}"
            market_buckets = {"h2h": {}, "spreads": {}, "totals": {}}

            for bm in ev.get("bookmakers", []):
                for mkt in bm.get("markets", []):
                    m_key = mkt.get("key")
                    if m_key not in market_buckets: continue
                    outcomes = mkt.get("outcomes", [])
                    
                    if len(outcomes) != 2: continue

                    prices = [o.get("price", 0) for o in outcomes]
                    if any(p <= 1.0 for p in prices): continue

                    vig = sum(1.0 / p for p in prices)

                    for o in outcomes:
                        p_dec = o.get("price", 0)
                        p_fair = (1.0 / p_dec) / vig
                        k = (o.get("name"), o.get("point"))
                        if k not in market_buckets[m_key]:
                            market_buckets[m_key][k] = []
                        market_buckets[m_key][k].append({"price": p_dec, "fair": p_fair})

            game_side_candidates = []
            game_total_candidates = []

            for m_key, outcome_dict in market_buckets.items():
                if not outcome_dict: continue

                mkt_name = "Puck Line" if m_key == "spreads" else ("Moneyline" if m_key == "h2h" else "Total")

                for (name, point), quotes in outcome_dict.items():
                    if len(quotes) < 2: continue
                    best_quote = max(quotes, key=lambda q: q["price"])
                    avg_fair = np.mean([q["fair"] for q in quotes])
                    
                    price = best_quote["price"]
                    edge_boost = 1.035

                    fair_p = min(0.92, avg_fair * edge_boost)
                    ev_pct = round(((fair_p * price) - 1.0) * 100.0, 1)

                    if 1.5 <= ev_pct <= 18.0:
                        pick_str = f"{name} {point:+g}" if point is not None else name
                        amer_odds = decimal_to_american(price)
                        b = price - 1.0
                        raw_k = (fair_p * b - (1.0 - fair_p)) / b
                        
                        q_kelly = round(max(0.25, min(2.0, raw_k * 25.0)), 2)

                        item = {
                            "sport": sport_label,
                            "matchup": matchup,
                            "market": mkt_name,
                            "pick": pick_str,
                            "team_backed": name,
                            "home_team": h_team,
                            "away_team": a_team,
                            "book_odds": amer_odds,
                            "ev_percent": ev_pct,
                            "suggested_stake": q_kelly
                        }

                        if mkt_name == "Total":
                            game_total_candidates.append(item)
                        else:
                            game_side_candidates.append(item)

            if game_side_candidates:
                game_side_candidates.sort(key=lambda x: x["ev_percent"], reverse=True)
                recommendations.append(game_side_candidates[0])

            if game_total_candidates:
                game_total_candidates.sort(key=lambda x: x["ev_percent"], reverse=True)
                recommendations.append(game_total_candidates[0])

    return pd.DataFrame(recommendations)

def filter_unique_teams(df):
    if df.empty: return df
    seen_teams = set()
    unique_rows = []
    df = df.sort_values(by="ev_percent", ascending=False)

    for _, row in df.iterrows():
        h = row.get("home_team")
        a = row.get("away_team")
        if h in seen_teams or a in seen_teams:
            continue
        seen_teams.add(h)
        seen_teams.add(a)
        unique_rows.append(row)

    return pd.DataFrame(unique_rows)

def apply_portfolio_risk_governor(recs_df, max_slate_exposure=6.0):
    if recs_df.empty or "suggested_stake" not in recs_df.columns:
        return recs_df, False

    recs_df["suggested_stake"] = recs_df["suggested_stake"].astype(float)
    total_raw_stake = recs_df["suggested_stake"].sum()
    was_capped = False

    if total_raw_stake > max_slate_exposure:
        was_capped = True
        haircut_ratio = max_slate_exposure / total_raw_stake
        recs_df["suggested_stake"] = (recs_df["suggested_stake"] * haircut_ratio).round(2)
        recs_df["suggested_stake"] = recs_df["suggested_stake"].clip(lower=0.25)

    return recs_df, was_capped

def run_pipeline():
    print("[*] Ingesting tonight's active NHL slate...")
    df = extract_all_recommendations()

    if df.empty:
        print("[-] Notice: No qualifying NHL edges detected for tonight's games.")
        # Clear out previous stale rows
        requests.delete(f"{SUPABASE_URL}/rest/v1/bet_recommendations?id=neq.00000000-0000-0000-0000-000000000000", headers=HEADERS, timeout=8)
        return

    df = filter_unique_teams(df)
    df = df.sort_values(by="ev_percent", ascending=False).head(6)

    governed_df, was_capped = apply_portfolio_risk_governor(df, MAX_DAILY_EXPOSURE_UNITS)

    print("[*] Purging Supabase bet_recommendations table...")
    requests.delete(f"{SUPABASE_URL}/rest/v1/bet_recommendations?id=neq.00000000-0000-0000-0000-000000000000", headers=HEADERS, timeout=8)

    records = governed_df[["sport", "matchup", "market", "pick", "book_odds", "ev_percent", "suggested_stake"]].to_dict(orient="records")
    for r in records:
        r["created_at"] = datetime.now(timezone.utc).isoformat()

    res = requests.post(f"{SUPABASE_URL}/rest/v1/bet_recommendations", headers=HEADERS, json=records, timeout=8)
    if res.status_code in [200, 201]:
        print(f"[✓] Committed {len(records)} tonight-only NHL plays to Supabase!")
    else:
        print(f"[-] Supabase write error: {res.status_code} - {res.text}")

if __name__ == "__main__":
    run_pipeline()
