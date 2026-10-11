import math
from typing import Dict, Tuple

def american_to_decimal(american: float) -> float:
    """Converts American odds to decimal odds."""
    if american > 0:
        return (american / 100.0) + 1.0
    else:
        return (100.0 / abs(american)) + 1.0

def decimal_to_american(decimal_odds: float) -> int:
    """Converts decimal odds back to American integer odds."""
    if decimal_odds >= 2.0:
        return int(round((decimal_odds - 1.0) * 100))
    else:
        return int(round(-100.0 / (decimal_odds - 1.0)))

def power_devig_two_way(odds_a: float, odds_b: float) -> Tuple[float, float]:
    """
    Solves for power k such that (1/dec_a)^k + (1/dec_b)^k = 1.0.
    Standardized de-vigging against sharp consensus books (Pinnacle/Circa).
    """
    dec_a = american_to_decimal(odds_a)
    dec_b = american_to_decimal(odds_b)
    
    implied_a = 1.0 / dec_a
    implied_b = 1.0 / dec_b
    total_implied = implied_a + implied_b
    
    if total_implied <= 1.0:
        return implied_a / total_implied, implied_b / total_implied
        
    k = math.log(2.0) / math.log(total_implied * 2.0)
    fair_a = implied_a ** (1.0 / k)
    fair_b = implied_b ** (1.0 / k)
    norm = fair_a + fair_b
    return fair_a / norm, fair_b / norm
