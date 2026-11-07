import os
import json
import sqlite3
import time
from pathlib import Path

def get_db_path():
    candidates = [
        Path("/data/data/com.termux/files/home/village_sim/village.db"),
        Path(__file__).parent / "village.db",
        Path.home() / "village_sim" / "village.db"
    ]
    for c in candidates:
        if c.parent.exists():
            return c
    candidates[1].parent.mkdir(parents=True, exist_ok=True)
    return candidates[1]

class VillageDB:
    def __init__(self, path=None):
        self.path = Path(path) if path else get_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.init_schema()

    def get_conn(self):
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        return conn

    def init_schema(self):
        with self.get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS villagers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE,
                    gender TEXT,
                    age INTEGER,
                    profession TEXT,
                    personality TEXT,
                    secret TEXT,
                    color TEXT,
                    dream TEXT,
                    x REAL DEFAULT 18.0,
                    y REAL DEFAULT 12.0,
                    target_x REAL DEFAULT 18.0,
                    target_y REAL DEFAULT 12.0,
                    status TEXT DEFAULT 'Arrived in Elysium',
                    thought TEXT DEFAULT 'Contemplating the world...',
                    intention TEXT DEFAULT 'Exploring surroundings',
                    intuition TEXT DEFAULT 'Sensing the balance of the land',
                    inventory TEXT DEFAULT '[]',
                    hp INTEGER DEFAULT 100,
                    max_hp INTEGER DEFAULT 100,
                    is_alive INTEGER DEFAULT 1,
                    energy INTEGER DEFAULT 100,
                    happiness INTEGER DEFAULT 100,
                    created_at REAL,
                    updated_at REAL
                );

                CREATE TABLE IF NOT EXISTS dialogues (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    speaker_id INTEGER,
                    listener_id INTEGER,
                    speaker_name TEXT,
                    listener_name TEXT,
                    content TEXT,
                    timestamp REAL
                );

                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    villager_id INTEGER,
                    description TEXT,
                    importance INTEGER DEFAULT 1,
                    timestamp REAL
                );

                CREATE TABLE IF NOT EXISTS world_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT,
                    content TEXT,
                    timestamp REAL
                );

                CREATE TABLE IF NOT EXISTS god_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target_villager TEXT,
                    action_type TEXT,
                    content TEXT,
                    processed INTEGER DEFAULT 0,
                    created_at REAL
                );
            """)
            # Schema migration
            cols = [r[1] for r in conn.execute("PRAGMA table_info(villagers)").fetchall()]
            if "intention" not in cols:
                conn.execute("ALTER TABLE villagers ADD COLUMN intention TEXT DEFAULT 'Exploring surroundings'")
            if "intuition" not in cols:
                conn.execute("ALTER TABLE villagers ADD COLUMN intuition TEXT DEFAULT 'Sensing the land'")
            if "hp" not in cols:
                conn.execute("ALTER TABLE villagers ADD COLUMN hp INTEGER DEFAULT 100")
            if "max_hp" not in cols:
                conn.execute("ALTER TABLE villagers ADD COLUMN max_hp INTEGER DEFAULT 100")
            if "is_alive" not in cols:
                conn.execute("ALTER TABLE villagers ADD COLUMN is_alive INTEGER DEFAULT 1")

    def get_villagers(self):
        with self.get_conn() as conn:
            rows = conn.execute("SELECT * FROM villagers ORDER BY id ASC").fetchall()
            return [dict(r) for r in rows]

    def get_villager(self, vid_or_name):
        with self.get_conn() as conn:
            if isinstance(vid_or_name, int) or str(vid_or_name).isdigit():
                row = conn.execute("SELECT * FROM villagers WHERE id = ?", (int(vid_or_name),)).fetchone()
            else:
                row = conn.execute("SELECT * FROM villagers WHERE name = ?", (str(vid_or_name),)).fetchone()
            return dict(row) if row else None

    def add_villager(self, v):
        now = time.time()
        inv = json.dumps(v.get("inventory", [])) if isinstance(v.get("inventory"), list) else v.get("inventory", "[]")
        with self.get_conn() as conn:
            cur = conn.execute("""
                INSERT INTO villagers 
                (name, gender, age, profession, personality, secret, color, dream, x, y, target_x, target_y, status, thought, intention, intuition, inventory, hp, max_hp, is_alive, energy, happiness, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                v["name"], v.get("gender", "Unspecified"), v.get("age", 25), v.get("profession", "Wanderer"),
                v.get("personality", "Curious soul"), v.get("secret", "None"), v.get("color", "#4ade80"),
                v.get("dream", "To live fully"), v.get("x", 18.0), v.get("y", 12.0),
                v.get("target_x", 18.0), v.get("target_y", 12.0), v.get("status", "Arrived"),
                v.get("thought", "Observing surroundings"),
                v.get("intention", "Exploring and gathering materials"),
                v.get("intuition", "Need shelter before the undead roam"),
                inv,
                v.get("hp", 100), v.get("max_hp", 100), v.get("is_alive", 1),
                v.get("energy", 100), v.get("happiness", 100), now, now
            ))
            return cur.lastrowid

    def update_villager_pos(self, vid, x, y, target_x, target_y, status=None, thought=None, intention=None, intuition=None, hp=None, is_alive=None):
        now = time.time()
        query = "UPDATE villagers SET x = ?, y = ?, target_x = ?, target_y = ?, updated_at = ?"
        params = [x, y, target_x, target_y, now]
        if status is not None:
            query += ", status = ?"
            params.append(status)
        if thought is not None:
            query += ", thought = ?"
            params.append(thought)
        if intention is not None:
            query += ", intention = ?"
            params.append(intention)
        if intuition is not None:
            query += ", intuition = ?"
            params.append(intuition)
        if hp is not None:
            query += ", hp = ?"
            params.append(int(hp))
        if is_alive is not None:
            query += ", is_alive = ?"
            params.append(int(is_alive))
        query += " WHERE id = ?"
        params.append(vid)
        with self.get_conn() as conn:
            conn.execute(query, params)

    def log_dialogue(self, s_id, l_id, s_name, l_name, content):
        now = time.time()
        with self.get_conn() as conn:
            conn.execute("""
                INSERT INTO dialogues (speaker_id, listener_id, speaker_name, listener_name, content, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (s_id, l_id, s_name, l_name, content, now))

    def get_recent_dialogues(self, limit=15):
        with self.get_conn() as conn:
            rows = conn.execute("SELECT * FROM dialogues ORDER BY timestamp DESC LIMIT ?", (limit,)).fetchall()
            return [dict(r) for r in reversed(rows)]

    def add_memory(self, vid, desc, importance=1):
        now = time.time()
        with self.get_conn() as conn:
            conn.execute("""
                INSERT INTO memories (villager_id, description, importance, timestamp)
                VALUES (?, ?, ?, ?)
            """, (vid, desc, importance, now))

    def get_memories(self, vid, limit=10):
        with self.get_conn() as conn:
            rows = conn.execute("SELECT * FROM memories WHERE villager_id = ? ORDER BY timestamp DESC LIMIT ?", (vid, limit)).fetchall()
            return [dict(r) for r in rows]

    def log_world_event(self, ev_type, content):
        now = time.time()
        with self.get_conn() as conn:
            conn.execute("""
                INSERT INTO world_events (event_type, content, timestamp)
                VALUES (?, ?, ?)
            """, (ev_type, content, now))

    def get_recent_events(self, limit=10):
        with self.get_conn() as conn:
            rows = conn.execute("SELECT * FROM world_events ORDER BY timestamp DESC LIMIT ?", (limit,)).fetchall()
            return [dict(r) for r in reversed(rows)]

    def add_god_action(self, target, action_type, content):
        now = time.time()
        with self.get_conn() as conn:
            conn.execute("""
                INSERT INTO god_queue (target_villager, action_type, content, processed, created_at)
                VALUES (?, ?, ?, 0, ?)
            """, (target, action_type, content, now))

    def pop_unprocessed_god_actions(self):
        with self.get_conn() as conn:
            rows = conn.execute("SELECT * FROM god_queue WHERE processed = 0 ORDER BY id ASC").fetchall()
            actions = [dict(r) for r in rows]
            if actions:
                ids = [a["id"] for a in actions]
                placeholders = ",".join("?" for _ in ids)
                conn.execute(f"UPDATE god_queue SET processed = 1 WHERE id IN ({placeholders})", ids)
            return actions

    def init_blocks_table(self):
        with self.get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS world_blocks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    x INTEGER,
                    y INTEGER,
                    block_type TEXT,
                    placed_by TEXT,
                    placed_at REAL,
                    data TEXT DEFAULT '',
                    UNIQUE(x, y)
                );
            """)

    def set_block(self, x, y, b_type, placed_by='terrain', data=''):
        now = time.time()
        with self.get_conn() as conn:
            conn.execute("""
                INSERT INTO world_blocks (x, y, block_type, placed_by, placed_at, data)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(x, y) DO UPDATE SET
                    block_type = excluded.block_type,
                    placed_by = excluded.placed_by,
                    placed_at = excluded.placed_at,
                    data = excluded.data
            """, (int(x), int(y), b_type, placed_by, now, data))

    def get_all_blocks(self):
        self.init_blocks_table()
        with self.get_conn() as conn:
            rows = conn.execute("SELECT x, y, block_type, placed_by, data FROM world_blocks").fetchall()
            return [{"x": r["x"], "y": r["y"], "type": r["block_type"], "by": r["placed_by"], "data": r["data"]} for r in rows]

    def remove_block(self, x, y):
        with self.get_conn() as conn:
            conn.execute("DELETE FROM world_blocks WHERE x = ? AND y = ?", (int(x), int(y)))

    def init_tool_calls_table(self):
        with self.get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tool_calls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent TEXT,
                    tool_name TEXT,
                    args TEXT,
                    result TEXT,
                    timestamp REAL
                );
            """)

    def log_tool_call(self, agent, tool_name, args_dict, result_str):
        self.init_tool_calls_table()
        now = time.time()
        args_json = json.dumps(args_dict) if isinstance(args_dict, dict) else str(args_dict)
        with self.get_conn() as conn:
            conn.execute("""
                INSERT INTO tool_calls (agent, tool_name, args, result, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, (agent, tool_name, args_json, result_str, now))

    def get_recent_tool_calls(self, limit=20):
        self.init_tool_calls_table()
        with self.get_conn() as conn:
            rows = conn.execute("SELECT * FROM tool_calls ORDER BY timestamp DESC LIMIT ?", (limit,)).fetchall()
            return [dict(r) for r in reversed(rows)]
