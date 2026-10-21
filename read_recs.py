import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")

if not url or not key:
    try:
        import config.settings as s
        url = getattr(s, "SUPABASE_URL", None)
        key = getattr(s, "SUPABASE_KEY", None)
    except Exception:
        pass

sb = create_client(url, key)
res = sb.table("bet_recommendations").select("*").execute()

print(f"[*] Total rows in bet_recommendations: {len(res.data)}")
for r in res.data[:5]:
    print(" ->", {k: r[k] for k in ["sport", "matchup", "pick", "ev_pct", "suggested_stake", "is_active", "commence_time"] if k in r})
