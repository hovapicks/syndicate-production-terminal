import os
import math
import requests
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from scipy.stats import poisson

CONFIG = {
    "ODDS_API_KEYS": [
        os.getenv("ODDS_API_KEY_1", "0546f5420442d0179ff437806ddd3b6d"),
        os.getenv("ODDS_API_KEY_2", "b57a9742abb4c32ac9bd245ea8ca47ff"),
        os.getenv("ODDS_API_KEY_3", "6c404361bcf2dcf77c92b9b0598674c6"),
        os.getenv("ODDS_API_KEY_4", "9137cefef71eb58610901407cf582c8b")
    ],
    "FOOTBALL_DATA_API_KEY": os.getenv("FOOTBALL_DATA_API_KEY", ""),
    "SPORT": "soccer_epl",
    "REGIONS": "uk,eu,us",
    "MARKETS": "h2h,spreads,totals",
    "WINDOW_HOURS": 24,            # Strict horizon: Kickoff within 24 hours
    "KELLY_FRACTION": 0.25,        # Quarter-Kelly risk sizing
    "MAX_BANKROLL_BET_PCT": 0.030, # 3.0% maximum allocation per single bet
    "MAX_SLATE_RISK_PCT": 0.150,   # 15.0% maximum aggregate slate risk
    "MIN_EV_THRESHOLD": 0.020,     # 2.0% minimum EV hurdle rate
    "CIRCUIT_BREAKER_EV": 0.120,   # Halt bets exceeding 12% EV (bad data guard)
    "BAYESIAN_SHRINKAGE_W": 0.25,  # 25% anchor toward sharp consensus totals
    "HOME_PITCH_ADVANTAGE": 0.22,  # Log-scale baseline home attack boost
    "DIXON_COLES_RHO": -0.11,      # Bivariate low-scoring correlation parameter
    "ROLLING_MATCH_WINDOW": 10
}

VALID_EPL_TEAMS = [
    "Manchester City", "Arsenal", "Liverpool", "Aston Villa", "Tottenham Hotspur",
    "Chelsea", "Newcastle United", "Manchester United", "Brighton and Hove Albion",
    "West Ham United", "Fulham", "Brentford", "Crystal Palace", "Bournemouth",
    "Everton", "Wolverhampton Wanderers", "Nottingham Forest", "Leicester City",
    "Ipswich Town", "Southampton"
]

def decimal_to_american(decimal_odds):
    if decimal_odds <= 1.001:
        return -10000
    if decimal_odds >= 2.0:
        return int(round((decimal_odds - 1.0) * 100))
    else:
        return int(round(-100 / (decimal_odds - 1.0)))

def prob_to_american(p):
    if p <= 0.001: return 99900
    if p >= 0.999: return -99900
    return decimal_to_american(1.0 / p)

def snap_to_quarter(val):
    return round(float(val) * 4.0) / 4.0

def fetch_rolling_team_metrics():
    headers = {}
    if CONFIG["FOOTBALL_DATA_API_KEY"]:
        headers["X-Auth-Token"] = CONFIG["FOOTBALL_DATA_API_KEY"]

    ratings = {}
    try:
        if CONFIG["FOOTBALL_DATA_API_KEY"]:
            url = "https://api.football-data.org/v4/competitions/PL/matches?status=FINISHED"
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                team_stats = {t: {"gf": [], "ga": []} for t in VALID_EPL_TEAMS}
                for m in reversed(data.get("matches", [])):
                    h = m["homeTeam"]["name"]
                    a = m["awayTeam"]["name"]
                    if h in team_stats and len(team_stats[h]["gf"]) < CONFIG["ROLLING_MATCH_WINDOW"]:
                        team_stats[h]["gf"].append(m["score"]["fullTime"]["home"])
                        team_stats[h]["ga"].append(m["score"]["fullTime"]["away"])
                    if a in team_stats and len(team_stats[a]["gf"]) < CONFIG["ROLLING_MATCH_WINDOW"]:
                        team_stats[a]["gf"].append(m["score"]["fullTime"]["away"])
                        team_stats[a]["ga"].append(m["score"]["fullTime"]["home"])

                league_gf = np.mean([np.mean(v["gf"]) for v in team_stats.values() if len(v["gf"]) > 0]) or 1.40
                for t, s in team_stats.items():
                    if len(s["gf"]) > 0:
                        att_log = math.log(max(0.2, np.mean(s["gf"])) / league_gf)
                        def_log = math.log(max(0.2, np.mean(s["ga"])) / league_gf)
                        ratings[t] = {"att": round(att_log, 3), "def": round(def_log, 3), "rest_days": 6, "inj_impact": 0.0}
                return ratings
    except Exception:
        pass

    # Baseline calibrated universe fallback
    return {
        "Manchester City":          {"att": 0.48, "def": -0.32, "rest_days": 6, "inj_impact": 0.00},
        "Arsenal":                  {"att": 0.42, "def": -0.34, "rest_days": 4, "inj_impact": -0.04},
        "Liverpool":                {"att": 0.44, "def": -0.25, "rest_days": 3, "inj_impact": -0.06},
        "Aston Villa":              {"att": 0.18, "def": -0.08, "rest_days": 7, "inj_impact": 0.00},
        "Tottenham Hotspur":        {"att": 0.22, "def": -0.02, "rest_days": 6, "inj_impact": -0.08},
        "Chelsea":                  {"att": 0.20, "def": -0.04, "rest_days": 6, "inj_impact": -0.02},
        "Newcastle United":         {"att": 0.15, "def": -0.06, "rest_days": 7, "inj_impact": -0.03},
        "Manchester United":        {"att": 0.08, "def":  0.02, "rest_days": 4, "inj_impact": -0.10},
        "Brighton and Hove Albion": {"att": 0.10, "def":  0.05, "rest_days": 7, "inj_impact": 0.00},
        "West Ham United":          {"att":-0.02, "def":  0.10, "rest_days": 7, "inj_impact": 0.00},
        "Fulham":                   {"att":-0.05, "def":  0.08, "rest_days": 6, "inj_impact": 0.00},
        "Brentford":                {"att":-0.02, "def":  0.12, "rest_days": 7, "inj_impact": -0.02},
        "Crystal Palace":           {"att":-0.10, "def":  0.04, "rest_days": 7, "inj_impact": -0.05},
        "Bournemouth":              {"att":-0.08, "def":  0.14, "rest_days": 7, "inj_impact": 0.00},
        "Everton":                  {"att":-0.18, "def":  0.02, "rest_days": 6, "inj_impact": 0.00},
        "Wolverhampton Wanderers":  {"att":-0.15, "def":  0.15, "rest_days": 6, "inj_impact": -0.05},
        "Nottingham Forest":        {"att":-0.16, "def":  0.12, "rest_days": 7, "inj_impact": 0.00},
        "Leicester City":           {"att":-0.22, "def":  0.22, "rest_days": 6, "inj_impact": -0.02},
        "Ipswich Town":             {"att":-0.28, "def":  0.26, "rest_days": 7, "inj_impact": 0.00},
        "Southampton":              {"att":-0.30, "def":  0.28, "rest_days": 5, "inj_impact": -0.03},
    }

def fetch_epl_market_data():
    url = f"https://api.the-odds-api.com/v4/sports/{CONFIG['SPORT']}/odds/"
    for key in CONFIG["ODDS_API_KEYS"]:
        if not key:
            continue
        params = {
            "apiKey": key,
            "regions": CONFIG["REGIONS"],
            "markets": CONFIG["MARKETS"],
            "oddsFormat": "decimal"
        }
        try:
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                events = resp.json()
                if events:
                    parsed = parse_odds_api_response(events, apply_time_filter=True)
                    if parsed:
                        return parsed
        except Exception:
            continue
    return []

def parse_odds_api_response(api_json, apply_time_filter=True):
    fixtures = []
    now_utc = datetime.now(timezone.utc)

    for event in api_json:
        home = event.get("home_team")
        away = event.get("away_team")
        commence_time = event.get("commence_time")

        if home not in VALID_EPL_TEAMS or away not in VALID_EPL_TEAMS:
            continue

        if apply_time_filter and commence_time:
            try:
                match_dt = datetime.fromisoformat(commence_time.replace("Z", "+00:00"))
                hours_to_ko = (match_dt - now_utc).total_seconds() / 3600.0
                if not (0 <= hours_to_ko <= CONFIG["WINDOW_HOURS"]):
                    continue
            except Exception:
                continue

        h2h_home, h2h_draw, h2h_away = [], [], []
        spread_pts, spread_h, spread_a = [], [], []
        totals_pts, totals_o, totals_u = [], [], []

        for bm in event.get("bookmakers", []):
            for mkt in bm.get("markets", []):
                if mkt["key"] == "h2h":
                    for oc in mkt.get("outcomes", []):
                        if oc["name"] == home: h2h_home.append(oc["price"])
                        elif oc["name"] == away: h2h_away.append(oc["price"])
                        elif oc["name"] == "Draw": h2h_draw.append(oc["price"])
                elif mkt["key"] == "spreads":
                    for oc in mkt.get("outcomes", []):
                        if oc["name"] == home:
                            spread_pts.append(oc.get("point", 0))
                            spread_h.append(oc["price"])
                        else:
                            spread_a.append(oc["price"])
                elif mkt["key"] == "totals":
                    for oc in mkt.get("outcomes", []):
                        if oc["name"] == "Over":
                            totals_pts.append(oc.get("point", 2.5))
                            totals_o.append(oc["price"])
                        else:
                            totals_u.append(oc["price"])

        if h2h_home and h2h_draw and h2h_away:
            raw_spread = float(np.median(spread_pts)) if spread_pts else -0.5
            raw_total  = float(np.median(totals_pts)) if totals_pts else 2.5

            fixtures.append({
                "id": event.get("id"),
                "home": home,
                "away": away,
                "commence_time": commence_time,
                "consensus": {
                    "h2h": {
                        "home": round(float(np.median(h2h_home)), 2),
                        "draw": round(float(np.median(h2h_draw)), 2),
                        "away": round(float(np.median(h2h_away)), 2)
                    },
                    "spread": {
                        "point": snap_to_quarter(raw_spread),
                        "home": round(float(np.median(spread_h)), 2) if spread_h else 1.95,
                        "away": round(float(np.median(spread_a)), 2) if spread_a else 1.95
                    },
                    "total": {
                        "point": snap_to_quarter(raw_total),
                        "over": round(float(np.median(totals_o)), 2) if totals_o else 1.95,
                        "under": round(float(np.median(totals_u)), 2) if totals_u else 1.95
                    }
                }
            })
    return fixtures

def get_dixon_coles_tau(x, y, lambda_h, mu_a, rho):
    if x == 0 and y == 0: return 1.0 - (lambda_h * mu_a * rho)
    elif x == 0 and y == 1: return 1.0 + (lambda_h * rho)
    elif x == 1 and y == 0: return 1.0 + (mu_a * rho)
    elif x == 1 and y == 1: return 1.0 - rho
    return 1.0

def simulate_match_distribution(home_team, away_team, market_consensus_total, ratings):
    h_data = ratings.get(home_team, {"att": 0.0, "def": 0.1, "rest_days": 6, "inj_impact": 0.0})
    a_data = ratings.get(away_team, {"att": 0.0, "def": 0.1, "rest_days": 6, "inj_impact": 0.0})

    rest_diff = (h_data["rest_days"] - a_data["rest_days"]) * 0.015
    h_sit = rest_diff + h_data["inj_impact"]
    a_sit = -rest_diff + a_data["inj_impact"]

    gamma = CONFIG["HOME_PITCH_ADVANTAGE"]
    lambda_h = math.exp(0.32 + gamma + h_data["att"] + a_data["def"] + h_sit)
    mu_a     = math.exp(0.18 + a_data["att"] + h_data["def"] + a_sit)

    model_total = lambda_h + mu_a
    target_total = (1.0 - CONFIG["BAYESIAN_SHRINKAGE_W"]) * model_total + (CONFIG["BAYESIAN_SHRINKAGE_W"] * market_consensus_total)
    scale = target_total / model_total
    lambda_h *= scale
    mu_a *= scale

    max_goals = 10
    prob_matrix = np.zeros((max_goals, max_goals))
    for x in range(max_goals):
        for y in range(max_goals):
            p_x = poisson.pmf(x, lambda_h)
            p_y = poisson.pmf(y, mu_a)
            tau = get_dixon_coles_tau(x, y, lambda_h, mu_a, CONFIG["DIXON_COLES_RHO"])
            prob_matrix[x, y] = p_x * p_y * tau

    prob_matrix /= np.sum(prob_matrix)

    return {
        "lambda_h": lambda_h,
        "mu_a": mu_a,
        "proj_total": lambda_h + mu_a,
        "prob_matrix": prob_matrix,
        "1x2": {
            "H": float(np.sum(np.tril(prob_matrix, -1))),
            "D": float(np.trace(prob_matrix)),
            "A": float(np.sum(np.triu(prob_matrix, 1)))
        }
    }

def evaluate_single_handicap(prob_matrix, h_spread):
    max_g = prob_matrix.shape[0]
    expected_units = 0.0
    for x in range(max_g):
        for y in range(max_g):
            diff = x - y + h_spread
            p = prob_matrix[x, y]
            if diff > 0: expected_units += p * 1.0
            elif diff < 0: expected_units += p * -1.0
    return (expected_units + 1.0) / 2.0

def evaluate_quarter_handicap(prob_matrix, h_spread):
    h1 = math.floor(h_spread * 2.0) / 2.0
    h2 = math.ceil(h_spread * 2.0) / 2.0
    if h1 == h2:
        return evaluate_single_handicap(prob_matrix, h_spread)
    return (evaluate_single_handicap(prob_matrix, h1) + evaluate_single_handicap(prob_matrix, h2)) / 2.0

def evaluate_single_total(prob_matrix, total_line):
    max_g = prob_matrix.shape[0]
    expected_units = 0.0
    for x in range(max_g):
        for y in range(max_g):
            g = x + y
            p = prob_matrix[x, y]
            if g > total_line: expected_units += p * 1.0
            elif g < total_line: expected_units += p * -1.0
    return (expected_units + 1.0) / 2.0

def evaluate_split_total(prob_matrix, total_line):
    t1 = math.floor(total_line * 2.0) / 2.0
    t2 = math.ceil(total_line * 2.0) / 2.0
    if t1 == t2:
        return evaluate_single_total(prob_matrix, total_line)
    return (evaluate_single_total(prob_matrix, t1) + evaluate_single_total(prob_matrix, t2)) / 2.0

def remove_vig_multiplicative(odds_dict):
    raw_probs = {k: 1.0 / v for k, v in odds_dict.items()}
    overround = sum(raw_probs.values())
    return {k: p / overround for k, p in raw_probs.items()}

def calculate_kelly(p_win, decimal_odds, fraction=CONFIG["KELLY_FRACTION"], cap=CONFIG["MAX_BANKROLL_BET_PCT"]):
    b = decimal_odds - 1.0
    q = 1.0 - p_win
    f = (b * p_win - q) / b
    if f <= 0: return 0.0
    return min(f * fraction, cap)

def generate_epl_recommendations():
    rolling_ratings = fetch_rolling_team_metrics()
    fixtures = fetch_epl_market_data()
    all_executable_bets = []

    for f in fixtures:
        home, away = f["home"], f["away"]
        cons = f["consensus"]

        sim = simulate_match_distribution(home, away, cons["total"]["point"], rolling_ratings)
        p_matrix = sim["prob_matrix"]

        fair_h2h = sim["1x2"]
        h_spread = cons["spread"]["point"]
        fair_spread_h = evaluate_quarter_handicap(p_matrix, h_spread)
        fair_spread_a = 1.0 - fair_spread_h

        tot_pt = cons["total"]["point"]
        fair_tot_o = evaluate_split_total(p_matrix, tot_pt)
        fair_tot_u = 1.0 - fair_tot_o

        unvig_h2h = remove_vig_multiplicative(cons["h2h"])
        unvig_spread = remove_vig_multiplicative({"home": cons["spread"]["home"], "away": cons["spread"]["away"]})
        unvig_total = remove_vig_multiplicative({"over": cons["total"]["over"], "under": cons["total"]["under"]})

        markets = [
            {"mkt": "Moneyline", "type": "SIDE", "sel": f"{home} ML", "fair_p": fair_h2h["H"], "unvig_p": unvig_h2h["home"], "odds": cons["h2h"]["home"]},
            {"mkt": "Moneyline", "type": "DRAW", "sel": "Draw ML", "fair_p": fair_h2h["D"], "unvig_p": unvig_h2h["draw"], "odds": cons["h2h"]["draw"]},
            {"mkt": "Moneyline", "type": "SIDE", "sel": f"{away} ML", "fair_p": fair_h2h["A"], "unvig_p": unvig_h2h["away"], "odds": cons["h2h"]["away"]},
            {"mkt": "Spread", "type": "SIDE", "sel": f"{home} {h_spread:+}", "fair_p": fair_spread_h, "unvig_p": unvig_spread["home"], "odds": cons["spread"]["home"]},
            {"mkt": "Spread", "type": "SIDE", "sel": f"{away} {-h_spread:+}", "fair_p": fair_spread_a, "unvig_p": unvig_spread["away"], "odds": cons["spread"]["away"]},
            {"mkt": "Total", "type": "TOTAL", "sel": f"Over {tot_pt} Goals", "fair_p": fair_tot_o, "unvig_p": unvig_total["over"], "odds": cons["total"]["over"]},
            {"mkt": "Total", "type": "TOTAL", "sel": f"Under {tot_pt} Goals", "fair_p": fair_tot_u, "unvig_p": unvig_total["under"], "odds": cons["total"]["under"]}
        ]

        for cand in markets:
            p = cand["fair_p"]
            d_odds = cand["odds"]
            cand["ev"] = (p * d_odds) - 1.0
            cand["edge"] = p - cand["unvig_p"]
            cand["kelly_pct"] = calculate_kelly(p, d_odds)

            if cand["ev"] >= CONFIG["CIRCUIT_BREAKER_EV"]:
                cand["audit_flag"] = "HALT_ANOMALY"
            elif cand["ev"] < CONFIG["MIN_EV_THRESHOLD"]:
                cand["audit_flag"] = "NO_EDGE"
            else:
                cand["audit_flag"] = "PASS"

        # Deduplicate: Pick highest risk-adjusted edge per category
        side_cands = [c for c in markets if c["type"] == "SIDE" and c["audit_flag"] == "PASS"]
        filtered_side = [sorted(side_cands, key=lambda x: x["kelly_pct"], reverse=True)[0]] if side_cands else []

        total_cands = [c for c in markets if c["type"] == "TOTAL" and c["audit_flag"] == "PASS"]
        filtered_totals = [sorted(total_cands, key=lambda x: x["kelly_pct"], reverse=True)[0]] if total_cands else []

        fixture_bets = filtered_side + filtered_totals
        for b in fixture_bets:
            b["matchup"] = f"{away} @ {home}"
            all_executable_bets.append(b)

    # Portfolio Slate Risk Cap: Scale stakes if aggregate exceeds cap
    total_unscaled_stake = sum(b["kelly_pct"] for b in all_executable_bets)
    scale_multiplier = 1.0
    if total_unscaled_stake > CONFIG["MAX_SLATE_RISK_PCT"]:
        scale_multiplier = CONFIG["MAX_SLATE_RISK_PCT"] / total_unscaled_stake
        for b in all_executable_bets:
            b["kelly_pct"] *= scale_multiplier

    recs = []
    for b in all_executable_bets:
        # Convert decimal percentage (e.g. 0.015 = 1.5%) to standard unit sizing (1.0% bankroll = 1.0u)
        units = round(b["kelly_pct"] / 0.010, 2)
        recs.append({
            "sport": "EPL",
            "matchup": b["matchup"],
            "market": b["mkt"],
            "pick": b["sel"],
            "fair_odds": prob_to_american(b["fair_p"]),
            "book_odds": decimal_to_american(b["odds"]),
            "ev_percent": round(b["ev"] * 100.0, 1),
            "suggested_stake": max(0.5, units),
            "status": "ACTIVE"
        })

    return recs
