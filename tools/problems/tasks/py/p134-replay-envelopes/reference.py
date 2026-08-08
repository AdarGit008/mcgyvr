def replay_envelopes(envelopes, months):
    order = []
    monthly_of = {}
    cap_of = {}
    balance = {}
    for envelope in envelopes:
        name = envelope["name"]
        monthly = envelope["monthly"]
        cap = envelope["cap"]
        if not isinstance(name, str) or name == "":
            raise ValueError("an envelope name must be a non-empty string")
        if name in monthly_of:
            raise ValueError("duplicate envelope name")
        if not isinstance(monthly, int) or isinstance(monthly, bool) or monthly < 0:
            raise ValueError("monthly must be a non-negative integer")
        if not isinstance(cap, int) or isinstance(cap, bool) or cap < 0:
            raise ValueError("cap must be a non-negative integer")
        order.append(name)
        monthly_of[name] = monthly
        cap_of[name] = cap
        balance[name] = 0
    forfeited = 0
    for month in months:
        for name in order:
            balance[name] += monthly_of[name]
        for name, amount in month:
            if name not in balance:
                raise ValueError("outlay names an unknown envelope")
            if not isinstance(amount, int) or isinstance(amount, bool) or amount < 1:
                raise ValueError("an outlay amount must be a positive integer")
            balance[name] -= amount
        for name in order:
            if balance[name] > cap_of[name]:
                forfeited += balance[name] - cap_of[name]
                balance[name] = cap_of[name]
    return {
        "balances": [[name, balance[name]] for name in order],
        "forfeited": forfeited,
    }
