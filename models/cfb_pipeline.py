import os
import requests
import numpy as np
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from scipy.stats import norm

ODDS_API_KEYS = [
    os.getenv("ODDS_API_KEY_1", "b57a9742abb4c32ac9bd245ea8ca47ff"),
    os.getenv("ODDS_API_KEY_2", "6c404361bcf2dcf77c92b9b0598674c6"),
    os.getenv("ODDS_API_KEY_3", "9137cefef71eb58610901407cf582c8b"),
    os.getenv("ODDS_API_KEY_4", "0546f5420442d0179ff437806ddd3b6d")
]

CFB_SPREAD_STD_DEV = 16.8          
CFB_TOTAL_STD_DEV = 13.5
CFB_LEAGUE_AVG_TOTAL = 53.5        

CFB_SPREAD_MARKET_REGRESSION = 0.75  
CFB_TOTAL_MARKET_REGRESSION = 0.70   

CFB_SPREAD_KEYS = {3: 0.088, 7: 0.076, 10: 0.057, 14: 0.052}
CFB_TOTAL_KEYS = {41: 0.024, 45: 0.025, 48: 0.026, 51: 0.028, 55: 0.029}

TALENT_COMPOSITE_PRIORS = {
    "Georgia": 24.5, "Ohio State": 24.5, "Alabama": 24.0, "Texas": 23.5, "Oregon": 21.0,
    "Penn State": 19.5, "LSU": 19.5, "Notre Dame": 19.0, "Clemson": 18.0, "Miami": 18.0,
    "Oklahoma": 18.0, "Michigan": 17.5, "Tennessee": 17.5, "Texas A&M": 17.5, "USC": 16.5,
    "Ole Miss": 16.5, "Florida": 14.5, "Missouri": 14.0, "Florida State": 14.0, "Utah": 13.5,
    "Auburn": 13.5, "Kentucky": 11.5, "Wisconsin": 11.0, "Louisville": 11.0, "Iowa": 10.5,
    "Nebraska": 10.5, "North Carolina": 9.5, "SMU": 9.5, "TCU": 9.0, "Iowa State": 8.5,
    "Minnesota": 8.0, "South Carolina": 8.0, "Arkansas": 8.0, "Kansas": 8.0, "UCF": 7.5,
    "Illinois": 6.5, "BYU": 6.0, "Purdue": 4.5, "Maryland": 4.5, "Northwestern": 2.5,
    "Wake Forest": 2.0, "Stanford": 2.0, "Houston": 1.5, "Mississippi State": 3.5,
    "Virginia": 1.0, "Syracuse": 3.5, "Pittsburgh": 5.0, "Washington": 9.0, "Arizona": 4.5,
    "West Virginia": 4.0, "NC State": 5.0, "Indiana": 7.0, "California": 3.5, "Virginia Tech": 4.0,
    "Kansas State": 8.5, "Arizona State": 4.0, "Baylor": 3.5, "Rutgers": 4.0, "Duke": 5.0,
    "UCLA": 4.5, "Vanderbilt": 2.0,
    "Liberty": 2.0, "Memphis": 1.5, "Boise State": 2.5, "Tulane": 1.0, "Appalachian State": -1.0,
    "Air Force": -1.5, "Navy": -2.0, "James Madison": 0.5, "UNLV": 0.0, "Florida Atlantic": -4.0,
    "Troy": -2.0, "Southern Miss": -11.5, "Jacksonville State": -5.0, "Kennesaw State": -16.0,
    "New Mexico State": -12.0, "Florida International": -10.0, "Sam Houston": -8.5,
    "Western Kentucky": -6.5, "South Alabama": -4.5, "Arkansas State": -7.5, "South Florida": -4.0,
    "UTSA": -3.5, "Wyoming": -9.0, "San Jose State": -6.5, "Utah State": -8.0, "Washington State": 2.5,
    "Bowling Green": -7.5, "Army": -3.0, "Old Dominion": -8.0, "Miami (OH)": -7.0, "UMass": -14.5,
    "Tulsa": -8.5, "Toledo": -4.5, "Buffalo": -12.0, "Charlotte": -14.0, "North Texas": -7.0,
    "Northern Illinois": -7.5, "Nevada": -9.0, "UTEP": -16.5, "Coastal Carolina": -4.0,
    "Marshall": -5.5, "Colorado State": -6.5, "Texas State": -4.0,
    "Central Michigan": -8.5, "Eastern Michigan": -9.0, "Western Michigan": -10.0, "Akron": -18.0, "Ohio": -5.5,
    "North Dakota State": -13.0, "Sacramento State": -22.0, "Delaware": -21.0, "Samford": -23.0,
    "DEFAULT_P4": 4.0, "DEFAULT_G5": -8.0, "DEFAULT_FCS": -25.0
}

CFB_HFA_TIERS = {
    "LSU": 3.8, "Penn State": 3.7, "Tennessee": 3.7, "Ohio State": 3.5, "Georgia": 3.5,
    "Florida": 3.5, "Oklahoma": 3.5, "Air Force": 2.6, "DEFAULT_P4": 2.2, "DEFAULT_G5": 1.8
}

CFB_VENUE_COORDINATES = {
    "Nebraska": {"lat": 40.8206, "lon": -96.7056, "is_dome": False, "tz": "America/Chicago"},
    "UCLA": {"lat": 34.1613, "lon": -118.1676, "is_dome": False, "tz": "America/Los_Angeles"},
    "NC State": {"lat": 35.7958, "lon": -78.7188, "is_dome": False, "tz": "America/New_York"},
    "Michigan": {"lat": 42.2658, "lon": -83.7487, "is_dome": False, "tz": "America/Detroit"},
    "Oklahoma": {"lat": 32.7797, "lon": -96.7597, "is_dome": False, "tz": "America/Chicago"},
    "North Texas": {"lat": 33.2039, "lon": -97.1592, "is_dome": False, "tz": "America/Chicago"},
    "Toledo": {"lat": 41.6508, "lon": -83.6136, "is_dome": False, "tz": "America/New_York"},
    "Navy": {"lat": 38.9847, "lon": -76.4863, "is_dome": False, "tz": "America/New_York"},
    "UTEP": {"lat": 31.7733, "lon": -106.5079, "is_dome": False, "tz": "America/Denver"},
    "Utah": {"lat": 40.7599, "lon": -111.8488, "is_dome": False, "tz": "America/Denver"},
    "Northern Illinois": {"lat": 41.9344, "lon": -88.7766, "is_dome": False, "tz": "America/Chicago"},
    "Duke": {"lat": 35.9977, "lon": -78.9422, "is_dome": False, "tz": "America/New_York"},
    "West Virginia": {"lat": 39.6500, "lon": -79.9550, "is_dome": False, "tz": "America/New_York"},
    "Bowling Green": {"lat": 41.3780, "lon": -83.6225, "is_dome": False, "tz": "America/New_York"},
    "Army": {"lat": 41.3875, "lon": -73.9639, "is_dome": False, "tz": "America/New_York"},
    "Akron": {"lat": 41.0722, "lon": -81.5083, "is_dome": False, "tz": "America/New_York"},
    "Pittsburgh": {"lat": 40.4468, "lon": -80.0158, "is_dome": False, "tz": "America/New_York"},
    "Vanderbilt": {"lat": 36.1444, "lon": -86.8093, "is_dome": False, "tz": "America/Chicago"},
    "Kansas State": {"lat": 39.2020, "lon": -96.5938, "is_dome": False, "tz": "America/Chicago"},
    "Marshall": {"lat": 38.4248, "lon": -82.4222, "is_dome": False, "tz": "America/New_York"},
    "Oregon": {"lat": 44.0583, "lon": -123.0685, "is_dome": False, "tz": "America/Los_Angeles"},
    "Texas State": {"lat": 29.8911, "lon": -97.9256, "is_dome": False, "tz": "America/Chicago"},
    "Virginia": {"lat": 38.0315, "lon": -78.5137, "is_dome": False, "tz": "America/New_York"},
    "DEFAULT": {"lat": 39.8283, "lon": -98.5795, "is_dome": False, "tz": "America/New_York"}
}

EXACT_NAME_OVERRIDES = {
    "Central Michigan": "Central Michigan", "Eastern Michigan": "Eastern Michigan", "Western Michigan": "Western Michigan",
    "Northern Illinois": "Northern Illinois", "Southern Illinois": "Southern Illinois",
    "Miami (OH)": "Miami (OH)", "Miami OH": "Miami (OH)", "Southern Mississippi": "Southern Miss", "Southern Miss": "Southern Miss",
    "Troy": "Troy", "Jacksonville State": "Jacksonville State", "Kennesaw State": "Kennesaw State",
    "New Mexico State": "New Mexico State", "Florida International": "Florida International",
    "Sam Houston": "Sam Houston", "Missouri State": "Missouri State", "South Alabama": "South Alabama",
    "Arkansas State": "Arkansas State", "South Florida": "South Florida", "UTSA": "UTSA",
    "Florida State": "Florida State", "Louisville": "Louisville", "Wyoming": "Wyoming",
    "San Jose State": "San Jose State", "Washington State": "Washington State", "Utah State": "Utah State",
    "Iowa State": "Iowa State", "BYU": "BYU", "West Virginia": "West Virginia", "Bowling Green": "Bowling Green",
    "Sacramento State": "Sacramento State", "Nebraska": "Nebraska", "Wake Forest": "Wake Forest",
    "NC State": "NC State", "Tulane": "Tulane", "Army": "Army", "Texas A&M": "Texas A&M",
    "Missouri": "Missouri", "North Carolina": "North Carolina", "Pittsburgh": "Pittsburgh",
    "Oklahoma State": "Oklahoma State", "South Carolina": "South Carolina", "Florida": "Florida",
    "Appalachian State": "Appalachian State", "Old Dominion": "Old Dominion", "UMass": "UMass",
    "Tulsa": "Tulsa", "Navy": "Navy", "Texas": "Texas", "Oklahoma": "Oklahoma", "Toledo": "Toledo",
    "Buffalo": "Buffalo", "Virginia Tech": "Virginia Tech", "California": "California",
    "Charlotte": "Charlotte", "North Texas": "North Texas", "Houston": "Houston", "Kansas State": "Kansas State",
    "Ohio Bobcats": "Ohio", "Akron Zips": "Akron", "Duke Blue Devils": "Duke", "UCLA Bruins": "UCLA",
    "Wisconsin Badgers": "Wisconsin", "Nevada Wolf Pack": "Nevada", "UTEP Miners": "UTEP",
    "Marshall Thundering Herd": "Marshall", "Coastal Carolina Chanticleers": "Coastal Carolina",
    "Penn State Nittany Lions": "Penn State", "Michigan Wolverines": "Michigan", "Oregon Ducks": "Oregon",
    "Texas State Bobcats": "Texas State", "Colorado State Rams": "Colorado State", "Syracuse Orange": "Syracuse",
    "Virginia Cavaliers": "Virginia", "Kansas Jayhawks": "Kansas", "Utah Utes": "Utah",
    "Ole Miss Rebels": "Ole Miss", "Vanderbilt Commodores": "Vanderbilt"
}

def resolve_clean_name(raw_name):
    for match_str, resolved in EXACT_NAME_OVERRIDES.items():
        if match_str in raw_name:
            return resolved
    for key in sorted(TALENT_COMPOSITE_PRIORS.keys(), key=len, reverse=True):
        if key in raw_name:
            return key
    return raw_name.split(" ")[0].strip()

def get_live_stadium_weather(home_team, kickoff_iso):
    venue = CFB_VENUE_COORDINATES.get(home_team, CFB_VENUE_COORDINATES["DEFAULT"])
    if venue.get("is_dome", False):
        return 0.0

    lat = venue["lat"]
    lon = venue["lon"]
    tz_name = venue.get("tz", "America/New_York")

    try:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat, "longitude": lon,
            "hourly": "temperature_2m,wind_speed_10m",
            "temperature_unit": "fahrenheit", "wind_speed_unit": "mph",
            "timezone": tz_name
        }
        resp = requests.get(url, params=params, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            hourly = data.get("hourly", {})
            times = hourly.get("time", [])
            temps = hourly.get("temperature_2m", [])
            winds = hourly.get("wind_speed_10m", [])

            dt_utc = datetime.fromisoformat(kickoff_iso.replace("Z", "+00:00"))
            local_dt = dt_utc.astimezone(ZoneInfo(tz_name))
            target_str = local_dt.strftime("%Y-%m-%dT%H:00")

            idx = times.index(target_str) if target_str in times else 0
            wind = float(winds[idx]) if idx < len(winds) else 8.0
            temp = float(temps[idx]) if idx < len(temps) else 65.0

            wind_penalty = min(6.0, (wind - 10.0) * 0.40) if wind >= 10.0 else 0.0
            temp_penalty = (40.0 - temp) * 0.05 if temp < 40.0 else 0.0
            return -(round(wind_penalty + temp_penalty, 1))
    except Exception:
        pass
    return 0.0

def quarter_kelly(win_prob):
    b = 100.0 / 110.0
    full_kelly = (b * win_prob - (1.0 - win_prob)) / b
    return max(0.0, min(round((full_kelly / 4.0) * 100, 2), 2.5))

def calculate_spread_edge(model_spd, market_spd):
    raw_diff = market_spd - model_spd  
    abs_diff = abs(raw_diff)

    if abs_diff < 1.5 or abs_diff > 7.5:
        return "PASS", [], 1

    side = "HOME" if raw_diff > 0 else "AWAY"
    low_line = min(model_spd, market_spd)
    high_line = max(model_spd, market_spd)
    
    crossed_keys = []
    for k, prob in CFB_SPREAD_KEYS.items():
        if (low_line < k < high_line) or (low_line < -k < high_line):
            crossed_keys.append(k)

    has_primary = (3 in crossed_keys) or (7 in crossed_keys)

    if has_primary and abs_diff >= 3.5:
        stars = 5
    elif has_primary and abs_diff >= 2.0:
        stars = 4
    elif len(crossed_keys) > 0 and abs_diff >= 1.5:
        stars = 3
    else:
        stars = 1

    action = f"BET {side}" if stars >= 3 else "PASS"
    return action, crossed_keys, stars

def calculate_total_edge(model_tot, market_tot):
    raw_diff = model_tot - market_tot
    abs_diff = abs(raw_diff)

    if abs_diff < 2.0 or abs_diff > 7.5:
        return "PASS", [], 1

    side = "OVER" if raw_diff > 0 else "UNDER"
    low = min(model_tot, market_tot)
    high = max(model_tot, market_tot)

    crossed_keys = [k for k in CFB_TOTAL_KEYS if low < k < high]

    if len(crossed_keys) >= 2 and abs_diff >= 3.5:
        stars = 5
    elif len(crossed_keys) >= 1 and abs_diff >= 2.5:
        stars = 4
    elif len(crossed_keys) >= 1 and abs_diff >= 2.0:
        stars = 3
    else:
        stars = 1

    action = f"{side} {market_tot}" if stars >= 3 else "PASS"
    return action, crossed_keys, stars

def fetch_live_cfb_odds(api_keys):
    url = "https://api.the-odds-api.com/v4/sports/americanfootball_ncaaf/odds"
    now_utc = datetime.now(timezone.utc)
    lookahead_limit = now_utc + timedelta(hours=48)

    for key in api_keys:
        if not key:
            continue
        params = {"apiKey": key, "regions": "us", "markets": "spreads,totals", "oddsFormat": "american"}
        try:
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                games = resp.json()
                live_market_data = {}
                for g in games:
                    commence_time = g.get("commence_time", "")
                    if not commence_time:
                        continue
                    dt_ko = datetime.fromisoformat(commence_time.replace("Z", "+00:00"))
                    if not (now_utc <= dt_ko <= lookahead_limit):
                        continue

                    h_raw = g.get("home_team", "")
                    a_raw = g.get("away_team", "")
                    home_team = resolve_clean_name(h_raw)
                    away_team = resolve_clean_name(a_raw)

                    home_spreads, totals = [], []
                    for book in g.get("bookmakers", []):
                        for market in book.get("markets", []):
                            if market.get("key") == "spreads":
                                for out in market.get("outcomes", []):
                                    if out.get("name") == h_raw and out.get("point") is not None:
                                        home_spreads.append(float(out["point"]))
                            elif market.get("key") == "totals":
                                for out in market.get("outcomes", []):
                                    if out.get("name") == "Over" and out.get("point") is not None:
                                        totals.append(float(out["point"]))

                    if home_spreads or totals:
                        live_market_data[(away_team, home_team)] = {
                            "commence_time": commence_time,
                            "market_spread": float(np.median(home_spreads)) if home_spreads else 0.0,
                            "market_total": float(np.median(totals)) if totals else 52.5,
                            "raw_home": h_raw, "raw_away": a_raw
                        }
                if live_market_data:
                    return live_market_data
        except Exception:
            continue
    return {}

def generate_cfb_recommendations():
    slate = fetch_live_cfb_odds(ODDS_API_KEYS)
    recs = []

    for (away, home), mkt in slate.items():
        h_pwr = TALENT_COMPOSITE_PRIORS.get(home, TALENT_COMPOSITE_PRIORS["DEFAULT_G5"])
        a_pwr = TALENT_COMPOSITE_PRIORS.get(away, TALENT_COMPOSITE_PRIORS["DEFAULT_G5"])
        hfa = CFB_HFA_TIERS.get(home, CFB_HFA_TIERS["DEFAULT_P4"] if h_pwr >= 0 else CFB_HFA_TIERS["DEFAULT_G5"])

        mkt_spd = mkt.get("market_spread", 0.0)
        mkt_tot = mkt.get("market_total", CFB_LEAGUE_AVG_TOTAL)
        raw_time = mkt.get("commence_time", "")

        raw_margin = (h_pwr + hfa) - a_pwr
        raw_spread = -raw_margin
        fair_spread = (raw_spread * (1.0 - CFB_SPREAD_MARKET_REGRESSION)) + (mkt_spd * CFB_SPREAD_MARKET_REGRESSION)
        model_spread = round(fair_spread * 2) / 2

        weather_drag = get_live_stadium_weather(home, raw_time) if raw_time else 0.0

        is_academy = (away in ["Navy", "Army", "Air Force"]) or (home in ["Navy", "Army", "Air Force"])
        both_academy = (away in ["Navy", "Army", "Air Force"]) and (home in ["Navy", "Army", "Air Force"])

        home_offense = max(10.0, 26.0 + (h_pwr * 0.40) - (a_pwr * 0.25))
        away_offense = max(10.0, 24.0 + (a_pwr * 0.40) - (h_pwr * 0.25))

        if both_academy:
            home_offense *= 0.78
            away_offense *= 0.78
        elif is_academy:
            home_offense *= 0.88
            away_offense *= 0.88

        if home in ["Iowa", "Minnesota", "Northwestern", "Michigan"] and away in ["Iowa", "Minnesota", "Northwestern", "Michigan"]:
            home_offense -= 3.5
            away_offense -= 3.5

        raw_projected_total = home_offense + away_offense + weather_drag
        fair_total = (raw_projected_total * (1.0 - CFB_TOTAL_MARKET_REGRESSION)) + (mkt_tot * CFB_TOTAL_MARKET_REGRESSION)
        model_total = round(fair_total * 2) / 2

        # 1. Spread Action
        act_spd, spd_keys, spd_stars = calculate_spread_edge(model_spread, mkt_spd)
        if act_spd != "PASS":
            team = home if "HOME" in act_spd else away
            line_str = f"{mkt_spd:+}" if "HOME" in act_spd else f"{-mkt_spd:+}"
            cover_margin = (mkt_spd - model_spread) if "HOME" in act_spd else (model_spread - mkt_spd)
            win_p = float(norm.cdf(cover_margin / CFB_SPREAD_STD_DEV))
            stake = quarter_kelly(win_p)
            ev_pct = round(((win_p * 1.9091) - 1.0) * 100.0, 1)

            fair_odds = -int(round(100.0 * win_p / (1.0 - win_p))) if win_p >= 0.5 else int(round(100.0 * (1.0 - win_p) / win_p))

            recs.append({
                "sport": "CFB",
                "matchup": f"{mkt.get('raw_away', away)} @ {mkt.get('raw_home', home)}",
                "market": "Spread",
                "pick": f"{team} {line_str}",
                "fair_odds": fair_odds,
                "book_odds": -110,
                "ev_percent": max(0.5, ev_pct),
                "suggested_stake": stake if stake > 0 else 1.0,
                "status": "ACTIVE"
            })

        # 2. Total Action
        act_tot, tot_keys, tot_stars = calculate_total_edge(model_total, mkt_tot)
        if act_tot != "PASS":
            win_p = float(norm.cdf(abs(model_total - mkt_tot) / CFB_TOTAL_STD_DEV))
            stake = quarter_kelly(win_p)
            ev_pct = round(((win_p * 1.9091) - 1.0) * 100.0, 1)

            fair_odds = -int(round(100.0 * win_p / (1.0 - win_p))) if win_p >= 0.5 else int(round(100.0 * (1.0 - win_p) / win_p))

            recs.append({
                "sport": "CFB",
                "matchup": f"{mkt.get('raw_away', away)} @ {mkt.get('raw_home', home)}",
                "market": "Total",
                "pick": act_tot,
                "fair_odds": fair_odds,
                "book_odds": -110,
                "ev_percent": max(0.5, ev_pct),
                "suggested_stake": stake if stake > 0 else 1.0,
                "status": "ACTIVE"
            })

    return recs
