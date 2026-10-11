import os
import streamlit as st
import pandas as pd
import sqlalchemy as sa
from dotenv import load_dotenv
from notifier import dispatch_wager_alert

load_dotenv()

st.set_page_config(page_title="Syndicate Production Terminal", layout="wide", initial_sidebar_state="collapsed")

# Prioritize Streamlit Cloud secrets over local environment variables
def get_config(key, default=None):
    try:
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return os.getenv(key, default)

DATABASE_URL = get_config("DATABASE_URL")

@st.cache_resource
def get_engine():
    return sa.create_engine(DATABASE_URL, pool_pre_ping=True)

engine = get_engine()

st.title("Syndicate Production Terminal")

tab_recs, tab_ledger, tab_clv = st.tabs(["Active Model Recommendations", "Execution Ledger", "CLV Audit"])

# --- TAB 1: RECOMMENDATIONS ---
with tab_recs:
    col_t, col_btn = st.columns([6, 1])
    with col_t:
        st.subheader("Daily Model Edge Recommendations")
    with col_btn:
        if st.button("🔄 Sync Live Slate", use_container_width=True):
            st.rerun()

    try:
        with engine.connect() as conn:
            df = pd.read_sql("SELECT * FROM bet_recommendations WHERE status = 'ACTIVE' ORDER BY ev_percent DESC", conn)
        
        if not df.empty:
            sports = list(df["sport"].unique())
            selected_sports = st.pills("Filter by Sport", sports, selection_mode="multi", default=sports)
            filtered_df = df[df["sport"].isin(selected_sports)] if selected_sports else df
            st.dataframe(filtered_df, use_container_width=True, hide_index=True)
        else:
            st.info("No active recommendations currently logged for today's slate.")
    except Exception as exc:
        st.error(f"Error loading recommendations: {exc}")

# --- TAB 2: EXECUTION LEDGER ---
with tab_ledger:
    st.subheader("Log Executed Position")
    with st.form("wager_entry_form"):
        f_sport = st.selectbox("Sport", ["NFL", "NHL", "EPL", "CFB"])
        f_matchup = st.text_input("Matchup", placeholder="e.g. Houston Texans @ Tennessee Titans")
        f_market = st.selectbox("Market Type", ["Spread", "Moneyline", "Total"])
        f_pick = st.text_input("Selection", placeholder="e.g. Houston Texans -7")
        f_book = st.selectbox("Sportsbook", ["DraftKings", "FanDuel", "BetMGM", "Caesars", "Circa", "Pinnacle"])
        f_odds = st.number_input("Book Odds (American)", value=-110, step=1)
        f_stake = st.number_input("Allocated Stake (Units)", value=1.25, step=0.25)
        f_ev = st.number_input("Estimated Edge (% EV)", value=4.0, step=0.1)
        
        submit = st.form_submit_button("Commit Wager to Ledger & Dispatch Alerts")
        if submit:
            try:
                with engine.begin() as conn:
                    conn.execute(sa.text("""
                        INSERT INTO wagers (sport, matchup, market, pick, bookmaker, locked_odds, stake, ev_percent, status)
                        VALUES (:sport, :matchup, :market, :pick, :bookmaker, :locked_odds, :stake, :ev_percent, 'PENDING')
                    """), {
                        "sport": f_sport,
                        "matchup": f_matchup,
                        "market": f_market,
                        "pick": f_pick,
                        "bookmaker": f_book,
                        "locked_odds": f_odds,
                        "stake": f_stake,
                        "ev_percent": f_ev
                    })
                st.success("Wager successfully committed to Supabase ledger.")
                res = dispatch_wager_alert(f_sport, f_pick, f_book, f_odds, f_stake, f_ev)
                if res["email"][0]:
                    st.info(res["email"][1])
                if res["telegram"][0]:
                    st.info(res["telegram"][1])
            except Exception as e:
                st.error(f"Failed to record wager: {e}")

# --- TAB 3: CLV AUDIT ---
with tab_clv:
    st.subheader("Closing Line Value (CLV) Performance Ledger")
    try:
        with engine.connect() as conn:
            df_ledger = pd.read_sql("SELECT * FROM wagers ORDER BY created_at DESC", conn)
        if not df_ledger.empty:
            st.dataframe(df_ledger, use_container_width=True, hide_index=True)
        else:
            st.info("No wagers recorded yet.")
    except Exception as exc:
        st.error(f"Error fetching ledger: {exc}")
