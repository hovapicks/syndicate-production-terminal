from typing import Dict

# Empirical push probabilities across historical NFL and CFB game margins
NFL_PUSH_PROBS: Dict[float, float] = {
    3.0: 0.148,
    7.0: 0.092,
    6.0: 0.058,
    4.0: 0.052,
    10.0: 0.048,
    14.0: 0.041
}

CFB_PUSH_PROBS: Dict[float, float] = {
    3.0: 0.091,
    7.0: 0.076,
    4.0: 0.042,
    6.0: 0.040,
    10.0: 0.038,
    14.0: 0.035
}

def get_push_probability(spread: float, sport: str = "NFL") -> float:
    """Returns discrete push probability if the line lands on a whole number."""
    abs_spread = abs(round(spread, 1))
    chart = NFL_PUSH_PROBS if sport.upper() == "NFL" else CFB_PUSH_PROBS
    return chart.get(abs_spread, 0.015 if abs_spread.is_integer() else 0.0)
