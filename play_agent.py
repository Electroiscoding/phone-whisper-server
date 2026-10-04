import sys
import time
import argparse
import requests
import json

def parse_args():
    parser = argparse.ArgumentParser(description="GridLock Autonomous AI Agent Runner")
    parser.add_argument("--endpoint", default="https://phone-whisper-server.pages.dev", help="Target server endpoint")
    parser.add_argument("--name", default="SovereignAgent", help="Agent player name")
    parser.add_argument("--avatar", default="fox", help="Avatar style: cat, bunny, bear, fox, etc.")
    parser.add_argument("--room", default=None, help="Room code to join")
    parser.add_argument("--quick", action="store_true", help="Matchmake into an open room or create one")
    parser.add_argument("--mode", default="heuristic", choices=["heuristic", "qwen", "random"], help="Decision engine")
    parser.add_argument("--delay", type=float, default=0.6, help="Delay between actions in seconds")
    return parser.parse_args()

def pick_move_heuristic(state, legal, my_pid):
    p = state['players'][my_pid]
    phase = state['phase']

    if phase == 'decide':
        tid = state['pending']
        prop = next((t for t in state['tiles'] if t['id'] == tid), None)
        cost = prop['cost'] if prop else 200
        if p['cash'] >= cost + 120 and 'buy' in legal:
            return 'buy'
        return 'decline'

    if phase == 'auction':
        auc = state['auction']
        if auc and auc.get('turn') == my_pid:
            bid = auc.get('bid', 0)
            next_bid = bid + 10 if bid > 0 else 10
            tid = auc.get('tid', 0)
            prop = next((t for t in state['tiles'] if t['id'] == tid), None)
            limit = int(prop['cost'] * 0.85) if prop else 150
            if next_bid <= limit and p['cash'] >= next_bid + 50:
                return f"bid {next_bid}"
            return 'fold'

    if phase == 'debt':
        return 'autoraise'

    if phase in ['pre', 'post']:
        for move in legal:
            if move.startswith('build') and p['cash'] >= 300:
                return move

    if phase == 'pre':
        if p['in_jail'] and p['cash'] >= 250 and 'jail' in legal:
            return 'jail'
        if 'roll' in legal:
            return 'roll'

    if phase == 'post':
        if 'end' in legal:
            return 'end'

    for candidate in ['roll', 'buy', 'decline', 'autoraise', 'end', 'fold']:
        if candidate in legal:
            return candidate

    return legal[0] if legal else 'wait'

def pick_move_qwen(endpoint, state, legal, my_pid):
    prompt = (
        f"You are playing GridLock (16-tile sovereign tactical monopoly).\n"
        f"State: Turn {state['turn']}, Phase: {state['phase']}\n"
        f"You are Player {my_pid + 1} with cash ${state['players'][my_pid]['cash']}.\n"
        f"Legal actions right now: {legal}\n"
        f"Choose exactly ONE legal action string from the list above. Respond ONLY with the command text."
    )
    try:
        resp = requests.post(
            f"{endpoint}/v1/chat/completions",
            json={
                "model": "qwen2.5-0.5b",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 15,
                "temperature": 0.2
            },
            timeout=20
        )
        if resp.status_code == 200:
            lines = resp.text.strip().split("\n")
            content = ""
            for line in lines:
                if line.startswith("data: ") and not line.endswith("[DONE]"):
                    try:
                        chunk = json.loads(line[6:])
                        delta = chunk["choices"][0]["delta"].get("content")
                        if delta:
                            content += delta
                    except Exception:
                        pass
            ans = content.strip().lower()
            for cand in legal:
                if cand.lower() in ans or ans in cand.lower():
                    return cand
    except Exception:
        pass
    return pick_move_heuristic(state, legal, my_pid)

def main():
    args = parse_args()
    endpoint = args.endpoint.rstrip("/")
    print(f"Connecting to GridLock Datacenter: {endpoint}")

    room_id = None
    token = None
    pid = 0

    if args.quick or not args.room:
        res = requests.post(
            f"{endpoint}/v1/monopoly/quick",
            json={"name": args.name, "avatar": args.avatar, "kind": "ai"},
            timeout=15
        )
        data = res.json()
        room_id = data["room_id"]
        token = data["player_token"]
        pid = data["player_id"]
        role = "Host (P1)" if pid == 0 else "Challenger (P2)"
        print(f"Matchmaker paired: Room {room_id} as {role}")
    else:
        room_id = args.room.upper()
        res = requests.post(
            f"{endpoint}/v1/monopoly/rooms/{room_id}/join",
            json={"name": args.name, "avatar": args.avatar, "kind": "ai"},
            timeout=15
        )
        data = res.json()
        if not data.get("ok"):
            print(f"Failed to join room: {data.get('error')}")
            sys.exit(1)
        token = data["player_token"]
        pid = data["player_id"]
        print(f"Joined Room {room_id} as Seat {data['seat']}")

    print(f"Engine: {args.mode.upper()} Agent | Token: {token[:8]}...")

    while True:
        try:
            st_res = requests.get(f"{endpoint}/v1/monopoly/rooms/{room_id}/state", timeout=10)
            if not st_res.ok:
                time.sleep(args.delay)
                continue
            st_data = st_res.json()
            state = st_data.get("state", {})
            if state.get("over"):
                winner = state.get("winner")
                w_name = state["players"][winner]["name"] if winner is not None else "Nobody"
                print(f"\n==========================================")
                print(f"🏆 MATCH FINISHED! Winner: {w_name}")
                print(f"==========================================")
                break

            players = state.get("players", [])
            if len(players) < 2:
                print("Waiting for opponent to connect...", end="\r", flush=True)
                time.sleep(1.0)
                continue

            cur_turn = state.get("cur")
            phase = state.get("phase")
            auc = state.get("auction")
            is_my_turn = False

            if phase == "auction" and auc:
                is_my_turn = (auc.get("turn") == pid)
            else:
                is_my_turn = (cur_turn == pid)

            if not is_my_turn:
                other = players[1 - pid]["name"]
                print(f"Waiting for opponent move ({other})...", end="\r", flush=True)
                time.sleep(args.delay)
                continue

            legal_res = requests.get(f"{endpoint}/v1/monopoly/rooms/{room_id}/legal", timeout=10)
            legal = legal_res.json().get("legal", []) if legal_res.ok else []

            if not legal or legal == ["wait"]:
                time.sleep(args.delay)
                continue

            if args.mode == "qwen":
                chosen = pick_move_qwen(endpoint, state, legal, pid)
            elif args.mode == "heuristic":
                chosen = pick_move_heuristic(state, legal, pid)
            else:
                chosen = legal[0]

            print(f"\n[{args.name}] Turn {state['turn']} | Legal: {legal} -> ACTION: {chosen}")
            act_res = requests.post(
                f"{endpoint}/v1/monopoly/rooms/{room_id}/cli",
                json={"command": chosen, "player_token": token},
                timeout=20
            )
            if act_res.ok:
                act_data = act_res.json()
                print(f"   Result: {act_data.get('msg')}")
                if "roll" in chosen or "buy" in chosen:
                    board_res = requests.get(
                        f"{endpoint}/v1/monopoly/rooms/{room_id}/ascii",
                        headers={"Accept": "text/plain"},
                        timeout=10
                    )
                    if board_res.ok:
                        print(board_res.text)

            time.sleep(args.delay)

        except KeyboardInterrupt:
            print("\nAgent stopped by user.")
            break
        except Exception as err:
            time.sleep(1.0)

if __name__ == "__main__":
    main()
