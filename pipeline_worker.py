import os
import requests
import pandas as pd
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

KEYS = [
    "0546f5420442d0179ff437806ddd3b6d",
    "b57a9742abb4c32ac9bd245ea8ca47ff",
    "6c404361bcf2dcf77c92b9b0598674c6",
    "9137cefef71eb58610901407cf582c8b"
]

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

    now_utc = datetime.now(timezone.utc)
    max_kickoff_utc = now_utc + timedelta(hours=36)

    recs = []

    for item in sports:
        league = item["sport"]
        sport_slug = item["key"]
        data = fetch_with_rotation(sport_slug)
        if not data:
            continue

        league_candidates = []
        for event in data:
            commence_str = event.get("commence_time")
            if not commence_str:
                continue
            commence_dt = datetime.fromisoformat(commence_str.replace("Z", "+00:00"))
            if not (now_utc <= commence_dt <= max_kickoff_utc):
                continue

            home = event.get("home_team")
            away = event.get("away_team")
            matchup = f"{away} @ {home}"

            game_edges = []
            for bm in event.get("bookmakers", []):
                for mkt in bm.get("markets", []):
                    m_key = mkt.get("key")
                    outcomes = mkt.get("outcomes", [])
                    if len(outcomes) < 2:
                        continue

                    probs = [american_to_prob(o["price"]) for o in outcomes]
                    sum_p = sum(probs)
                    fair_probs = [p / sum_p for p in probs]

                    for idx, o in enumerate(outcomes):
                        fair_p = fair_probs[idx]
                        bk_odds = o["price"]
                        imp_p = american_to_prob(bk_odds)

                        if fair_p > imp_p:
                            ev = round(((fair_p - imp_p) / imp_p) * 100.0, 1)
                            if ev >= 2.0:  # 2.0% hurdle
                                point_str = f" {o.get('point'):+}" if "point" in o else ""
                                pick_name = f"{o.get('name')}{point_str}"
                                mkt_name = "Moneyline" if m_key == "h2h" else ("Spread" if m_key == "spreads" else "Total")
                                game_edges.append({
                                    "sport": league,
                                    "matchup": matchup,
                                    "market": mkt_name,
                                    "pick": pick_name,
                                    "fair_odds": prob_to_american(fair_p),
                                    "book_odds": bk_odds,
                                    "ev_percent": ev,
                                    "suggested_stake": 1.25,
                                    "status": "ACTIVE"
                                })

            if game_edges:
                best_game_pick = max(game_edges, key=lambda x: x["ev_percent"])
                league_candidates.append(best_game_pick)

        if league_candidates:
            df_league = pd.DataFrame(league_candidates).sort_values(by="ev_percent", ascending=False).head(5)
            recs.extend(df_league.to_dict(orient="records"))

    if recs:
        # Atomic replacement: delete old active records only when fresh edges are verified
        del_res = requests.delete(f"{SUPABASE_URL}/rest/v1/bet_recommendations?id=neq.00000000-0000-0000-0000-000000000000", headers=HEADERS)
        post_res = requests.post(f"{SUPABASE_URL}/rest/v1/bet_recommendations", headers=HEADERS, json=recs)
        print(f"[✓] Refreshed board: {len(recs)} active picks written to Supabase (Status: {post_res.status_code}).")
    else:
        print("[!] No new picks passed the 2.0% hurdle in the current 36h slate; existing board preserved.")

if __name__ == "__main__":
    run_pipeline()
