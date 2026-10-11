import os
import requests
import pandas as pd
import streamlit as st
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="Syndicate Production Terminal", layout="wide", initial_sidebar_state="collapsed")

# Custom Dark Terminal CSS
st.markdown("""
<style>
    .stApp { background-color: #0b111e; color: #d1d5db; }
    div[data-testid="stMetricValue"] { color: #f3f4f6; }
    .rec-card {
        background-color: #111827;
        border: 1px solid #1f2937;
        border-radius: 8px;
        padding: 14px 18px;
        margin-bottom: 12px;
        display: flex;
        align-items: center;
        justify-content: space-between;
    }
    .badge-sport {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 4px;
        font-weight: 700;
        font-size: 11px;
        background: #1f2937;
        color: #93c5fd;
        margin-right: 8px;
    }
    .badge-edge {
        color: #10b981;
        font-weight: 700;
        font-size: 13px;
    }
</style>
""", unsafe_allow_html=True)

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://btzzkdjnijzzdqvjnomr.supabase.co").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

def send_telegram_alert(sport, matchup, market, pick, odds, stake, ev):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    text = (
        f"🚨 *HOVA SYNDICATE PLAY LOCKED*\n\n"
        f"🏆 *Sport:* {sport}\n"
        f"⚔️ *Matchup:* {matchup}\n"
        f"🎯 *Market:* {market}\n"
        f"⚡ *Pick:* {pick}\n"
        f"📈 *Book Odds:* {odds}\n"
        f"💰 *Stake:* {stake}u\n"
        f"💎 *EV:* +{ev}%\n\n"
        f"⏰ {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
    )
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}, timeout=5)
    except Exception:
        pass

def fetch_table(table_name):
    try:
        r = requests.get(f"{SUPABASE_URL}/rest/v1/{table_name}?select=*", headers=HEADERS, timeout=8)
        if r.status_code == 200:
            return pd.DataFrame(r.json())
    except Exception:
        pass
    return pd.DataFrame()

def record_wager(row_data, booked_odds, booked_units, bookmaker):
    payload = {
        "sport": row_data["sport"],
        "matchup": row_data["matchup"],
        "market": row_data["market"],
        "pick": row_data["pick"],
        "odds": int(booked_odds),
        "stake_units": float(booked_units),
        "bookmaker": bookmaker,
        "status": "OPEN",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    try:
        r = requests.post(f"{SUPABASE_URL}/rest/v1/ledger_entries", headers=HEADERS, json=payload, timeout=8)
        if r.status_code in [200, 201]:
            send_telegram_alert(
                row_data["sport"], row_data["matchup"], row_data["market"],
                row_data["pick"], booked_odds, booked_units, row_data["ev_percent"]
            )
            return True
    except Exception:
        pass
    return False

# Header & Controls
st.markdown("<h2 style='margin-bottom:0;'>Syndicate Production Terminal</h2>", unsafe_allow_html=True)
st.caption("Quantitative Multi-Sport Desk • Quarter-Kelly Sizing • Autonomous Cloud Pipeline")

tabs = st.tabs(["Active Model Recommendations", "Execution Ledger", "CLV Audit"])

# ==============================================================================
# TAB 1: RECOMMENDATIONS + 1-CLICK BET LOGGER
# ==============================================================================
with tabs[0]:
    col_t1, col_t2 = st.columns([4, 1])
    with col_t1:
        st.subheader("Daily Model Edge Recommendations")
    with col_t2:
        if st.button("🔄 Sync Live Slate", use_container_width=True):
            st.rerun()

    df_recs = fetch_table("bet_recommendations")

    if not df_recs.empty:
        # Sport selector
        sports_present = sorted(df_recs["sport"].unique().tolist())
        selected_sport = st.pills("Filter by Sport", ["ALL"] + sports_present, default="ALL")

        view_df = df_recs if selected_sport == "ALL" else df_recs[df_recs["sport"] == selected_sport]

        if "staged_pick" not in st.session_state:
            st.session_state.staged_pick = None

        # Display Staged Wager Action Panel if a bet is selected
        if st.session_state.staged_pick:
            stg = st.session_state.staged_pick
            with st.container():
                st.markdown(f"""
                <div style="background: rgba(37, 99, 235, 0.12); border: 1px solid #2563eb; border-radius: 6px; padding: 14px 18px; margin-bottom: 20px;">
                    <div style="font-weight: 700; color: #93c5fd; font-size: 14px; margin-bottom: 8px;">
                        ⚡ CONFIRM & STAGE WAGER: {stg['sport']} • {stg['matchup']} • {stg['pick']}
                    </div>
                </div>
                """, unsafe_allow_html=True)

                col_b1, col_b2, col_b3, col_b4, col_b5 = st.columns([2, 2, 2, 2, 1.5])
                with col_b1:
                    b_odds = st.number_input("Book Odds (American)", value=int(stg["book_odds"]), step=1, key="stage_odds")
                with col_b2:
                    b_stake = st.number_input("Stake Units", value=float(stg["suggested_stake"]), min_value=0.25, step=0.25, key="stage_stake")
                with col_b3:
                    book_name = st.selectbox("Bookmaker", ["DraftKings", "FanDuel", "BetMGM", "Caesars", "Circa", "Pinnacle"], key="stage_book")
                with col_b4:
                    st.write("")
                    st.write("")
                    if st.button("✅ Commit to Ledger", use_container_width=True, type="primary"):
                        if record_wager(stg, b_odds, b_stake, book_name):
                            st.success(f"Locked {stg['pick']} ({b_stake}u) to Ledger & dispatched alert!")
                            st.session_state.staged_pick = None
                            st.rerun()
                        else:
                            st.error("Failed to commit wager to database.")
                with col_b5:
                    st.write("")
                    st.write("")
                    if st.button("✖ Cancel", use_container_width=True):
                        st.session_state.staged_pick = None
                        st.rerun()

        # Render Active Bets Table with Row-Level Action Buttons
        for idx, row in view_df.iterrows():
            c1, c2, c3, c4, c5, c6, c7 = st.columns([1.2, 2.5, 2.2, 1.3, 1.3, 1.4, 1.5])
            with c1:
                st.markdown(f"<span class='badge-sport'>{row['sport']}</span>", unsafe_allow_html=True)
            with c2:
                st.write(f"**{row['matchup']}**")
            with c3:
                st.write(f"{row['pick']} ({row['market']})")
            with c4:
                st.write(f"Odds: **{row['book_odds']}**")
            with c5:
                st.markdown(f"<span class='badge-edge'>+{row['ev_percent']}%</span>", unsafe_allow_html=True)
            with c6:
                st.write(f"Rec: **{row['suggested_stake']}u**")
            with c7:
                if st.button("⚡ Lock", key=f"btn_lock_{idx}", use_container_width=True):
                    st.session_state.staged_pick = row.to_dict()
                    st.rerun()
            st.divider()

    else:
        st.info("No active edge recommendations currently in database. Hit Sync Live Slate above.")

# ==============================================================================
# TAB 2: EXECUTION LEDGER
# ==============================================================================
with tabs[1]:
    st.subheader("Locked Positions Ledger")
    df_ledger = fetch_table("ledger_entries")
    if not df_ledger.empty:
        df_ledger = df_ledger.sort_values(by="created_at", ascending=False)
        st.dataframe(
            df_ledger[["created_at", "sport", "matchup", "market", "pick", "odds", "stake_units", "bookmaker", "status"]],
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("No wagers locked in the ledger yet.")

# ==============================================================================
# TAB 3: CLV AUDIT
# ==============================================================================
with tabs[2]:
    st.subheader("Closing Line Value (CLV) Performance Audit")
    st.caption("Tracks line movement delta between entry price and final closing consensus.")
    df_ledger = fetch_table("ledger_entries")
    if not df_ledger.empty:
        col_m1, col_m2, col_m3 = st.columns(3)
        col_m1.metric("Total Wagers Locked", len(df_ledger))
        col_m2.metric("Total Bankroll Allocated", f"{df_ledger['stake_units'].sum():.2f}u")
        col_m3.metric("Open Action Count", len(df_ledger[df_ledger['status'] == 'OPEN']))
    else:
        st.info("Log wagers to begin tracking closing line value performance.")
