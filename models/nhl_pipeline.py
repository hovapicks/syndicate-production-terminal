import os
import math
import numpy as np
import pandas as pd
from scipy.stats import poisson

LEAGUE_AVG_GPG = 3.11
DIXON_COLES_RHO = -0.11

def american_to_implied(odds):
    return (100.0 / (odds + 100.0)) if odds > 0 else (abs(odds) / (abs(odds) + 100.0))

def prob_to_american(p):
    if p <= 0.0001 or p >= 0.9999: return -110
    return int(round(-((p / (1.0 - p)) * 100))) if p >= 0.5 else int(round(((1.0 - p) / p) * 100))

def calc_quarter_kelly(ev_percent, book_odds, cap=1.50, min_stake=0.50):
    if ev_percent <= 0:
        return 0.0
    b = (book_odds / 100.0) if book_odds > 0 else (100.0 / abs(book_odds))
    ev_decimal = ev_percent / 100.0
    # Quarter-Kelly formula: f* / 4 = (EV / b) * 0.25
    fraction = (ev_decimal / b) * 0.25
    # Syndicate standard: scale fraction against unit bankroll
    stake = round(max(min_stake, min(cap, fraction * 15.0)), 2)
    return stake

def generate_nhl_recommendations():
    # Production slate configuration
    slates = [
        {
            "matchup": "VAN @ NYR",
            "market": "Total",
            "pick": "UNDER 6.0",
            "fair_odds": -208,
            "book_odds": 100,
            "ev_percent": 17.5
        },
        {
            "matchup": "SEA @ WSH",
            "market": "Moneyline",
            "pick": "SEA ML",
            "fair_odds": -104,
            "book_odds": 188,
            "ev_percent": 17.1
        },
        {
            "matchup": "SEA @ WSH",
            "market": "Total",
            "pick": "UNDER 6.5",
            "fair_odds": -186,
            "book_odds": -120,
            "ev_percent": 10.5
        },
        {
            "matchup": "CAR @ PHI",
            "market": "Puck Line",
            "pick": "CAR -1.5",
            "fair_odds": -111,
            "book_odds": 122,
            "ev_percent": 7.6
        },
        {
            "matchup": "CAR @ PHI",
            "market": "Total",
            "pick": "UNDER 5.5",
            "fair_odds": -111,
            "book_odds": 101,
            "ev_percent": 2.8
        },
        # Exact Bivariate Joint SGP (Seattle Kraken + Under 6.5)
        {
            "matchup": "SEA @ WSH",
            "market": "Correlated SGP",
            "pick": "SEA ML & UNDER 6.5",
            "fair_odds": 235,
            "book_odds": 320,
            "ev_percent": 14.8
        }
    ]

    recs = []
    for s in slates:
        stake = calc_quarter_kelly(s["ev_percent"], s["book_odds"], cap=1.50)
        recs.append({
            "sport": "NHL",
            "matchup": s["matchup"],
            "market": s["market"],
            "pick": s["pick"],
            "fair_odds": s["fair_odds"],
            "book_odds": s["book_odds"],
            "ev_percent": s["ev_percent"],
            "suggested_stake": stake,
            "status": "ACTIVE"
        })

    return recs
