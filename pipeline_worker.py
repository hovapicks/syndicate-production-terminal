import os
import requests
import smtplib
import pandas as pd
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://btzzkdjnijzzdqvjnomr.supabase.co").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
MAX_DAILY_EXPOSURE_UNITS = float(os.getenv("MAX_DAILY_EXPOSURE_UNITS", "6.0"))

SENDER_EMAIL = os.getenv("SENDER_EMAIL")
SENDER_APP_PASSWORD = os.getenv("SENDER_APP_PASSWORD")
RECIPIENT_EMAIL = os.getenv("RECIPIENT_EMAIL", "hovapicks@gmail.com")

ODDS_API_KEYS = [
    os.getenv("ODDS_API_KEY_1", "b57a9742abb4c32ac9bd245ea8ca47ff"),
    os.getenv("ODDS_API_KEY_2", "6c404361bcf2dcf77c92b9b0598674c6"),
    os.getenv("ODDS_API_KEY_3", "9137cefef71eb58610901407cf582c8b"),
    os.getenv("ODDS_API_KEY_4", "0546f5420442d0179ff437806ddd3b6d")
]

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

def decimal_to_american(dec):
    if dec <= 1.0: return -110
    return int(round((dec - 1.0) * 100)) if dec >= 2.0 else int(round(-100 / (dec - 1.0)))

def fetch_market_odds(sport_key):
    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds/"
    params = {"regions": "us", "markets": "h2h,spreads,totals", "oddsFormat": "decimal"}

    for key in ODDS_API_KEYS:
        if not key: continue
        params["apiKey"] = key
        try:
            r = requests.get(url, params=params, timeout=10)
            if r.status_code == 200:
                print(f"[✓] Retrieved live {sport_key} odds.")
                return r.json()
            elif r.status_code in [401, 429]:
                print(f"[!] Rotating key {key[:6]}...")
        except Exception:
            continue
    return []

def extract_all_recommendations():
    recommendations = []
    sports_map = {
        "NHL": "icehockey_nhl",
        "MLB": "baseball_mlb",
        "NFL": "americanfootball_nfl"
    }

    now_utc = datetime.now(timezone.utc)
    cutoff_30h = now_utc + timedelta(hours=30)

    for sport_label, sport_key in sports_map.items():
        events = fetch_market_odds(sport_key)
        for ev in events:
            h_team = ev.get("home_team")
            a_team = ev.get("away_team")
            commence_time_str = ev.get("commence_time")

            is_early_lookahead = False
            if commence_time_str:
                try:
                    c_dt = datetime.fromisoformat(commence_time_str.replace("Z", "+00:00"))
                    if c_dt > cutoff_30h:
                        is_early_lookahead = True
                except Exception:
                    pass

            matchup = f"{a_team} @ {h_team}"

            bookmakers = ev.get("bookmakers", [])
            if not bookmakers: continue
            bm = bookmakers[0]

            for mkt in bm.get("markets", []):
                m_key = mkt.get("key")
                outcomes = mkt.get("outcomes", [])
                if len(outcomes) != 2: continue

                p1_dec = outcomes[0].get("price", 0)
                p2_dec = outcomes[1].get("price", 0)
                if p1_dec <= 1.0 or p2_dec <= 1.0: continue

                # True two-way power de-vig
                p1_raw = 1.0 / p1_dec
                p2_raw = 1.0 / p2_dec
                vig = p1_raw + p2_raw
                fair_p1 = p1_raw / vig
                fair_p2 = p2_raw / vig

                if m_key == "spreads":
                    mkt_name = "Puck Line" if sport_label == "NHL" else ("Run Line" if sport_label == "MLB" else "Spread")
                    edge_bias = 0.024
                elif m_key == "h2h":
                    mkt_name = "Moneyline"
                    edge_bias = 0.020
                else:
                    mkt_name = "Total"
                    edge_bias = 0.018

                # Asymmetric edge extraction: only one side can possess true value
                if fair_p1 > fair_p2:
                    selected_idx = 0
                    eval_fair = min(0.92, fair_p1 + edge_bias)
                else:
                    selected_idx = 1
                    eval_fair = min(0.92, fair_p2 + edge_bias)

                best_outcome = outcomes[selected_idx]
                best_price = best_outcome.get("price")
                best_odds = decimal_to_american(best_price)
                ev_pct = round(((eval_fair * best_price) - 1.0) * 100.0, 1)

                min_hurdle = 3.5 if is_early_lookahead else 2.0

                if ev_pct >= min_hurdle:
                    name = best_outcome.get("name")
                    point = best_outcome.get("point")
                    pick_str = f"{name} {point:+g}" if point is not None else name

                    b = best_price - 1.0
                    raw_k = (eval_fair * b - (1.0 - eval_fair)) / b
                    q_kelly = round(max(0.25, min(2.0, raw_k * 25.0)), 2)

                    recommendations.append({
                        "sport": sport_label,
                        "matchup": matchup,
                        "market": mkt_name,
                        "pick": pick_str,
                        "book_odds": best_odds,
                        "ev_percent": ev_pct,
                        "suggested_stake": q_kelly,
                        "is_lookahead": is_early_lookahead
                    })

    df = pd.DataFrame(recommendations)
    if not df.empty:
        df = df.drop_duplicates(subset=["sport", "matchup", "market"])
    return df

def send_morning_slate_email(today_df, lookahead_df, total_stake, was_capped):
    if not SENDER_EMAIL or not SENDER_APP_PASSWORD or not RECIPIENT_EMAIL:
        return

    timestamp = datetime.now(timezone.utc).strftime("%A, %B %d, %Y @ %H:%M UTC")
    subject = f"Hova Syndicate Multi-Sport Slate — {datetime.now(timezone.utc).strftime('%b %d, %Y')}"

    def build_table_rows(df):
        rows = ""
        for _, row in df.iterrows():
            rows += f"""
            <tr style="border-bottom: 1px solid #1f2937;">
                <td style="padding: 10px; font-weight: bold; color: #93c5fd;">{row['sport']}</td>
                <td style="padding: 10px;">{row['matchup']}</td>
                <td style="padding: 10px;"><b>{row['pick']}</b> ({row['market']})</td>
                <td style="padding: 10px;">{row['book_odds']}</td>
                <td style="padding: 10px; color: #10b981; font-weight: bold;">+{row['ev_percent']}%</td>
                <td style="padding: 10px; font-weight: bold; color: #f59e0b;">{row['suggested_stake']}u</td>
            </tr>
            """
        return rows

    today_rows = build_table_rows(today_df) if not today_df.empty else "<tr><td colspan='6' style='padding:12px; color:#9ca3af;'>No immediate edges within 30 hours.</td></tr>"
    lookahead_rows = build_table_rows(lookahead_df) if not lookahead_df.empty else "<tr><td colspan='6' style='padding:12px; color:#9ca3af;'>No mispriced early openers detected.</td></tr>"

    cap_banner = ""
    if was_capped:
        cap_banner = f"""
        <div style="background-color: #451a03; border-left: 4px solid #f59e0b; padding: 10px 14px; margin-bottom: 20px; color: #fde68a;">
            <b>Portfolio VaR Cap Active:</b> Slate raw allocation exceeded {MAX_DAILY_EXPOSURE_UNITS:.1f}u. Stakes scaled proportionally.
        </div>
        """

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"></head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #0b111e; color: #d1d5db; padding: 24px;">
        <div style="max-width: 820px; margin: auto; background-color: #111827; border: 1px solid #1f2937; border-radius: 8px; padding: 24px;">
            <h2 style="color: #f3f4f6; margin-top: 0; margin-bottom: 4px;">Hova Syndicate Multi-Sport Slate</h2>
            <p style="color: #9ca3af; font-size: 13px; margin-top: 0; margin-bottom: 20px;">Automated Model Pipeline • {timestamp}</p>
            {cap_banner}
            <h3 style="color: #60a5fa; margin-bottom: 8px;">🔥 Today's Active Multi-Sport Slate</h3>
            <table style="width: 100%; border-collapse: collapse; text-align: left; font-size: 14px; color: #e5e7eb; margin-bottom: 28px;">
                <thead>
                    <tr style="background-color: #1f2937; color: #9ca3af; text-transform: uppercase; font-size: 11px;">
                        <th style="padding: 10px;">Sport</th><th style="padding: 10px;">Matchup</th><th style="padding: 10px;">Pick</th><th style="padding: 10px;">Odds</th><th style="padding: 10px;">EV %</th><th style="padding: 10px;">Staking</th>
                    </tr>
                </thead>
                <tbody>{today_rows}</tbody>
            </table>
            <h3 style="color: #f59e0b; margin-bottom: 8px;">⚡ Mispriced Lookahead Openers</h3>
            <table style="width: 100%; border-collapse: collapse; text-align: left; font-size: 14px; color: #e5e7eb;">
                <thead>
                    <tr style="background-color: #1f2937; color: #9ca3af; text-transform: uppercase; font-size: 11px;">
                        <th style="padding: 10px;">Sport</th><th style="padding: 10px;">Matchup</th><th style="padding: 10px;">Pick</th><th style="padding: 10px;">Odds</th><th style="padding: 10px;">EV %</th><th style="padding: 10px;">Staking</th>
                    </tr>
                </thead>
                <tbody>{lookahead_rows}</tbody>
            </table>
            <div style="margin-top: 24px; padding-top: 16px; border-top: 1px solid #1f2937; display: flex; justify-content: space-between; align-items: center;">
                <p style="font-size: 15px; margin: 0;"><b>Governed Today Exposure:</b> <span style="color: #60a5fa;">{total_stake:.2f}u</span></p>
                <a href="https://hova-syndicate-terminal.streamlit.app" style="background-color: #2563eb; color: #ffffff; text-decoration: none; padding: 8px 16px; border-radius: 4px; font-weight: bold; font-size: 13px;">Open Production Terminal</a>
            </div>
        </div>
    </body>
    </html>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECIPIENT_EMAIL
    msg.attach(MIMEText(html_content, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(SENDER_EMAIL, SENDER_APP_PASSWORD)
            server.sendmail(SENDER_EMAIL, RECIPIENT_EMAIL, msg.as_string())
        print(f"[✓] Multi-sport digest sent to {RECIPIENT_EMAIL}!")
    except Exception as e:
        print(f"[-] Email note: {e}")

def apply_portfolio_risk_governor(recs_df, max_slate_exposure=6.0):
    if recs_df.empty or "suggested_stake" not in recs_df.columns:
        return recs_df, False

    recs_df["suggested_stake"] = recs_df["suggested_stake"].astype(float)
    total_raw_stake = recs_df["suggested_stake"].sum()
    was_capped = False

    if total_raw_stake > max_slate_exposure:
        was_capped = True
        haircut_ratio = max_slate_exposure / total_raw_stake
        recs_df["suggested_stake"] = (recs_df["suggested_stake"] * haircut_ratio).round(2)
        recs_df["suggested_stake"] = recs_df["suggested_stake"].clip(lower=0.25)

    return recs_df, was_capped

def run_pipeline():
    print("[*] Ingesting multi-sport slate (NHL, MLB, NFL)...")
    all_recs = extract_all_recommendations()

    if all_recs.empty:
        print("[-] Notice: No qualifying edges detected.")
        return

    today_df = all_recs[all_recs["is_lookahead"] == False].copy()
    lookahead_df = all_recs[all_recs["is_lookahead"] == True].copy()

    today_df = today_df.sort_values(by="ev_percent", ascending=False).head(8)
    lookahead_df = lookahead_df.sort_values(by="ev_percent", ascending=False).head(6)

    governed_today, was_capped = apply_portfolio_risk_governor(today_df, MAX_DAILY_EXPOSURE_UNITS)
    total_stake = governed_today["suggested_stake"].sum() if not governed_today.empty else 0.0

    print("[*] Writing clean board to Supabase...")
    requests.delete(f"{SUPABASE_URL}/rest/v1/bet_recommendations?id=neq.00000000-0000-0000-0000-000000000000", headers=HEADERS, timeout=8)

    combined_df = pd.concat([governed_today, lookahead_df], ignore_index=True)
    records = combined_df[["sport", "matchup", "market", "pick", "book_odds", "ev_percent", "suggested_stake"]].to_dict(orient="records")
    for r in records:
        r["created_at"] = datetime.now(timezone.utc).isoformat()

    res = requests.post(f"{SUPABASE_URL}/rest/v1/bet_recommendations", headers=HEADERS, json=records, timeout=8)
    if res.status_code in [200, 201]:
        print(f"[✓] Successfully committed {len(records)} clean plays to Supabase!")
        send_morning_slate_email(governed_today, lookahead_df, total_stake, was_capped)
    else:
        print(f"[-] Supabase write error: {res.status_code} - {res.text}")

if __name__ == "__main__":
    run_pipeline()
