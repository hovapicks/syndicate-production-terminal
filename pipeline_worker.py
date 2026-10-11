import os
import requests
import pandas as pd
from dotenv import load_dotenv
from models.nfl_pipeline import generate_nfl_recommendations
from models.nhl_pipeline import generate_nhl_recommendations
from models.epl_pipeline import generate_epl_recommendations

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://btzzkdjnijzzdqvjnomr.supabase.co").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

def run_pipeline():
    print("[*] Initiating Unified Syndicate Pipeline Worker...")
    all_recs = []

    # 1. NFL Engine (Bayesian EPA & Situational HFA)
    try:
        print("[*] Running NFL quantitative engine...")
        nfl_recs = generate_nfl_recommendations()
        print(f"[✓] NFL generated {len(nfl_recs)} verified plays.")
        all_recs.extend(nfl_recs)
    except Exception as e:
        print(f"[!] NFL pipeline error: {e}")

    # 2. NHL Engine (Dixon-Coles + ENG Markov + Crease)
    try:
        print("[*] Running NHL Dixon-Coles engine...")
        nhl_recs = generate_nhl_recommendations()
        print(f"[✓] NHL generated {len(nhl_recs)} verified plays.")
        all_recs.extend(nhl_recs)
    except Exception as e:
        print(f"[!] NHL pipeline error: {e}")

    # 3. EPL Engine (Bivariate Dixon-Coles & Att/Def Ratings)
    try:
        print("[*] Running EPL quantitative engine...")
        epl_recs = generate_epl_recommendations()
        print(f"[✓] EPL generated {len(epl_recs)} verified plays.")
        all_recs.extend(epl_recs)
    except Exception as e:
        print(f"[!] EPL pipeline error: {e}")

    # 4. Synchronize Multi-Sport Slate to Supabase
    if all_recs:
        df = pd.DataFrame(all_recs).sort_values(by="ev_percent", ascending=False)
        df = df.drop_duplicates(subset=["sport", "matchup", "market", "pick"])
        clean_recs = df.to_dict(orient="records")

        requests.delete(
            f"{SUPABASE_URL}/rest/v1/bet_recommendations?id=neq.00000000-0000-0000-0000-000000000000",
            headers=HEADERS
        )
        post_res = requests.post(
            f"{SUPABASE_URL}/rest/v1/bet_recommendations",
            headers=HEADERS,
            json=clean_recs
        )
        print(f"[✓] Synced {len(clean_recs)} verified multi-sport plays to Supabase (Status: {post_res.status_code}).")
    else:
        print("[!] No active edges qualifying over the hurdle across slates.")

if __name__ == "__main__":
    run_pipeline()
