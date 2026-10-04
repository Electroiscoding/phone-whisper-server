import sys
import time
import argparse
import requests
import json
from mobile.gridlock import GridLockGame, GLOBAL_ROOM_MANAGER

def parse_args():
    parser = argparse.ArgumentParser(description="GridLock Autonomous Tournament & Agent Benchmark Suite")
    parser.add_argument("--endpoint", default="https://phone-whisper-server.pages.dev", help="Target server endpoint")
    parser.add_argument("--games", type=int, default=10, help="Number of benchmark games to run")
    parser.add_argument("--mode", default="server", choices=["server", "local"], help="Benchmark execution target")
    parser.add_argument("--p1", default="NovaBot", help="Player 1 name")
    parser.add_argument("--p2", default="EchoBot", help="Player 2 name")
    parser.add_argument("--turns", type=int, default=50, help="Max turns per game")
    parser.add_argument("--cash", type=int, default=1500, help="Starting cash per player")
    return parser.parse_args()

def run_server_game(endpoint, p1_name, p2_name, max_turns, start_cash):
    t0 = time.perf_counter()
    res = requests.post(
        f"{endpoint}/v1/monopoly/simulate",
        json={"p1_name": p1_name, "p2_name": p2_name, "max_turns": max_turns, "start_cash": start_cash},
        timeout=30
    )
    dur = (time.perf_counter() - t0) * 1000
    if not res.ok:
        return None
    data = res.json()
    data["network_rtt_ms"] = round(dur, 2)
    return data

def run_local_game(p1_name, p2_name, max_turns, start_cash):
    return GLOBAL_ROOM_MANAGER.simulate(p1_name=p1_name, p2_name=p2_name, max_turns=max_turns, start_cash=start_cash)

def main():
    args = parse_args()
    endpoint = args.endpoint.rstrip("/")

    print("=" * 65)
    print(" 🎲 GRIDLOCK SOVEREIGN 1v1 TOURNAMENT BENCHMARK SUITE")
    print(f" Target Mode: {args.mode.upper()} | Endpoint: {endpoint}")
    print(f" Matchup: {args.p1} vs {args.p2} | Matches: {args.games} | Max Turns: {args.turns}")
    print("=" * 65)

    stats = {
        "p1_wins": 0,
        "p2_wins": 0,
        "draws": 0,
        "total_turns": 0,
        "total_steps": 0,
        "total_duration_ms": 0,
        "p1_cash": 0,
        "p2_cash": 0,
        "p1_props": 0,
        "p2_props": 0
    }

    t_start = time.perf_counter()

    for i in range(1, args.games + 1):
        if args.mode == "server":
            res = run_server_game(endpoint, args.p1, args.p2, args.turns, args.cash)
        else:
            res = run_local_game(args.p1, args.p2, args.turns, args.cash)

        if not res or not res.get("ok"):
            print(f"Match #{i:02d}: Failed / Network error")
            continue

        winner = res.get("winner")
        turns = res.get("turns", 0)
        steps = res.get("steps", 0)
        dur = res.get("duration_ms", 0)

        stats["total_turns"] += turns
        stats["total_steps"] += steps
        stats["total_duration_ms"] += dur
        stats["p1_cash"] += res.get("p1", {}).get("cash", 0)
        stats["p2_cash"] += res.get("p2", {}).get("cash", 0)
        stats["p1_props"] += res.get("p1", {}).get("props", 0)
        stats["p2_props"] += res.get("p2", {}).get("props", 0)

        if winner == args.p1:
            stats["p1_wins"] += 1
            w_str = f"🏆 {args.p1}"
        elif winner == args.p2:
            stats["p2_wins"] += 1
            w_str = f"🏆 {args.p2}"
        else:
            stats["draws"] += 1
            w_str = "🤝 Draw"

        rtt_str = f" | RTT {res.get('network_rtt_ms')}ms" if "network_rtt_ms" in res else ""
        print(f"Match #{i:02d}: {w_str:<16} in {turns:02d} turns ({steps:03d} steps, {dur:.1f}ms{rtt_str})")

    t_total = time.perf_counter() - t_start
    n = max(1, args.games)

    print("\n" + "=" * 65)
    print(" 📊 TOURNAMENT BENCHMARK SCORECARD")
    print("=" * 65)
    print(f" Total Matches Completed : {args.games}")
    print(f" Total Wallclock Time    : {t_total:.2f}s ({args.games / max(0.001, t_total):.1f} games/sec)")
    print(f" Average Engine Time     : {stats['total_duration_ms'] / n:.2f} ms/game")
    print(f" Average Turns to Win    : {stats['total_turns'] / n:.1f} turns ({stats['total_steps'] / n:.1f} moves)")
    print("-" * 65)
    p1_rate = (stats["p1_wins"] / n) * 100
    p2_rate = (stats["p2_wins"] / n) * 100
    print(f" {args.p1:<18} : {stats['p1_wins']:02d} wins ({p1_rate:.1f}%) | Avg Props: {stats['p1_props']/n:.1f} | Avg Cash: ${stats['p1_cash']/n:,.0f}")
    print(f" {args.p2:<18} : {stats['p2_wins']:02d} wins ({p2_rate:.1f}%) | Avg Props: {stats['p2_props']/n:.1f} | Avg Cash: ${stats['p2_cash']/n:,.0f}")
    if stats["draws"] > 0:
        print(f" Draws / Turn Limit : {stats['draws']:02d} games ({(stats['draws']/n)*100:.1f}%)")
    print("=" * 65)

if __name__ == "__main__":
    main()
