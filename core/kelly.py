from typing import Dict, Any

MIN_EV_THRESHOLD = 0.018    # 1.8% Net EV minimum
MAX_EV_CEILING = 0.120      # 12.0% circuit breaker ceiling
KELLY_MULTIPLIER = 0.25     # Quarter-Kelly
MAX_UNIT_CAP = 2.50         # Max 2.50 units per game

def evaluate_edge_and_stake(fair_prob: float, market_american_odds: float) -> Dict[str, Any]:
    """
    Evaluates net edge and calculates Quarter-Kelly unit sizing.
    """
    if market_american_odds > 0:
        b = market_american_odds / 100.0
    else:
        b = 100.0 / abs(market_american_odds)
        
    market_implied = 1.0 / (b + 1.0)
    ev = (fair_prob * b) - (1.0 - fair_prob)
    
    # Check circuit breaker and edge thresholds
    if ev < MIN_EV_THRESHOLD or ev > MAX_EV_CEILING:
        return {
            "qualifies": False,
            "ev_percent": round(ev * 100, 2),
            "units": 0.0,
            "reason": "Out of EV bounds" if ev > MAX_EV_CEILING else "Below 1.8% threshold"
        }
        
    # Full Kelly: (bp - q) / b
    q = 1.0 - fair_prob
    full_kelly = (b * fair_prob - q) / b
    
    if full_kelly <= 0:
        return {"qualifies": False, "ev_percent": round(ev * 100, 2), "units": 0.0, "reason": "Negative Kelly"}
        
    staked_units = min(full_kelly * KELLY_MULTIPLIER * 100.0, MAX_UNIT_CAP)
    staked_units = round(staked_units, 2)
    
    return {
        "qualifies": True,
        "ev_percent": round(ev * 100, 2),
        "units": staked_units,
        "market_implied": round(market_implied, 4),
        "fair_prob": round(fair_prob, 4)
    }
