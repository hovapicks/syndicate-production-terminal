import os
import subprocess
import streamlit as st
import pandas as pd
import sqlalchemy as sa
from dotenv import load_dotenv
from notifier import dispatch_wager_alert

load_dotenv()

st.set_page_config(page_title="Syndicate Production Terminal", layout="wide")
st.title("Syndicate Production Terminal")

DATABASE_URL = os.getenv("DATABASE_URL")

@st.cache_resource
def get_engine():
    return sa.create_engine(DATABASE_URL, pool_pre_ping=True)

engine = get_engine()

tabs = st.tabs(["Active Model Recommendations", "Execution Ledger", "CLV Audit"])

# TAB 1: MODEL RECOMMENDATIONS
with tabs[0]:
    col1, col2 = st.columns([4, 1])
    with col1:
        st.subheader("Daily Model Edge Recommendations")
    with col2:
        if st.button("🔄 Sync Live Slate"):
            with st.spinner("Fetching latest odds and running syndicate model..."):
                subprocess.run(["python", "pipeline_worker.py"], capture_output=True, text=True)
                st.success("Slate synchronized!")
                st.rerun()

    try:
        with engine.connect() as conn:
            df_recs = pd.read_sql_query(
                sa.text("""
                    SELECT 
                        id::text AS id, 
                        sport, 
                        matchup, 
                        market, 
                        pick, 
                        fair_odds, 
                        book_odds, 
                        ev_percent, 
                        suggested_stake, 
                        status, 
                        created_at 
                    FROM bet_recommendations 
                    ORDER BY created_at DESC
                """),
                conn
            )
        if not df_recs.empty:
            available_sports = sorted(df_recs["sport"].unique().tolist())
            selected_sports = st.multiselect("Filter by Sport", available_sports, default=available_sports)
            filtered_df = df_recs[df_recs["sport"].isin(selected_sports)]
            st.dataframe(filtered_df, use_container_width=True)
        else:
            st.info("No active recommendations currently in Supabase. Click 'Sync Live Slate' to load.")
    except Exception as e:
        st.error(f"Error loading recommendations: {e}")

# TAB 2: EXECUTION LEDGER
with tabs[1]:
    st.subheader("Wager Execution Ledger")
    with st.form("ledger_entry_form"):
        c1, c2, c3 = st.columns(3)
        with c1:
            sport = st.selectbox("Sport", ["NFL", "NHL", "EPL", "CFB", "MLB", "WNBA", "CBB"])
            pick = st.text_input("Pick / Selection", value="IND +2.5")
        with c2:
            book = st.selectbox("Sportsbook", ["DraftKings", "FanDuel", "BetMGM", "Caesars", "Circa", "Pinnacle"])
            locked_line = st.number_input("Locked Line", value=2.5, step=0.5)
        with c3:
            locked_odds = st.number_input("Locked American Odds", value=-105, step=5)
            stake = st.number_input("Staked Units", value=1.25, min_value=0.10, step=0.25)
            
        submitted = st.form_submit_button("Commit Wager to Ledger & Dispatch Alerts")
        if submitted:
            try:
                with engine.begin() as conn:
                    conn.execute(
                        sa.text("""
                            INSERT INTO bet_ledger (sport, pick, sportsbook, locked_line, locked_odds, staked_units, status)
                            VALUES (:sport, :pick, :book, :line, :odds, :stake, 'PENDING')
                        """),
                        {"sport": sport, "pick": pick, "book": book, "line": locked_line, "odds": locked_odds, "stake": stake}
                    )
                st.success(f"Wager locked: {sport} | {pick} ({locked_odds:+d}) for {stake:.2f}u on {book}")
                
                # Phase 6: Multi-Channel Alert Dispatch
                results = dispatch_wager_alert(sport, pick, book, locked_odds, stake)
                email_ok, email_msg = results["email"]
                tg_ok, tg_msg = results["telegram"]
                
                if email_ok:
                    st.info(f"📧 {email_msg}")
                else:
                    st.warning(f"📧 {email_msg}")
                    
                if tg_ok:
                    st.info(f"📱 {tg_msg}")
                else:
                    st.caption(f"📱 Telegram: {tg_msg}")
                    
                st.rerun()
            except Exception as ex:
                st.error(f"Commit failed: {ex}")

# TAB 3: CLV AUDIT
with tabs[2]:
    st.subheader("Closing Line Value (CLV) Audit")
    try:
        with engine.connect() as conn:
            df_ledger = pd.read_sql_query(
                sa.text("""
                    SELECT 
                        id::text AS id, 
                        sport, 
                        pick, 
                        sportsbook, 
                        locked_line, 
                        locked_odds, 
                        staked_units, 
                        closing_line, 
                        clv, 
                        status, 
                        created_at 
                    FROM bet_ledger 
                    ORDER BY created_at DESC
                """),
                conn
            )
        
        if not df_ledger.empty:
            m1, m2, m3 = st.columns(3)
            m1.metric("Total Active Exposure", f"{df_ledger['staked_units'].sum():.2f}u")
            m2.metric("Total Wagers Logged", len(df_ledger))
            m3.metric("Avg CLV %", f"{df_ledger['clv'].mean():.2f}%" if df_ledger['clv'].notnull().any() else "Pending Game Close")
            
            st.dataframe(df_ledger, use_container_width=True)
            
            st.markdown("---")
            st.subheader("Update Closing Line & Settle CLV")
            with st.form("clv_update_form"):
                sc1, sc2, sc3 = st.columns(3)
                with sc1:
                    ticket_id = st.selectbox("Select Ticket ID", df_ledger["id"].tolist())
                with sc2:
                    closing_line = st.number_input("Closing Line / Number", value=0.0, step=0.5)
                    closing_odds = st.number_input("Closing American Odds", value=-110, step=5)
                with sc3:
                    new_status = st.selectbox("Grade Status", ["PENDING", "WON", "LOST", "PUSH"])
                    
                update_btn = st.form_submit_button("Settle & Calculate CLV")
                if update_btn:
                    row = df_ledger[df_ledger["id"] == ticket_id].iloc[0]
                    locked_o = float(row["locked_odds"])
                    
                    def to_implied(o):
                        return 100 / (o + 100) if o > 0 else abs(o) / (abs(o) + 100)
                    
                    p_locked = to_implied(locked_o)
                    p_closing = to_implied(closing_odds)
                    clv_val = round(((p_closing / p_locked) - 1.0) * 100.0, 2)
                    
                    with engine.begin() as conn:
                        conn.execute(
                            sa.text("""
                                UPDATE bet_ledger 
                                SET closing_line = :cl, clv = :clv, status = :st 
                                WHERE id::text = :id
                            """),
                            {"cl": closing_line, "clv": clv_val, "st": new_status, "id": ticket_id}
                        )
                    st.success(f"Ticket {ticket_id[:8]} updated! CLV: {clv_val:+0.2f}% | Status: {new_status}")
                    st.rerun()
        else:
            st.info("No wager records committed to Supabase yet.")
    except Exception as e:
        st.error(f"Error loading ledger: {e}")
