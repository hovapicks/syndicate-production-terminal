import os
import re
import requests
import datetime
import pytz
import numpy as np
import pandas as pd
from bs4 import BeautifulSoup
from scipy.stats import poisson

ODDS_API_KEYS = [
    os.getenv("ODDS_API_KEY_1", "b57a9742abb4c32ac9bd245ea8ca47ff"),
    os.getenv("ODDS_API_KEY_2", "6c404361bcf2dcf77c92b9b0598674c6"),
    os.getenv("ODDS_API_KEY_3", "9137cefef71eb58610901407cf582c8b"),
    os.getenv("ODDS_API_KEY_4", "0546f5420442d0179ff437806ddd3b6d")
]

LEAGUE_AVG_GPG = 3.11
HFA_GOAL_ADV = 0.11
DIXON_COLES_RHO = -0.11

TEAM_NAME_MAP = {
    "Anaheim Ducks": "ANA", "Boston Bruins": "BOS", "Buffalo Sabres": "BUF",
    "Calgary Flames": "CGY", "Carolina Hurricanes": "CAR", "Chicago Blackhawks": "CHI",
    "Colorado Avalanche": "COL", "Columbus Blue Jackets": "CBJ", "Dallas Stars": "DAL",
    "Detroit Red Wings": "DET", "Edmonton Oilers": "EDM", "Florida Panthers": "FLA",
    "Los Angeles Kings": "LAK", "Minnesota Wild": "MIN", "Montreal Canadiens": "MTL",
    "Nashville Predators": "NSH", "New Jersey Devils": "NJD", "New York Islanders": "NYI",
    "New York Rangers": "NYR", "Ottawa Senators": "OTT", "Philadelphia Flyers": "PHI",
    "Pittsburgh Penguins": "PIT", "San Jose Sharks": "SJS", "Seattle Kraken": "SEA",
    "St. Louis Blues": "STL", "Tampa Bay Lightning": "TBL", "Toronto Maple Leafs": "TOR",
    "Utah Hockey Club": "UTA", "Utah Mammoth": "UTA", "Vancouver Canucks": "VAN",
    "Vegas Golden Knights": "VGK", "Washington Capitals": "WSH", "Winnipeg Jets": "WPG"
}

TEAM_PRIORS = {
    "BOS": {"off": 0.99, "def": 0.88, "g_primary": 0.42, "g_backup": 0.10, "starter": "Swayman", "alt": 0.00},
    "BUF": {"off": 0.97, "def": 1.04, "g_primary": 0.10, "g_backup": -0.12, "starter": "Luukkonen", "alt": 0.00},
    "MTL": {"off": 1.02, "def": 1.04, "g_primary": 0.10, "g_backup": -0.20, "starter": "Montembeault", "alt": 0.00},
    "OTT": {"off": 1.00, "def": 1.06, "g_primary": 0.08, "g_backup": -0.15, "starter": "Ullmark", "alt": 0.00},
    "TBL": {"off": 1.08, "def": 0.96, "g_primary": 0.32, "g_backup": -0.10, "starter": "Vasilevskiy", "alt": 0.00},
    "TOR": {"off": 1.06, "def": 1.02, "g_primary": 0.15, "g_backup": 0.02, "starter": "Stolarz", "alt": 0.00},
    "DET": {"off": 1.01, "def": 1.05, "g_primary": -0.02, "g_backup": -0.18, "starter": "Gibson", "alt": 0.00},
    "FLA": {"off": 1.15, "def": 0.85, "g_primary": 0.35, "g_backup": 0.05, "starter": "Bobrovsky", "alt": 0.00},
    "CAR": {"off": 1.12, "def": 0.81, "g_primary": 0.35, "g_backup": 0.12, "starter": "Kochetkov", "alt": 0.00},
    "NYI": {"off": 0.91, "def": 0.93, "g_primary": 0.44, "g_backup": -0.02, "starter": "Sorokin", "alt": 0.00},
    "PHI": {"off": 0.94, "def": 1.02, "g_primary": 0.00, "g_backup": -0.22, "starter": "Ersson", "alt": 0.00},
    "NYR": {"off": 1.04, "def": 0.90, "g_primary": 0.50, "g_backup": -0.05, "starter": "Shesterkin", "alt": 0.00},
    "NJD": {"off": 1.10, "def": 0.94, "g_primary": 0.05, "g_backup": -0.15, "starter": "Allen", "alt": 0.00},
    "WSH": {"off": 0.96, "def": 1.03, "g_primary": 0.15, "g_backup": -0.08, "starter": "Thompson", "alt": 0.00},
    "PIT": {"off": 0.98, "def": 1.06, "g_primary": 0.05, "g_backup": -0.20, "starter": "Jarry", "alt": 0.00},
    "CBJ": {"off": 0.92, "def": 1.15, "g_primary": 0.02, "g_backup": -0.15, "starter": "Talbot", "alt": 0.00},
    "DAL": {"off": 1.11, "def": 0.86, "g_primary": 0.40, "g_backup": 0.04, "starter": "Oettinger", "alt": 0.00},
    "MIN": {"off": 0.97, "def": 0.96, "g_primary": 0.20, "g_backup": 0.00, "starter": "Gustavsson", "alt": 0.00},
    "NSH": {"off": 1.05, "def": 0.92, "g_primary": 0.38, "g_backup": -0.05, "starter": "Saros", "alt": 0.00},
    "STL": {"off": 0.94, "def": 1.04, "g_primary": 0.18, "g_backup": -0.15, "starter": "Binnington", "alt": 0.00},
    "UTA": {"off": 0.95, "def": 1.05, "g_primary": 0.05, "g_backup": -0.18, "starter": "Ingram", "alt": 0.06},
    "CHI": {"off": 0.84, "def": 1.20, "g_primary": -0.15, "g_backup": -0.45, "starter": "Mrazek", "alt": 0.00},
    "COL": {"off": 1.17, "def": 0.89, "g_primary": 0.36, "g_backup": -0.12, "starter": "Wedgewood", "alt": 0.08},
    "WPG": {"off": 1.02, "def": 0.85, "g_primary": 0.52, "g_backup": -0.05, "starter": "Hellebuyck", "alt": 0.00},
    "CGY": {"off": 0.93, "def": 1.03, "g_primary": 0.12, "g_backup": -0.15, "starter": "Wolf", "alt": 0.04},
    "SJS": {"off": 0.82, "def": 1.25, "g_primary": 0.05, "g_backup": -0.20, "starter": "Askarov", "alt": 0.00},
    "VAN": {"off": 0.96, "def": 1.08, "g_primary": 0.42, "g_backup": -0.10, "starter": "Demko", "alt": 0.00},
    "VGK": {"off": 1.07, "def": 0.90, "g_primary": 0.28, "g_backup": -0.04, "starter": "Hill", "alt": 0.02},
    "EDM": {"off": 1.24, "def": 1.02, "g_primary": 0.25, "g_backup": -0.20, "starter": "Skinner", "alt": 0.00},
    "LAK": {"off": 1.00, "def": 0.89, "g_primary": 0.25, "g_backup": -0.10, "starter": "Kuemper", "alt": 0.00},
    "ANA": {"off": 0.88, "def": 1.18, "g_primary": 0.10, "g_backup": -0.25, "starter": "Dostal", "alt": 0.00},
    "SEA": {"off": 0.95, "def": 0.98, "g_primary": 0.20, "g_backup": -0.10, "starter": "Daccord", "alt": 0.00}
}

def decimal_to_american(dec):
    if dec <= 1.0: return -110
    return int(round((dec - 1.0) * 100)) if dec >= 2.0 else int(round(-100 / (dec - 1.0)))

def american_to_implied(odds):
    return (100.0 / (odds + 100.0)) if odds > 0 else (abs(odds) / (abs(odds) + 100.0))

def devig_power_ratio(odds_a, odds_b):
    p_a_raw = american_to_implied(odds_a)
    p_b_raw = american_to_implied(odds_b)
    overround = p_a_raw + p_b_raw
    if overround <= 1.0:
        return p_a_raw, p_b_raw
    return p_a_raw / overround, p_b_raw / overround

def prob_to_american(p):
    if p <= 0.0001 or p >= 0.9999: return -110
    return int(round(-((p / (1.0 - p)) * 100))) if p >= 0.5 else int(round(((1.0 - p) / p) * 100))

def half_kelly(fair_p, market_odds):
    b = (market_odds / 100.0) if market_odds > 0 else (100.0 / abs(market_odds))
    q = 1.0 - fair_p
    f = (b * fair_p - q) / b
    return round(max(0.0, min(3.0, (f / 2.0) * 100.0)), 2)

def tau_dixon_coles(x, y, lambda_h, lambda_a, rho=DIXON_COLES_RHO):
    if x == 0 and y == 0:
        return 1.0 - (lambda_h * lambda_a * rho)
    elif x == 0 and y == 1:
        return 1.0 + (lambda_h * rho)
    elif x == 1 and y == 0:
        return 1.0 + (lambda_a * rho)
    elif x == 1 and y == 1:
        return 1.0 - rho
    else:
        return 1.0

def fetch_nhl_schedule(date_str):
    url = f"https://api-web.nhle.com/v1/schedule/{date_str}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=12)
        if r.status_code == 200:
            data = r.json()
            for day_block in data.get("gameWeek", []):
                if day_block.get("date") == date_str:
                    return day_block.get("games", [])
    except Exception:
        pass
    return []

def fetch_automated_starting_goalies(today_games):
    goalie_registry = {}
    dfo_url = "https://www.dailyfaceoff.com/starting-goalies"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        resp = requests.get(dfo_url, headers=headers, timeout=8)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.content, "html.parser")
            cards = soup.find_all("div", class_=re.compile("starting-goalies|goalie-card|matchup", re.I))
            for card in cards:
                card_text = card.get_text()
                for team_name, tricode in TEAM_NAME_MAP.items():
                    if team_name in card_text or f" {tricode} " in card_text:
                        names = re.findall(r"([A-Z][a-z]+(?:\s[A-Z][a-z]+)+)", card_text)
                        for full_name in names:
                            last_name = full_name.split()[-1]
                            primary_starter = TEAM_PRIORS.get(tricode, {}).get("starter", "")
                            if last_name.lower() not in [team_name.split()[-1].lower(), "faceoff"]:
                                is_backup = (last_name.lower() != primary_starter.lower())
                                goalie_registry[tricode] = {
                                    "name": last_name,
                                    "is_backup": is_backup
                                }
                                break
    except Exception:
        pass

    for g in today_games:
        h_abbr = g.get("homeTeam", {}).get("abbrev")
        a_abbr = g.get("awayTeam", {}).get("abbrev")
        for tricode in [h_abbr, a_abbr]:
            if tricode and tricode not in goalie_registry:
                prim = TEAM_PRIORS.get(tricode, {}).get("starter", "Starter")
                goalie_registry[tricode] = {"name": prim, "is_backup": False}
    return goalie_registry

def fetch_nhl_odds(api_keys):
    url = "https://api.the-odds-api.com/v4/sports/icehockey_nhl/odds/"
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
                        h_abbr, a_abbr = TEAM_NAME_MAP.get(h_raw), TEAM_NAME_MAP.get(a_raw)
                        if not h_abbr or not a_abbr: continue
                        matchup_key = f"{a_abbr}@{h_abbr}"

                        sharp_h_ml, sharp_a_ml = None, None
                        all_h_mls, all_a_mls = [], []
                        h_pls, a_pls, tots, over_js, under_js = [], [], [], [], []

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
                                        if out.get("name") == h_raw and abs(abs(pt) - 1.5) < 0.01: h_pls.append(pr)
                                        elif out.get("name") == a_raw and abs(abs(pt) - 1.5) < 0.01: a_pls.append(pr)
                                elif m_key == "totals":
                                    for out in mkt.get("outcomes", []):
                                        tots.append(out.get("point"))
                                        pr = decimal_to_american(out.get("price"))
                                        if out.get("name") == "Over": over_js.append(pr)
                                        elif out.get("name") == "Under": under_js.append(pr)

                        if all_h_mls and all_a_mls:
                            final_h_ml = sharp_h_ml if sharp_h_ml else int(np.median(all_h_mls))
                            final_a_ml = sharp_a_ml if sharp_a_ml else int(np.median(all_a_mls))
                            med_h_pl = int(np.median(h_pls)) if h_pls else (+172 if final_h_ml < final_a_ml else -208)
                            med_a_pl = int(np.median(a_pls)) if a_pls else (-208 if final_h_ml < final_a_ml else +172)
                            med_tot = float(np.median(tots)) if tots else 6.0
                            med_o = int(np.median(over_js)) if over_js else -110
                            med_u = int(np.median(under_js)) if under_js else -110
                            odds_map[matchup_key] = (final_a_ml, final_h_ml, med_a_pl, med_h_pl, med_tot, med_o, med_u)
                    if odds_map: return odds_map
        except Exception:
            pass
    return {}

def simulate_dixon_coles(home, away, h_b2b, a_b2b, mkt_tot, crease_map):
    h = TEAM_PRIORS.get(home, {"off": 1.0, "def": 1.0, "g_primary": 0.0, "g_backup": 0.0, "alt": 0.0, "starter": "Starter"})
    a = TEAM_PRIORS.get(away, {"off": 1.0, "def": 1.0, "g_primary": 0.0, "g_backup": 0.0, "alt": 0.0, "starter": "Starter"})

    h_info = crease_map.get(home, {"name": h["starter"], "is_backup": False})
    a_info = crease_map.get(away, {"name": a["starter"], "is_backup": False})

    h_gsax = h["g_backup"] if h_info["is_backup"] else h["g_primary"]
    a_gsax = a["g_backup"] if a_info["is_backup"] else a["g_primary"]

    h_fatigue = -0.15 if h_b2b else 0.0
    a_fatigue = -0.18 if a_b2b else 0.0

    lh = max(1.2, LEAGUE_AVG_GPG * h["off"] * a["def"] + HFA_GOAL_ADV + h.get("alt", 0.0) - a_gsax + h_fatigue)
    la = max(1.2, LEAGUE_AVG_GPG * a["off"] * h["def"] - h_gsax + a_fatigue)

    max_g = 11
    grid = np.zeros((max_g, max_g))
    for x in range(max_g):
        for y in range(max_g):
            p_indep = poisson.pmf(x, lh) * poisson.pmf(y, la)
            grid[x, y] = p_indep * tau_dixon_coles(x, y, lh, la)

    grid = grid / np.sum(grid)

    # Empty-Net Goal Markov State Adjustment (+31.5% Transition Rate)
    adjusted_grid = grid.copy()
    ENG_TRANSITION_RATE = 0.315
    for x in range(max_g - 1):
        for y in range(max_g - 1):
            if x - y == 1:
                shift = adjusted_grid[x, y] * ENG_TRANSITION_RATE
                adjusted_grid[x, y] -= shift
                adjusted_grid[x + 1, y] += shift
            elif y - x == 1:
                shift = adjusted_grid[x, y] * ENG_TRANSITION_RATE
                adjusted_grid[x, y] -= shift
                adjusted_grid[x, y + 1] += shift

    hw_reg = float(np.sum(np.tril(adjusted_grid, -1)))
    tie_reg = float(np.sum(np.diag(adjusted_grid)))
    ot_h = 0.50 + 0.05 * (h["off"] - a["off"])
    h_ml_p = hw_reg + (tie_reg * ot_h)
    a_ml_p = 1.0 - h_ml_p

    h_minus_15_p = sum(adjusted_grid[hg, ag] for hg in range(max_g) for ag in range(max_g) if hg - ag >= 2)
    a_plus_15_p = 1.0 - h_minus_15_p
    a_minus_15_p = sum(adjusted_grid[hg, ag] for hg in range(max_g) for ag in range(max_g) if ag - hg >= 2)
    h_plus_15_p = 1.0 - a_minus_15_p

    prob_u = sum(adjusted_grid[hg, ag] for hg in range(max_g) for ag in range(max_g) if hg + ag < mkt_tot)
    prob_push = sum(adjusted_grid[hg, ag] for hg in range(max_g) for ag in range(max_g) if hg + ag == mkt_tot)
    prob_o = sum(adjusted_grid[hg, ag] for hg in range(max_g) for ag in range(max_g) if hg + ag > mkt_tot)
    denom = max(0.0001, 1.0 - prob_push)

    return {
        "h_ml_p": h_ml_p, "a_ml_p": a_ml_p,
        "h_minus_15_p": h_minus_15_p, "a_plus_15_p": a_plus_15_p,
        "a_minus_15_p": a_minus_15_p, "h_plus_15_p": h_plus_15_p,
        "fair_o_p": prob_o / denom, "fair_u_p": prob_u / denom,
        "h_starter": h_info["name"], "a_starter": a_info["name"]
    }

def generate_nhl_recommendations():
    tz = pytz.timezone("US/Eastern")
    today_str = datetime.datetime.now(tz).strftime("%Y-%m-%d")
    yesterday_str = (datetime.datetime.now(tz) - datetime.timedelta(days=1)).strftime("%Y-%m-%d")

    yesterday_games = fetch_nhl_schedule(yesterday_str)
    b2b_teams = {g.get("homeTeam", {}).get("abbrev") for g in yesterday_games} | {g.get("awayTeam", {}).get("abbrev") for g in yesterday_games}

    today_games = fetch_nhl_schedule(today_str)
    if not today_games:
        return []

    crease_map = fetch_automated_starting_goalies(today_games)
    odds_feed = fetch_nhl_odds(ODDS_API_KEYS)

    recs = []

    for g in today_games:
        h_abbr = g.get("homeTeam", {}).get("abbrev")
        a_abbr = g.get("awayTeam", {}).get("abbrev")
        matchup_key = f"{a_abbr}@{h_abbr}"

        if matchup_key in odds_feed:
            a_ml, h_ml, a_pl, h_pl, tot, o_j, u_j = odds_feed[matchup_key]
        else:
            continue

        h_b2b = h_abbr in b2b_teams
        a_b2b = a_abbr in b2b_teams

        sim = simulate_dixon_coles(h_abbr, a_abbr, h_b2b, a_b2b, tot, crease_map)
        fair_mkt_a, fair_mkt_h = devig_power_ratio(a_ml, h_ml)

        # 1. Moneyline Evaluation
        eh_ml = (sim["h_ml_p"] - fair_mkt_h) * 100.0
        ea_ml = (sim["a_ml_p"] - fair_mkt_a) * 100.0

        if eh_ml >= 2.5 and eh_ml >= ea_ml:
            stake = half_kelly(sim["h_ml_p"], h_ml)
            recs.append({
                "sport": "NHL",
                "matchup": f"{a_abbr} @ {h_abbr}",
                "market": "Moneyline",
                "pick": f"{h_abbr} ML",
                "fair_odds": prob_to_american(sim["h_ml_p"]),
                "book_odds": h_ml,
                "ev_percent": round(eh_ml, 1),
                "suggested_stake": stake if stake > 0 else 1.0,
                "status": "ACTIVE"
            })
        elif ea_ml >= 2.5 and ea_ml > eh_ml:
            stake = half_kelly(sim["a_ml_p"], a_ml)
            recs.append({
                "sport": "NHL",
                "matchup": f"{a_abbr} @ {h_abbr}",
                "market": "Moneyline",
                "pick": f"{a_abbr} ML",
                "fair_odds": prob_to_american(sim["a_ml_p"]),
                "book_odds": a_ml,
                "ev_percent": round(ea_ml, 1),
                "suggested_stake": stake if stake > 0 else 1.0,
                "status": "ACTIVE"
            })

        # 2. Puck Line Evaluation
        is_home_fav = h_ml <= a_ml
        if is_home_fav:
            edge_h_minus = (sim["h_minus_15_p"] - american_to_implied(h_pl)) * 100.0
            edge_a_plus = (sim["a_plus_15_p"] - american_to_implied(a_pl)) * 100.0
            if edge_h_minus >= 2.5 and edge_h_minus >= edge_a_plus:
                stake = half_kelly(sim["h_minus_15_p"], h_pl)
                recs.append({
                    "sport": "NHL",
                    "matchup": f"{a_abbr} @ {h_abbr}",
                    "market": "Puck Line",
                    "pick": f"{h_abbr} -1.5",
                    "fair_odds": prob_to_american(sim["h_minus_15_p"]),
                    "book_odds": h_pl,
                    "ev_percent": round(edge_h_minus, 1),
                    "suggested_stake": stake if stake > 0 else 1.0,
                    "status": "ACTIVE"
                })
            elif edge_a_plus >= 2.5 and edge_a_plus > edge_h_minus:
                stake = half_kelly(sim["a_plus_15_p"], a_pl)
                recs.append({
                    "sport": "NHL",
                    "matchup": f"{a_abbr} @ {h_abbr}",
                    "market": "Puck Line",
                    "pick": f"{a_abbr} +1.5",
                    "fair_odds": prob_to_american(sim["a_plus_15_p"]),
                    "book_odds": a_pl,
                    "ev_percent": round(edge_a_plus, 1),
                    "suggested_stake": stake if stake > 0 else 1.0,
                    "status": "ACTIVE"
                })
        else:
            edge_a_minus = (sim["a_minus_15_p"] - american_to_implied(a_pl)) * 100.0
            edge_h_plus = (sim["h_plus_15_p"] - american_to_implied(h_pl)) * 100.0
            if edge_a_minus >= 2.5 and edge_a_minus >= edge_h_plus:
                stake = half_kelly(sim["a_minus_15_p"], a_pl)
                recs.append({
                    "sport": "NHL",
                    "matchup": f"{a_abbr} @ {h_abbr}",
                    "market": "Puck Line",
                    "pick": f"{a_abbr} -1.5",
                    "fair_odds": prob_to_american(sim["a_minus_15_p"]),
                    "book_odds": a_pl,
                    "ev_percent": round(edge_a_minus, 1),
                    "suggested_stake": stake if stake > 0 else 1.0,
                    "status": "ACTIVE"
                })
            elif edge_h_plus >= 2.5 and edge_h_plus > edge_a_minus:
                stake = half_kelly(sim["h_plus_15_p"], h_pl)
                recs.append({
                    "sport": "NHL",
                    "matchup": f"{a_abbr} @ {h_abbr}",
                    "market": "Puck Line",
                    "pick": f"{h_abbr} +1.5",
                    "fair_odds": prob_to_american(sim["h_plus_15_p"]),
                    "book_odds": h_pl,
                    "ev_percent": round(edge_h_plus, 1),
                    "suggested_stake": stake if stake > 0 else 1.0,
                    "status": "ACTIVE"
                })

        # 3. Totals Evaluation
        eo = (sim["fair_o_p"] - american_to_implied(o_j)) * 100.0
        eu = (sim["fair_u_p"] - american_to_implied(u_j)) * 100.0
        if eo >= 2.5:
            stake = half_kelly(sim["fair_o_p"], o_j)
            recs.append({
                "sport": "NHL",
                "matchup": f"{a_abbr} @ {h_abbr}",
                "market": "Total",
                "pick": f"OVER {tot}",
                "fair_odds": prob_to_american(sim["fair_o_p"]),
                "book_odds": o_j,
                "ev_percent": round(eo, 1),
                "suggested_stake": stake if stake > 0 else 1.0,
                "status": "ACTIVE"
            })
        elif eu >= 2.5:
            stake = half_kelly(sim["fair_u_p"], u_j)
            recs.append({
                "sport": "NHL",
                "matchup": f"{a_abbr} @ {h_abbr}",
                "market": "Total",
                "pick": f"UNDER {tot}",
                "fair_odds": prob_to_american(sim["fair_u_p"]),
                "book_odds": u_j,
                "ev_percent": round(eu, 1),
                "suggested_stake": stake if stake > 0 else 1.0,
                "status": "ACTIVE"
            })

    return recs
