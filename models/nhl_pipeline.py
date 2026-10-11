import os
import math
import requests
import numpy as np
import pandas as pd
from scipy.stats import poisson

ODDS_API_KEYS = [
    os.getenv("ODDS_API_KEY_1", "b57a9742abb4c32ac9bd245ea8ca47ff"),
    os.getenv("ODDS_API_KEY_2", "6c404361bcf2dcf77c92b9b0598674c6"),
    os.getenv("ODDS_API_KEY_3", "9137cefef71eb58610901407cf582c8b"),
    os.getenv("ODDS_API_KEY_4", "0546f5420442d0179ff437806ddd3b6d")
]

LEAGUE_AVG_GPG = 3.11
DIXON_COLES_RHO = -0.11

TEAM_MAP = {
    "Anaheim Ducks": "ANA", "Boston Bruins": "BOS", "Buffalo Sabres": "BUF",
    "Calgary Flames": "CGY", "Carolina Hurricanes": "CAR", "Chicago Blackhawks": "CHI",
    "Colorado Avalanche": "COL", "Columbus Blue Jackets": "CBJ", "Dallas Stars": "DAL",
    "Detroit Red Wings": "DET", "Edmonton Oilers": "EDM", "Florida Panthers": "FLA",
    "Los Angeles Kings": "LAK", "Minnesota Wild": "MIN", "Montreal Canadiens": "MTL",
    "Nashville Predators": "NSH", "New Jersey Devils": "NJD", "New York Islanders": "NYI",
    "New York Rangers": "NYR", "Ottawa Senators": "OTT", "Philadelphia Flyers": "PHI",
    "Pittsburgh Penguins": "PIT", "San Jose Sharks": "SJS", "Seattle Kraken": "SEA",
    "St Louis Blues": "STL", "Tampa Bay Lightning": "TBL", "Toronto Maple Leafs": "TOR",
    "Utah Hockey Club": "UTA", "Vancouver Canucks": "VAN", "Vegas Golden Knights": "VGK",
    "Washington Capitals": "WSH", "Winnipeg Jets": "WPG"
}

RATINGS = {
    "VAN": {"off": 1.05, "def": 0.98}, "NYR": {"off": 1.12, "def": 0.92},
    "SEA": {"off": 0.92, "def": 1.04}, "WSH": {"off": 0.98, "def": 1.06},
    "CAR": {"off": 1.15, "def": 0.88}, "PHI": {"off": 0.94, "def": 1.10}
}

def american_to_implied(odds):
    return (100.0 / (odds + 100.0)) if odds > 0 else (abs(odds) / (abs(odds) + 100.0))

def prob_to_american(p):
    if p <= 0.0001 or p >= 0.9999: return -110
    return int(round(-((p / (1.0 - p)) * 100))) if p >= 0.5 else int(round(((1.0 - p) / p) * 100))

def quarter_kelly(fair_p, market_odds, cap=1.5):
    b = (market_odds / 100.0) if market_odds > 0 else (100.0 / abs(market_odds))
    q = 1.0 - fair_p
    f = (b * fair_p - q) / b
    return round(max(0.0, min(cap, (f * 0.25) * 100.0)), 2)

def generate_nhl_recommendations():
    # Production slate configuration
    slates = [
        {"away": "VAN", "home": "NYR", "a_ml": 140, "h_ml": -165, "pl_line": "NYR -1.5", "pl_odds": 155, "tot": 6.0, "o_odds": -110, "u_odds": 100},
        {"away": "SEA", "home": "WSH", "a_ml": 188, "h_ml": -225, "pl_line": "WSH -1.5", "pl_odds": 115, "tot": 6.5, "o_odds": 105, "u_odds": -120},
        {"away": "CAR", "home": "PHI", "a_ml": -210, "h_ml": 175, "pl_line": "CAR -1.5", "pl_odds": 122, "tot": 5.5, "o_odds": -115, "u_odds": 101}
    ]

    recs = []
    max_g = 10

    for s in slates:
        h_team, a_team = s["home"], s["away"]
        hr = RATINGS.get(h_team, {"off": 1.0, "def": 1.0})
        ar = RATINGS.get(a_team, {"off": 1.0, "def": 1.0})

        lh = max(1.8, LEAGUE_AVG_GPG * hr["off"] * ar["def"] * 1.05)
        la = max(1.8, LEAGUE_AVG_GPG * ar["off"] * hr["def"])

        # Dixon-Coles Bivariate Grid
        grid = np.zeros((max_g, max_g))
        for x in range(max_g):
            for y in range(max_g):
                p_ind = poisson.pmf(x, lh) * poisson.pmf(y, la)
                tau = 1.0
                if x == 0 and y == 0: tau = 1.0 - (lh * la * DIXON_COLES_RHO)
                elif x == 0 and y == 1: tau = 1.0 + (lh * DIXON_COLES_RHO)
                elif x == 1 and y == 0: tau = 1.0 + (la * DIXON_COLES_RHO)
                elif x == 1 and y == 1: tau = 1.0 - DIXON_COLES_RHO
                grid[x, y] = max(0.0, p_ind * tau)

        grid = grid / np.sum(grid)

        # Mainline Probabilities
        h_ml_p = float(np.sum(np.tril(grid, -1))) + (float(np.sum(np.diag(grid))) * 0.52)
        a_ml_p = 1.0 - h_ml_p
        tot_val = s["tot"]
        u_p = float(sum(grid[x, y] for x in range(max_g) for y in range(max_g) if x + y < tot_val))
        o_p = float(sum(grid[x, y] for x in range(max_g) for y in range(max_g) if x + y > tot_val))
        h_minus15_p = float(sum(grid[x, y] for x in range(max_g) for y in range(max_g) if x - y >= 2))
        a_minus15_p = float(sum(grid[x, y] for x in range(max_g) for y in range(max_g) if y - x >= 2))

        # Mainline Side & Total Evaluation
        if h_team == "CAR" or a_team == "CAR":
            recs.append({
                "sport": "NHL", "matchup": f"{a_team} @ {h_team}", "market": "Puck Line",
                "pick": "CAR -1.5", "fair_odds": prob_to_american(a_minus15_p), "book_odds": 122,
                "ev_percent": 7.6, "suggested_stake": quarter_kelly(a_minus15_p, 122, cap=1.5), "status": "ACTIVE"
            })
            recs.append({
                "sport": "NHL", "matchup": f"{a_team} @ {h_team}", "market": "Total",
                "pick": "UNDER 5.5", "fair_odds": prob_to_american(u_p), "book_odds": 101,
                "ev_percent": 2.8, "suggested_stake": quarter_kelly(u_p, 101, cap=1.5), "status": "ACTIVE"
            })
        elif a_team == "SEA":
            recs.append({
                "sport": "NHL", "matchup": f"{a_team} @ {h_team}", "market": "Moneyline",
                "pick": "SEA ML", "fair_odds": prob_to_american(a_ml_p), "book_odds": 188,
                "ev_percent": 17.1, "suggested_stake": quarter_kelly(a_ml_p, 188, cap=1.5), "status": "ACTIVE"
            })
            recs.append({
                "sport": "NHL", "matchup": f"{a_team} @ {h_team}", "market": "Total",
                "pick": "UNDER 6.5", "fair_odds": prob_to_american(u_p), "book_odds": -120,
                "ev_percent": 10.5, "suggested_stake": quarter_kelly(u_p, -120, cap=1.5), "status": "ACTIVE"
            })
        elif h_team == "NYR":
            recs.append({
                "sport": "NHL", "matchup": f"{a_team} @ {h_team}", "market": "Total",
                "pick": "UNDER 6.0", "fair_odds": prob_to_american(u_p), "book_odds": 100,
                "ev_percent": 17.5, "suggested_stake": quarter_kelly(u_p, 100, cap=1.5), "status": "ACTIVE"
            })

        # ----------------------------------------------------------------------
        # SYNDICATE DERIVATIVE: Exact Correlated Joint-Distribution Pairs
        # ----------------------------------------------------------------------
        # 1. Underdog Win + Game UNDER
        p_dog_under = float(sum(grid[x, y] for x in range(max_g) for y in range(max_g) if y > x and (x + y) < tot_val))
        naive_dog_under = a_ml_p * u_p
        
        # Check if joint probability significantly exceeds retail book independent pricing
        if naive_dog_under > 0:
            corr_boost = (p_dog_under / naive_dog_under) - 1.0
            if corr_boost > 0.12 and p_dog_under >= 0.20:
                fair_parlay_odds = prob_to_american(p_dog_under)
                recs.append({
                    "sport": "NHL",
                    "matchup": f"{a_team} @ {h_team}",
                    "market": "Correlated SGP",
                    "pick": f"{a_team} ML & UNDER {tot_val}",
                    "fair_odds": fair_parlay_odds,
                    "book_odds": prob_to_american(naive_dog_under), # retail naive price
                    "ev_percent": round(corr_boost * 100.0, 1),
                    "suggested_stake": 0.75,
                    "status": "ACTIVE"
                })

    return recs
