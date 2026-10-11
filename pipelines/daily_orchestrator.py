import sys
import os
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

# Ensure project root is in Python's search path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.settings import (
    SUPABASE_URL,
    SUPABASE_KEY,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
)
from core.notifier import send_telegram_alert

try:
    from supabase import create_client, Client
except ImportError:
    create_client = None

def get_supabase_client():
    if not SUPABASE_URL or not SUPABASE_KEY or not create_client:
        print("[Orchestrator] Supabase client or credentials missing.")
        return None
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def run_pipeline():
    print(f"[{datetime.now().isoformat()}] Starting 4:00 AM Syndicate Production Pipeline...")
    all_recommendations: List[Dict[str, Any]] = []

    # 1. Execute NHL Model
    try:
        from models.nhl import run_nhl_slate
        nhl_plays = run_nhl_slate()
        if nhl_plays:
            all_recommendations.extend(nhl_plays)
            print(f"[Orchestrator] Ingested {len(nhl_plays)} NHL plays.")
    except Exception as e:
        print(f"[Orchestrator] NHL module wrapper notice: {e}")

    # 2. Execute EPL Model
    try:
        from models.epl import run_epl_slate
        epl_plays = run_epl_slate()
        if epl_plays:
            all_recommendations.extend(epl_plays)
            print(f"[Orchestrator] Ingested {len(epl_plays)} EPL plays.")
    except Exception as e:
        print(f"[Orchestrator] EPL module wrapper notice: {e}")

    # 3. Store to Supabase
    supabase = get_supabase_client()
    if supabase and all_recommendations:
        try:
            res = supabase.table("bet_recommendations").insert(all_recommendations).execute()
            print(f"[Orchestrator] Successfully logged {len(all_recommendations)} plays to Supabase.")
        except Exception as e:
            print(f"[Orchestrator] Error writing to Supabase: {e}")

    # 4. Dispatch Telegram Morning Card
    today_str = datetime.now().strftime('%b %d, %Y')
    if all_recommendations:
        lines = [f"🏆 *4:00 AM Production Card* ({today_str})"]
        for play in all_recommendations:
            lines.append(
                f"• *{play['sport']}*: {play['pick']} | EV: `+{play['ev_percent']}%` | Stake: `{play['kelly_units']}u`"
            )
        alert_body = "\n".join(lines)
    else:
        alert_body = f"📊 *4:00 AM Slate Scan Complete* ({today_str})\nNo plays crossed the >= 1.8% EV hurdle this morning."

    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        send_telegram_alert(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, alert_body)
    else:
        print("[Orchestrator] Telegram credentials not set. Alert skipped.")

    print("[Orchestrator] Morning run complete.")

if __name__ == "__main__":
    run_pipeline()
