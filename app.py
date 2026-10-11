import os
import requests
import pandas as pd
import streamlit as st
from datetime import datetime, timezone
from dotenv import load_dotenv
from settlement_engine import run_settlement, calculate_clv

load_dotenv()

st.set_page_config(page_title="Syndicate Production Terminal", layout="wide", initial_sidebar_state="collapsed")

# Custom Dark Terminal Styling
st.markdown("""
<style>
    .stApp { background-color: #0b111e; color: #d1d5db; }
    div[data-testid="stMetricValue"] { color: #f3f4f6; }
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
    .badge-edge { color: #10b981; font-weight: 700; font-size: 13px; }
</style>
""", unsafe_allow_html=True)

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://btzzkdjnijzzdqvjnomr.supabase.co").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Master list of active books across your desk
BOOKMAKERS = [
    "DraftKings",
    "FanDuel",
    "BetMGM",
    "Caesars",
    "bet365",
    "theScore",
    "Bally Bet",
    "Fanatics",
    "BetOnline",
    "Novig",
    "Kalshi",
    "Circa",
    "Pinnacle",
    "Other"
]

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

def send_telegram_alert(sport, matchup, market, pick, odds, stake, ev="MANUAL"):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID: return
    ev_display = f"+{ev}%" if ev != "MANUAL" else "MANUAL / OFF-MODEL"
    text = (
        f"🚨 *HOVA SYNDICATE PLAY LOCKED*\n\n"
        f"🏆 *Sport:* {sport}\n"
        f"⚔️ *Matchup:* {matchup}\n"
        f"🎯 *Market:* {market}\n"
        f"⚡ *Pick:* {pick}\n"
        f"📈 *Book Odds:* {odds:+d}\n"
        f"💰 *Stake:* {stake}u\n"
        f"💎 *EV:* {ev_display}\n\n"
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
        "sport": str(row_data["sport"]),
        "matchup": str(row_data["matchup"]),
        "market": str(row_data["market"]),
        "pick": str(row_data["pick"]),
        "odds": int(booked_odds),
        "stake_units": float(booked_units),
        "bookmaker": str(bookmaker),
        "status": "OPEN",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    try:
        r = requests.post(f"{SUPABASE_URL}/rest/v1/ledger_entries", headers=HEADERS, json=payload, timeout=8)
        if r.status_code in [200, 201]:
            ev_val = row_data.get("ev_percent", "MANUAL")
            send_telegram_alert(
                row_data["sport"], row_data["matchup"], row_data["market"],
                row_data["pick"], booked_odds, booked_units, ev_val
            )
            return True, "Success"
        else:
            return False, f"HTTP {r.status_code}: {r.text}"
    except Exception as e:
        return False, str(e)

# Layout Setup
st.markdown("<h2 style='margin-bottom:0;'>Syndicate Production Terminal</h2>", unsafe_allow_html=True)
st.caption("Quantitative Multi-Sport Desk • Quarter-Kelly Sizing • Autonomous Cloud Pipeline")

tabs = st.tabs(["Active Model Recommendations", "Execution Ledger", "CLV & Settlement Audit"])

# ==============================================================================
# TAB 1: RECOMMENDATIONS + 1-CLICK BET STAGER
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
        sports_present = sorted(df_recs["sport"].unique().tolist())
        selected_sport = st.pills("Filter by Sport", ["ALL"] + sports_present, default="ALL")

        view_df = df_recs if selected_sport == "ALL" else df_recs[df_recs["sport"] == selected_sport]

        if "staged_pick" not in st.session_state:
            st.session_state.staged_pick = None

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
                    book_name = st.selectbox("Bookmaker", BOOKMAKERS, key="stage_book")
                with col_b4:
                    st.write("")
                    st.write("")
                    if st.button("✅ Commit to Ledger", use_container_width=True, type="primary"):
                        success, msg = record_wager(stg, b_odds, b_stake, book_name)
                        if success:
                            st.success(f"Locked {stg['pick']} ({b_stake}u) to Ledger & dispatched alert!")
                            st.session_state.staged_pick = None
                            st.rerun()
                        else:
                            st.error(f"Commit Failed: {msg}")
                with col_b5:
                    st.write("")
                    st.write("")
                    if st.button("✖ Cancel", use_container_width=True):
                        st.session_state.staged_pick = None
                        st.rerun()

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
# TAB 2: EXECUTION LEDGER + MANUAL ENTRY DRAWER
# ==============================================================================
with tabs[1]:
    col_l1, col_l2 = st.columns([4, 1])
    with col_l1:
        st.subheader("Locked Positions Ledger")
    with col_l2:
        with st.popover("➕ Log Manual Bet", use_container_width=True):
            st.markdown("##### Manual / Off-Model Entry")
            m_sport = st.selectbox("Sport", ["NFL", "CFB", "NHL", "MLB", "WNBA", "EPL"])
            m_matchup = st.text_input("Matchup (e.g. AWAY @ HOME)", placeholder="KC @ BAL")
            m_market = st.selectbox("Market", ["Moneyline", "Spread", "Total", "Puck Line", "Run Line", "Player Prop"])
            m_pick = st.text_input("Pick", placeholder="KC +3.0")
            m_odds = st.number_input("Odds (American)", value=-110, step=1)
            m_stake = st.number_input("Stake Units", value=1.00, min_value=0.25, step=0.25)
            m_book = st.selectbox("Bookmaker", BOOKMAKERS, key="manual_book")
            
            if st.button("Submit Manual Wager", type="primary", use_container_width=True):
                if m_matchup and m_pick:
                    payload = {
                        "sport": m_sport,
                        "matchup": m_matchup.strip().upper(),
                        "market": m_market,
                        "pick": m_pick.strip(),
                        "ev_percent": "MANUAL"
                    }
                    success, msg = record_wager(payload, m_odds, m_stake, m_book)
                    if success:
                        st.success(f"Logged {m_pick} ({m_stake}u) successfully!")
                        st.rerun()
                    else:
                        st.error(f"Commit Failed: {msg}")
                else:
                    st.warning("Please fill in Matchup and Pick fields.")

    df_ledger = fetch_table("ledger_entries")
    if not df_ledger.empty:
        df_ledger = df_ledger.sort_values(by="created_at", ascending=False)
        display_cols = ["created_at", "sport", "matchup", "market", "pick", "odds", "stake_units", "bookmaker", "status"]
        if "net_units" in df_ledger.columns: display_cols.append("net_units")
        if "result_score" in df_ledger.columns: display_cols.append("result_score")
        st.dataframe(df_ledger[display_cols], use_container_width=True, hide_index=True)
    else:
        st.info("No wagers locked in the ledger yet.")

# ==============================================================================
# TAB 3: CLV & SETTLEMENT AUDIT
# ==============================================================================
with tabs[2]:
    col_s1, col_s2 = st.columns([4, 1])
    with col_s1:
        st.subheader("Closing Line Value & Performance Audit")
    with col_s2:
        if st.button("⚡ Audit & Settle", use_container_width=True, type="primary"):
            with st.spinner("Checking ESPN scores & settling tickets..."):
                run_settlement()
                st.success("Reconciliation complete!")
                st.rerun()

    df_ledger = fetch_table("ledger_entries")
    if not df_ledger.empty:
        settled_mask = df_ledger["status"].isin(["WON", "LOST", "PUSH"])
        df_settled = df_ledger[settled_mask]
        
        net_profit = df_settled["net_units"].astype(float).sum() if "net_units" in df_settled.columns else 0.0
        total_risk = df_settled["stake_units"].astype(float).sum()
        roi_pct = (net_profit / total_risk * 100.0) if total_risk > 0 else 0.0

        wins = len(df_ledger[df_ledger["status"] == "WON"])
        losses = len(df_ledger[df_ledger["status"] == "LOST"])
        pushes = len(df_ledger[df_ledger["status"] == "PUSH"])
        open_bets = len(df_ledger[df_ledger["status"] == "OPEN"])

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Cumulative Net P&L", f"{net_profit:+.2f}u", delta=f"{roi_pct:+.1f}% ROI")
        m2.metric("Graded Record", f"{wins}W - {losses}L - {pushes}P", f"{open_bets} Pending")
        m3.metric("Total Volume Wagered", f"{df_ledger['stake_units'].astype(float).sum():.2f}u")
        
        if "clv_percent" in df_ledger.columns and not df_ledger["clv_percent"].dropna().empty:
            avg_clv = df_ledger["clv_percent"].astype(float).mean()
            m4.metric("Consensus CLV Edge", f"{avg_clv:+.2f}%")
        else:
            m4.metric("Consensus CLV Edge", "--")

        st.divider()
        st.markdown("#### Audited Position History")
        audit_cols = ["sport", "matchup", "pick", "odds", "stake_units", "status"]
        if "net_units" in df_ledger.columns: audit_cols.append("net_units")
        if "result_score" in df_ledger.columns: audit_cols.append("result_score")
        if "clv_percent" in df_ledger.columns: audit_cols.append("clv_percent")
        st.dataframe(df_ledger[audit_cols], use_container_width=True, hide_index=True)
    else:
        st.info("Lock wagers in the Recommendations tab to start tracking settlement and closing line value.")
