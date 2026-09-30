from datetime import timedelta

RULES = [("on_time_delivery", "<", 95, "On-time delivery"), ("fill_rate", "<", 96, "Fill rate"),
         ("internal_cost_delta", ">", 1.0, "Internal cost Δ")]


def kpi_status(s):
    flags = [f"{label} {s[k]}% {op} {limit}%" for k, op, limit, label in RULES
             if (s[k] < limit if op == "<" else s[k] > limit)]
    return ("Normal", "Watch", "Elevated", "Elevated")[len(flags)], flags


def third_party_feed(s, today):
    last = today.replace(day=1) if today.day != 1 else (today - timedelta(days=1)).replace(day=1)
    nxt = (last + timedelta(days=32)).replace(day=1)
    return {"rating": s["third_party_rating"], "last": last, "next": nxt, "age_days": (today - last).days}
