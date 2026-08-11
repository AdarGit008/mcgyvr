def receipt_net(lines: list) -> int:
    net = 0
    for line in lines:
        if not line["voided"]:
            net += line["amount"]
    return net
