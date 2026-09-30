def money(x):
    sign, x = ("-" if x < 0 else ""), abs(x)
    return f"{sign}${x / 1e6:.2f}M" if x >= 1e6 else f"{sign}${x:,.0f}"


def exposure_label(spend, low_pct, high_pct):
    pcts = sorted(p for p in (low_pct, high_pct) if p is not None and abs(p) <= 50)
    if not pcts:
        return None
    lo, hi = spend * pcts[0] / 100, spend * pcts[-1] / 100
    return money(lo) if lo == hi else f"{money(lo)} to {money(hi)}"
