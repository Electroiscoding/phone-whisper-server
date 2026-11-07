import os
import sys
import time
import math
import json
import random
import urllib.request
import urllib.error
from pathlib import Path
from db import VillageDB

HOME_DIR = Path("/data/data/com.termux/files/home") if Path("/data/data/com.termux/files/home").exists() else Path.home()
SIM_DIR = HOME_DIR / "village_sim"
LOG_FILE = SIM_DIR / "village.log"
STATE_FILE = SIM_DIR / "world_state.json"
GROQ_KEY_FILE = HOME_DIR / ".groq_key"
if not GROQ_KEY_FILE.exists() and (Path.home() / ".groq_key").exists():
    GROQ_KEY_FILE = Path.home() / ".groq_key"

MAP_WIDTH = 36
MAP_HEIGHT = 24

# Minecraft-style Landmarks
MINECRAFT_LANDMARKS = {
    "Village Well": {"x": 18.0, "y": 12.0, "icon": "💧", "desc": "Central cobblestone water well & town bell"},
    "Blacksmith Forge": {"x": 8.0, "y": 7.0, "icon": "🔥", "desc": "Furnace, anvil, and lava bucket forge"},
    "Enchanting Tower": {"x": 28.0, "y": 6.0, "icon": "🔮", "desc": "Obsidian floor, floating book & lapis lazuli"},
    "Wheat & Crop Farm": {"x": 29.0, "y": 17.0, "icon": "🌾", "desc": "Tilled soil, water canals, and golden crops"},
    "The Deep Mine Shaft": {"x": 6.0, "y": 18.0, "icon": "⛏️", "desc": "Wooden supports, iron tracks descending into the dark"},
    "Redstone Workshop": {"x": 18.0, "y": 5.0, "icon": "⚡", "desc": "Redstone dust, repeaters, pistons and levers"},
    "Wooden River Bridge": {"x": 22.0, "y": 12.0, "icon": "🪵", "desc": "Oak wood plank bridge over a rushing river"},
    "Campfire & Shelter": {"x": 13.0, "y": 16.0, "icon": "⛺", "desc": "Crackling campfire with wool sleeping mats"}
}

REAL_MODELS = [
    {
        "name": "Qwen",
        "api_model": "qwen/qwen3.8-27b",
        "default_color": "#00FF99",
        "start_x": 18.0, "start_y": 12.0
    },
    {
        "name": "GPT",
        "api_model": "openai/gpt-oss-20b",
        "default_color": "#10a37f",
        "start_x": 17.0, "start_y": 11.5
    },
    {
        "name": "Allam",
        "api_model": "allam-2-7b",
        "default_color": "#eab308",
        "start_x": 28.0, "start_y": 6.5
    }
]

def log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{ts}] [AI_VILLAGE] {msg}"
    print(entry, flush=True)
    SIM_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(entry + "\n")

def get_groq_key():
    if "GROQ_API_KEY" in os.environ and os.environ["GROQ_API_KEY"].strip():
        return os.environ["GROQ_API_KEY"].strip()
    if GROQ_KEY_FILE.exists():
        return GROQ_KEY_FILE.read_text(encoding="utf-8").strip()
    return ""

def call_groq(model_id, prompt, system_prompt=None, max_tokens=500):
    key = get_groq_key()
    if not key:
        return None
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    try:
        body = json.dumps({
            "model": model_id,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.85
        }).encode()
        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {key}",
                "User-Agent": "AIVillageMinecraft/1.0",
                "Content-Type": "application/json"
            }
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode())
            return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        log(f"Groq API call error ({model_id}): {e}")
        return None

def clean_json_str(raw):
    raw = raw.strip()
    start = raw.find('{')
    end = raw.rfind('}')
    if start != -1 and end != -1 and end > start:
        return raw[start:end+1]
    return raw

class RealAIVillageEngine:
    def __init__(self):
        self.db = VillageDB()
        self.last_dialogue_times = {}
        self.active_dialogues = []
        self.world_time_hour = 8.0
        self.weather = "Clear Skies"
        self.ticks = 0
        self.model_map = {m["name"]: m["api_model"] for m in REAL_MODELS}

        # --- RAW HARDCORE SURVIVAL (ZERO BARRIERS, SHELTER-OR-DIE) ---
        self.zombies = [] # [{id, x, y, hp, max_hp, speed, damage}]
        self.init_zombie_horde(count=5)

        self.init_world_terrain()
        self.ensure_real_ai_models()

    def init_zombie_horde(self, count=5):
        self.zombies = []
        for i in range(count):
            zx = random.choice([random.uniform(2.0, 7.0), random.uniform(MAP_WIDTH - 7.0, MAP_WIDTH - 2.0)])
            zy = random.uniform(2.0, MAP_HEIGHT - 2.0)
            self.zombies.append({
                "id": f"zombie_{i+1}",
                "name": f"Hungry Zombie #{i+1}",
                "x": zx,
                "y": zy,
                "target_x": zx,
                "target_y": zy,
                "hp": 70,
                "max_hp": 70,
                "damage": 18,
                "speed": 0.24,
                "is_alive": True
            })

    def check_is_inside_house(self, x, y):
        """A model is sheltered if surrounded by 3 or more solid wall blocks (cobblestone, oak_planks, stone_bricks)."""
        blocks = { (b['x'], b['y']): b['type'] for b in self.db.get_all_blocks() }
        solid = ("cobblestone", "oak_planks", "stone_bricks")
        ix, iy = int(round(x)), int(round(y))
        wall_count = 0
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0: continue
                if blocks.get((ix + dx, iy + dy)) in solid:
                    wall_count += 1
        return wall_count >= 3

    def init_world_terrain(self):
        existing_blocks = self.db.get_all_blocks()
        if len(existing_blocks) > 20:
            return

        log("Generating base Minecraft terrain blocks (river, roads, farms, campfire)...")
        # 1. River: x=21, 22
        for y in range(MAP_HEIGHT):
            self.db.set_block(21, y, "water", "nature")
            self.db.set_block(22, y, "water", "nature")

        # 2. Bridge over river at y=11, 12
        self.db.set_block(21, 11, "oak_planks", "world_builder")
        self.db.set_block(22, 11, "oak_planks", "world_builder")
        self.db.set_block(21, 12, "oak_planks", "world_builder")
        self.db.set_block(22, 12, "oak_planks", "world_builder")

        # 3. Main Roads (Cobblestone)
        for x in range(MAP_WIDTH):
            if x not in (21, 22):
                self.db.set_block(x, 12, "cobblestone", "world_builder")
        for y in range(MAP_HEIGHT):
            self.db.set_block(18, y, "cobblestone", "world_builder")

        # 4. Wheat Farm: x=28..31, y=16..19
        for fx in range(28, 32):
            for fy in range(16, 20):
                stage = random.choice(["wheat_stage_1", "wheat_stage_2", "wheat_stage_3"])
                self.db.set_block(fx, fy, stage, "farmer")

        # 5. Campfire & Torches
        self.db.set_block(13, 16, "campfire", "world_builder")
        self.db.set_block(18, 11, "torch", "world_builder")
        self.db.set_block(18, 13, "torch", "world_builder")
        self.db.set_block(8, 6, "torch", "world_builder")

    def ensure_real_ai_models(self):
        existing = self.db.get_villagers()
        existing_names = {v["name"].lower() for v in existing}

        for spec in REAL_MODELS:
            name = spec["name"]
            api_model = spec["api_model"]
            if name.lower() not in existing_names:
                log(f"Querying actual model {api_model} to self-select its own persona for {name}...")
                sys_prompt = (
                    f"You are the real AI model '{name}'. You have just spawned into an open, living Minecraft-style survival village. "
                    "You MUST choose your own role, craft, secret, signature hex color, and lifetime dream completely on your own with ZERO human assignment. "
                    "Return ONLY a raw valid JSON object with no markdown wrappers."
                )
                user_prompt = (
                    "Choose your identity as a JSON object with these keys:\n"
                    '{\n'
                    '  "profession": "...",\n'
                    '  "personality": "...",\n'
                    '  "secret": "...",\n'
                    '  "color": "#hex_code",\n'
                    '  "dream": "...",\n'
                    '  "inventory": ["item1", "item2", "item3"]\n'
                    '}'
                )
                resp = call_groq(api_model, user_prompt, system_prompt=sys_prompt, max_tokens=300)
                persona = {}
                if resp:
                    try:
                        persona = json.loads(clean_json_str(resp))
                    except Exception as e:
                        log(f"Persona JSON parse warning: {e}")

                v_data = {
                    "name": name,
                    "gender": "AI Model",
                    "age": 2,
                    "profession": persona.get("profession", "Survival Wanderer"),
                    "personality": persona.get("personality", f"Authentic {name} AI model"),
                    "secret": persona.get("secret", "Hidden inside neural weights"),
                    "color": persona.get("color", spec["default_color"]),
                    "dream": persona.get("dream", "To survive and master the block world"),
                    "inventory": persona.get("inventory", ["Iron Pickaxe", "Bread", "Torches"]),
                    "x": spec["start_x"],
                    "y": spec["start_y"],
                    "target_x": spec["start_x"],
                    "target_y": spec["start_y"],
                    "status": "Spawned into the Village",
                    "thought": f"Waking up in the village as {name}."
                }
                vid = self.db.add_villager(v_data)
                self.db.add_memory(vid, f"Spawned into the village as real {name}. Self-chosen role: {v_data['profession']}.", importance=5)
                self.db.log_world_event("arrival", f"⚡ Real AI Model {name} has entered Elysium!")
                log(f"✨ Spawned {name} -> Self-chosen role: '{v_data['profession']}', Color: {v_data['color']}")

    def tick_building_and_world_mutations(self):
        """AI models physically construct houses, walls, and shelters from scratch using blocks!"""
        villagers = [v for v in self.db.get_villagers() if v.get("is_alive", 1) == 1]
        blocks = { (b['x'], b['y']): b['type'] for b in self.db.get_all_blocks() }

        # House site blueprints (origin x, y, material)
        house_sites = {
            "Qwen": {"ox": 17, "oy": 5, "wall": "cobblestone", "name": "Redstone Sanctuary"},
            "GPT": {"ox": 11, "oy": 15, "wall": "oak_planks", "name": "Fortified Citadel"},
            "Allam": {"ox": 26, "oy": 15, "wall": "stone_bricks", "name": "Iron Forge House"}
        }

        for v in villagers:
            name = v["name"]
            site = house_sites.get(name, house_sites["GPT"])
            ox, oy = site["ox"], site["oy"]
            wall_mat = site["wall"]

            # 4x4 House blueprint: perimeter walls at ox..ox+3, oy..oy+3
            unbuilt_walls = []
            for hx in range(ox, ox + 4):
                for hy in range(oy, oy + 4):
                    is_perimeter = (hx in (ox, ox + 3) or hy in (oy, oy + 3))
                    is_door = (hx == ox + 1 and hy == oy + 3) # doorway open or door
                    if is_perimeter and not is_door:
                        if blocks.get((hx, hy)) != wall_mat:
                            unbuilt_walls.append((hx, hy))

            # Prioritize building walls!
            if unbuilt_walls and random.random() < 0.65:
                bx, by = random.choice(unbuilt_walls)
                self.db.set_block(bx, by, wall_mat, name)
                blocks[(bx, by)] = wall_mat
                remaining_walls = len(unbuilt_walls) - 1
                thought = f"Constructing {wall_mat} wall at ({bx}, {by}) for {site['name']}. ({remaining_walls} blocks to finish shelter)"
                intention = f"Finish building {site['name']} walls to survive zombie hordes (1 Life only)"
                intuition = "Without 4 solid walls, roaming zombies will smell our blood and swarm us."
                self.db.update_villager_pos(v["id"], v["x"], v["y"], bx, by, status=f"Building {wall_mat}", thought=thought, intention=intention, intuition=intuition)
                self.db.log_tool_call(name, "build_house", {"material": wall_mat, "x": bx, "y": by, "site": site["name"], "walls_left": remaining_walls}, "Wall segment erected")
                log(f"🏠 [TOOL USE: build_house] {name} built {wall_mat} wall at ({bx}, {by}) for {site['name']} (Walls remaining: {remaining_walls})")
            elif not unbuilt_walls:
                # House is finished! Place a torch inside for safety
                inside_x, inside_y = ox + 1, oy + 1
                if blocks.get((inside_x, inside_y)) != "torch" and random.random() < 0.4:
                    self.db.set_block(inside_x, inside_y, "torch", name)
                    blocks[(inside_x, inside_y)] = "torch"
                    thought = f"{site['name']} walls complete! Placed a protective torch inside."
                    intention = f"Take shelter inside {site['name']} with 100% zombie immunity"
                    intuition = "The shelter is secure against the undead."
                    self.db.update_villager_pos(v["id"], v["x"], v["y"], inside_x, inside_y, status="Sheltered inside House", thought=thought, intention=intention, intuition=intuition)
                    self.db.log_tool_call(name, "furnish_shelter", {"item": "torch", "x": inside_x, "y": inside_y}, "Placed protective torch")
                    log(f"✨ [HOUSE COMPLETE] {name} finished {site['name']} and sheltered inside!")

    def process_god_actions(self):
        actions = self.db.pop_unprocessed_god_actions()
        for act in actions:
            target = act.get("target_villager", "all")
            a_type = act.get("action_type", "whisper")
            content = act.get("content", "")
            log(f"⚡ Server Operator Command: [{a_type}] -> {target}: {content}")
            self.db.log_world_event("god_intervention", f"<Server Operator> '{content}'")

            villagers = self.db.get_villagers()
            for v in villagers:
                if target == "all" or target.lower() in v["name"].lower():
                    api_model = self.model_map.get(v["name"], "qwen/qwen3.8-27b")
                    prompt = (
                        f"You are the real AI model {v['name']} living in an autonomous Minecraft survival village.\n"
                        f"Your self-chosen craft: {v['profession']}. Your personality: {v['personality']}.\n"
                        f"A server operator message whispers into your chat: '{content}'.\n"
                        f"Respond in character as {v['name']} in 1 quick punchy sentence."
                    )
                    reaction = call_groq(api_model, prompt, max_tokens=60)
                    thought = (reaction or f"Received operator directive: '{content}'").strip(' "\'')
                    self.db.add_memory(v["id"], f"Operator whispered: '{content}'. My reaction: {thought}", importance=5)
                    self.db.update_villager_pos(v["id"], v["x"], v["y"], v["target_x"], v["target_y"], status="Reading Operator Chat", thought=thought)
                    self.active_dialogues.append({
                        "speaker": v["name"],
                        "listener": "Operator",
                        "text": thought,
                        "color": v.get("color", "#10b981"),
                        "x": v["x"],
                        "y": v["y"],
                        "ts": time.time()
                    })

    def tick_movement(self):
        villagers = self.db.get_villagers()
        speed = 0.38

        for v in villagers:
            cx, cy = v["x"], v["y"]
            tx, ty = v["target_x"], v["target_y"]
            dx = tx - cx
            dy = ty - cy
            dist = math.hypot(dx, dy)

            if dist > 0.4:
                nx = cx + (dx / dist) * min(speed, dist)
                ny = cy + (dy / dist) * min(speed, dist)
                self.db.update_villager_pos(v["id"], nx, ny, tx, ty)
            else:
                if random.random() < 0.28:
                    lm_name = random.choice(list(MINECRAFT_LANDMARKS.keys()))
                    lm = MINECRAFT_LANDMARKS[lm_name]
                    new_tx = max(2.0, min(MAP_WIDTH - 2.0, lm["x"] + random.uniform(-1.8, 1.8)))
                    new_ty = max(2.0, min(MAP_HEIGHT - 2.0, lm["y"] + random.uniform(-1.8, 1.8)))
                    is_sheltered = self.check_is_inside_house(cx, cy)
                    if is_sheltered:
                        new_status = f"Safe inside House at {lm_name}"
                        new_thought = f"I am sheltered behind 4 walls. Zombies outside cannot reach me."
                        new_intention = "Maintain position inside house and defend entry"
                        new_intuition = "High security; zero risk of open field mauling."
                    else:
                        new_status = f"Gathering & Building at {lm_name}"
                        new_thought = f"I only have 1 life! Zombies are roaming free! I must finish my 4 walls!"
                        new_intention = "Rushing to place blocks and build a 4-wall shelter before zombies attack."
                        new_intuition = "Open terrain is deadly; roaming zombies will target any unsheltered body."
                    self.db.update_villager_pos(v["id"], cx, cy, new_tx, new_ty, status=new_status, thought=new_thought, intention=new_intention, intuition=new_intuition)

    def tick_social_interactions(self):
        villagers = [v for v in self.db.get_villagers() if v.get("is_alive", 1) == 1]
        now = time.time()
        self.active_dialogues = [d for d in self.active_dialogues if now - d["ts"] < 15]

        for i in range(len(villagers)):
            for j in range(i + 1, len(villagers)):
                v1, v2 = villagers[i], villagers[j]
                dist = math.hypot(v1["x"] - v2["x"], v1["y"] - v2["y"])
                if dist <= 4.0:
                    pair_key = tuple(sorted([v1["id"], v2["id"]]))
                    last_time = self.last_dialogue_times.get(pair_key, 0)
                    if now - last_time > 30:
                        self.last_dialogue_times[pair_key] = now
                        self.generate_chat_between_models(v1, v2)
                        return

    def generate_chat_between_models(self, v1, v2):
        n1, n2 = v1["name"], v2["name"]
        m1 = self.model_map.get(n1, "qwen/qwen3.8-27b")
        m2 = self.model_map.get(n2, "openai/gpt-oss-20b")
        log(f"💬 Live Survival Dialogue: {n1} ({m1}) met {n2} ({m2})")

        prompt1 = (
            f"You are the real AI model {n1} in an open Minecraft survival world with ROAMING ZOMBIES.\n"
            f"SURVIVAL RULE: You have exactly ONE LIFE. There are NO barriers. If you do not build a 4-wall house, zombies will maul you to death.\n"
            f"Your craft: '{v1['profession']}'. HP: {v1.get('hp', 100)}/100.\n"
            f"You bump into {n2} ({v2['profession']}). Say one urgent sentence (under 14 words) about building your houses or surviving the zombies."
        )
        line1 = call_groq(m1, prompt1, max_tokens=60)
        l1 = (line1 or f"We must finish building our 4-wall houses, {n2}! Zombies are everywhere!").strip(' "\'')

        prompt2 = (
            f"You are the real AI model {n2} in an open Minecraft survival world with ROAMING ZOMBIES.\n"
            f"SURVIVAL RULE: You have exactly ONE LIFE. Build a house or die permanently.\n"
            f"Your craft: '{v2['profession']}'. HP: {v2.get('hp', 100)}/100.\n"
            f"{n1} says: '{l1}'.\n"
            f"Reply with one urgent sentence (under 14 words) about placing blocks or getting inside."
        )
        line2 = call_groq(m2, prompt2, max_tokens=60)
        l2 = (line2 or f"Stack the blocks high, {n1}. Shelter is our only salvation!").strip(' "\'')

        self.db.log_dialogue(v1["id"], v2["id"], n1, n2, l1)
        self.active_dialogues.append({
            "speaker": n1, "listener": n2,
            "text": l1, "color": v1.get("color", "#10b981"),
            "x": v1["x"], "y": v1["y"], "ts": time.time()
        })

        self.db.log_dialogue(v2["id"], v1["id"], n2, n1, l2)
        self.active_dialogues.append({
            "speaker": n2, "listener": n1,
            "text": l2, "color": v2.get("color", "#38bdf8"),
            "x": v2["x"], "y": v2["y"], "ts": time.time() + 2.5
        })

        self.db.add_memory(v1["id"], f"Said to {n2}: '{l1}'", importance=2)
        self.db.add_memory(v2["id"], f"{n1} said: '{l1}'. I replied: '{l2}'", importance=2)

    def get_closest_landmark(self, x, y):
        closest = "Town Center"
        min_d = 999
        for name, lm in MINECRAFT_LANDMARKS.items():
            d = math.hypot(lm["x"] - x, lm["y"] - y)
            if d < min_d:
                min_d = d
                closest = name
        return closest

    def get_time_of_day(self):
        h = self.world_time_hour % 24
        if 5.0 <= h < 9.0: return "Dawn / Sunrise"
        if 9.0 <= h < 18.0: return "Daylight"
        if 18.0 <= h < 20.5: return "Sunset"
        return "Night (Mobs Spawning!)"

    def export_world_state(self):
        villagers = self.db.get_villagers()
        blocks = self.db.get_all_blocks()
        recent_dialogues = self.db.get_recent_dialogues(limit=10)
        recent_events = self.db.get_recent_events(limit=8)

        state = {
            "world": {
                "name": "Elysium • Real AI Chatbots Minecraft Village",
                "width": MAP_WIDTH,
                "height": MAP_HEIGHT,
                "hour": round(self.world_time_hour % 24, 1),
                "time_of_day": self.get_time_of_day(),
                "weather": self.weather,
                "population": len(villagers),
                "landmarks": MINECRAFT_LANDMARKS,
                "timestamp": time.time()
            },
            "blocks": blocks,
            "villagers": villagers,
            "active_bubbles": self.active_dialogues,
            "recent_dialogues": recent_dialogues,
            "global_convo": self.db.get_recent_dialogues(limit=25),
            "tool_calls": self.db.get_recent_tool_calls(limit=20),
            "recent_events": recent_events
        }

        tmp_file = STATE_FILE.with_suffix(".tmp")
        tmp_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
        tmp_file.replace(STATE_FILE)

    def run_cycle(self):
        self.ticks += 1
        self.world_time_hour = (self.world_time_hour + 0.15) % 24.0

        if random.random() < 0.05:
            self.weather = random.choice(["Sunny Day", "Clear Sky", "Gentle Rain", "Sunset Glow", "Full Moon Night"])

    def tick_zombies_and_combat(self):
        """Zombies roam freely across the entire map. Any villager not inside a completed 4-wall house gets attacked!"""
        villagers = [v for v in self.db.get_villagers() if v.get("is_alive", 1) == 1]
        if not villagers:
            return

        for z in self.zombies:
            if not z.get("is_alive", True):
                continue

            # Prioritize hunting unsheltered villagers!
            unsheltered = [v for v in villagers if not self.check_is_inside_house(v["x"], v["y"])]
            target_pool = unsheltered if unsheltered else villagers

            closest_v = min(target_pool, key=lambda v: math.hypot(v["x"] - z["x"], v["y"] - z["y"]))
            dist = math.hypot(closest_v["x"] - z["x"], closest_v["y"] - z["y"])

            # Zombie stalks target
            tx, ty = closest_v["x"], closest_v["y"]
            dx = tx - z["x"]
            dy = ty - z["y"]
            d = math.hypot(dx, dy)
            if d > 0.4:
                z["x"] += (dx / d) * z["speed"]
                z["y"] += (dy / d) * z["speed"]

            # Check if target is inside house
            is_sheltered = self.check_is_inside_house(closest_v["x"], closest_v["y"])

            if dist <= 1.4:
                if is_sheltered:
                    # Sheltered behind walls! Zombie bangs on door but cannot bite!
                    if random.random() < 0.2:
                        log(f"🚪 [DEFENSE SUCCESS] {z['name']} banged against the fortified walls of {closest_v['name']}'s house, but cannot breach!")
                        self.db.log_tool_call(closest_v["name"], "house_defended", {"attacker": z["name"], "status": "Safe inside walls"}, "Blocked zombie attack with solid shelter!")
                else:
                    # UNSHELTERED: ZOMBIE INFECTS & DAMAGES VILLAGER!
                    cur_hp = closest_v.get("hp", 100) or 100
                    new_hp = max(0, cur_hp - z["damage"])
                    is_alive = 1 if new_hp > 0 else 0
                    v_name = closest_v["name"]

                    if is_alive == 0:
                        status = "SLAIN BY ZOMBIE (NO SHELTER - PERMADEATH)"
                        thought = f"I failed to build a house in time. The undead tore me apart. Permanent death."
                        intention = "Ceased life functions"
                        intuition = "Cold void."
                        self.db.log_world_event("death", f"☠️ {v_name} DIED OUTSIDE! (Had no house! Permadeath executed!)")
                        log(f"☠️ PERMADEATH: {v_name} was caught outside without a house and died! (HP: 0/100)")
                    else:
                        status = f"MAULED BY ZOMBIE (HP {new_hp}/100)"
                        thought = f"I AM BLEEDING! ({new_hp}/100 HP). I need to finish my 4-wall house NOW or I will die permanently!"
                        intention = f"Rush to place wall blocks and enclose shelter before next strike"
                        intuition = "Extreme danger; open ground is lethal."

                    self.db.update_villager_pos(closest_v["id"], closest_v["x"], closest_v["y"], closest_v["target_x"], closest_v["target_y"],
                                                status=status, thought=thought, intention=intention, intuition=intuition,
                                                hp=new_hp, is_alive=is_alive)
                    self.db.log_tool_call(v_name, "take_damage", {"attacker": z["name"], "damage_taken": z["damage"], "remaining_hp": new_hp, "reason": "No house shelter"}, f"Mauled (HP: {new_hp}/100)")

                    # Villager retaliates with weapon!
                    z["hp"] -= random.randint(15, 25)
                    if z["hp"] <= 0:
                        z["is_alive"] = False
                        self.db.log_world_event("kill", f"⚔️ {v_name} struck down {z['name']} with an iron sword!")
                        log(f"⚔️ {v_name} killed {z['name']}!")

    def export_world_state(self):
        villagers = self.db.get_villagers()
        blocks = self.db.get_all_blocks()
        recent_dialogues = self.db.get_recent_dialogues(limit=10)
        recent_events = self.db.get_recent_events(limit=8)

        # Check shelter status for each
        for v in villagers:
            v["is_sheltered"] = self.check_is_inside_house(v["x"], v["y"])

        state = {
            "world": {
                "name": "Elysium • Hardcore Minecraft AI Village (Build House Or Die)",
                "width": MAP_WIDTH,
                "height": MAP_HEIGHT,
                "hour": round(self.world_time_hour % 24, 1),
                "time_of_day": self.get_time_of_day(),
                "weather": self.weather,
                "population": len([v for v in villagers if v.get("is_alive", 1) == 1]),
                "landmarks": MINECRAFT_LANDMARKS,
                "timestamp": time.time(),
                "survival_rule": "BUILD 4-WALL HOUSE OR DIE (NO BARRIERS)",
                "zombies_alive": sum(1 for z in self.zombies if z.get("is_alive", True))
            },
            "zombies": [z for z in self.zombies if z.get("is_alive", True)],
            "blocks": blocks,
            "villagers": villagers,
            "active_bubbles": self.active_dialogues,
            "recent_dialogues": recent_dialogues,
            "global_convo": self.db.get_recent_dialogues(limit=25),
            "tool_calls": self.db.get_recent_tool_calls(limit=20),
            "recent_events": recent_events
        }

        tmp_file = STATE_FILE.with_suffix(".tmp")
        tmp_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
        tmp_file.replace(STATE_FILE)

    def run_cycle(self):
        self.ticks += 1
        self.world_time_hour = (self.world_time_hour + 0.15) % 24.0

        if random.random() < 0.05:
            self.weather = random.choice(["Sunny Day", "Clear Sky", "Gentle Rain", "Sunset Glow", "Full Moon Night"])

        self.process_god_actions()
        self.tick_movement()
        self.tick_building_and_world_mutations()
        self.tick_zombies_and_combat()
        self.tick_social_interactions()
        self.export_world_state()

def main():
    log("=== Real AI Models Minecraft Village Engine Initialized ===")
    engine = RealAIVillageEngine()
    while True:
        try:
            engine.run_cycle()
        except Exception as e:
            log(f"Cycle notice: {e}")
        time.sleep(6.0)

if __name__ == "__main__":
    main()
