"""V4.1 defensive exit rules. Signals are evaluated at completed closes only.

HYBRID_D: (a) 3 consecutive closes below MA50, negative ROC20, and
MA50 rolling over vs 5 sessions earlier; OR (b) 3 closes below MA250.
The MA250 fallback remains active even if the faster condition is absent.
No intraday stop claims: all orders fill at the next available open.
"""

BASELINE = "MA250_3CLOSE"
HYBRID = "HYBRID_D"


def exit_trigger(prior, rule):
    if rule == "MA250_3CLOSE":
        return bool(prior.below3)
    if rule == "MA250_ATR3":
        return bool(prior.belowatr3)
    if rule == HYBRID:
        return bool(prior.below3 or prior.defensive_ma50)
    raise ValueError(f"Unknown exit rule: {rule}")


def exit_reason(prior, rule):
    if not exit_trigger(prior, rule):
        return ""
    if rule == HYBRID and bool(prior.defensive_ma50):
        return "HYBRID_D: MA50 3-close + negative ROC20 + falling MA50"
    if bool(prior.below3):
        return "MA250: 3 closes below"
    return "MA250 ATR-buffer: 3 closes below"
