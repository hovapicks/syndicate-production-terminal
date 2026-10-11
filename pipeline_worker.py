import os
import requests
import datetime
from dotenv import load_dotenv

from models.nfl_pipeline import generate_nfl_recommendations
from models.nhl_pipeline import generate_nhl_recommendations
from models.epl_pipeline import generate_epl_recommendations
from models.cfb_pipeline import generate_cfb_recommendations
from models.wnba_pipeline import generate_wnba_recommendations
from models.mlb_pipeline import generate_mlb_recommendations

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://btzzkdjnijzzdqvjnomr.supabase.co").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

def sync_pipeline():
    print(f"[*] Starting 6-Sport Quantitative Syndicate Production Run: {datetime.datetime.utcnow().isoformat()}Z")
    
    all_recs = []
    
    # 1. NFL
    try:
        print("[*] Generating NFL positions...")
        nfl_plays = generate_nfl_recommendations()
        print(f"[✓] NFL generated: {len(nfl_plays)} edges.")
        all_recs.extend(nfl_plays)
    except Exception as e:
        print(f"[!] NFL Pipeline Exception: {e}")

    # 2. NHL
    try:
        print("[*] Generating NHL positions...")
        nhl_plays = generate_nhl_recommendations()
        print(f"[✓] NHL generated: {len(nhl_plays)} edges.")
        all_recs.extend(nhl_plays)
    except Exception as e:
        print(f"[!] NHL Pipeline Exception: {e}")

    # 3. EPL
    try:
        print("[*] Generating EPL positions...")
        epl_plays = generate_epl_recommendations()
        print(f"[✓] EPL generated: {len(epl_plays)} edges.")
        all_recs.extend(epl_plays)
    except Exception as e:
        print(f"[!] EPL Pipeline Exception: {e}")

    # 4. CFB
    try:
        print("[*] Generating CFB positions...")
        cfb_plays = generate_cfb_recommendations()
        print(f"[✓] CFB generated: {len(cfb_plays)} edges.")
        all_recs.extend(cfb_plays)
    except Exception as e:
        print(f"[!] CFB Pipeline Exception: {e}")

    # 5. WNBA
    try:
        print("[*] Generating WNBA positions...")
        wnba_plays = generate_wnba_recommendations()
        print(f"[✓] WNBA generated: {len(wnba_plays)} edges.")
        all_recs.extend(wnba_plays)
    except Exception as e:
        print(f"[!] WNBA Pipeline Exception: {e}")

    # 6. MLB Postseason
    try:
        print("[*] Generating MLB Postseason positions...")
        mlb_plays = generate_mlb_recommendations()
        print(f"[✓] MLB generated: {len(mlb_plays)} edges.")
        all_recs.extend(mlb_plays)
    except Exception as e:
        print(f"[!] MLB Pipeline Exception: {e}")

    print(f"[*] Total Qualified Syndicate Recommendations: {len(all_recs)}")

    # Wipe existing table and insert fresh production recommendations
    print("[*] Syncing recommendations to Supabase...")
    del_r = requests.delete(
        f"{SUPABASE_URL}/rest/v1/bet_recommendations?id=neq.00000000-0000-0000-0000-000000000000",
        headers=HEADERS,
        timeout=10
    )
    
    if all_recs:
        ins_r = requests.post(
            f"{SUPABASE_URL}/rest/v1/bet_recommendations",
            headers=HEADERS,
            json=all_recs,
            timeout=10
        )
        if ins_r.status_code in [200, 201]:
            print(f"[✓] Successfully committed {len(all_recs)} edges to Supabase.")
        else:
            print(f"[!] Supabase Insert Error {ins_r.status_code}: {ins_r.text}")
    else:
        print("[*] No qualifying plays across current slate.")

if __name__ == "__main__":
    sync_pipeline()
