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

CFB_SPREAD_KEYS = {3.0, 7.0, 10.0, 14.0}
CFB_TOTAL_KEYS = {41.0, 44.0, 47.0, 51.0}

def decimal_to_american(dec):
    if dec <= 1.0: return -110
    return int(round((dec - 1.0) * 100)) if dec >= 2.0 else int(round(-100 / (dec - 1.0)))

def fetch_market_odds(sport_key, sport_label):
    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds/"
    regions = "us,uk" if sport_label == "EPL" else "us"
    params = {"regions": regions, "markets": "h2h,spreads,totals", "oddsFormat": "decimal"}

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
        "MLB": "baseball_mlb",
        "NFL": "americanfootball_nfl",
        "NCAAF": "americanfootball_ncaaf",
        "EPL": "soccer_epl"
    }

    now_utc = datetime.now(timezone.utc)
    cutoff_30h = now_utc + timedelta(hours=30)

    for sport_label, sport_key in sports_map.items():
        events = fetch_market_odds(sport_key, sport_label)
        for ev in events:
            h_team = ev.get("home_team")
            a_team = ev.get("away_team")
            commence_time_str = ev.get("commence_time")

            if commence_time_str:
                try:
                    c_dt = datetime.fromisoformat(commence_time_str.replace("Z", "+00:00"))
                    if c_dt <= now_utc:
                        continue
                    is_early_lookahead = (c_dt > cutoff_30h)
                except Exception:
                    is_early_lookahead = False
            else:
                is_early_lookahead = False

            matchup = f"{a_team} @ {h_team}" if sport_label != "EPL" else f"{h_team} vs {a_team}"
            market_buckets = {"h2h": {}, "spreads": {}, "totals": {}}

            for bm in ev.get("bookmakers", []):
                for mkt in bm.get("markets", []):
                    m_key = mkt.get("key")
                    if m_key not in market_buckets: continue
                    outcomes = mkt.get("outcomes", [])
                    
                    # Strictly 2-way for US sports; 3-way only for EPL
                    expected_count = [2, 3] if sport_label == "EPL" else [2]
                    if len(outcomes) not in expected_count: continue

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

                if m_key == "spreads":
                    mkt_name = "Puck Line" if sport_label == "NHL" else ("Run Line" if sport_label == "MLB" else ("Goal Line" if sport_label == "EPL" else "Spread"))
                elif m_key == "h2h":
                    mkt_name = "Match Result" if sport_label == "EPL" else "Moneyline"
                else:
                    mkt_name = "Total"

                for (name, point), quotes in outcome_dict.items():
                    if len(quotes) < 2: continue
                    best_quote = max(quotes, key=lambda q: q["price"])
                    avg_fair = np.mean([q["fair"] for q in quotes])
                    
                    price = best_quote["price"]
                    edge_boost = 1.035
                    
                    if sport_label == "NCAAF" and point is not None:
                        abs_pt = abs(float(point))
                        if mkt_name == "Spread" and abs_pt in CFB_SPREAD_KEYS:
                            edge_boost = 1.045
                        elif mkt_name == "Total" and abs_pt in CFB_TOTAL_KEYS:
                            edge_boost = 1.042

                    fair_p = min(0.92, avg_fair * edge_boost)
                    ev_pct = round(((fair_p * price) - 1.0) * 100.0, 1)

                    # Strict filter to drop synthetic regulation lines and noise
                    if 1.5 <= ev_pct <= 18.0:
                        pick_str = f"{name} {point:+g}" if point is not None else name
                        amer_odds = decimal_to_american(price)
                        b = price - 1.0
                        raw_k = (fair_p * b - (1.0 - fair_p)) / b
                        
                        max_stake_cap = 3.5 if sport_label == "NCAAF" else 2.0
                        q_kelly = round(max(0.25, min(max_stake_cap, raw_k * 25.0)), 2)

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
                            "suggested_stake": q_kelly,
                            "is_lookahead": is_early_lookahead
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

def balance_multi_sport_board(df, max_picks=8):
    if df.empty: return df
    df = filter_unique_teams(df)

    nhl_df = df[df["sport"] == "NHL"].sort_values(by="ev_percent", ascending=False)
    mlb_df = df[df["sport"] == "MLB"].sort_values(by="ev_percent", ascending=False)
    nfl_df = df[df["sport"] == "NFL"].sort_values(by="ev_percent", ascending=False)
    cfb_df = df[df["sport"] == "NCAAF"].sort_values(by="ev_percent", ascending=False)
    epl_df = df[df["sport"] == "EPL"].sort_values(by="ev_percent", ascending=False)

    selected = []
    if not nhl_df.empty: selected.append(nhl_df.head(2))
    if not mlb_df.empty: selected.append(mlb_df.head(2))
    if not nfl_df.empty: selected.append(nfl_df.head(2))
    if not cfb_df.empty: selected.append(cfb_df.head(2))
    if not epl_df.empty: selected.append(epl_df.head(2))

    res_df = pd.concat(selected, ignore_index=True) if selected else df.head(max_picks)

    if len(res_df) < max_picks:
        remaining = df[~df.index.isin(res_df.index)].sort_values(by="ev_percent", ascending=False)
        needed = max_picks - len(res_df)
        res_df = pd.concat([res_df, remaining.head(needed)], ignore_index=True)

    return res_df.sort_values(by="ev_percent", ascending=False).drop_duplicates(subset=["matchup", "market", "pick"]).head(max_picks)

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
    print("[*] Ingesting multi-sport slate with strict 2-way OT and isolated EPL regions...")
    all_recs = extract_all_recommendations()

    if all_recs.empty:
        print("[-] Notice: No qualifying edges detected.")
        return

    today_mask = all_recs["is_lookahead"] == False
    today_df = all_recs[today_mask].copy()
    lookahead_df = all_recs[~today_mask].copy()

    balanced_today = balance_multi_sport_board(today_df, max_picks=8)
    balanced_lookahead = balance_multi_sport_board(lookahead_df, max_picks=8)

    governed_today, was_capped = apply_portfolio_risk_governor(balanced_today, MAX_DAILY_EXPOSURE_UNITS)

    print("[*] Purging old entries in Supabase bet_recommendations table...")
    requests.delete(f"{SUPABASE_URL}/rest/v1/bet_recommendations?id=neq.00000000-0000-0000-0000-000000000000", headers=HEADERS, timeout=8)

    combined_df = pd.concat([governed_today, balanced_lookahead], ignore_index=True)
    combined_df = combined_df.drop_duplicates(subset=["matchup", "market", "pick"])

    records = combined_df[["sport", "matchup", "market", "pick", "book_odds", "ev_percent", "suggested_stake"]].to_dict(orient="records")
    for r in records:
        r["created_at"] = datetime.now(timezone.utc).isoformat()

    res = requests.post(f"{SUPABASE_URL}/rest/v1/bet_recommendations", headers=HEADERS, json=records, timeout=8)
    if res.status_code in [200, 201]:
        print(f"[✓] Committed {len(records)} clean plays to Supabase!")
    else:
        print(f"[-] Supabase write error: {res.status_code} - {res.text}")

if __name__ == "__main__":
    run_pipeline()
