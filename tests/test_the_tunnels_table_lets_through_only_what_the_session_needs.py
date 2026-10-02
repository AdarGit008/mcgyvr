"""The tunnel's table lets through only what the session needs, at each step.

The tunnel container's namespace starts closed: every chain drops, loopback
aside, and the chains the session's steps fill start empty. While the port
asks the hub's responders where it is seen from, only those responders,
from and to that port, are let through. When the tunnel comes up, the
responders' rules go, and each peer's WireGuard packets may come from and go
to the address being tried, and nothing else; once a path is confirmed, only
that endpoint, port and all, or the relay. Every table is written in one
transaction before WireGuard is pointed anywhere, so its first packet is
never the one the table drops.

The scripts run here as they run in the tunnel, under ``sh``, with ``nft``,
``wg`` and ``ip`` stood in for by recorders, so what is asserted is the very
ruleset the kernel would be handed and the order of every call.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

KEY = "B" * 42 + "g="
OTHER_KEY = "C" * 42 + "g="
STUN = "203.0.113.9"
PEER = "192.0.2.20"
RELAY = "203.0.113.50"


def _stubs(folder: Path) -> dict[str, str]:
    log = folder / "calls.log"
    for name in ("nft", "wg", "ip"):
        stub = folder / name
        body = f'echo "{name} $*" >> "{log}"\n'
        if name == "nft":
            body += f'cat >> "{folder}/nft.rules"\n'
        stub.write_text("#!/bin/sh\n" + body)
        stub.chmod(0o755)
    return {"PATH": f"{folder}:{os.environ['PATH']}"}


def _run(tmp_path: Path, script: str, *args: str) -> tuple[list[str], list[str]]:
    env = _stubs(tmp_path)
    subprocess.run(
        ["sh", "-c", script, "mcgyvr", *args],
        env=env,
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    )
    calls = (tmp_path / "calls.log").read_text().splitlines()
    rules = (tmp_path / "nft.rules").read_text().splitlines()
    return calls, [" ".join(line.split()) for line in rules if line.strip()]


def _accepts_name_an_address(rules: list[str]) -> None:
    for rule in rules:
        if rule.endswith("accept"):
            assert re.search(r"ip [sd]addr \d", rule), rule


def test_the_namespace_starts_closed_with_its_step_chains_empty() -> None:
    from mcgyvr.sandbox import pooled

    table = pooled.TUNNEL_ENTRY.split("<<'RULES'\n")[1].split("RULES\n")[0]
    assert " ".join(table.split()) == " ".join(
        (
            "table inet mcgyvr {",
            "chain stun_in { } chain stun_out { } chain wg_in { } chain wg_out { }",
            "chain input { type filter hook input priority 0; policy drop;",
            'iif "lo" accept jump stun_in jump wg_in }',
            "chain output { type filter hook output priority 0; policy drop;",
            'oif "lo" accept jump stun_out jump wg_out }',
            "chain forward { type filter hook forward priority 0; policy drop; }",
            "}",
        )
    )
    # WireGuard does not take the port before the tunnel comes up.
    assert "listen-port" not in pooled.TUNNEL_ENTRY


def test_the_responders_alone_are_let_through_while_the_port_asks_them(
    tmp_path: Path,
) -> None:
    from mcgyvr.sandbox import pooled

    calls, rules = _run(tmp_path, pooled.STUN_SCRIPT, "51820", STUN, "3478")
    assert calls == ["nft -f -"]
    assert rules == [
        "flush chain inet mcgyvr stun_in",
        "flush chain inet mcgyvr stun_out",
        f"add rule inet mcgyvr stun_out oifname eth0 ip daddr {STUN} "
        "udp sport 51820 udp dport 3478 accept",
        f"add rule inet mcgyvr stun_in iifname eth0 ip saddr {STUN} "
        "udp sport 3478 udp dport 51820 accept",
    ]


def test_coming_up_drops_the_responders_and_lets_each_peer_reach_only_its_aim(
    tmp_path: Path,
) -> None:
    from mcgyvr.sandbox import pooled

    calls, rules = _run(
        tmp_path,
        pooled.TUNNEL_SCRIPT,
        "198.51.100.2/24",
        "51820",
        KEY,
        PEER,
        "51820",
        "25",
        "198.51.100.1/32",
        OTHER_KEY,
        "-",
        "0",
        "25",
        "198.51.100.3/32",
    )
    assert rules[:4] == [
        "flush chain inet mcgyvr stun_in",
        "flush chain inet mcgyvr stun_out",
        "flush chain inet mcgyvr wg_in",
        "flush chain inet mcgyvr wg_out",
    ]
    wireguard = [r for r in rules if " wg_in " in r or " wg_out " in r]
    assert wireguard == [
        f"add rule inet mcgyvr wg_in iifname eth0 ip saddr {PEER} "
        "udp dport 51820 accept",
        f"add rule inet mcgyvr wg_out oifname eth0 ip daddr {PEER} "
        "udp sport 51820 accept",
    ]
    _accepts_name_an_address(rules)
    assert calls[0] == "nft -f -"
    assert calls[1] == "wg set wg0 listen-port 51820"
    assert (
        f"wg set wg0 peer {KEY} allowed-ips 198.51.100.1/32 endpoint {PEER}:51820 "
        "persistent-keepalive 25"
    ) in calls
    assert (
        f"wg set wg0 peer {OTHER_KEY} allowed-ips 198.51.100.3/32 "
        "persistent-keepalive 25"
    ) in calls
    script = pooled.TUNNEL_SCRIPT
    assert script.index("stun.pid") < script.index("listen-port")


def test_a_confirmed_path_is_held_to_its_endpoint_and_a_moved_peer_alone_is_pointed(
    tmp_path: Path,
) -> None:
    from mcgyvr.sandbox import pooled

    calls, rules = _run(
        tmp_path,
        pooled.PATH_SCRIPT,
        "51820",
        KEY,
        RELAY,
        "40001",
        "exact",
        "0",
        OTHER_KEY,
        PEER,
        "40000",
        "host",
        "1",
        "D" * 42 + "g=",
        "-",
        "0",
        "host",
        "0",
    )
    assert rules == [
        "flush chain inet mcgyvr wg_in",
        "flush chain inet mcgyvr wg_out",
        f"add rule inet mcgyvr wg_in iifname eth0 ip saddr {RELAY} "
        "udp sport 40001 udp dport 51820 accept",
        f"add rule inet mcgyvr wg_out oifname eth0 ip daddr {RELAY} "
        "udp dport 40001 udp sport 51820 accept",
        f"add rule inet mcgyvr wg_in iifname eth0 ip saddr {PEER} "
        "udp dport 51820 accept",
        f"add rule inet mcgyvr wg_out oifname eth0 ip daddr {PEER} "
        "udp sport 51820 accept",
    ]
    assert calls == ["nft -f -", f"wg set wg0 peer {OTHER_KEY} endpoint {PEER}:40000"]


def test_what_the_tunnel_says_of_its_peers_is_read_and_nothing_else() -> None:
    from mcgyvr.sandbox import pooled

    said = (
        "now 1700000000\n"
        f"handshake {KEY}\t1699999990\n"
        f"handshake {OTHER_KEY}\t0\n"
        f"endpoint {KEY}\t{PEER}:40000\n"
        f"endpoint {OTHER_KEY}\t(none)\n"
        f"endpoint {KEY[:-2]}\t{PEER}:1\n"
        f"endpoint {OTHER_KEY}\t[2001:db8::1]:51820\n"
        f"handshake {KEY}\tsoon\n"
        f"endpoint {OTHER_KEY}\t{PEER}:99999\n"
    )
    seen = pooled.read_peers(said)
    assert seen == pooled.PeersSeen(
        now=1700000000,
        handshakes={KEY: 1699999990, OTHER_KEY: 0},
        endpoints={KEY: (PEER, 40000)},
    )
    assert pooled.read_peers(f"handshake {KEY}\t1\n") is None
