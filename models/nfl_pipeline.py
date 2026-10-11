import os
import requests
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from scipy.stats import norm
from tabulate import tabulate

ODDS_API_KEYS = [
    os.getenv("ODDS_API_KEY_1", "b57a9742abb4c32ac9bd245ea8ca47ff"),
    os.getenv("ODDS_API_KEY_2", "6c404361bcf2dcf77c92b9b0598674c6"),
    os.getenv("ODDS_API_KEY_3", "0546f5420442d0179ff437806ddd3b6d"),
    os.getenv("ODDS_API_KEY_4", "9137cefef71eb58610901407cf582c8b")
]

TOTAL_BANKROLL = 10000.0
UNIT_PERCENT = 0.010
KELLY_FRACTION = 0.25
STANDARD_JUICE_PAYOUT = 100.0 / 110.0

BASE_HFA = 1.8
LEAGUE_AVG_TOTAL = 44.5
SPREAD_STD_DEV = 13.5
TOTALS_STD_DEV = 13.8

OFF_WEIGHT = 0.62
DEF_WEIGHT = 0.38
POWER_SCALE = 36.0

PRIMARY_SPREAD_KEYS = [3, 7]
PRIMARY_TOTAL_KEYS = [41, 44, 47, 51, 37, 40, 43]
FILTERED_LEAGUE_PACE = 43.5

INJURY_STATUS = {
    'KC':  {'starter_out': False, 'dropoff': 5.5, 'pos': 'QB'},
    'BAL': {'starter_out': False, 'dropoff': 4.5, 'pos': 'QB'},
    'BUF': {'starter_out': False, 'dropoff': 5.0, 'pos': 'QB'},
    'CIN': {'starter_out': False, 'dropoff': 4.0, 'pos': 'QB'},
    'PHI': {'starter_out': False, 'dropoff': 3.5, 'pos': 'QB'},
    'HOU': {'starter_out': False, 'dropoff': 3.5, 'pos': 'QB'},
    'DET': {'starter_out': False, 'dropoff': 3.0, 'pos': 'QB'},
    'GB':  {'starter_out': False, 'dropoff': 3.5, 'pos': 'QB'},
    'DAL': {'starter_out': False, 'dropoff': 3.5, 'pos': 'QB'},
    'CHI': {'starter_out': False, 'dropoff': 2.0, 'pos': 'QB'},
    'MIA': {'starter_out': False, 'dropoff': 3.5, 'pos': 'QB'},
    'LAC': {'starter_out': False, 'dropoff': 4.0, 'pos': 'QB'},
    'SF':  {'starter_out': False, 'dropoff': 3.0, 'pos': 'QB'},
    'MIN': {'starter_out': False, 'dropoff': 2.0, 'pos': 'QB'},
    'NYJ': {'starter_out': False, 'dropoff': 3.0, 'pos': 'QB'},
    'LAR': {'starter_out': False, 'dropoff': 3.5, 'pos': 'QB'},
    'TB':  {'starter_out': False, 'dropoff': 2.5, 'pos': 'QB'},
    'IND': {'starter_out': False, 'dropoff': 2.0, 'pos': 'QB'},
    'WAS': {'starter_out': False, 'dropoff': 2.5, 'pos': 'QB'},
    'PIT': {'starter_out': False, 'dropoff': 1.5, 'pos': 'QB'},
    'JAX': {'starter_out': False, 'dropoff': 2.5, 'pos': 'QB'},
    'SEA': {'starter_out': False, 'dropoff': 2.0, 'pos': 'QB'},
    'ARI': {'starter_out': False, 'dropoff': 2.5, 'pos': 'QB'},
    'NO':  {'starter_out': False, 'dropoff': 1.5, 'pos': 'QB'},
    'ATL': {'starter_out': False, 'dropoff': 2.0, 'pos': 'QB'},
    'NYG': {'starter_out': False, 'dropoff': 1.5, 'pos': 'QB'},
    'CLE': {'starter_out': False, 'dropoff': 1.5, 'pos': 'QB'},
    'DEN': {'starter_out': False, 'dropoff': 1.5, 'pos': 'QB'},
    'LV':  {'starter_out': False, 'dropoff': 1.5, 'pos': 'QB'},
    'TEN': {'starter_out': False, 'dropoff': 1.5, 'pos': 'QB'},
    'NE':  {'starter_out': False, 'dropoff': 1.5, 'pos': 'QB'},
    'CAR': {'starter_out': False, 'dropoff': 1.5, 'pos': 'QB'}
}

WEST_TEAMS = {'SEA', 'SF', 'LAR', 'LAC', 'ARI', 'LV'}
EAST_TIMEZONE_TEAMS = {'MIA', 'TB', 'JAX', 'ATL', 'CAR', 'WAS', 'BAL', 'PHI', 'NYG', 'NYJ', 'NE', 'BUF', 'PIT', 'CLE', 'CIN', 'DET', 'IND'}
INTERNATIONAL_GAMES = set()

STADIUM_COORDS = {
    'ARI': {'lat': 33.5276, 'lon': -112.2626, 'dome': True},
    'ATL': {'lat': 33.7554, 'lon': -84.4010,  'dome': True},
    'BAL': {'lat': 39.2780, 'lon': -76.6227,  'dome': False},
    'BUF': {'lat': 42.7738, 'lon': -78.7870,  'dome': False},
    'CAR': {'lat': 35.2258, 'lon': -80.8528,  'dome': False},
    'CHI': {'lat': 41.8623, 'lon': -87.6167,  'dome': False},
    'CIN': {'lat': 39.0955, 'lon': -84.5161,  'dome': False},
    'CLE': {'lat': 41.5061, 'lon': -81.6995,  'dome': False},
    'DAL': {'lat': 32.7473, 'lon': -97.0945,  'dome': True},
    'DEN': {'lat': 39.7439, 'lon': -105.0201, 'dome': False},
    'DET': {'lat': 42.3400, 'lon': -83.0456,  'dome': True},
    'GB':  {'lat': 44.5013, 'lon': -88.0622,  'dome': False},
    'HOU': {'lat': 29.6847, 'lon': -95.4107,  'dome': True},
    'IND': {'lat': 39.7601, 'lon': -86.1639,  'dome': True},
    'JAX': {'lat': 30.3239, 'lon': -81.6373,  'dome': False},
    'KC':  {'lat': 39.0489, 'lon': -94.4839,  'dome': False},
    'LV':  {'lat': 36.0909, 'lon': -115.1833, 'dome': True},
    'LAC': {'lat': 33.9535, 'lon': -118.3390, 'dome': True},
    'LAR': {'lat': 33.9535, 'lon': -118.3390, 'dome': True},
    'MIA': {'lat': 25.9580, 'lon': -80.2389,  'dome': False},
    'MIN': {'lat': 44.9735, 'lon': -93.2575,  'dome': True},
    'NE':  {'lat': 42.0909, 'lon': -71.2643,  'dome': False},
    'NO':  {'lat': 29.9511, 'lon': -90.0812,  'dome': True},
    'NYG': {'lat': 40.8128, 'lon': -74.0742,  'dome': False},
    'NYJ': {'lat': 40.8128, 'lon': -74.0742,  'dome': False},
    'PHI': {'lat': 39.9008, 'lon': -75.1675,  'dome': False},
    'PIT': {'lat': 40.4468, 'lon': -80.0158,  'dome': False},
    'SF':  {'lat': 37.4032, 'lon': -121.9698, 'dome': False},
    'SEA': {'lat': 47.5952, 'lon': -122.3316, 'dome': False},
    'TB':  {'lat': 27.9759, 'lon': -82.5033,  'dome': False},
    'TEN': {'lat': 36.1665, 'lon': -86.7713,  'dome': False},
    'WAS': {'lat': 38.9076, 'lon': -76.8645,  'dome': False}
}

NFL_MAP = {
    "Arizona Cardinals": "ARI", "Atlanta Falcons": "ATL", "Baltimore Ravens": "BAL",
    "Buffalo Bills": "BUF", "Carolina Panthers": "CAR", "Chicago Bears": "CHI",
    "Cincinnati Bengals": "CIN", "Cleveland Browns": "CLE", "Dallas Cowboys": "DAL",
    "Denver Broncos": "DEN", "Detroit Lions": "DET", "Green Bay Packers": "GB",
    "Houston Texans": "HOU", "Indianapolis Colts": "IND", "Jacksonville Jaguars": "JAX",
    "Kansas City Chiefs": "KC", "Las Vegas Raiders": "LV", "Los Angeles Chargers": "LAC",
    "Los Angeles Rams": "LAR", "Miami Dolphins": "MIA", "Minnesota Vikings": "MIN",
    "New England Patriots": "NE", "New Orleans Saints": "NO", "New York Giants": "NYG",
    "New York Jets": "NYJ", "Philadelphia Eagles": "PHI", "Pittsburgh Steelers": "PIT",
    "San Francisco 49ers": "SF", "Seattle Seahawks": "SEA", "Tampa Bay Buccaneers": "TB",
    "Tennessee Titans": "TEN", "Washington Commanders": "WAS"
}

NFL_MARGIN_PROBS = {
    1: 0.024, 2: 0.038, 3: 0.151, 4: 0.034, 5: 0.027,
    6: 0.058, 7: 0.091, 8: 0.025, 9: 0.015, 10: 0.060,
    11: 0.022, 12: 0.019, 13: 0.025, 14: 0.052, 15: 0.012,
    16: 0.014, 17: 0.035
}

NFL_TOTALS_PROBS = {
    33: 0.016, 34: 0.017, 35: 0.017, 36: 0.024, 37: 0.037,
    38: 0.020, 39: 0.020, 40: 0.033, 41: 0.038, 42: 0.015,
    43: 0.035, 44: 0.038, 45: 0.025, 46: 0.020, 47: 0.032,
    48: 0.028, 49: 0.020, 50: 0.023, 51: 0.038, 52: 0.021,
    53: 0.014, 54: 0.021, 55: 0.025, 56: 0.009, 57: 0.020,
    58: 0.020
}

def calculate_situational_hfa(home, away, game_dt, sched_df, base_hfa=BASE_HFA):
    if (away, home) in INTERNATIONAL_GAMES:
        return 0.0, "Neutral/International Site (0.0 HFA)"

    def get_last_game_date(team, current_dt):
        past = sched_df[
            ((sched_df['home_team'] == team) | (sched_df['away_team'] == team)) &
            (pd.to_datetime(sched_df['gameday'] + ' ' + sched_df['gametime'].fillna('13:00')) < current_dt)
        ]
        if past.empty:
            return None
        last_dt = pd.to_datetime(past['gameday'].iloc[-1] + ' ' + past['gametime'].iloc[-1])
        return (current_dt - last_dt).days

    h_rest = get_last_game_date(home, game_dt)
    a_rest = get_last_game_date(away, game_dt)

    eff_hfa = base_hfa
    notes = []

    if a_rest is not None and a_rest <= 4 and game_dt.weekday() == 3:
        eff_hfa += 1.2
        notes.append("Short Rest Road (+1.2 HFA)")

    if h_rest is not None and h_rest >= 10:
        eff_hfa += 1.0
        notes.append(f"{home} Extended Prep (+1.0)")
    if a_rest is not None and a_rest >= 10:
        eff_hfa -= 1.0
        notes.append(f"{away} Extended Prep (-1.0)")

    if away in WEST_TEAMS and home in EAST_TIMEZONE_TEAMS and game_dt.hour == 13:
        eff_hfa += 0.6
        notes.append("West-to-East 1PM Trip (+0.6 HFA)")

    desc = ", ".join(notes) if notes else "Standard Base HFA (+1.8)"
    return round(eff_hfa, 1), desc

def calculate_kelly_stake(raw_diff, is_key_crossover=False, std_dev=SPREAD_STD_DEV,
                          payout_b=STANDARD_JUICE_PAYOUT, fraction=KELLY_FRACTION, bankroll=TOTAL_BANKROLL):
    abs_diff = abs(raw_diff)
    z = abs_diff / std_dev
    base_win_prob = float(norm.cdf(z))

    if is_key_crossover and abs_diff >= 0.5:
        win_prob = max(base_win_prob, 0.535 + (abs_diff * 0.015))
    else:
        win_prob = base_win_prob

    q = 1.0 - win_prob
    full_kelly = (payout_b * win_prob - q) / payout_b

    if full_kelly <= 0:
        return 0.0, 0.0, "$0", round(win_prob, 4)

    alloc_pct = min(full_kelly * fraction, 0.035)
    dollars = round(bankroll * alloc_pct)
    units = round(alloc_pct / UNIT_PERCENT, 2)

    return units, dollars, f"{units}u (${dollars})", round(win_prob, 4)

def fetch_stadium_weather(home_team, kickoff_dt):
    stadium = STADIUM_COORDS.get(home_team)
    if not stadium or stadium['dome']:
        return {
            'is_dome': True, 'temp_f': 72, 'wind_mph': 0.0,
            'wind_penalty': 0.0, 'condition': 'Dome / Controlled'
        }

    lat, lon = stadium['lat'], stadium['lon']
    date_str = kickoff_dt.strftime('%Y-%m-%d')
    target_hour = kickoff_dt.hour

    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat}&longitude={lon}&hourly=temperature_2m,wind_speed_10m,precipitation_probability"
        f"&temperature_unit=fahrenheit&wind_speed_unit=mph&start_date={date_str}&end_date={date_str}"
    )

    try:
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            data = r.json().get('hourly', {})
            temps = data.get('temperature_2m', [])
            winds = data.get('wind_speed_10m', [])
            precips = data.get('precipitation_probability', [])

            temp = temps[target_hour] if target_hour < len(temps) else 65
            wind = winds[target_hour] if target_hour < len(winds) else 5.0
            precip = precips[target_hour] if target_hour < len(precips) else 0

            wind_penalty = round(max(0.0, (wind - 12.0) * 0.25), 1) if wind >= 14.0 else 0.0
            cond_desc = f"{temp:.0f}°F, {wind:.0f} mph wind"
            if wind >= 15.0:
                cond_desc += " ⚠️ HIGH WIND"

            return {
                'is_dome': False, 'temp_f': round(temp), 'wind_mph': round(wind, 1),
                'precip_prob': precip, 'wind_penalty': wind_penalty, 'condition': cond_desc
            }
    except Exception:
        pass

    return {
        'is_dome': False, 'temp_f': 65, 'wind_mph': 6.0,
        'wind_penalty': 0.0, 'condition': 'Outdoor / Standard'
    }

def evaluate_spread_key_numbers(model_spd, market_spd):
    raw_diff = market_spd - model_spd
    if abs(raw_diff) < 0.5:
        return "PASS", [], 0.0

    side = "HOME" if raw_diff > 0 else "AWAY"
    low = min(abs(model_spd), abs(market_spd))
    high = max(abs(model_spd), abs(market_spd))
    crossed_zero = (model_spd * market_spd < 0)

    crossed_keys = []
    prob_edge = 0.0

    for margin, prob in NFL_MARGIN_PROBS.items():
        if crossed_zero:
            if margin <= abs(model_spd) or margin <= abs(market_spd):
                prob_edge += prob
                crossed_keys.append(margin)
        else:
            if low <= margin <= high:
                prob_edge += prob
                crossed_keys.append(margin)

    primary_keys = [k for k in crossed_keys if k in PRIMARY_SPREAD_KEYS]

    if (len(primary_keys) >= 1 and abs(raw_diff) >= 0.5) or (prob_edge >= 0.095) or (abs(raw_diff) >= 2.5):
        action = f"BET {side}"
    else:
        action = "PASS"

    return action, primary_keys, round(prob_edge * 100, 1)

def evaluate_total_key_numbers(model_tot, market_tot):
    raw_diff = model_tot - market_tot
    if abs(raw_diff) < 0.5:
        return "PASS", [], 0.0

    side = "OVER" if raw_diff > 0 else "UNDER"
    low = min(model_tot, market_tot)
    high = max(model_tot, market_tot)

    crossed_keys = []
    prob_edge = 0.0

    for total_num, prob in NFL_TOTALS_PROBS.items():
        if low <= total_num <= high:
            prob_edge += prob
            crossed_keys.append(total_num)

    key_hits = [k for k in crossed_keys if k in PRIMARY_TOTAL_KEYS]

    if (len(key_hits) >= 1 and abs(raw_diff) >= 0.8) or (prob_edge >= 0.055) or (abs(raw_diff) >= 2.0):
        action = f"{side} {market_tot}"
    else:
        action = "PASS"

    return action, key_hits, round(prob_edge * 100, 1)

def calculate_spread_confidence(raw_diff, keys_crossed, edge_density):
    abs_diff = abs(raw_diff)
    clamped_density = min(edge_density, 20.0)

    if (3 in keys_crossed) and (clamped_density >= 14.0) and (abs_diff >= 2.0):
        stars = 5
    elif (3 in keys_crossed or 7 in keys_crossed) and (clamped_density >= 9.0) and (abs_diff >= 1.5):
        stars = 4
    elif (len(keys_crossed) >= 1 and clamped_density >= 6.5) or (abs_diff >= 2.5):
        stars = 3
    elif abs_diff >= 1.0 or len(keys_crossed) >= 1:
        stars = 2
    else:
        stars = 1

    star_str = "★" * stars + "☆" * (5 - stars)
    return stars, star_str

def calculate_total_confidence(raw_diff, keys_crossed, edge_density, pace_delta=0.0):
    abs_diff = abs(raw_diff)
    clamped_density = min(edge_density, 18.0)
    strong_pace_match = (raw_diff > 0 and pace_delta >= 1.0) or (raw_diff < 0 and pace_delta <= -1.0)

    if (len(keys_crossed) >= 2) and (clamped_density >= 9.0) and strong_pace_match and (abs_diff >= 2.0):
        stars = 5
    elif (len(keys_crossed) >= 1) and (clamped_density >= 6.5) and (abs_diff >= 1.2):
        stars = 4
    elif (len(keys_crossed) >= 1 and clamped_density >= 4.0) or (abs_diff >= 1.5):
        stars = 3
    elif abs_diff >= 1.0 or len(keys_crossed) >= 1:
        stars = 2
    else:
        stars = 1

    star_str = "★" * stars + "☆" * (5 - stars)
    return stars, star_str

def load_metrics(seasons=[2025, 2026], decay=0.94):
    global FILTERED_LEAGUE_PACE
    frames = []
    cols = [
        'season', 'week', 'game_id', 'play_type', 'epa',
        'quarter_seconds_remaining', 'posteam', 'defteam',
        'fumble', 'touchdown', 'yardline_100', 'field_goal_result',
        'wp', 'vegas_wp'
    ]

    for yr in seasons:
        url = f"https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{yr}.parquet"
        try:
            print(f"[*] Loading {yr} play-by-play...")
            df = pd.read_parquet(url, columns=cols)
            frames.append(df)
        except Exception:
            pass

    if not frames:
        raise RuntimeError("No play-by-play data found.")

    pbp = pd.concat(frames, ignore_index=True)

    valid = pbp[
        (pbp['play_type'].isin(['pass', 'run'])) &
        (pbp['epa'].notna()) &
        (pbp['quarter_seconds_remaining'] > 120)
    ].copy()

    wp_metric = valid['vegas_wp'].fillna(valid['wp'])
    valid = valid[(wp_metric >= 0.05) & (wp_metric <= 0.95)].copy()

    valid['adj_epa'] = valid['epa']
    valid.loc[valid['fumble'] == 1, 'adj_epa'] = -2.85

    rz_plays = (valid['yardline_100'] <= 20)
    valid.loc[rz_plays & (valid['touchdown'] == 1), 'adj_epa'] *= 0.85
    valid.loc[rz_plays & (valid['field_goal_result'] == 'made'), 'adj_epa'] += 0.84

    valid['timeline'] = (valid['season'] - min(seasons)) * 22 + valid['week']
    valid['weight'] = decay ** (valid['timeline'].max() - valid['timeline'])
    valid['w_epa'] = valid['adj_epa'] * valid['weight']

    games = valid.groupby('posteam')['game_id'].nunique()
    plays = valid.groupby('posteam')['play_type'].count()
    pace = (plays / games).rename('pace')
    FILTERED_LEAGUE_PACE = float(pace.mean())
    print(f"[*] Dynamic Filtered Pace Baseline: {FILTERED_LEAGUE_PACE:.1f} snaps/team/game")

    PASS_WEIGHT = 0.75
    RUSH_WEIGHT = 0.25

    pass_df = valid[valid['play_type'] == 'pass']
    rush_df = valid[valid['play_type'] == 'run']

    off_pass = pass_df.groupby('posteam')[['w_epa', 'weight']].sum().apply(lambda g: g['w_epa'] / g['weight'], axis=1)
    off_rush = rush_df.groupby('posteam')[['w_epa', 'weight']].sum().apply(lambda g: g['w_epa'] / g['weight'], axis=1)
    def_pass = pass_df.groupby('defteam')[['w_epa', 'weight']].sum().apply(lambda g: g['w_epa'] / g['weight'], axis=1)
    def_rush = rush_df.groupby('defteam')[['w_epa', 'weight']].sum().apply(lambda g: g['w_epa'] / g['weight'], axis=1)

    off_strength = (PASS_WEIGHT * off_pass) + (RUSH_WEIGHT * off_rush)
    def_strength = (PASS_WEIGHT * def_pass) + (RUSH_WEIGHT * def_rush)

    team_df = pd.DataFrame({
        'off_epa': off_strength,
        'def_epa': def_strength,
        'pace': pace
    })

    team_df['net_epa'] = (OFF_WEIGHT * team_df['off_epa']) - (DEF_WEIGHT * team_df['def_epa'])
    team_df['power_rating'] = (team_df['net_epa'] - team_df['net_epa'].mean()) * POWER_SCALE

    return team_df

def fetch_market_lines_rolling(api_keys=ODDS_API_KEYS):
    default_lines = {
        ("PIT", "CLE"): {'open_spd': 2.5,   'open_tot': 38.0, 'market_spread': 2.5,   'market_total': 38.5},
        ("IND", "WAS"): {'open_spd': 3.0,   'open_tot': 47.0, 'market_spread': 3.5,   'market_total': 47.0},
        ("TEN", "BAL"): {'open_spd': -11.5, 'open_tot': 43.5, 'market_spread': -11.5, 'market_total': 43.5},
        ("NE", "BUF"):  {'open_spd': -7.0,  'open_tot': 48.5, 'market_spread': -6.5,  'market_total': 48.5},
        ("NYJ", "CHI"): {'open_spd': -3.0,  'open_tot': 43.0, 'market_spread': -3.0,  'market_total': 43.0},
        ("JAX", "CIN"): {'open_spd': -2.5,  'open_tot': 51.5, 'market_spread': -2.5,  'market_total': 51.5},
        ("DAL", "HOU"): {'open_spd': -2.5,  'open_tot': 47.5, 'market_spread': -2.5,  'market_total': 48.0},
        ("ARI", "NYG"): {'open_spd': 1.0,   'open_tot': 44.5, 'market_spread': 1.5,   'market_total': 44.5},
        ("LAR", "PHI"): {'open_spd': -3.5,  'open_tot': 46.0, 'market_spread': -3.5,  'market_total': 46.0},
        ("GB", "TB"):   {'open_spd': 3.5,   'open_tot': 39.5, 'market_spread': 4.0,   'market_total': 39.5},
        ("MIA", "MIN"): {'open_spd': -9.75, 'open_tot': 39.0, 'market_spread': -11.0, 'market_total': 38.5},
        ("KC", "LV"):   {'open_spd': 4.5,   'open_tot': 47.5, 'market_spread': 4.25,  'market_total': 48.0},
        ("LAC", "SEA"): {'open_spd': -7.0,  'open_tot': 43.5, 'market_spread': -7.0,  'market_total': 42.5},
        ("DEN", "SF"):  {'open_spd': -2.75, 'open_tot': 46.25,'market_spread': -2.5,  'market_total': 48.0},
        ("DET", "CAR"): {'open_spd': 3.0,   'open_tot': 50.0, 'market_spread': 3.5,   'market_total': 50.5},
        ("ATL", "NO"):  {'open_spd': -3.0,  'open_tot': 48.5, 'market_spread': -2.5,  'market_total': 48.5}
    }

    url = "https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds"

    for idx, key in enumerate(api_keys):
        try:
            params = {"apiKey": key, "regions": "us", "markets": "spreads,totals", "oddsFormat": "american"}
            resp = requests.get(url, params=params, timeout=6)
            if resp.status_code in [401, 429, 403] or resp.status_code != 200:
                continue

            events = resp.json()
            if not events:
                continue

            market_data = {}
            for g in events:
                h = NFL_MAP.get(g.get('home_team'))
                a = NFL_MAP.get(g.get('away_team'))
                if not h or not a:
                    continue

                spreads, totals = [], []
                for b in g.get('bookmakers', []):
                    for m in b.get('markets', []):
                        if m.get('key') == 'spreads':
                            for out in m.get('outcomes', []):
                                if out['name'] == g.get('home_team'):
                                    spreads.append(out.get('point'))
                        elif m.get('key') == 'totals':
                            for out in m.get('outcomes', []):
                                if out.get('point'):
                                    totals.append(out.get('point'))

                cur_spd = float(np.median(spreads)) if spreads else None
                cur_tot = float(np.median(totals)) if totals else None
                pair_open = default_lines.get((a, h), {'open_spd': cur_spd, 'open_tot': cur_tot})

                market_data[(a, h)] = {
                    'open_spd': pair_open.get('open_spd', cur_spd),
                    'open_tot': pair_open.get('open_tot', cur_tot),
                    'market_spread': cur_spd,
                    'market_total': cur_tot
                }

            if market_data:
                return market_data

        except Exception:
            continue

    return default_lines

def get_current_nfl_week(sched_df, season=None):
    now = datetime.now(timezone.utc)
    target_season = season if season is not None else now.year

    reg_games = sched_df[
        (sched_df['season'] == int(target_season)) &
        (sched_df['game_type'].astype(str).str.upper() == 'REG')
    ].copy()

    if reg_games.empty:
        latest_season = int(sched_df['season'].max())
        reg_games = sched_df[
            (sched_df['season'] == latest_season) &
            (sched_df['game_type'].astype(str).str.upper() == 'REG')
        ].copy()
        target_season = latest_season

    reg_games['gametime'] = reg_games['gametime'].fillna('13:00')
    reg_games['kickoff_dt'] = pd.to_datetime(
        reg_games['gameday'] + ' ' + reg_games['gametime']
    ).dt.tz_localize('UTC')

    unplayed = reg_games[
        reg_games['result'].isna() | (reg_games['kickoff_dt'] >= (now - pd.Timedelta(hours=4)))
    ]

    if not unplayed.empty:
        current_week = int(unplayed['week'].min())
    else:
        current_week = int(reg_games['week'].max())

    return target_season, current_week

def generate_nfl_recommendations(season=None, week=None, bankroll=TOTAL_BANKROLL):
    """
    Executes the Colab model and returns a structured list of active syndicate recommendations.
    """
    sched_url = "https://github.com/nflverse/nflverse-data/releases/download/schedules/games.parquet"
    sched = pd.read_parquet(sched_url)

    if week is None or season is None:
        detected_season, detected_week = get_current_nfl_week(sched, season=season)
        season = season or detected_season
        week = week or detected_week

    slate = sched[
        (sched['season'] == int(season)) &
        (sched['week'] == int(week)) &
        (sched['game_type'].astype(str).str.upper() == 'REG')
    ].copy()

    if slate.empty:
        return []

    slate['gametime'] = slate['gametime'].fillna('13:00')
    slate['kickoff_dt'] = pd.to_datetime(slate['gameday'] + ' ' + slate['gametime'])
    slate = slate.sort_values(by='kickoff_dt').reset_index(drop=True)

    metrics = load_metrics(seasons=[season - 1, season])
    market_lines = fetch_market_lines_rolling(ODDS_API_KEYS)

    league_off = metrics['off_epa'].mean()
    league_def = metrics['def_epa'].mean()

    recs = []

    for _, game in slate.iterrows():
        away = game['away_team']
        home = game['home_team']

        if home not in metrics.index or away not in metrics.index:
            continue

        weather = fetch_stadium_weather(home, game['kickoff_dt'])
        eff_hfa, hfa_note = calculate_situational_hfa(home, away, game['kickoff_dt'], sched)

        h_inj = INJURY_STATUS.get(home, {'starter_out': False, 'dropoff': 0.0})
        a_inj = INJURY_STATUS.get(away, {'starter_out': False, 'dropoff': 0.0})
        h_adj = h_inj['dropoff'] if h_inj['starter_out'] else 0.0
        a_adj = a_inj['dropoff'] if a_inj['starter_out'] else 0.0

        h_pwr = metrics.loc[home, 'power_rating'] - h_adj
        a_pwr = metrics.loc[away, 'power_rating'] - a_adj

        market = market_lines.get((away, home), {
            'open_spd': None, 'open_tot': None,
            'market_spread': None, 'market_total': None
        })
        mkt_spd = market['market_spread']
        mkt_tot = market['market_total']

        raw_margin = (h_pwr + eff_hfa) - a_pwr
        anchor_spd = mkt_spd if mkt_spd is not None else market['open_spd']
        if anchor_spd is not None:
            fair_spread = -round((0.35 * raw_margin) + (0.65 * (-anchor_spd)), 1)
        else:
            fair_spread = -round(raw_margin, 1)

        h_pace = metrics.loc[home, 'pace']
        a_pace = metrics.loc[away, 'pace']
        anchor_total = float(mkt_tot) if mkt_tot is not None else (float(market['open_tot']) if market['open_tot'] is not None else LEAGUE_AVG_TOTAL)

        combined_snaps = h_pace + a_pace
        pace_delta = (combined_snaps - (2.0 * FILTERED_LEAGUE_PACE)) * 0.30

        h_edge = (metrics.loc[home, 'off_epa'] - league_off) - (metrics.loc[away, 'def_epa'] - league_def)
        a_edge = (metrics.loc[away, 'off_epa'] - league_off) - (metrics.loc[home, 'def_epa'] - league_def)
        eff_delta = (h_edge + a_edge) * 7.5

        fair_total = round(anchor_total + ((pace_delta + eff_delta) * 0.50) - weather['wind_penalty'], 1)

        # Spread Action Evaluation
        if mkt_spd is not None:
            action, keys_crossed, edge_density = evaluate_spread_key_numbers(fair_spread, mkt_spd)
            if action != "PASS":
                raw_diff = mkt_spd - fair_spread
                units, dollars, stake_str, win_prob = calculate_kelly_stake(
                    raw_diff=raw_diff,
                    is_key_crossover=(len(keys_crossed) > 0),
                    std_dev=SPREAD_STD_DEV,
                    bankroll=bankroll
                )
                if units > 0:
                    team = home if "HOME" in action else away
                    line = f"{mkt_spd:+}" if "HOME" in action else f"{-mkt_spd:+}"
                    fair_odds = -int(round(100.0 * win_prob / (1.0 - win_prob))) if win_prob >= 0.5 else int(round(100.0 * (1.0 - win_prob) / win_prob))
                    ev_pct = round(((win_prob * 1.9091) - 1.0) * 100.0, 1)

                    recs.append({
                        "sport": "NFL",
                        "matchup": f"{away} @ {home}",
                        "market": "Spread",
                        "pick": f"{team} {line}",
                        "fair_odds": fair_odds,
                        "book_odds": -110,
                        "ev_percent": max(0.5, ev_pct),
                        "suggested_stake": units,
                        "status": "ACTIVE"
                    })

        # Total Action Evaluation
        if mkt_tot is not None:
            tot_action, tot_keys, tot_density = evaluate_total_key_numbers(fair_total, mkt_tot)
            if tot_action != "PASS":
                raw_diff = fair_total - mkt_tot
                units, dollars, stake_str, win_prob = calculate_kelly_stake(
                    raw_diff=raw_diff,
                    is_key_crossover=(len(tot_keys) > 0),
                    std_dev=TOTALS_STD_DEV,
                    bankroll=bankroll
                )
                if units > 0:
                    fair_odds = -int(round(100.0 * win_prob / (1.0 - win_prob))) if win_prob >= 0.5 else int(round(100.0 * (1.0 - win_prob) / win_prob))
                    ev_pct = round(((win_prob * 1.9091) - 1.0) * 100.0, 1)

                    recs.append({
                        "sport": "NFL",
                        "matchup": f"{away} @ {home}",
                        "market": "Total",
                        "pick": tot_action,
                        "fair_odds": fair_odds,
                        "book_odds": -110,
                        "ev_percent": max(0.5, ev_pct),
                        "suggested_stake": units,
                        "status": "ACTIVE"
                    })

    return recs
