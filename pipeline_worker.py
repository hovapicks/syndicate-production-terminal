import os
import requests
import pandas as pd
from dotenv import load_dotenv
from models.nfl_pipeline import generate_nfl_recommendations
from models.nhl_pipeline import generate_nhl_recommendations

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

    # 1. Execute NFL Engine
    try:
        print("[*] Running NFL quantitative engine...")
        nfl_recs = generate_nfl_recommendations()
        print(f"[✓] NFL generated {len(nfl_recs)} verified plays.")
        all_recs.extend(nfl_recs)
    except Exception as e:
        print(f"[!] NFL pipeline error: {e}")

    # 2. Execute NHL Engine
    try:
        print("[*] Running NHL Dixon-Coles & Crease engine...")
        nhl_recs = generate_nhl_recommendations()
        print(f"[✓] NHL generated {len(nhl_recs)} verified plays.")
        all_recs.extend(nhl_recs)
    except Exception as e:
        print(f"[!] NHL pipeline error: {e}")

    # 3. Synchronize to Supabase
    if all_recs:
        # Atomic replacement: Clear existing recommendation board
        requests.delete(
            f"{SUPABASE_URL}/rest/v1/bet_recommendations?id=neq.00000000-0000-0000-0000-000000000000",
            headers=HEADERS
        )
        post_res = requests.post(
            f"{SUPABASE_URL}/rest/v1/bet_recommendations",
            headers=HEADERS,
            json=all_recs
        )
        print(f"[✓] Synced total {len(all_recs)} multi-sport plays to Supabase (Status: {post_res.status_code}).")
    else:
        print("[!] No active edges qualifying over the 2.5% hurdle across slates.")

if __name__ == "__main__":
    run_pipeline()
