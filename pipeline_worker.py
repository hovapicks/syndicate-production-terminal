import os
import requests
import pandas as pd
import sqlalchemy as sa
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
KEYS = [
    "0546f5420442d0179ff437806ddd3b6d",
    "b57a9742abb4c32ac9bd245ea8ca47ff",
    "6c404361bcf2dcf77c92b9b0598674c6",
    "9137cefef71eb58610901407cf582c8b"
]

def get_engine():
    return sa.create_engine(DATABASE_URL, pool_pre_ping=True)

def american_to_prob(odds):
    if odds > 0:
        return 100.0 / (odds + 100.0)
    return abs(odds) / (abs(odds) + 100.0)

def prob_to_american(prob):
    if prob >= 0.5:
        return int(round(-100.0 * prob / (1.0 - prob)))
    return int(round(100.0 * (1.0 - prob) / prob))

def fetch_with_rotation(sport_slug):
    for key in KEYS:
        url = f"https://api.the-odds-api.com/v4/sports/{sport_slug}/odds/?apiKey={key}&regions=us&markets=h2h,spreads,totals&oddsFormat=american"
        try:
            r = requests.get(url, timeout=12)
            if r.status_code == 200:
                return r.json()
            elif r.status_code in [401, 429]:
                continue
        except Exception:
            continue
    return None

def run_pipeline():
    sports = [
        {"sport": "NFL", "key": "americanfootball_nfl"},
        {"sport": "NHL", "key": "icehockey_nhl"},
        {"sport": "EPL", "key": "soccer_epl"},
        {"sport": "CFB", "key": "americanfootball_ncaaf"}
    ]
    
    # 24-Hour Slate Window: Now through tomorrow morning
    now_utc = datetime.now(timezone.utc)
    max_kickoff_utc = now_utc + timedelta(hours=24)
    
    recs = []
    engine = get_engine()

    for item in sports:
        league = item["sport"]
        sport_slug = item["key"]
        data = fetch_with_rotation(sport_slug)
        if not data:
            continue
            
        league_candidates = []
        for g in data:
            # 1. Slate Timing Filter (Ignores next week's games)
            commence_str = g.get("commence_time")
            if commence_str:
                commence_dt = datetime.fromisoformat(commence_str.replace("Z", "+00:00"))
                if commence_dt > max_kickoff_utc or commence_dt < (now_utc - timedelta(hours=4)):
                    continue

            home = g.get("home_team")
            away = g.get("away_team")
            matchup = f"{away} @ {home}"
            books = g.get("bookmakers", [])
            if len(books) < 2:
                continue

            game_edges = []
            
            # 2. Extract quotes across markets
            for mkt_key in ["spreads", "totals", "h2h"]:
                mkt_label = "Spread" if mkt_key == "spreads" else ("Total" if mkt_key == "totals" else "Moneyline")
                quotes_by_pick = {}
                
                for bm in books:
                    for m in bm.get("markets", []):
                        if m.get("key") == mkt_key:
                            for out in m.get("outcomes", []):
                                name = out.get("name")
                                price = out.get("price")
                                point = out.get("point", 0.0)
                                p_str = f"{name} {point:+g}" if point else f"{name} ML"
                                quotes_by_pick.setdefault(p_str, []).append(price)

                # Consensus pricing & EV calculation
                for pick_str, prices in quotes_by_pick.items():
                    if len(prices) >= 2:
                        best_book_price = max(prices)
                        avg_prob = sum(american_to_prob(p) for p in prices) / len(prices)
                        fair_price = prob_to_american(avg_prob)
                        implied_book = american_to_prob(best_book_price)
                        
                        if avg_prob > implied_book:
                            ev = round(((avg_prob - implied_book) / implied_book) * 100.0, 1)
                            if 1.5 <= ev <= 12.0:
                                game_edges.append({
                                    "sport": league,
                                    "matchup": matchup,
                                    "market": mkt_label,
                                    "pick": pick_str,
                                    "fair_odds": fair_price,
                                    "book_odds": best_book_price,
                                    "ev_percent": ev,
                                    "suggested_stake": 1.25,
                                    "status": "ACTIVE"
                                })

            # Strictly 1 top pick per fixture
            if game_edges:
                best_game_pick = max(game_edges, key=lambda x: x["ev_percent"])
                league_candidates.append(best_game_pick)

        # Cap at top 5 games for today's slate
        if league_candidates:
            df_league = pd.DataFrame(league_candidates).sort_values(by="ev_percent", ascending=False).head(5)
            recs.extend(df_league.to_dict(orient="records"))

    # Update database
    with engine.begin() as conn:
        conn.execute(sa.text("TRUNCATE TABLE bet_recommendations CASCADE;"))
        if recs:
            for r in recs:
                conn.execute(sa.text("""
                    INSERT INTO bet_recommendations (sport, matchup, market, pick, fair_odds, book_odds, ev_percent, suggested_stake, status)
                    VALUES (:sport, :matchup, :market, :pick, :fair_odds, :book_odds, :ev_percent, :suggested_stake, :status)
                """), r)
            print(f"[✓] Synced {len(recs)} active picks strictly for TODAY'S slate to Supabase.")
        else:
            print("[✓] Cleared recommendations. No live edges found for today's active window.")

if __name__ == "__main__":
    run_pipeline()
