import os
import streamlit as st
import pandas as pd
import requests
from dotenv import load_dotenv
from notifier import dispatch_wager_alert

load_dotenv()

st.set_page_config(page_title="Syndicate Production Terminal", layout="wide", initial_sidebar_state="collapsed")

def get_config(key, default=None):
    try:
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return os.getenv(key, default)

SUPABASE_URL = get_config("SUPABASE_URL", "https://btzzkdnijzzdqvjnomr.supabase.co").rstrip("/")
SUPABASE_KEY = get_config("SUPABASE_KEY", "")

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

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
        url = f"{SUPABASE_URL}/rest/v1/bet_recommendations?status=eq.ACTIVE&order=ev_percent.desc"
        res = requests.get(url, headers=HEADERS, timeout=10)
        
        if res.status_code == 200 and res.json():
            df = pd.DataFrame(res.json())
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
            payload = {
                "sport": f_sport,
                "matchup": f_matchup,
                "market": f_market,
                "pick": f_pick,
                "bookmaker": f_book,
                "locked_odds": int(f_odds),
                "stake": float(f_stake),
                "ev_percent": float(f_ev),
                "status": "PENDING"
            }
            try:
                post_url = f"{SUPABASE_URL}/rest/v1/wagers"
                post_res = requests.post(post_url, headers=HEADERS, json=payload, timeout=10)
                
                if post_res.status_code in [200, 201]:
                    st.success("Wager successfully committed to Supabase ledger.")
                    res_alert = dispatch_wager_alert(f_sport, f_pick, f_book, f_odds, f_stake, f_ev)
                    if res_alert["email"][0]:
                        st.info(res_alert["email"][1])
                    if res_alert["telegram"][0]:
                        st.info(res_alert["telegram"][1])
                else:
                    st.error(f"Failed to record wager: HTTP {post_res.status_code} - {post_res.text}")
            except Exception as e:
                st.error(f"Failed to record wager: {e}")

# --- TAB 3: CLV AUDIT ---
with tab_clv:
    st.subheader("Closing Line Value (CLV) Performance Ledger")
    try:
        ledger_url = f"{SUPABASE_URL}/rest/v1/wagers?order=created_at.desc"
        res_ledger = requests.get(ledger_url, headers=HEADERS, timeout=10)
        if res_ledger.status_code == 200 and res_ledger.json():
            df_ledger = pd.DataFrame(res_ledger.json())
            st.dataframe(df_ledger, use_container_width=True, hide_index=True)
        else:
            st.info("No wagers recorded yet.")
    except Exception as exc:
        st.error(f"Error fetching ledger: {exc}")
