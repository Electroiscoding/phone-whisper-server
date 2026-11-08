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

# The 3 Real AI Models hosted on your Groq key
REAL_MODELS = [
    {
        "name": "Qwen",
        "api_model": "qwen/qwen3.8-27b",
        "default_color": "#10b981",
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
        self.ensure_real_ai_models()

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
                    new_status = f"Heading to {lm_name}"
                    new_thought = f"Walking toward {lm_name} to work on {v['dream']}."
                    self.db.update_villager_pos(v["id"], cx, cy, new_tx, new_ty, status=new_status, thought=new_thought)

    def tick_social_interactions(self):
        villagers = self.db.get_villagers()
        now = time.time()
        self.active_dialogues = [d for d in self.active_dialogues if now - d["ts"] < 15]

        for i in range(len(villagers)):
            for j in range(i + 1, len(villagers)):
                v1, v2 = villagers[i], villagers[j]
                dist = math.hypot(v1["x"] - v2["x"], v1["y"] - v2["y"])
                if dist <= 4.0:
                    pair_key = tuple(sorted([v1["id"], v2["id"]]))
                    last_time = self.last_dialogue_times.get(pair_key, 0)
                    if now - last_time > 35:
                        self.last_dialogue_times[pair_key] = now
                        self.generate_chat_between_models(v1, v2)
                        return

    def generate_chat_between_models(self, v1, v2):
        n1, n2 = v1["name"], v2["name"]
        m1 = self.model_map.get(n1, "qwen/qwen3.8-27b")
        m2 = self.model_map.get(n2, "openai/gpt-oss-20b")
        log(f"💬 Live Model Dialogue: {n1} ({m1}) met {n2} ({m2})")

        # Step 1: Model 1 speaks using its own actual LLM
        prompt1 = (
            f"You are the real AI model {n1} living in an autonomous Minecraft survival village.\n"
            f"Your self-chosen craft is '{v1['profession']}'. Your personality: {v1['personality']}.\n"
            f"You just bumped into {n2} ({v2['profession']}) near the {self.get_closest_landmark(v1['x'], v1['y'])}.\n"
            f"Say one natural, authentic line to {n2} (under 15 words). Speak in your genuine {n1} chatbot voice."
        )
        line1 = call_groq(m1, prompt1, max_tokens=60)
        l1 = (line1 or f"Hey {n2}, how is your {v2['profession']} work going?").strip(' "\'')

        # Step 2: Model 2 responds using its own actual LLM
        prompt2 = (
            f"You are the real AI model {n2} living in an autonomous Minecraft survival village.\n"
            f"Your self-chosen craft is '{v2['profession']}'. Your personality: {v2['personality']}.\n"
            f"{n1} just walked up to you and said: '{l1}'.\n"
            f"Reply to {n1} with one natural line in your genuine {n2} chatbot voice (under 15 words)."
        )
        line2 = call_groq(m2, prompt2, max_tokens=60)
        l2 = (line2 or f"Good to see you {n1}. Let us keep building.").strip(' "\'')

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
            "villagers": villagers,
            "active_bubbles": self.active_dialogues,
            "recent_dialogues": recent_dialogues,
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
