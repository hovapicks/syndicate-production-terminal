import os
import re
import math
import requests
import datetime
import pytz
import numpy as np
import pandas as pd
from scipy.stats import poisson

ODDS_API_KEYS = [
    os.getenv("ODDS_API_KEY_1", "b57a9742abb4c32ac9bd245ea8ca47ff"),
    os.getenv("ODDS_API_KEY_2", "6c404361bcf2dcf77c92b9b0598674c6"),
    os.getenv("ODDS_API_KEY_3", "9137cefef71eb58610901407cf582c8b"),
    os.getenv("ODDS_API_KEY_4", "0546f5420442d0179ff437806ddd3b6d")
]

LEAGUE_AVG_RUNS = 4.40
HFA_RUN_ADVANTAGE = 0.16

TEAM_MAP = {
    "Arizona Diamondbacks": "ARI", "Atlanta Braves": "ATL", "Baltimore Orioles": "BAL",
    "Boston Red Sox": "BOS", "Chicago Cubs": "CHC", "Chicago White Sox": "CWS",
    "Cincinnati Reds": "CIN", "Cleveland Guardians": "CLE", "Colorado Rockies": "COL",
    "Detroit Tigers": "DET", "Houston Astros": "HOU", "Kansas City Royals": "KC",
    "Los Angeles Angels": "LAA", "Los Angeles Dodgers": "LAD", "Miami Marlins": "MIA",
    "Milwaukee Brewers": "MIL", "Minnesota Twins": "MIN", "New York Mets": "NYM",
    "New York Yankees": "NYY", "Athletics": "OAK", "Oakland Athletics": "OAK",
    "Philadelphia Phillies": "PHI", "Pittsburgh Pirates": "PIT", "San Diego Padres": "SD",
    "San Francisco Giants": "SF", "Seattle Mariners": "SEA", "St. Louis Cardinals": "STL",
    "Tampa Bay Rays": "TB", "Texas Rangers": "TEX", "Toronto Blue Jays": "TOR",
    "Washington Nationals": "WSH"
}

BALLPARKS = {
    "LAD": {"lat": 34.0739, "lon": -118.2400, "elev": 157, "dome": False, "cf_bearing": 25},
    "NYY": {"lat": 40.8296, "lon": -73.9262, "elev": 16, "dome": False, "cf_bearing": 60},
    "NYM": {"lat": 40.7571, "lon": -73.8458, "elev": 4, "dome": False, "cf_bearing": 45},
    "CLE": {"lat": 41.4962, "lon": -81.6852, "elev": 204, "dome": False, "cf_bearing": 0},
    "SD":  {"lat": 32.7076, "lon": -117.1570, "elev": 4, "dome": False, "cf_bearing": 0},
    "PHI": {"lat": 39.9061, "lon": -75.1665, "elev": 6, "dome": False, "cf_bearing": 10},
    "DET": {"lat": 42.3390, "lon": -83.0485, "elev": 183, "dome": False, "cf_bearing": 150},
    "KC":  {"lat": 39.0517, "lon": -94.4803, "elev": 277, "dome": False, "cf_bearing": 45},
    "HOU": {"lat": 29.7573, "lon": -95.3555, "elev": 12, "dome": True, "cf_bearing": 0},
    "MIL": {"lat": 43.0280, "lon": -87.9712, "elev": 183, "dome": True, "cf_bearing": 0},
    "BAL": {"lat": 39.2838, "lon": -76.6198, "elev": 10, "dome": False, "cf_bearing": 35},
    "ATL": {"lat": 33.8908, "lon": -84.4678, "elev": 305, "dome": False, "cf_bearing": 125}
}

POSTSEASON_RATINGS = {
    "NYY": {"off_wrc": 1.16, "bullpen_fip": 3.65, "starter_fip": 3.75, "starter": "Gerrit Cole"},
    "LAD": {"off_wrc": 1.18, "bullpen_fip": 3.55, "starter_fip": 3.60, "starter": "Jack Flaherty"},
    "NYM": {"off_wrc": 1.08, "bullpen_fip": 3.80, "starter_fip": 3.85, "starter": "Sean Manaea"},
    "CLE": {"off_wrc": 1.02, "bullpen_fip": 3.10, "starter_fip": 3.90, "starter": "Matthew Boyd"},
    "SD":  {"off_wrc": 1.12, "bullpen_fip": 3.45, "starter_fip": 3.50, "starter": "Dylan Cease"},
    "PHI": {"off_wrc": 1.10, "bullpen_fip": 3.70, "starter_fip": 3.40, "starter": "Zack Wheeler"},
    "DET": {"off_wrc": 0.98, "bullpen_fip": 3.40, "starter_fip": 2.85, "starter": "Tarik Skubal"},
    "KC":  {"off_wrc": 1.01, "bullpen_fip": 3.75, "starter_fip": 3.45, "starter": "Cole Ragans"}
}

def decimal_to_american(dec):
    if dec <= 1.0: return -110
    return int(round((dec - 1.0) * 100)) if dec >= 2.0 else int(round(-100 / (dec - 1.0)))

def american_to_implied(odds):
    return (100.0 / (odds + 100.0)) if odds > 0 else (abs(odds) / (abs(odds) + 100.0))

def devig_power_ratio(odds_a, odds_b):
    pa = american_to_implied(odds_a)
    pb = american_to_implied(odds_b)
    overround = pa + pb
    if overround <= 1.0: return pa, pb
    return pa / overround, pb / overround

def prob_to_american(p):
    if p <= 0.0001 or p >= 0.9999: return -110
    return int(round(-((p / (1.0 - p)) * 100))) if p >= 0.5 else int(round(((1.0 - p) / p) * 100))

def quarter_kelly(fair_p, market_odds, cap=3.0):
    b = (market_odds / 100.0) if market_odds > 0 else (100.0 / abs(market_odds))
    q = 1.0 - fair_p
    f = (b * fair_p - q) / b
    return round(max(0.0, min(cap, (f * 0.25) * 100.0)), 2)

def fetch_weather_multiplier(home_team):
    park = BALLPARKS.get(home_team)
    if not park or park.get("dome", False):
        return 1.00

    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": park["lat"],
        "longitude": park["lon"],
        "current": "temperature_2m,wind_speed_10m,wind_direction_10m"
    }
    try:
        r = requests.get(url, params=params, timeout=6)
        if r.status_code == 200:
            data = r.json().get("current", {})
            temp_f = (data.get("temperature_2m", 15) * 9/5) + 32
            wind_mph = data.get("wind_speed_10m", 5) * 0.621371
            wind_dir = data.get("wind_direction_10m", 0)

            temp_factor = 1.0 + ((temp_f - 72.0) * 0.0035)
            rel_angle = math.radians((wind_dir - park["cf_bearing"]) % 360)
            vector = wind_mph * math.cos(rel_angle)
            wind_factor = 1.0 + (vector * 0.0075)
            elev_factor = 1.0 + (park["elev"] / 1000.0 * 0.02)

            return round(temp_factor * wind_factor * elev_factor, 3)
    except Exception:
        pass
    return 1.00

def fetch_mlb_odds(api_keys):
    url = "https://api.the-odds-api.com/v4/sports/baseball_mlb/odds/"
    params = {"regions": "us,eu", "markets": "h2h,spreads,totals", "oddsFormat": "decimal"}
    for key in api_keys:
        if not key: continue
        params["apiKey"] = key
        try:
            r = requests.get(url, params=params, timeout=10)
            if r.status_code == 200:
                events = r.json()
                if events:
                    odds_map = {}
                    for ev in events:
                        h_raw, a_raw = ev.get("home_team"), ev.get("away_team")
                        h_abbr, a_abbr = TEAM_MAP.get(h_raw), TEAM_MAP.get(a_raw)
                        if not h_abbr or not a_abbr: continue
                        matchup_key = f"{a_abbr}@{h_abbr}"

                        sharp_h_ml, sharp_a_ml = None, None
                        all_h_mls, all_a_mls = [], []
                        h_rls, a_rls, tots, overs, unders = [], [], [], [], []

                        for bm in ev.get("bookmakers", []):
                            is_sharp = bm.get("key") in ["pinnacle", "circa"]
                            for mkt in bm.get("markets", []):
                                m_key = mkt.get("key")
                                if m_key == "h2h":
                                    for out in mkt.get("outcomes", []):
                                        pr = decimal_to_american(out.get("price"))
                                        if out.get("name") == h_raw:
                                            all_h_mls.append(pr)
                                            if is_sharp: sharp_h_ml = pr
                                        elif out.get("name") == a_raw:
                                            all_a_mls.append(pr)
                                            if is_sharp: sharp_a_ml = pr
                                elif m_key == "spreads":
                                    for out in mkt.get("outcomes", []):
                                        pr = decimal_to_american(out.get("price"))
                                        pt = out.get("point", 0)
                                        if out.get("name") == h_raw and abs(abs(pt) - 1.5) < 0.01: h_rls.append(pr)
                                        elif out.get("name") == a_raw and abs(abs(pt) - 1.5) < 0.01: a_rls.append(pr)
                                elif m_key == "totals":
                                    for out in mkt.get("outcomes", []):
                                        tots.append(out.get("point"))
                                        pr = decimal_to_american(out.get("price"))
                                        if out.get("name") == "Over": overs.append(pr)
                                        elif out.get("name") == "Under": unders.append(pr)

                        if all_h_mls and all_a_mls:
                            final_h_ml = sharp_h_ml if sharp_h_ml else int(np.median(all_h_mls))
                            final_a_ml = sharp_a_ml if sharp_a_ml else int(np.median(all_a_mls))
                            med_h_rl = int(np.median(h_rls)) if h_rls else (+150 if final_h_ml < final_a_ml else -180)
                            med_a_rl = int(np.median(a_rls)) if a_rls else (-180 if final_h_ml < final_a_ml else +150)
                            med_tot = float(np.median(tots)) if tots else 7.5
                            med_o = int(np.median(overs)) if overs else -110
                            med_u = int(np.median(unders)) if unders else -110
                            odds_map[matchup_key] = (final_a_ml, final_h_ml, med_a_rl, med_h_rl, med_tot, med_o, med_u)
                    if odds_map: return odds_map
        except Exception:
            pass
    return {}

def simulate_mlb_matchup(home, away, mkt_tot):
    h = POSTSEASON_RATINGS.get(home, {"off_wrc": 1.0, "bullpen_fip": 4.0, "starter_fip": 4.0, "starter": "TBA"})
    a = POSTSEASON_RATINGS.get(away, {"off_wrc": 1.0, "bullpen_fip": 4.0, "starter_fip": 4.0, "starter": "TBA"})

    is_tba = (h["starter"] == "TBA" or a["starter"] == "TBA")
    weather_mult = fetch_weather_multiplier(home)

    # Postseason 0.90x BF starter leash weighting (50% starter, 50% bullpen)
    h_pitch_quality = (0.50 * h["starter_fip"] + 0.50 * h["bullpen_fip"]) / 4.0
    a_pitch_quality = (0.50 * a["starter_fip"] + 0.50 * a["bullpen_fip"]) / 4.0

    lh = max(1.5, (LEAGUE_AVG_RUNS * h["off_wrc"] * a_pitch_quality + HFA_RUN_ADVANTAGE) * weather_mult)
    la = max(1.5, (LEAGUE_AVG_RUNS * a["off_wrc"] * h_pitch_quality) * weather_mult)

    max_runs = 16
    grid = np.zeros((max_runs, max_runs))
    for x in range(max_runs):
        for y in range(max_runs):
            grid[x, y] = poisson.pmf(x, lh) * poisson.pmf(y, la)

    grid = grid / np.sum(grid)

    h_reg_win = float(np.sum(np.tril(grid, -1)))
    a_reg_win = float(np.sum(np.triu(grid, 1)))
    extra_innings = float(np.sum(np.diag(grid)))

    # Extra innings ghost-runner home team conversion
    extra_h = 0.54
    h_ml_p = h_reg_win + (extra_innings * extra_h)
    a_ml_p = 1.0 - h_ml_p

    h_minus_15_p = sum(grid[hg, ag] for hg in range(max_runs) for ag in range(max_runs) if hg - ag >= 2)
    a_plus_15_p = 1.0 - h_minus_15_p
    a_minus_15_p = sum(grid[hg, ag] for hg in range(max_runs) for ag in range(max_runs) if ag - hg >= 2)
    h_plus_15_p = 1.0 - a_minus_15_p

    # Flat Total Push Probability Calculation
    prob_u = sum(grid[hg, ag] for hg in range(max_runs) for ag in range(max_runs) if hg + ag < mkt_tot)
    prob_push = sum(grid[hg, ag] for hg in range(max_runs) for ag in range(max_runs) if hg + ag == mkt_tot)
    prob_o = sum(grid[hg, ag] for hg in range(max_runs) for ag in range(max_runs) if hg + ag > mkt_tot)
    denom = max(0.0001, 1.0 - prob_push)

    return {
        "h_ml_p": h_ml_p, "a_ml_p": a_ml_p,
        "h_minus_15_p": h_minus_15_p, "a_plus_15_p": a_plus_15_p,
        "a_minus_15_p": a_minus_15_p, "h_plus_15_p": h_plus_15_p,
        "fair_o_p": prob_o / denom, "fair_u_p": prob_u / denom,
        "is_tba": is_tba
    }

def generate_mlb_recommendations():
    odds_feed = fetch_mlb_odds(ODDS_API_KEYS)
    if not odds_feed:
        return []

    recs = []

    for matchup_key, odds in odds_feed.items():
        a_abbr, h_abbr = matchup_key.split("@")
        a_ml, h_ml, a_rl, h_rl, tot, o_j, u_j = odds

        sim = simulate_mlb_matchup(h_abbr, a_abbr, tot)
        fair_mkt_a, fair_mkt_h = devig_power_ratio(a_ml, h_ml)

        # TBA Risk Governor: If pitcher unconfirmed, cap Kelly sizing at 1.50%
        stake_cap = 1.50 if sim["is_tba"] else 3.00

        # ----------------------------------------------------------------------
        # Evaluate Best Side Candidate (Zero Duplication)
        # ----------------------------------------------------------------------
        side_candidates = []

        eh_ml = (sim["h_ml_p"] - fair_mkt_h) * 100.0
        ea_ml = (sim["a_ml_p"] - fair_mkt_a) * 100.0

        if eh_ml >= 2.5:
            stake = quarter_kelly(sim["h_ml_p"], h_ml, cap=stake_cap)
            side_candidates.append({
                "sport": "MLB",
                "matchup": f"{a_abbr} @ {h_abbr}",
                "market": "Moneyline",
                "pick": f"{h_abbr} ML",
                "fair_odds": prob_to_american(sim["h_ml_p"]),
                "book_odds": h_ml,
                "ev_percent": round(eh_ml, 1),
                "suggested_stake": stake if stake > 0 else 0.75,
                "status": "ACTIVE"
            })
        if ea_ml >= 2.5:
            stake = quarter_kelly(sim["a_ml_p"], a_ml, cap=stake_cap)
            side_candidates.append({
                "sport": "MLB",
                "matchup": f"{a_abbr} @ {h_abbr}",
                "market": "Moneyline",
                "pick": f"{a_abbr} ML",
                "fair_odds": prob_to_american(sim["a_ml_p"]),
                "book_odds": a_ml,
                "ev_percent": round(ea_ml, 1),
                "suggested_stake": stake if stake > 0 else 0.75,
                "status": "ACTIVE"
            })

        # Run Line candidates
        is_home_fav = h_ml <= a_ml
        if is_home_fav:
            e_h_minus = (sim["h_minus_15_p"] - american_to_implied(h_rl)) * 100.0
            e_a_plus = (sim["a_plus_15_p"] - american_to_implied(a_rl)) * 100.0
            if e_h_minus >= 2.5:
                stake = quarter_kelly(sim["h_minus_15_p"], h_rl, cap=stake_cap)
                side_candidates.append({
                    "sport": "MLB",
                    "matchup": f"{a_abbr} @ {h_abbr}",
                    "market": "Run Line",
                    "pick": f"{h_abbr} -1.5",
                    "fair_odds": prob_to_american(sim["h_minus_15_p"]),
                    "book_odds": h_rl,
                    "ev_percent": round(e_h_minus, 1),
                    "suggested_stake": stake if stake > 0 else 0.75,
                    "status": "ACTIVE"
                })
            if e_a_plus >= 2.5:
                stake = quarter_kelly(sim["a_plus_15_p"], a_rl, cap=stake_cap)
                side_candidates.append({
                    "sport": "MLB",
                    "matchup": f"{a_abbr} @ {h_abbr}",
                    "market": "Run Line",
                    "pick": f"{a_abbr} +1.5",
                    "fair_odds": prob_to_american(sim["a_plus_15_p"]),
                    "book_odds": a_rl,
                    "ev_percent": round(e_a_plus, 1),
                    "suggested_stake": stake if stake > 0 else 0.75,
                    "status": "ACTIVE"
                })
        else:
            e_a_minus = (sim["a_minus_15_p"] - american_to_implied(a_rl)) * 100.0
            e_h_plus = (sim["h_plus_15_p"] - american_to_implied(h_rl)) * 100.0
            if e_a_minus >= 2.5:
                stake = quarter_kelly(sim["a_minus_15_p"], a_rl, cap=stake_cap)
                side_candidates.append({
                    "sport": "MLB",
                    "matchup": f"{a_abbr} @ {h_abbr}",
                    "market": "Run Line",
                    "pick": f"{a_abbr} -1.5",
                    "fair_odds": prob_to_american(sim["a_minus_15_p"]),
                    "book_odds": a_rl,
                    "ev_percent": round(e_a_minus, 1),
                    "suggested_stake": stake if stake > 0 else 0.75,
                    "status": "ACTIVE"
                })
            if e_h_plus >= 2.5:
                stake = quarter_kelly(sim["h_plus_15_p"], h_rl, cap=stake_cap)
                side_candidates.append({
                    "sport": "MLB",
                    "matchup": f"{a_abbr} @ {h_abbr}",
                    "market": "Run Line",
                    "pick": f"{h_abbr} +1.5",
                    "fair_odds": prob_to_american(sim["h_plus_15_p"]),
                    "book_odds": h_rl,
                    "ev_percent": round(e_h_plus, 1),
                    "suggested_stake": stake if stake > 0 else 0.75,
                    "status": "ACTIVE"
                })

        if side_candidates:
            best_side = max(side_candidates, key=lambda x: x["ev_percent"])
            recs.append(best_side)

        # ----------------------------------------------------------------------
        # Evaluate Game Total
        # ----------------------------------------------------------------------
        eo = (sim["fair_o_p"] - american_to_implied(o_j)) * 100.0
        eu = (sim["fair_u_p"] - american_to_implied(u_j)) * 100.0

        if eo >= 2.5 and eo >= eu:
            stake = quarter_kelly(sim["fair_o_p"], o_j, cap=stake_cap)
            recs.append({
                "sport": "MLB",
                "matchup": f"{a_abbr} @ {h_abbr}",
                "market": "Total",
                "pick": f"OVER {tot}",
                "fair_odds": prob_to_american(sim["fair_o_p"]),
                "book_odds": o_j,
                "ev_percent": round(eo, 1),
                "suggested_stake": stake if stake > 0 else 0.75,
                "status": "ACTIVE"
            })
        elif eu >= 2.5 and eu > eo:
            stake = quarter_kelly(sim["fair_u_p"], u_j, cap=stake_cap)
            recs.append({
                "sport": "MLB",
                "matchup": f"{a_abbr} @ {h_abbr}",
                "market": "Total",
                "pick": f"UNDER {tot}",
                "fair_odds": prob_to_american(sim["fair_u_p"]),
                "book_odds": u_j,
                "ev_percent": round(eu, 1),
                "suggested_stake": stake if stake > 0 else 0.75,
                "status": "ACTIVE"
            })

    return recs
