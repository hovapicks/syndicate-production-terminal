import os
import requests
import pandas as pd
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://btzzkdjnijzzdqvjnomr.supabase.co").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
MAX_DAILY_EXPOSURE_UNITS = float(os.getenv("MAX_DAILY_EXPOSURE_UNITS", "6.0"))

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

def apply_portfolio_risk_governor(recs_df, max_slate_exposure=6.0):
    if recs_df.empty or "suggested_stake" not in recs_df.columns:
        return recs_df

    recs_df["suggested_stake"] = recs_df["suggested_stake"].astype(float)
    total_raw_stake = recs_df["suggested_stake"].sum()

    print(f"[*] Raw Model Portfolio Exposure: {total_raw_stake:.2f}u across {len(recs_df)} positions")

    if total_raw_stake > max_slate_exposure:
        haircut_ratio = max_slate_exposure / total_raw_stake
        print(f"[!] Exposure cap ({max_slate_exposure}u) exceeded. Applying {haircut_ratio:.3f} scaling factor.")
        recs_df["suggested_stake"] = (recs_df["suggested_stake"] * haircut_ratio).round(2)
        # Ensure institutional minimum execution floor
        recs_df["suggested_stake"] = recs_df["suggested_stake"].clip(lower=0.25)
    else:
        print("[✓] Slate exposure safely within Daily VaR limit.")

    return recs_df

def push_recommendations_to_supabase(recs_df):
    if recs_df.empty:
        print("[-] No positive EV recommendations surfaced for this slate.")
        return

    # Enforce Daily VaR Portfolio Governor
    governed_df = apply_portfolio_risk_governor(recs_df, MAX_DAILY_EXPOSURE_UNITS)

    # Clear outdated slate recommendations
    try:
        requests.delete(f"{SUPABASE_URL}/rest/v1/bet_recommendations?id=neq.00000000-0000-0000-0000-000000000000", headers=HEADERS, timeout=8)
    except Exception as e:
        print(f"[-] Clear failed: {e}")

    records = governed_df.to_dict(orient="records")
    for r in records:
        r["created_at"] = datetime.now(timezone.utc).isoformat()

    try:
        res = requests.post(f"{SUPABASE_URL}/rest/v1/bet_recommendations", headers=HEADERS, json=records, timeout=8)
        if res.status_code in [200, 201]:
            print(f"[✓] Successfully synced {len(records)} risk-governed plays to Supabase!")
        else:
            print(f"[-] Failed to push to Supabase: {res.status_code} - {res.text}")
    except Exception as e:
        print(f"[-] Push error: {e}")

if __name__ == "__main__":
    print("[*] Running Syndicate Pipeline with Portfolio VaR Governor...")
    # Import and aggregate slates across production sport models
    # Example ingestion structure:
    # all_plays = pd.concat([nfl_plays, nhl_plays, mlb_plays], ignore_index=True)
    # push_recommendations_to_supabase(all_plays)
