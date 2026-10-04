import math
import random
import time
import json
import uuid
import threading

SEAT_COLORS = ['#38bdf8', '#fb7185', '#fbbf24', '#a3e635']

DISTRICTS = {
    'BRONZE': {'name': 'Bronze Row', 'hex': '#f59e0b', 'tiles': [1, 2], 'build': 60},
    'CYBER': {'name': 'Cyber Hub', 'hex': '#22d3ee', 'tiles': [5, 6], 'build': 110},
    'CLEAN': {'name': 'CleanTech', 'hex': '#34d399', 'tiles': [9, 10], 'build': 160},
    'DEEP': {'name': 'DeepTech', 'hex': '#a78bfa', 'tiles': [13, 14], 'build': 220}
}

TILES = [
    {'id': 0, 'name': 'START', 'type': 'start', 'icon': '🏁', 'desc': 'Pass: +00 • Land: +00 bonus'},
    {'id': 1, 'name': 'Rust Ave', 'type': 'prop', 'd': 'BRONZE', 'cost': 120, 'rent': [20, 60, 130, 240, 420], 'icon': '🦀'},
    {'id': 2, 'name': 'Python Way', 'type': 'prop', 'd': 'BRONZE', 'cost': 140, 'rent': [25, 75, 160, 280, 500], 'icon': '🐍'},
    {'id': 3, 'name': 'Surge Tax', 'type': 'tax', 'amount': 100, 'icon': '⚡', 'desc': 'Pay 00 to Jackpot pool'},
    {'id': 4, 'name': 'REBOOT', 'type': 'jail', 'icon': '🔌', 'desc': 'Visiting safe. Jailed: roll 6 or pay 0'},
    {'id': 5, 'name': 'Neon St', 'type': 'prop', 'd': 'CYBER', 'cost': 220, 'rent': [40, 120, 260, 460, 780], 'icon': '🌃'},
    {'id': 6, 'name': 'Matrix Blvd', 'type': 'prop', 'd': 'CYBER', 'cost': 240, 'rent': [45, 135, 300, 520, 880], 'icon': '🟩'},
    {'id': 7, 'name': 'Airdrop', 'type': 'crate', 'icon': '🎁', 'desc': 'Mystery crate: random reward'},
    {'id': 8, 'name': 'FREE NODE', 'type': 'jackpot', 'icon': '🎰', 'desc': 'Win the Jackpot pool'},
    {'id': 9, 'name': 'Solar Row', 'type': 'prop', 'd': 'CLEAN', 'cost': 320, 'rent': [60, 180, 400, 700, 1150], 'icon': '☀️'},
    {'id': 10, 'name': 'Fusion Alley', 'type': 'prop', 'd': 'CLEAN', 'cost': 350, 'rent': [70, 210, 450, 780, 1300], 'icon': '⚛️'},
    {'id': 11, 'name': 'Audit Tax', 'type': 'tax', 'amount': 120, 'icon': '🧾', 'desc': 'Pay 20 to Jackpot pool'},
    {'id': 12, 'name': 'OVERCLOCK', 'type': 'wheel', 'icon': '🚀', 'desc': 'Spin wheel: surprise reward'},
    {'id': 13, 'name': 'Quantum Way', 'type': 'prop', 'd': 'DEEP', 'cost': 440, 'rent': [95, 290, 620, 1050, 1750], 'icon': '🌀'},
    {'id': 14, 'name': 'Orbit Peak', 'type': 'prop', 'd': 'DEEP', 'cost': 480, 'rent': [110, 330, 720, 1200, 2000], 'icon': '🛰️'},
    {'id': 15, 'name': 'Venture Fund', 'type': 'crate', 'icon': '💎', 'desc': 'Mystery crate: random reward'}
]

CRATE_WEIGHTS = [
    {'w': 34, 'k': 'cash', 'min': 60, 'max': 140, 't': 'Pocket Change'},
    {'w': 30, 'k': 'cash', 'min': 150, 'max': 260, 't': 'Nice Haul'},
    {'w': 14, 'k': 'cash', 'min': 300, 'max': 500, 't': 'Big Payout!'},
    {'w': 5, 'k': 'cash', 'min': 700, 'max': 900, 't': 'LEGENDARY HAUL'},
    {'w': 8, 'k': 'shield', 't': 'Rent Shield'},
    {'w': 6, 'k': 'roll', 't': 'Free Roll'}
]

WHEEL_WEIGHTS = [
    {'w': 22, 'k': 'cash', 'val': 150, 'name': '+50'},
    {'w': 16, 'k': 'cash', 'val': 300, 'name': '+00'},
    {'w': 6, 'k': 'cash', 'val': 600, 'name': '+00'},
    {'w': 14, 'k': 'roll', 'val': 0, 'name': 'Bonus Roll'},
    {'w': 14, 'k': 'shield', 'val': 0, 'name': 'Rent Shield'},
    {'w': 10, 'k': 'cashback', 'val': 0.1, 'name': 'Cashback 10%'},
    {'w': 6, 'k': 'glitch', 'val': -60, 'name': 'Glitch -0'}
]

def grid_of(tid):
    if tid <= 4:
        return (5, 5 - tid)
    elif tid <= 8:
        return (5 - (tid - 4), 1)
    elif tid <= 12:
        return (1, 1 + (tid - 8))
    else:
        return (1 + (tid - 12), 5)

def pad_str(s, n):
    s = str(s)
    if len(s) >= n:
        return s[:n]
    return s + ' ' * (n - len(s))

def fmt_money(n):
    sign = '-' if n < 0 else ''
    return sign + '$' + f'{abs(int(round(n))):,}'

def pick_weighted(items):
    total = sum(x['w'] for x in items)
    r = random.uniform(0, total)
    for x in items:
        r -= x['w']
        if r <= 0:
            return x
    return items[-1]

class GridLockGame:
    def __init__(self, start_cash=1500, max_turns=50):
        self.lock = threading.RLock()
        self.start_cash = start_cash
        self.max_turns = max_turns
        self.pass_start = 200
        self.land_bonus = 100
        self.jail_fee = 50
        self.sell_rate = 0.5
        self.unmortgage_fee = 0.1
        self.jackpot = 100
        self.turn = 1
        self.cur = 0
        self.phase = 'pre'
        self.extra = False
        self.last_roll = 1
        self.debt = None
        self.auction = None
        self.pending = None
        self.over = False
        self.winner = None
        self.logs = []
        self.history = []
        self.created_at = time.time()
        self.last_activity = time.time()
        self.players = []
        self.tiles = [{'owner': None, 'level': 0, 'mortgaged': False} for _ in range(16)]

    def add_player(self, name, kind='human', avatar='cat', acc='none'):
        with self.lock:
            pid = len(self.players)
            if pid >= 2:
                return None
            token = uuid.uuid4().hex[:16]
            color = SEAT_COLORS[pid]
            p = {
                'id': pid,
                'token': token,
                'name': name or f'Player {pid + 1}',
                'kind': kind,
                'avatar': avatar,
                'acc': acc,
                'color': color,
                'tag': f'P{pid + 1}',
                'cash': self.start_cash,
                'pos': 0,
                'in_jail': False,
                'jail_turns': 0,
                'sixes': 0,
                'shield': False,
                'bankrupt': False,
                'hops': 0,
                'ai': {'reserve': 220, 'bold': 0.6} if kind == 'ai' else None
            }
            self.players.append(p)
            self.log(f"Player joined: {p['name']} ({p['tag']}) as {kind}")
            return p

    def log(self, text, kind='sys'):
        self.logs.append({
            'time': round(time.time() - self.created_at, 2),
            'text': text,
            'kind': kind
        })
        if len(self.logs) > 100:
            self.logs.pop(0)
        self.record_history('log', text, kind=kind)

    def record_history(self, action, detail, **extra):
        if not hasattr(self, 'history'):
            self.history = []
        cp = self.current_player()
        entry = {
            'time': round(time.time() - self.created_at, 2),
            'turn': self.turn,
            'phase': self.phase,
            'player': cp['name'] if cp else 'System',
            'tag': cp['tag'] if cp else 'SYS',
            'action': action,
            'detail': detail
        }
        entry.update(extra)
        self.history.append(entry)
        if len(self.history) > 300:
            self.history.pop(0)

    def current_player(self):
        if not self.players:
            return None
        return self.players[self.cur]

    def player_by_token(self, token):
        for p in self.players:
            if p['token'] == token:
                return p
        return None

    def district_tiles(self, dk):
        return DISTRICTS[dk]['tiles']

    def set_owner(self, dk):
        tiles = self.district_tiles(dk)
        o = self.tiles[tiles[0]]['owner']
        if o is not None and all(self.tiles[t]['owner'] == o for t in tiles):
            return o
        return None

    def has_set(self, pid, dk):
        return self.set_owner(dk) == pid

    def tiles_of(self, pid):
        return [t['id'] for t in TILES if t['type'] == 'prop' and self.tiles[t['id']]['owner'] == pid]

    def levels_of(self, dk):
        return [self.tiles[t]['level'] for t in self.district_tiles(dk)]

    def rent_of(self, tid):
        t = TILES[tid]
        st = self.tiles[tid]
        if st['owner'] is None or st['mortgaged']:
            return 0
        lvl = max(1, st['level'])
        r = t['rent'][lvl - 1]
        if st['level'] == 1 and self.set_owner(t['d']) == st['owner']:
            r *= 2
        return r

    def build_cost(self, tid):
        return DISTRICTS[TILES[tid]['d']]['build']

    def mortgage_value(self, tid):
        return TILES[tid]['cost'] // 2

    def unmortgage_cost(self, tid):
        return math.ceil(self.mortgage_value(tid) * (1 + self.unmortgage_fee))

    def net_worth(self, p):
        val = p['cash']
        for t in self.tiles_of(p['id']):
            st = self.tiles[t]
            val += self.mortgage_value(t) if st['mortgaged'] else TILES[t]['cost']
            val += (st['level'] - 1) * self.build_cost(t)
        return val

    def lock_reason(self, tid):
        t = TILES[tid]
        if t['type'] != 'prop':
            return 'Not tradable'
        if any(self.tiles[i]['level'] > 1 for i in self.district_tiles(t['d'])):
            return f"Locked: {DISTRICTS[t['d']]['name']} has upgrades. Sell buildings first."
        return ''

    def why_no_build(self, pid, tid):
        if tid < 0 or tid >= 16:
            return 'Invalid tile'
        t = TILES[tid]
        if t['type'] != 'prop':
            return 'Not a property'
        st = self.tiles[tid]
        p = self.players[pid]
        if st['owner'] != pid:
            return 'You do not own this tile'
        if not self.has_set(pid, t['d']):
            return f"Need the full {DISTRICTS[t['d']]['name']} set"
        if any(self.tiles[i]['mortgaged'] for i in self.district_tiles(t['d'])):
            return 'Unmortgage the entire district first'
        if st['level'] >= 5:
            return 'Already at maximum Empire Landmark'
        if st['level'] > min(self.levels_of(t['d'])):
            return 'Build evenly across the district'
        cost = self.build_cost(tid)
        if p['cash'] < cost:
            return f"Need {fmt_money(cost)}"
        return ''

    def why_no_sell(self, pid, tid):
        if tid < 0 or tid >= 16:
            return 'Invalid tile'
        t = TILES[tid]
        if t['type'] != 'prop':
            return 'Not a property'
        st = self.tiles[tid]
        if st['owner'] != pid:
            return 'You do not own this tile'
        if st['level'] <= 1:
            return 'No upgrades to sell'
        if st['level'] < max(self.levels_of(t['d'])):
            return 'Sell evenly across the district'
        return ''

    def why_no_mortgage(self, pid, tid):
        if tid < 0 or tid >= 16:
            return 'Invalid tile'
        t = TILES[tid]
        if t['type'] != 'prop':
            return 'Not a property'
        st = self.tiles[tid]
        if st['owner'] != pid:
            return 'You do not own this tile'
        if st['mortgaged']:
            return 'Already mortgaged'
        if any(self.tiles[i]['level'] > 1 for i in self.district_tiles(t['d'])):
            return 'Sell all district buildings before mortgaging'
        return ''

    def why_no_unmortgage(self, pid, tid):
        if tid < 0 or tid >= 16:
            return 'Invalid tile'
        t = TILES[tid]
        if t['type'] != 'prop':
            return 'Not a property'
        st = self.tiles[tid]
        if st['owner'] != pid:
            return 'You do not own this tile'
        if not st['mortgaged']:
            return 'Tile is not mortgaged'
        cost = self.unmortgage_cost(tid)
        if self.players[pid]['cash'] < cost:
            return f"Need {fmt_money(cost)}"
        return ''

    def legal_moves(self, for_pid=None):
        if self.over:
            return ['reset', 'help', 'status', 'board', 'state']
        if len(self.players) < 2:
            return ['wait', 'help', 'status']
        if for_pid is not None and self.phase != 'auction' and for_pid != self.cur:
            return ['wait', 'status', 'board', 'legal', 'help']

        cur_p = self.current_player()
        res = ['status', 'board', 'legal', 'help']

        if self.phase == 'auction':
            auc = self.auction
            if auc and (for_pid is None or for_pid == auc['turn']):
                tp = self.players[auc['turn']]
                min_bid = (auc['bid'] + 10) if auc['bid'] > 0 else 10
                if tp['cash'] >= min_bid:
                    res.append(f'bid {min_bid}')
                res.append('fold')
            return res

        if self.phase == 'debt':
            res.extend(['autoraise', 'bankrupt'])
            for t in self.tiles_of(cur_p['id']):
                if not self.why_no_sell(cur_p['id'], t):
                    res.append(f'sell {t}')
                if not self.why_no_mortgage(cur_p['id'], t):
                    res.append(f'mortgage {t}')
            return res

        if self.phase == 'decide':
            res.extend(['buy', 'decline'])
            return res

        if self.phase == 'pre':
            res.append('roll')
            if cur_p['in_jail'] and cur_p['cash'] >= self.jail_fee:
                res.append('jail')

        if self.phase == 'post':
            res.append('end')

        if self.phase in ['pre', 'post']:
            for t in self.tiles_of(cur_p['id']):
                if not self.why_no_build(cur_p['id'], t):
                    res.append(f'build {t}')
                if not self.why_no_sell(cur_p['id'], t):
                    res.append(f'sell {t}')
                if not self.why_no_mortgage(cur_p['id'], t):
                    res.append(f'mortgage {t}')
                if not self.why_no_unmortgage(cur_p['id'], t):
                    res.append(f'unmortgage {t}')
            opp = 1 - cur_p['id']
            res.append(f'trade {opp + 1}')

        return res

    def settle_phase(self):
        if self.over:
            return
        p = self.current_player()
        if p['bankrupt']:
            self.extra = False
            self.phase = 'post'
            return
        self.phase = 'pre' if (self.extra and not p['in_jail']) else 'post'

    def roll_dice(self, pid):
        with self.lock:
            self.last_activity = time.time()
            if self.over:
                return {'ok': False, 'msg': 'Game is already over'}
            if len(self.players) < 2:
                return {'ok': False, 'msg': 'Waiting for second player'}
            if pid != self.cur:
                return {'ok': False, 'msg': 'Not your turn'}
            if self.phase != 'pre':
                return {'ok': False, 'msg': f'Cannot roll during phase: {self.phase}'}

            p = self.players[pid]
            d = random.randint(1, 6)
            self.last_roll = d

            if p['in_jail']:
                if d == 6:
                    p['in_jail'] = False
                    p['jail_turns'] = 0
                    p['sixes'] = 0
                    self.extra = False
                    self.log(f"🎲 {p['name']} rolled a 6 and escaped REBOOT!", 'good')
                    self.move_player(p, d)
                    return {'ok': True, 'msg': f"{p['name']} rolled 6 and broke out of REBOOT!"}
                else:
                    p['jail_turns'] += 1
                    self.log(f"🎲 {p['name']} rolled {d} (needed 6 to escape REBOOT). Turn {p['jail_turns']}/3", 'sys')
                    if p['jail_turns'] >= 3:
                        if p['cash'] >= self.jail_fee:
                            p['cash'] -= self.jail_fee
                            self.jackpot += self.jail_fee
                            p['in_jail'] = False
                            p['jail_turns'] = 0
                            self.log(f"🔌 {p['name']} served 3 turns, paid {fmt_money(self.jail_fee)} to Jackpot and leaves REBOOT.", 'sys')
                            self.move_player(p, d)
                            return {'ok': True, 'msg': f"{p['name']} paid {fmt_money(self.jail_fee)} after 3 turns and moved {d} tiles"}
                        else:
                            self.start_debt(p, self.jail_fee, 'pool')
                            return {'ok': True, 'msg': f"{p['name']} owed {fmt_money(self.jail_fee)} jail fee"}
                    self.phase = 'post'
                    return {'ok': True, 'msg': f"{p['name']} rolled {d} and remains in REBOOT"}

            if d == 6:
                p['sixes'] += 1
                if p['sixes'] >= 3:
                    p['in_jail'] = True
                    p['jail_turns'] = 0
                    p['sixes'] = 0
                    p['pos'] = 4
                    self.extra = False
                    self.phase = 'post'
                    self.log(f"🚨 {p['name']} rolled three consecutive 6s! Sent directly to REBOOT!", 'bad')
                    return {'ok': True, 'msg': f"{p['name']} rolled three 6s and was sent to REBOOT!"}
                self.extra = True
                self.log(f"🎲 {p['name']} rolled a 6! Granted a bonus roll!", 'good')
            else:
                p['sixes'] = 0
                self.extra = False

            self.move_player(p, d)
            return {'ok': True, 'msg': f"{p['name']} rolled {d} and landed on {TILES[p['pos']]['name']}"}

    def move_player(self, p, steps):
        old_pos = p['pos']
        new_pos = (old_pos + steps) % 16
        p['pos'] = new_pos
        p['hops'] += steps

        if new_pos < old_pos:
            p['cash'] += self.pass_start
            self.log(f"🏁 {p['name']} passed START (+{fmt_money(self.pass_start)})", 'good')

        if new_pos == 0:
            p['cash'] += self.land_bonus
            self.log(f"🏁 {p['name']} landed right on START (+{fmt_money(self.land_bonus)} bonus)", 'good')

        self.resolve_tile(p, new_pos)

    def resolve_tile(self, p, tid):
        t = TILES[tid]
        st = self.tiles[tid]

        if t['type'] == 'start':
            self.settle_phase()
            return

        if t['type'] == 'jail':
            self.log(f"🔌 {p['name']} is just visiting REBOOT. All systems normal.", 'sys')
            self.settle_phase()
            return

        if t['type'] == 'jackpot':
            payout = self.jackpot
            p['cash'] += payout
            self.jackpot = 100
            self.log(f"🎰 JACKPOT! {p['name']} landed on FREE NODE and claimed {fmt_money(payout)}!", 'good')
            self.settle_phase()
            return

        if t['type'] == 'tax':
            amt = t['amount']
            if p['cash'] >= amt:
                p['cash'] -= amt
                self.jackpot += amt
                self.log(f"⚡ {p['name']} paid {fmt_money(amt)} tax to Jackpot pool", 'bad')
                self.settle_phase()
            else:
                self.start_debt(p, amt, 'pool')
            return

        if t['type'] == 'crate':
            item = pick_weighted(CRATE_WEIGHTS)
            if item['k'] == 'cash':
                c = random.randint(item['min'], item['max'])
                p['cash'] += c
                self.log(f"🎁 {p['name']} opened crate: {item['t']} (+{fmt_money(c)})", 'good')
            elif item['k'] == 'shield':
                p['shield'] = True
                self.log(f"🎁 {p['name']} opened crate: Rent Shield activated!", 'good')
            elif item['k'] == 'roll':
                self.extra = True
                self.log(f"🎁 {p['name']} opened crate: Free Bonus Roll!", 'good')
            self.settle_phase()
            return

        if t['type'] == 'wheel':
            res = pick_weighted(WHEEL_WEIGHTS)
            if res['k'] == 'cash':
                p['cash'] += res['val']
                self.log(f"🚀 {p['name']} spun OVERCLOCK: +{fmt_money(res['val'])}", 'good')
            elif res['k'] == 'roll':
                self.extra = True
                self.log(f"🚀 {p['name']} spun OVERCLOCK: Bonus Roll awarded!", 'good')
            elif res['k'] == 'shield':
                p['shield'] = True
                self.log(f"🚀 {p['name']} spun OVERCLOCK: Rent Shield equipped!", 'good')
            elif res['k'] == 'cashback':
                cb = min(250, max(50, int(round(self.net_worth(p) * 0.1 / 10) * 10)))
                p['cash'] += cb
                self.log(f"🚀 {p['name']} spun OVERCLOCK: 10% Cashback (+{fmt_money(cb)})", 'good')
            elif res['k'] == 'glitch':
                if p['cash'] >= 60:
                    p['cash'] -= 60
                    self.jackpot += 60
                    self.log(f"🚀 {p['name']} spun OVERCLOCK: Glitch penalty (-0 to Jackpot)", 'bad')
                else:
                    self.log(f"🚀 {p['name']} spun OVERCLOCK: Glitch avoided (low balance)", 'sys')
            self.settle_phase()
            return

        if t['type'] == 'prop':
            if st['owner'] is None:
                self.pending = tid
                self.phase = 'decide'
                self.log(f"🏠 {p['name']} landed on unowned {t['name']} (Price: {fmt_money(t['cost'])})", 'sys')
                return
            elif st['owner'] == p['id']:
                self.log(f"🏠 {p['name']} visited their own {t['name']}", 'sys')
                self.settle_phase()
                return
            else:
                owner = self.players[st['owner']]
                if st['mortgaged']:
                    self.log(f"🏠 {p['name']} landed on {t['name']}, but it is mortgaged. 0 rent.", 'sys')
                    self.settle_phase()
                    return
                if p['shield']:
                    p['shield'] = False
                    self.log(f"🛡️ {p['name']}'s Rent Shield absorbed the rent for {t['name']}!", 'good')
                    self.settle_phase()
                    return

                rent = self.rent_of(tid)
                if p['cash'] >= rent:
                    p['cash'] -= rent
                    owner['cash'] += rent
                    self.log(f"💸 {p['name']} paid {fmt_money(rent)} rent to {owner['name']} for {t['name']}", 'bad')
                    self.settle_phase()
                else:
                    self.start_debt(p, rent, owner['id'])
                return

    def start_debt(self, p, amt, to_target):
        self.debt = {'p': p['id'], 'amt': amt, 'to': to_target}
        self.phase = 'debt'
        cred_name = 'Jackpot pool' if to_target == 'pool' else self.players[to_target]['name']
        self.log(f"⚠️ DEBT CRISIS: {p['name']} owes {fmt_money(amt)} to {cred_name} (Cash: {fmt_money(p['cash'])}). Liquidate or declare bankruptcy!", 'bad')

    def buy_property(self, pid):
        with self.lock:
            self.last_activity = time.time()
            if self.over or self.phase != 'decide' or pid != self.cur or self.pending is None:
                return {'ok': False, 'msg': 'Cannot buy right now'}
            p = self.players[pid]
            tid = self.pending
            t = TILES[tid]
            if p['cash'] < t['cost']:
                return {'ok': False, 'msg': f"Insufficient funds. Need {fmt_money(t['cost'])}"}

            p['cash'] -= t['cost']
            st = self.tiles[tid]
            st['owner'] = pid
            st['level'] = 1
            st['mortgaged'] = False
            self.pending = None
            self.log(f"🏠 {p['name']} bought {t['name']} for {fmt_money(t['cost'])}", 'good')

            if self.has_set(pid, t['d']):
                self.log(f"⚡ SET COMPLETE! {p['name']} controls all of {DISTRICTS[t['d']]['name']}!", 'good')

            self.settle_phase()
            return {'ok': True, 'msg': f"Purchased {t['name']} for {fmt_money(t['cost'])}"}

    def decline_property(self, pid):
        with self.lock:
            self.last_activity = time.time()
            if self.over or self.phase != 'decide' or pid != self.cur or self.pending is None:
                return {'ok': False, 'msg': 'Cannot decline right now'}
            p = self.players[pid]
            tid = self.pending
            t = TILES[tid]
            self.pending = None
            self.log(f"{p['name']} declined {t['name']}. Starting auction!", 'sys')
            opp = 1 - pid
            self.auction = {
                'tid': tid,
                'bid': 0,
                'high': None,
                'folded': set(),
                'order': [opp, pid],
                'turn': opp
            }
            self.phase = 'auction'
            return {'ok': True, 'msg': f"Auction opened for {t['name']}. {self.players[opp]['name']} bids first."}

    def bid_auction(self, pid, amount):
        with self.lock:
            self.last_activity = time.time()
            if self.over or self.phase != 'auction' or not self.auction:
                return {'ok': False, 'msg': 'No auction active'}
            if pid != self.auction['turn']:
                return {'ok': False, 'msg': 'Not your turn to bid'}
            p = self.players[pid]
            min_bid = (self.auction['bid'] + 10) if self.auction['bid'] > 0 else 10
            if amount < min_bid:
                return {'ok': False, 'msg': f"Bid must be at least {fmt_money(min_bid)}"}
            if amount > p['cash']:
                return {'ok': False, 'msg': f"Cannot bid {fmt_money(amount)} with {fmt_money(p['cash'])} cash"}

            self.auction['bid'] = amount
            self.auction['high'] = pid
            self.log(f"🔨 {p['name']} bid {fmt_money(amount)} for {TILES[self.auction['tid']]['name']}", 'sys')
            self.auction['turn'] = 1 - pid
            return {'ok': True, 'msg': f"Bid placed: {fmt_money(amount)}"}

    def fold_auction(self, pid):
        with self.lock:
            self.last_activity = time.time()
            if self.over or self.phase != 'auction' or not self.auction:
                return {'ok': False, 'msg': 'No auction active'}
            if pid != self.auction['turn']:
                return {'ok': False, 'msg': 'Not your turn to bid'}
            p = self.players[pid]
            self.auction['folded'].add(pid)
            self.log(f"{p['name']} folded from auction", 'sys')

            tid = self.auction['tid']
            high_id = self.auction['high']
            t = TILES[tid]

            if high_id is not None:
                winner = self.players[high_id]
                cost = self.auction['bid']
                winner['cash'] -= cost
                st = self.tiles[tid]
                st['owner'] = winner['id']
                st['level'] = 1
                st['mortgaged'] = False
                self.log(f"🏆 {winner['name']} won the auction for {t['name']} at {fmt_money(cost)}!", 'good')
                if self.has_set(winner['id'], t['d']):
                    self.log(f"⚡ SET COMPLETE! {winner['name']} controls {DISTRICTS[t['d']]['name']}!", 'good')
            else:
                self.log(f"No bids placed. {t['name']} remains unowned.", 'sys')

            self.auction = None
            self.settle_phase()
            return {'ok': True, 'msg': f"{p['name']} folded"}

    def build_upgrade(self, pid, tid):
        with self.lock:
            self.last_activity = time.time()
            if self.phase not in ['pre', 'post']:
                return {'ok': False, 'msg': 'Can only build before roll or at end of turn'}
            why = self.why_no_build(pid, tid)
            if why:
                return {'ok': False, 'msg': why}
            cost = self.build_cost(tid)
            p = self.players[pid]
            st = self.tiles[tid]
            p['cash'] -= cost
            st['level'] += 1
            t = TILES[tid]
            nm = 'EMPIRE LANDMARK' if st['level'] == 5 else f"Level {st['level']}"
            self.log(f"🏗️ {p['name']} upgraded {t['name']} to {nm} (-{fmt_money(cost)}, rent: {fmt_money(self.rent_of(tid))})", 'good')
            return {'ok': True, 'msg': f"Upgraded {t['name']} to {nm}"}

    def sell_building(self, pid, tid):
        with self.lock:
            self.last_activity = time.time()
            why = self.why_no_sell(pid, tid)
            if why:
                return {'ok': False, 'msg': why}
            st = self.tiles[tid]
            cost = self.build_cost(tid)
            gain = int(cost * self.sell_rate)
            st['level'] -= 1
            p = self.players[pid]
            p['cash'] += gain
            t = TILES[tid]
            self.log(f"🔧 {p['name']} sold upgrade on {t['name']} (+{fmt_money(gain)})", 'warn')
            self.check_debt_resolved()
            return {'ok': True, 'msg': f"Sold building on {t['name']} for +{fmt_money(gain)}"}

    def mortgage_tile(self, pid, tid):
        with self.lock:
            self.last_activity = time.time()
            why = self.why_no_mortgage(pid, tid)
            if why:
                return {'ok': False, 'msg': why}
            st = self.tiles[tid]
            gain = self.mortgage_value(tid)
            st['mortgaged'] = True
            p = self.players[pid]
            p['cash'] += gain
            t = TILES[tid]
            self.log(f"🏦 {p['name']} mortgaged {t['name']} (+{fmt_money(gain)})", 'warn')
            self.check_debt_resolved()
            return {'ok': True, 'msg': f"Mortgaged {t['name']} for +{fmt_money(gain)}"}

    def unmortgage_tile(self, pid, tid):
        with self.lock:
            self.last_activity = time.time()
            why = self.why_no_unmortgage(pid, tid)
            if why:
                return {'ok': False, 'msg': why}
            st = self.tiles[tid]
            cost = self.unmortgage_cost(tid)
            p = self.players[pid]
            p['cash'] -= cost
            st['mortgaged'] = False
            t = TILES[tid]
            self.log(f"🏛️ {p['name']} unmortgaged {t['name']} (-{fmt_money(cost)})", 'good')
            return {'ok': True, 'msg': f"Unmortgaged {t['name']} for -{fmt_money(cost)}"}

    def check_debt_resolved(self):
        if not self.debt:
            return
        p = self.players[self.debt['p']]
        amt = self.debt['amt']
        if p['cash'] >= amt:
            p['cash'] -= amt
            if self.debt['to'] == 'pool':
                self.jackpot += amt
                self.log(f"✅ {p['name']} paid off their {fmt_money(amt)} tax debt to Jackpot pool", 'good')
            else:
                cred = self.players[self.debt['to']]
                cred['cash'] += amt
                self.log(f"✅ {p['name']} paid off their {fmt_money(amt)} rent debt to {cred['name']}", 'good')
            self.debt = None
            self.settle_phase()

    def auto_raise(self, pid):
        with self.lock:
            self.last_activity = time.time()
            if not self.debt or self.debt['p'] != pid:
                return {'ok': False, 'msg': 'No debt to raise funds for'}
            p = self.players[pid]
            steps = 0
            while self.debt and p['cash'] < self.debt['amt'] and steps < 30:
                steps += 1
                found = False
                for t in self.tiles_of(pid):
                    if not self.why_no_sell(pid, t):
                        self.sell_building(pid, t)
                        found = True
                        break
                if found:
                    continue
                for t in self.tiles_of(pid):
                    if not self.why_no_mortgage(pid, t):
                        self.mortgage_tile(pid, t)
                        found = True
                        break
                if not found:
                    break

            self.check_debt_resolved()
            if self.debt:
                return {'ok': True, 'msg': f"Assets liquidated. Still need {fmt_money(self.debt['amt'] - p['cash'])}"}
            return {'ok': True, 'msg': 'Debt successfully cleared!'}

    def bankrupt_player(self, pid):
        with self.lock:
            self.last_activity = time.time()
            p = self.players[pid]
            p['bankrupt'] = True
            cred_id = self.debt['to'] if self.debt else None
            self.debt = None
            cred = self.players[cred_id] if isinstance(cred_id, int) else None

            self.log(f"💀 BANKRUPT! {p['name']} has been eliminated from GridLock!", 'bad')
            if cred:
                cred['cash'] += p['cash']
                for t in self.tiles_of(pid):
                    st = self.tiles[t]
                    st['owner'] = cred['id']
                    st['level'] = 1
            else:
                self.jackpot += p['cash']
                for t in self.tiles_of(pid):
                    st = self.tiles[t]
                    st['owner'] = None
                    st['level'] = 0
                    st['mortgaged'] = False

            p['cash'] = 0
            alive = [x for x in self.players if not x['bankrupt']]
            if len(alive) <= 1:
                self.end_game(winner=alive[0] if alive else None, reason='elimination')
            else:
                self.settle_phase()
            return {'ok': True, 'msg': f"{p['name']} declared bankruptcy"}

    def pay_jail(self, pid):
        with self.lock:
            self.last_activity = time.time()
            if pid != self.cur or self.phase != 'pre':
                return {'ok': False, 'msg': 'Cannot pay jail fee right now'}
            p = self.players[pid]
            if not p['in_jail']:
                return {'ok': False, 'msg': 'Not in REBOOT'}
            if p['cash'] < self.jail_fee:
                return {'ok': False, 'msg': f"Need {fmt_money(self.jail_fee)}"}

            p['cash'] -= self.jail_fee
            self.jackpot += self.jail_fee
            p['in_jail'] = False
            p['jail_turns'] = 0
            self.log(f"🔌 {p['name']} paid {fmt_money(self.jail_fee)} to Jackpot pool to exit REBOOT", 'good')
            return {'ok': True, 'msg': 'Left REBOOT'}

    def trade_properties(self, pid, to_seat, give_tids, get_tids, give_cash, get_cash):
        with self.lock:
            self.last_activity = time.time()
            if self.phase not in ['pre', 'post']:
                return {'ok': False, 'msg': 'Trading only allowed before roll or after move'}
            p1 = self.players[pid]
            target_pid = to_seat - 1
            if target_pid < 0 or target_pid >= len(self.players) or target_pid == pid:
                return {'ok': False, 'msg': 'Invalid trade partner seat'}
            p2 = self.players[target_pid]

            if p1['cash'] < give_cash:
                return {'ok': False, 'msg': f"You do not have {fmt_money(give_cash)}"}
            if p2['cash'] < get_cash:
                return {'ok': False, 'msg': f"{p2['name']} does not have {fmt_money(get_cash)}"}

            for t in give_tids:
                if self.tiles[t]['owner'] != p1['id']:
                    return {'ok': False, 'msg': f"You do not own tile {t}"}
                if self.lock_reason(t):
                    return {'ok': False, 'msg': self.lock_reason(t)}

            for t in get_tids:
                if self.tiles[t]['owner'] != p2['id']:
                    return {'ok': False, 'msg': f"{p2['name']} does not own tile {t}"}
                if self.lock_reason(t):
                    return {'ok': False, 'msg': self.lock_reason(t)}

            p1['cash'] -= give_cash
            p2['cash'] += give_cash
            p2['cash'] -= get_cash
            p1['cash'] += get_cash

            for t in give_tids:
                self.tiles[t]['owner'] = p2['id']
            for t in get_tids:
                self.tiles[t]['owner'] = p1['id']

            self.log(f"🤝 TRADE COMPLETED between {p1['name']} and {p2['name']}", 'good')
            return {'ok': True, 'msg': 'Trade executed'}

    def end_turn(self, pid):
        with self.lock:
            self.last_activity = time.time()
            if self.over:
                return {'ok': False, 'msg': 'Game already over'}
            if pid != self.cur:
                return {'ok': False, 'msg': 'Not your turn'}
            if self.phase != 'post':
                return {'ok': False, 'msg': f'Cannot end turn in phase: {self.phase}'}

            self.cur = (self.cur + 1) % len(self.players)
            if self.cur == 0:
                self.turn += 1
                if self.turn > self.max_turns:
                    richest = sorted(self.players, key=lambda x: self.net_worth(x), reverse=True)[0]
                    self.end_game(winner=richest, reason='turn_limit')
                    return {'ok': True, 'msg': f"Max turn limit reached! {richest['name']} wins!"}

            self.phase = 'pre'
            self.extra = False
            next_p = self.current_player()
            self.log(f"Turn {self.turn}: {next_p['name']}'s turn", 'sys')
            return {'ok': True, 'msg': f"Turn passed to {next_p['name']}"}

    def end_game(self, winner, reason):
        self.over = True
        self.winner = winner['id'] if winner else None
        w_name = winner['name'] if winner else 'Nobody'
        self.log(f"🏆 MATCH OVER! {w_name} is victorious! (Reason: {reason})", 'good')

    def reset_game(self):
        with self.lock:
            self.turn = 1
            self.cur = 0
            self.phase = 'pre'
            self.extra = False
            self.last_roll = 1
            self.debt = None
            self.auction = None
            self.pending = None
            self.over = False
            self.winner = None
            self.jackpot = 100
            self.tiles = [{'owner': None, 'level': 0, 'mortgaged': False} for _ in range(16)]
            for p in self.players:
                p['cash'] = self.start_cash
                p['pos'] = 0
                p['in_jail'] = False
                p['jail_turns'] = 0
                p['sixes'] = 0
                p['shield'] = False
                p['bankrupt'] = False
                p['hops'] = 0
            self.logs = []
            self.log('Match restarted. All systems reset.')
            return {'ok': True, 'msg': 'Game reset'}

    def step_ai_once(self):
        with self.lock:
            if self.over or len(self.players) < 2:
                return False
            if self.phase == 'auction' and self.auction:
                tp = self.players[self.auction['turn']]
                if tp['kind'] != 'ai':
                    return False
                t = TILES[self.auction['tid']]
                limit = int(t['cost'] * 0.9)
                cur_bid = self.auction['bid']
                next_bid = cur_bid + 10 if cur_bid > 0 else 10
                if next_bid <= limit and next_bid <= tp['cash'] - 50:
                    self.bid_auction(tp['id'], next_bid)
                else:
                    self.fold_auction(tp['id'])
                return True

            cp = self.current_player()
            if cp['kind'] != 'ai':
                return False

            if self.phase == 'pre':
                if cp['in_jail'] and cp['cash'] >= 270:
                    self.pay_jail(cp['id'])
                for tid in self.tiles_of(cp['id']):
                    if not self.why_no_build(cp['id'], tid) and cp['cash'] >= 300:
                        self.build_upgrade(cp['id'], tid)
                self.roll_dice(cp['id'])
                return True

            if self.phase == 'decide':
                t = TILES[self.pending]
                if cp['cash'] >= t['cost'] + 150:
                    self.buy_property(cp['id'])
                else:
                    self.decline_property(cp['id'])
                return True

            if self.phase == 'debt':
                self.auto_raise(cp['id'])
                if self.debt:
                    self.bankrupt_player(cp['id'])
                return True

            if self.phase == 'post':
                for tid in self.tiles_of(cp['id']):
                    if not self.why_no_build(cp['id'], tid) and cp['cash'] >= 300:
                        self.build_upgrade(cp['id'], tid)
                self.end_turn(cp['id'])
                return True

            return False

    def auto_step_ai(self, max_steps=10):
        steps = 0
        while steps < max_steps and not self.over:
            if not self.step_ai_once():
                break
            steps += 1
        return steps

    def exec_cli(self, command_str, player_token=None):
        with self.lock:
            line = (command_str or '').strip()
            if not line:
                return {'ok': True, 'msg': self.status_line(), 'next': self.legal_line()}

            parts = line.split()
            cmd = parts[0].lower()
            args = parts[1:]

            if cmd == 'help':
                help_text = chr(10).join([
                    "GRIDLOCK CLI — 1v1 Sovereign Monopoly Engine",
                    "ACTIONS:   roll | buy | decline | bid <n> | fold | end | jail | autoraise | bankrupt",
                    "BUILDING:  build <tile> | sell <tile> | mortgage <tile> | unmortgage <tile>",
                    "TRADING:   trade <seat> give=<ids> get=<ids> givecash=<n> getcash=<n>",
                    "VIEW:      status | board | legal | state | tiles | reset",
                    "Every command outputs status and NEXT legal moves for AI agents."
                ])
                return {'ok': True, 'msg': help_text, 'next': self.legal_line()}

            if cmd == 'status':
                return {'ok': True, 'msg': self.status_text(), 'next': self.legal_line()}

            if cmd == 'board':
                return {'ok': True, 'msg': self.ascii_board(), 'next': self.legal_line()}

            if cmd == 'legal':
                return {'ok': True, 'msg': chr(10).join(self.legal_moves()), 'next': self.legal_line()}

            if cmd == 'state':
                return {'ok': True, 'msg': json.dumps(self.to_dict(), indent=2), 'next': self.legal_line()}

            if cmd == 'tiles':
                return {'ok': True, 'msg': self.tiles_text(), 'next': self.legal_line()}

            if cmd == 'reset':
                r = self.reset_game()
                return {'ok': r['ok'], 'msg': r['msg'], 'next': self.legal_line()}

            pid = None
            if player_token:
                p = self.player_by_token(player_token)
                if not p:
                    return {'ok': False, 'msg': 'Invalid player token', 'next': self.legal_line()}
                pid = p['id']
            else:
                if self.phase == 'auction' and self.auction:
                    pid = self.auction['turn']
                else:
                    pid = self.cur

            res = {'ok': False, 'msg': f"Unknown command '{cmd}'"}

            if cmd == 'roll':
                res = self.roll_dice(pid)
            elif cmd == 'buy':
                res = self.buy_property(pid)
            elif cmd == 'decline':
                res = self.decline_property(pid)
            elif cmd == 'bid':
                amt = int(args[0]) if args and args[0].isdigit() else 0
                res = self.bid_auction(pid, amt)
            elif cmd == 'fold':
                res = self.fold_auction(pid)
            elif cmd in ['build', 'up', 'upgrade']:
                tid = int(args[0]) if args and args[0].isdigit() else -1
                res = self.build_upgrade(pid, tid)
            elif cmd == 'sell':
                tid = int(args[0]) if args and args[0].isdigit() else -1
                res = self.sell_building(pid, tid)
            elif cmd == 'mortgage':
                tid = int(args[0]) if args and args[0].isdigit() else -1
                res = self.mortgage_tile(pid, tid)
            elif cmd == 'unmortgage':
                tid = int(args[0]) if args and args[0].isdigit() else -1
                res = self.unmortgage_tile(pid, tid)
            elif cmd == 'jail':
                res = self.pay_jail(pid)
            elif cmd == 'autoraise':
                res = self.auto_raise(pid)
            elif cmd == 'bankrupt':
                res = self.bankrupt_player(pid)
            elif cmd == 'end':
                res = self.end_turn(pid)
            elif cmd == 'trade':
                to_seat = int(args[0]) if args and args[0].isdigit() else (2 if pid == 0 else 1)
                give_t = []
                get_t = []
                give_c = 0
                get_c = 0
                for a in args[1:]:
                    if a.startswith('give='):
                        val = a[5:]
                        if val != '-':
                            give_t = [int(x) for x in val.split(',') if x.isdigit()]
                    elif a.startswith('get='):
                        val = a[4:]
                        if val != '-':
                            get_t = [int(x) for x in val.split(',') if x.isdigit()]
                    elif a.startswith('givecash='):
                        give_c = int(a[9:]) if a[9:].isdigit() else 0
                    elif a.startswith('getcash='):
                        get_c = int(a[8:]) if a[8:].isdigit() else 0
                res = self.trade_properties(pid, to_seat, give_t, get_t, give_c, get_c)

            self.auto_step_ai()

            return {
                'ok': res['ok'],
                'msg': res['msg'],
                'status': self.status_line(),
                'next': self.legal_line(),
                'state': self.to_dict(),
                'legal': self.legal_moves()
            }

    def status_line(self):
        if not self.players:
            return "Room open, waiting for players."
        cp = self.current_player()
        if not cp:
            return "No active player."
        jail_txt = " • IN REBOOT" if cp['in_jail'] else ""
        bonus_txt = " • BONUS ROLL" if self.extra else ""
        over_txt = f" • OVER (Winner: {self.players[self.winner]['name']})" if self.over and self.winner is not None else ""
        return f"[T{self.turn}] {cp['name']} ({cp['tag']}) {fmt_money(cp['cash'])} @{cp['pos']} {TILES[cp['pos']]['name']} • phase:{self.phase} • pool {fmt_money(self.jackpot)}{jail_txt}{bonus_txt}{over_txt}"

    def status_text(self):
        lines = [self.status_line()]
        for p in self.players:
            props = ','.join(str(x) for x in self.tiles_of(p['id']))
            out_txt = " OUT" if p['bankrupt'] else ""
            shd_txt = " 🛡️" if p['shield'] else ""
            lines.append(f"{p['tag']} {pad_str(p['name'], 12)} {pad_str(fmt_money(p['cash']), 8)} net {pad_str(fmt_money(self.net_worth(p)), 8)} props:[{props}]{out_txt}{shd_txt}")
        return chr(10).join(lines)

    def legal_line(self):
        return 'NEXT: ' + ' | '.join(self.legal_moves())

    def tiles_text(self):
        out = []
        for t in TILES:
            st = self.tiles[t['id']]
            if t['type'] == 'prop':
                stat = 'free' if st['owner'] is None else f"P{st['owner']+1} L{st['level']}" + (' MORT' if st['mortgaged'] else '')
                out.append(f"{pad_str('#' + str(t['id']), 4)} {pad_str(t['name'], 14)} {pad_str(DISTRICTS[t['d']]['name'], 11)} {pad_str(fmt_money(t['cost']), 6)} {stat}")
            else:
                out.append(f"{pad_str('#' + str(t['id']), 4)} {pad_str(t['name'], 14)} {t['type']}")
        return chr(10).join(out)

    def ascii_board(self):
        W = 15
        cell_dict = {}
        for t in TILES:
            tid = t['id']
            st = self.tiles[tid]
            here = ''.join(p['tag'] for p in self.players if not p['bankrupt'] and p['pos'] == tid)
            if t['type'] == 'prop':
                if st['owner'] is None:
                    line2 = fmt_money(t['cost'])
                else:
                    m_mark = 'M' if st['mortgaged'] else ''
                    l_mark = '*' if self.lock_reason(tid) else ''
                    line2 = f"P{st['owner']+1} L{st['level']}{m_mark}{l_mark}"
            else:
                line2 = t['type']

            row1 = pad_str(f"{str(tid).zfill(2)} {t['name']}", W)
            row2 = pad_str(line2, W)
            row3 = pad_str(f"<{here}>" if here else "", W)
            cell_dict[tid] = [row1, row2, row3]

        g = {}
        for t in TILES:
            r, c = grid_of(t['id'])
            g[f"{r},{c}"] = cell_dict[t['id']]

        full = '+' + '+'.join(['-' * W for _ in range(5)]) + '+'
        open_border = '+' + ('-' * W) + '+' + (' ' * (W * 3 + 2)) + '+' + ('-' * W) + '+'

        out = []
        for r in range(1, 6):
            out.append(open_border if (r == 3 or r == 4) else full)
            for k in range(3):
                if 2 <= r <= 4:
                    if k == 1 and r == 3:
                        mid = pad_str(f"  POOL {fmt_money(self.jackpot)}  T{self.turn}", W * 3 + 2)
                    else:
                        mid = ' ' * (W * 3 + 2)
                    out.append(f"|{g[f'{r},1'][k]}|{mid}|{g[f'{r},5'][k]}|")
                else:
                    row_cells = '|'.join(g[f"{r},{c}"][k] for c in range(1, 6))
                    out.append(f"|{row_cells}|")

        out.append(full)
        out.append('Legend: P#=player token • P# L# owner/level • M=mortgaged • *=trade-locked')
        return chr(10).join(out)

    def to_dict(self):
        return {
            'turn': self.turn,
            'phase': self.phase,
            'cur': self.cur,
            'cur_tag': f"P{self.cur + 1}" if self.players else None,
            'jackpot': self.jackpot,
            'extra': self.extra,
            'last_roll': self.last_roll,
            'over': self.over,
            'winner': self.winner,
            'pending': self.pending,
            'debt': self.debt,
            'auction': {
                'tid': self.auction['tid'],
                'bid': self.auction['bid'],
                'high': self.auction['high'],
                'turn': self.auction['turn'],
                'folded': list(self.auction['folded'])
            } if self.auction else None,
            'players': [
                {
                    'id': p['id'],
                    'seat': p['id'] + 1,
                    'tag': p['tag'],
                    'name': p['name'],
                    'kind': p['kind'],
                    'avatar': p['avatar'],
                    'cash': p['cash'],
                    'net': self.net_worth(p),
                    'pos': p['pos'],
                    'at': TILES[p['pos']]['name'],
                    'in_jail': p['in_jail'],
                    'shield': p['shield'],
                    'bankrupt': p['bankrupt'],
                    'props': self.tiles_of(p['id'])
                } for p in self.players
            ],
            'tiles': [
                {
                    'id': t['id'],
                    'name': t['name'],
                    'type': t['type'],
                    'district': DISTRICTS[t['d']]['name'] if t['type'] == 'prop' else None,
                    'cost': t.get('cost'),
                    'owner': self.tiles[t['id']]['owner'],
                    'level': self.tiles[t['id']]['level'],
                    'mortgaged': self.tiles[t['id']]['mortgaged'],
                    'rent': self.rent_of(t['id']) if t['type'] == 'prop' else 0,
                    'buildCost': self.build_cost(t['id']) if t['type'] == 'prop' else 0
                } for t in TILES
            ],
            'legal': self.legal_moves()
        }

class GridLockRoomManager:
    def __init__(self):
        self.rooms = {}
        self.lock = threading.RLock()

    def generate_code(self):
        chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
        for _ in range(100):
            c = ''.join(random.choice(chars) for _ in range(4))
            if c not in self.rooms:
                return c
        return uuid.uuid4().hex[:4].upper()

    def create_room(self, host_name='Host', host_kind='human', host_avatar='cat', max_turns=50, start_cash=1500, auto_ai=True):
        with self.lock:
            code = self.generate_code()
            game = GridLockGame(start_cash=start_cash, max_turns=max_turns)
            p1 = game.add_player(name=host_name, kind=host_kind, avatar=host_avatar)
            room_entry = {
                'id': code,
                'game': game,
                'created_at': time.time(),
                'last_activity': time.time(),
                'auto_ai': auto_ai,
                'subscribers': []
            }
            self.rooms[code] = room_entry
            self.cleanup_old_rooms()
            return code, p1, game

    def join_room(self, code, name='Challenger', kind='human', avatar='bunny'):
        with self.lock:
            code = code.upper().strip()
            if code not in self.rooms:
                return None, 'Room not found'
            r = self.rooms[code]
            game = r['game']
            if len(game.players) >= 2:
                return None, 'Room already full (1v1 maximum)'
            p2 = game.add_player(name=name, kind=kind, avatar=avatar)
            r['last_activity'] = time.time()
            if r['auto_ai']:
                game.auto_step_ai()
            return p2, None

    def get_room(self, code):
        with self.lock:
            code = code.upper().strip()
            return self.rooms.get(code)

    def list_rooms(self):
        with self.lock:
            res = []
            for code, r in self.rooms.items():
                g = r['game']
                res.append({
                    'id': code,
                    'players_count': len(g.players),
                    'players': [{'name': p['name'], 'kind': p['kind'], 'avatar': p['avatar']} for p in g.players],
                    'waiting_for_p2': len(g.players) < 2,
                    'turn': g.turn,
                    'phase': g.phase,
                    'over': g.over,
                    'created_at': r['created_at'],
                    'last_activity': r['last_activity']
                })
            return sorted(res, key=lambda x: x['last_activity'], reverse=True)

    def quick_match(self, name='Player', kind='human', avatar='cat'):
        with self.lock:
            for code, r in self.rooms.items():
                g = r['game']
                if len(g.players) == 1 and not g.over:
                    p2, err = self.join_room(code, name=name, kind=kind, avatar=avatar)
                    if not err and p2:
                        return {
                            'matched': True,
                            'room_id': code,
                            'seat': 2,
                            'player_id': 1,
                            'player_token': p2['token'],
                            'state': g.to_dict(),
                            'legal': g.legal_moves(),
                            'status': g.status_line()
                        }
            code, p1, game = self.create_room(host_name=name, host_kind=kind, host_avatar=avatar)
            return {
                'matched': False,
                'created': True,
                'room_id': code,
                'seat': 1,
                'player_id': 0,
                'player_token': p1['token'],
                'state': game.to_dict(),
                'legal': game.legal_moves(),
                'status': game.status_line()
            }

    def stats(self):
        with self.lock:
            total_rooms = len(self.rooms)
            active_games = sum(1 for r in self.rooms.values() if not r['game'].over)
            waiting_rooms = sum(1 for r in self.rooms.values() if len(r['game'].players) == 1 and not r['game'].over)
            completed_games = sum(1 for r in self.rooms.values() if r['game'].over)
            total_turns = sum(r['game'].turn for r in self.rooms.values())
            return {
                'ok': True,
                'total_rooms': total_rooms,
                'active_games': active_games,
                'waiting_rooms': waiting_rooms,
                'completed_games': completed_games,
                'total_turns': total_turns,
                'engine': 'GridLock Sovereign 16-Tile Tactical Phone Datacenter v2.0'
            }

    def cleanup_old_rooms(self, max_idle_sec=14400):
        now = time.time()
        to_del = []
        for code, r in self.rooms.items():
            if now - r['last_activity'] > max_idle_sec:
                to_del.append(code)
        for c in to_del:
            del self.rooms[c]

GLOBAL_ROOM_MANAGER = GridLockRoomManager()
