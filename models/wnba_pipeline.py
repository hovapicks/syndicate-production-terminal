import os
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from scipy.stats import norm

ODDS_API_KEYS = [
    os.getenv("ODDS_API_KEY_1", "b57a9742abb4c32ac9bd245ea8ca47ff"),
    os.getenv("ODDS_API_KEY_2", "6c404361bcf2dcf77c92b9b0598674c6"),
    os.getenv("ODDS_API_KEY_3", "9137cefef71eb58610901407cf582c8b"),
    os.getenv("ODDS_API_KEY_4", "0546f5420442d0179ff437806ddd3b6d")
]

TEAM_NAME_MAP = {
    'Las Vegas Aces': 'Las Vegas Aces',
    'New York Liberty': 'New York Liberty',
    'Connecticut Sun': 'Connecticut Sun',
    'Indiana Fever': 'Indiana Fever',
    'Minnesota Lynx': 'Minnesota Lynx',
    'Seattle Storm': 'Seattle Storm',
    'Phoenix Mercury': 'Phoenix Mercury',
    'Chicago Sky': 'Chicago Sky',
    'Atlanta Dream': 'Atlanta Dream',
    'Washington Mystics': 'Washington Mystics',
    'Dallas Wings': 'Dallas Wings',
    'Los Angeles Sparks': 'Los Angeles Sparks',
    'Golden State Valkyries': 'Golden State Valkyries'
}

def load_calibrated_ratings():
    seasons = [2024, 2025, 2026]
    dfs = []
    for yr in seasons:
        urls = [
            f"https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_wnba_schedules/wnba_schedule_{yr}.parquet",
            f"https://raw.githubusercontent.com/sportsdataverse/sportsdataverse-data/main/wnba/schedules/parquet/wnba_schedule_{yr}.parquet",
            f"https://github.com/sportsdataverse/wehoop-wnba-data/releases/download/wnba_schedule/wnba_schedule_{yr}.parquet",
            f"https://raw.githubusercontent.com/sportsdataverse/wehoop-wnba-data/main/wnba_schedule_{yr}.parquet"
        ]
        for url in urls:
            try:
                df_season = pd.read_parquet(url)
                if not df_season.empty:
                    dfs.append(df_season)
                    break
            except Exception:
                continue

    if not dfs:
        for fallback_yr in [2023, 2024]:
            try:
                df_fb = pd.read_parquet(f"https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_wnba_schedules/wnba_schedule_{fallback_yr}.parquet")
                dfs.append(df_fb)
            except Exception:
                pass

    if not dfs:
        return {}, {}, 80.8, 164.0, set()

    raw_df = pd.concat(dfs, ignore_index=True)
    status_col = 'status_type_completed' if 'status_type_completed' in raw_df.columns else 'completed'
    clean_mask = (
        (raw_df[status_col] == True) &
        (raw_df['home_score'].notnull()) &
        (raw_df['away_score'].notnull()) &
        (raw_df['home_score'] > 0)
    ) if status_col in raw_df.columns else (
        (raw_df['home_score'].notnull()) &
        (raw_df['away_score'].notnull()) &
        (raw_df['home_score'] > 0)
    )

    clean_games = raw_df[clean_mask].copy()
    clean_games['game_date'] = pd.to_datetime(clean_games['game_date'])
    clean_games = clean_games.sort_values('game_date').reset_index(drop=True)

    h_col = 'home_display_name' if 'home_display_name' in clean_games.columns else 'home_name'
    if h_col not in clean_games.columns: h_col = 'home_team'
    a_col = 'away_display_name' if 'away_display_name' in clean_games.columns else 'away_team'
    if a_col not in clean_games.columns: a_col = 'away_team'

    clean_games = clean_games.rename(columns={h_col: 'home_team', a_col: 'away_team'})
    clean_games['home_score'] = clean_games['home_score'].astype(float)
    clean_games['away_score'] = clean_games['away_score'].astype(float)

    league_avg_total = (clean_games['home_score'].mean() + clean_games['away_score'].mean())
    league_pace = 80.8
    hca_points = 2.1

    all_teams = sorted(list(set(clean_games['home_team'].unique()) | set(clean_games['away_team'].unique())))
    team_stats = {t: {'games': 0, 'pts_for': 0.0, 'pts_against': 0.0, 'pace_accum': 0.0} for t in all_teams}
    max_date = clean_games['game_date'].max()
    half_life = 30.0

    for _, row in clean_games.iterrows():
        h = row['home_team']
        a = row['away_team']
        hp = row['home_score']
        ap = row['away_score']

        days = (max_date - row['game_date']).days
        w = np.exp(-(np.log(2) / half_life) * max(0, days))
        poss = (hp + ap) / 2.02

        if h in team_stats:
            team_stats[h]['games'] += w
            team_stats[h]['pts_for'] += (hp - (hca_points / 2.0)) * w
            team_stats[h]['pts_against'] += (ap + (hca_points / 2.0)) * w
            team_stats[h]['pace_accum'] += poss * w

        if a in team_stats:
            team_stats[a]['games'] += w
            team_stats[a]['pts_for'] += (ap + (hca_points / 2.0)) * w
            team_stats[a]['pts_against'] += (hp - (hca_points / 2.0)) * w
            team_stats[a]['pace_accum'] += poss * w

    team_net_rating = {}
    team_pace_rating = {}

    for t, s in team_stats.items():
        if s['games'] > 0:
            off_edge = (s['pts_for'] / s['games']) - (league_avg_total / 2.0)
            def_edge = (league_avg_total / 2.0) - (s['pts_against'] / s['games'])
            shrinkage = s['games'] / (s['games'] + 10.0)
            net_pts = (off_edge + def_edge) * shrinkage
            team_net_rating[t] = float(np.clip(net_pts, -8.5, 8.5))
            team_pace_rating[t] = float((s['pace_accum'] / s['games']) * shrinkage + league_pace * (1 - shrinkage))
        else:
            team_net_rating[t] = 0.0
            team_pace_rating[t] = league_pace

    yesterday = (pd.Timestamp.now() - pd.Timedelta(days=1)).strftime('%Y-%m-%d')
    recent_mask = clean_games['game_date'].dt.strftime('%Y-%m-%d') == yesterday
    recent_teams = set(clean_games[recent_mask]['home_team']) | set(clean_games[recent_mask]['away_team'])

    return team_net_rating, team_pace_rating, league_pace, league_avg_total, recent_teams

def fetch_live_wnba_slate(api_keys, recent_teams):
    url = "https://api.the-odds-api.com/v4/sports/basketball_wnba/odds/"
    now_utc = datetime.now(timezone.utc)
    events = None

    for key in api_keys:
        if not key: continue
        params = {'apiKey': key, 'regions': 'us', 'markets': 'h2h,spreads,totals', 'oddsFormat': 'american'}
        try:
            res = requests.get(url, params=params, timeout=10)
            if res.status_code == 200:
                events = res.json()
                if events: break
        except Exception:
            continue

    if not events:
        return []

    slate = []
    for ev in events:
        commence_str = ev.get('commence_time')
        if commence_str:
            commence_dt = datetime.fromisoformat(commence_str.replace("Z", "+00:00"))
            if commence_dt <= now_utc:
                continue

        raw_home = ev.get('home_team')
        raw_away = ev.get('away_team')
        home_team = TEAM_NAME_MAP.get(raw_home, raw_home)
        away_team = TEAM_NAME_MAP.get(raw_away, raw_away)

        bookmakers = {b['key']: b for b in ev.get('bookmakers', [])}
        book = bookmakers.get('draftkings') or (ev['bookmakers'][0] if ev.get('bookmakers') else None)
        if not book: continue

        mkt_ml_home, mkt_ml_away = 0, 0
        mkt_spread_home = 0.0
        mkt_total = 0.0

        for market in book.get('markets', []):
            if market['key'] == 'h2h':
                for o in market['outcomes']:
                    if o['name'] == raw_home: mkt_ml_home = o['price']
                    else: mkt_ml_away = o['price']
            elif market['key'] == 'spreads':
                for o in market['outcomes']:
                    if o['name'] == raw_home: mkt_spread_home = o['point']
            elif market['key'] == 'totals':
                if market['outcomes']:
                    mkt_total = market['outcomes'][0]['point']

        slate.append({
            'home_team': home_team,
            'away_team': away_team,
            'home_b2b': home_team in recent_teams,
            'away_b2b': away_team in recent_teams,
            'mkt_ml_home': mkt_ml_home,
            'mkt_ml_away': mkt_ml_away,
            'mkt_spread_home': mkt_spread_home,
            'mkt_total': mkt_total
        })
    return slate

def american_to_prob(ml):
    if ml == 0: return 0.5
    return abs(ml) / (abs(ml) + 100.0) if ml < 0 else 100.0 / (ml + 100.0)

def prob_to_american(p):
    p = max(0.01, min(0.99, p))
    if p >= 0.5:
        return -int(round(100.0 * p / (1.0 - p)))
    return int(round(100.0 * (1.0 - p) / p))

def generate_wnba_recommendations(kelly_fraction=0.50, kelly_cap=0.03):
    team_net_rating, team_pace_rating, league_pace, league_avg_total, recent_teams = load_calibrated_ratings()
    slate_games = fetch_live_wnba_slate(ODDS_API_KEYS, recent_teams)

    hca_points = 2.1
    std_dev_spread = 10.8
    std_dev_total = 11.2

    recs = []

    for game in slate_games:
        home = game['home_team']
        away = game['away_team']
        is_b2b_away = game.get('away_b2b', False)
        is_b2b_home = game.get('home_b2b', False)

        h_net = team_net_rating.get(home, 0.0)
        a_net = team_net_rating.get(away, 0.0)

        hca = hca_points
        if is_b2b_home: hca -= 1.5
        if is_b2b_away: hca += 1.5

        proj_margin = round((h_net - a_net) + hca, 1)
        pace_h = team_pace_rating.get(home, league_pace)
        pace_a = team_pace_rating.get(away, league_pace)
        pace_adj = ((pace_h + pace_a) / 2.0) - league_pace
        proj_total = round((league_avg_total + (pace_adj * 1.02) + (h_net + a_net) * 0.4) * 2) / 2

        # 1. Moneyline Evaluation
        win_prob_home = norm.cdf(proj_margin / std_dev_spread)
        win_prob_away = 1.0 - win_prob_home
        mkt_ml_home = game['mkt_ml_home']
        mkt_ml_away = game['mkt_ml_away']

        implied_p_home = american_to_prob(mkt_ml_home)
        implied_p_away = american_to_prob(mkt_ml_away)

        ev_home_ml = (win_prob_home - implied_p_home) / implied_p_home if mkt_ml_home != 0 else 0
        ev_away_ml = (win_prob_away - implied_p_away) / implied_p_away if mkt_ml_away != 0 else 0

        if ev_home_ml >= 0.035 and mkt_ml_home != 0:
            recs.append({
                "sport": "WNBA",
                "matchup": f"{away} @ {home}",
                "market": "Moneyline",
                "pick": f"{home} ML",
                "fair_odds": prob_to_american(win_prob_home),
                "book_odds": mkt_ml_home,
                "ev_percent": round(ev_home_ml * 100.0, 1),
                "suggested_stake": 2.50,
                "status": "ACTIVE"
            })
        elif ev_away_ml >= 0.035 and mkt_ml_away != 0:
            recs.append({
                "sport": "WNBA",
                "matchup": f"{away} @ {home}",
                "market": "Moneyline",
                "pick": f"{away} ML",
                "fair_odds": prob_to_american(win_prob_away),
                "book_odds": mkt_ml_away,
                "ev_percent": round(ev_away_ml * 100.0, 1),
                "suggested_stake": 2.50,
                "status": "ACTIVE"
            })

        # 2. Spread Evaluation
        mkt_h_spread = game['mkt_spread_home']
        spread_diff = proj_margin - (-mkt_h_spread)

        if abs(spread_diff) >= 1.5:
            pick_home = spread_diff > 0
            spread_pick_team = home if pick_home else away
            spread_line = mkt_h_spread if pick_home else -mkt_h_spread

            p_cover = norm.cdf(abs(spread_diff) / std_dev_spread)
            b = 1.0 / 1.10
            q = 1.0 - p_cover
            f_star = max(0.0, (b * p_cover - q) / b)
            stake_pct = min(f_star * kelly_fraction, kelly_cap)
            spread_ev = (p_cover * 1.909) - 1.0
            stake_units = round(stake_pct / 0.010, 2)

            recs.append({
                "sport": "WNBA",
                "matchup": f"{away} @ {home}",
                "market": "Spread",
                "pick": f"{spread_pick_team} {spread_line:+}",
                "fair_odds": prob_to_american(p_cover),
                "book_odds": -110,
                "ev_percent": round(spread_ev * 100.0, 1),
                "suggested_stake": max(0.5, stake_units),
                "status": "ACTIVE"
            })

        # 3. Totals Evaluation
        mkt_tot = game['mkt_total']
        tot_diff = proj_total - mkt_tot

        if abs(tot_diff) >= 2.5 and mkt_tot > 0:
            direction = "OVER" if tot_diff > 0 else "UNDER"
            p_tot = norm.cdf(abs(tot_diff) / std_dev_total)
            tot_ev = (p_tot * 1.909) - 1.0
            tot_b = 1.0 / 1.10
            tot_q = 1.0 - p_tot
            tot_stake = min(max(0.0, (tot_b * p_tot - tot_q) / tot_b) * kelly_fraction, kelly_cap)
            tot_units = round(tot_stake / 0.010, 2)

            recs.append({
                "sport": "WNBA",
                "matchup": f"{away} @ {home}",
                "market": "Total",
                "pick": f"{direction} {mkt_tot}",
                "fair_odds": prob_to_american(p_tot),
                "book_odds": -110,
                "ev_percent": round(tot_ev * 100.0, 1),
                "suggested_stake": max(0.5, tot_units),
                "status": "ACTIVE"
            })

    return recs
