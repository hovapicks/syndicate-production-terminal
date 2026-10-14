import os
import requests
import pandas as pd
import streamlit as st
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="Syndicate Production Terminal",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Dark theme styling
st.markdown("""
<style>
    .stApp {
        background-color: #0b0f19;
        color: #f3f4f6;
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.6rem !important;
        font-weight: 700 !important;
        color: #38bdf8 !important;
    }
</style>
""", unsafe_allow_html=True)

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://btzzkdjnijzzdqvjnomr.supabase.co").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

# Dynamically collect all available keys
ODDS_API_KEYS = [
    val for k, val in sorted(os.environ.items(), key=lambda x: int(x[0].split('_')[-1]) if x[0].split('_')[-1].isdigit() else 99)
    if k.startswith("ODDS_API_KEY_") and val
]

@st.cache_data(ttl=60)
def fetch_api_pool_status():
    total_remaining = 0
    active_count = 0
    for key in ODDS_API_KEYS:
        if not key:
            continue
        try:
            r = requests.get(f"https://api.the-odds-api.com/v4/sports/?apiKey={key}", timeout=4)
            if r.status_code == 200:
                rem = r.headers.get("x-requests-remaining")
                if rem and rem.isdigit():
                    total_remaining += int(rem)
                    active_count += 1
        except Exception:
            continue
    return total_remaining, active_count

def fetch_table(table_name):
    try:
        r = requests.get(f"{SUPABASE_URL}/rest/v1/{table_name}?select=*&order=created_at.desc", headers=HEADERS, timeout=6)
        if r.status_code == 200:
            return pd.DataFrame(r.json())
    except Exception as e:
        st.error(f"Error connecting to Supabase: {e}")
    return pd.DataFrame()

# Header Section
col_title, col_btn = st.columns([4, 1])
with col_title:
    st.title("Syndicate Production Terminal")
    st.caption("Quantitative Multi-Sport Desk • Quarter-Kelly Sizing • Autonomous Cloud Pipeline")

with col_btn:
    if st.button("🔄 Sync Live Slate", use_container_width=True, type="primary"):
        st.cache_data.clear()
        st.rerun()

# Top Metrics Row
pool_remaining, active_keys = fetch_api_pool_status()
m1, m2, m3, m4 = st.columns(4)
m1.metric("API Pool Runway", f"{pool_remaining} reqs", f"{active_keys} Active Keys")

tab_recs, tab_ledger, tab_audit = st.tabs([
    "Active Model Recommendations",
    "Execution Ledger",
    "CLV & Settlement Audit"
])

# TAB 1: RECOMMENDATIONS
with tab_recs:
    st.subheader("Daily Model Edge Recommendations")
    df_recs = fetch_table("bet_recommendations")

    if df_recs.empty:
        st.info("No active recommendations currently staged. Run pipeline_worker.py to sweep the board.")
    else:
        sports_in_data = sorted(df_recs["sport"].dropna().unique().tolist())
        pill_options = ["ALL"] + [s for s in ["NHL", "MLB", "NFL", "NCAAF"] if s in sports_in_data or s == "NCAAF"]

        col_f1, col_f2 = st.columns([3, 2])
        with col_f1:
            selected_sport = st.pills("Filter by Sport", pill_options, default="ALL")
        with col_f2:
            slate_scope = st.segmented_control(
                "Slate Scope",
                ["🔥 Today's Active Slate", "⚡ All Markets (Inc. Lookaheads)"],
                default="🔥 Today's Active Slate"
            )

        # Filter by Scope
        if "is_lookahead" in df_recs.columns and slate_scope == "🔥 Today's Active Slate":
            filtered_df = df_recs[df_recs["is_lookahead"] == False].copy()
        else:
            filtered_df = df_recs.copy()

        # Filter by Sport
        if selected_sport != "ALL":
            filtered_df = filtered_df[filtered_df["sport"] == selected_sport]

        if filtered_df.empty:
            st.info("No qualified edges found for this sport/slate selection.")
        else:
            for idx, row in filtered_df.iterrows():
                with st.container(border=True):
                    c_badge, c_matchup, c_pick, c_odds, c_ev, c_stake, c_action = st.columns([1, 4, 3, 2, 2, 2, 2])
                    c_badge.markdown(f"**`{row.get('sport')}`**")
                    c_matchup.markdown(f"**{row.get('matchup')}**")
                    c_pick.markdown(f"{row.get('pick')} ({row.get('market')})")
                    
                    o_val = row.get("book_odds")
                    o_str = f"+{o_val}" if o_val > 0 else str(o_val)
                    c_odds.markdown(f"Odds: **{o_str}**")
                    
                    ev_val = float(row.get("ev_percent", 0.0))
                    c_ev.markdown(f":green[**+{ev_val:.1f}%**]")
                    
                    c_stake.markdown(f"Rec: **{row.get('suggested_stake')}u**")
                    
                    lock_btn = c_action.button("⚡ Lock", key=f"lock_{row.get('id', idx)}", use_container_width=True)
                    if lock_btn:
                        st.session_state["staging_row"] = row.to_dict()

            if "staging_row" in st.session_state:
                st.divider()
                st.write("### Stage Pick to Ledger")
                st_data = st.session_state["staging_row"]
                col_in1, col_in2, col_in3 = st.columns(3)
                bm = col_in1.selectbox("Bookmaker", ["DraftKings", "FanDuel", "BetMGM", "Caesars", "Pinnacle", "Circa", "Novig", "BetRivers", "ESPN BET"])
                stk = col_in2.number_input("Confirmed Units", value=float(st_data.get("suggested_stake", 1.0)), step=0.1)
                commit_btn = col_in3.button("✅ Commit to Ledger", type="primary", use_container_width=True)
                
                if commit_btn:
                    payload = {
                        "sport": str(st_data["sport"]),
                        "matchup": str(st_data["matchup"]),
                        "market": str(st_data["market"]),
                        "pick": str(st_data["pick"]),
                        "odds": int(st_data["book_odds"]),
                        "stake_units": float(stk),
                        "bookmaker": str(bm),
                        "status": "OPEN",
                        "created_at": datetime.now(timezone.utc).isoformat()
                    }
                    pres = requests.post(f"{SUPABASE_URL}/rest/v1/ledger_entries", headers=HEADERS, json=payload)
                    if pres.status_code in [200, 201]:
                        st.success(f"Position locked into ledger: {payload['pick']}")
                        del st.session_state["staging_row"]
                        st.cache_data.clear()
                        st.rerun()

# TAB 2: LEDGER
with tab_ledger:
    st.subheader("Active & Historical Ledger Entries")
    df_ledger = fetch_table("ledger_entries")
    if df_ledger.empty:
        st.info("No recorded ledger entries found.")
    else:
        st.dataframe(
            df_ledger[["sport", "matchup", "pick", "odds", "stake_units", "bookmaker", "status", "created_at"]],
            use_container_width=True,
            hide_index=True
        )

# TAB 3: SETTLEMENT AUDIT
with tab_audit:
    st.subheader("Settlement Grading & Cumulative Metrics")
    df_settled = fetch_table("ledger_entries")
    if not df_settled.empty and "status" in df_settled.columns:
        closed = df_settled[df_settled["status"].isin(["WON", "LOST", "PUSH"])]
        if not closed.empty and "net_units" in closed.columns:
            tot_pnl = closed["net_units"].fillna(0).astype(float).sum()
            tot_wagered = closed["stake_units"].fillna(0).astype(float).sum()
            roi = (tot_pnl / tot_wagered * 100.0) if tot_wagered > 0 else 0.0
            
            c_pnl, c_roi, c_closed = st.columns(3)
            c_pnl.metric("Realized P&L", f"{tot_pnl:+.2f}u")
            c_roi.metric("Realized ROI", f"{roi:+.1f}%")
            c_closed.metric("Settled Plays", len(closed))
            
            st.dataframe(closed[["sport", "matchup", "pick", "odds", "stake_units", "status", "net_units", "result_score"]], use_container_width=True, hide_index=True)
        else:
            st.info("Pending settlement audit. All ledger rows currently OPEN.")
    else:
        st.info("No ledger entries to audit.")
