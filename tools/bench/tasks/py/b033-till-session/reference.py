"""One point-of-sale till session, replayed from its events."""

OPEN = "open"
PAYMENT = "payment"
PAID = "paid"
CANCELLED = "cancelled"


def run_till_session(events, prices):
    for name, price in prices.items():
        if isinstance(price, bool) or not isinstance(price, int) or price <= 0:
            raise ValueError("price must be a positive integer: " + str(name))
    cart = {}
    state = OPEN
    total = 0
    paid = 0
    change = 0
    for event in events:
        if not isinstance(event, list) or not event:
            raise ValueError("event must be a non-empty list")
        action = event[0]
        if state in (PAID, CANCELLED):
            raise ValueError("no events after " + state)
        if action in ("scan", "void"):
            if len(event) != 2:
                raise ValueError(str(action) + " takes exactly an item")
            if state != OPEN:
                raise ValueError(str(action) + " is lawful only while open")
            item = event[1]
            if not isinstance(item, str) or item not in prices:
                raise ValueError("item absent from the price list")
            if action == "scan":
                cart[item] = cart.get(item, 0) + 1
            else:
                if item not in cart:
                    raise ValueError("void of an item not in the cart")
                cart[item] -= 1
                if cart[item] == 0:
                    del cart[item]
        elif action == "close":
            if len(event) != 1:
                raise ValueError("close takes no payload")
            if state != OPEN:
                raise ValueError("close is lawful only while open")
            if not cart:
                raise ValueError("close with an empty cart")
            total = sum(cart[name] * prices[name] for name in cart)
            state = PAYMENT
        elif action == "pay":
            if len(event) != 2:
                raise ValueError("pay takes exactly an amount")
            if state != PAYMENT:
                raise ValueError("pay is lawful only during payment")
            amount = event[1]
            if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
                raise ValueError("pay amount must be a positive integer")
            paid += amount
            if paid >= total:
                change = paid - total
                state = PAID
        elif action == "cancel":
            if len(event) != 1:
                raise ValueError("cancel takes no payload")
            state = CANCELLED
        else:
            raise ValueError("unknown action: " + str(action))
    items = [[name, cart[name]] for name in sorted(cart)]
    return {
        "state": state,
        "items": items,
        "total": total,
        "paid": paid,
        "change": change,
    }
