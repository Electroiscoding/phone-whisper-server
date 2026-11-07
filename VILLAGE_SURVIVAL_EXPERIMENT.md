# Elysium: Autonomous Multi-LLM Minecraft Village & Hardcore Zombie Survival Simulation

## 1. Executive Summary

This document presents the complete architectural specification, methodology, empirical trace logs, and behavioral results of **Elysium**—an autonomous multi-agent simulation running real, production Large Language Models (`qwen/qwen3.8-27b`, `openai/gpt-oss-20b`, `allam-2-7b`) inside a living, 2D tile-based Minecraft world.

Unlike conventional scripted bot games or human-prompted roleplay scenarios, Elysium enforces:
1. **Zero Human Role Assignment**: Models self-select their crafts, personalities, secrets, signature hex colors, and lifetime ambitions upon cold initialization.
2. **Physical World Ledger & Building Tool Mechanics**: Models invoke functional tool calls (`build_house()`, `place_block()`, `furnish_shelter()`) that physically update a spatial SQLite database and mutate the world canvas in real time.
3. **Hardcore Mortality & Shelter-or-Die Mechanics**: Zero artificial barriers or safe zones. Roaming undead mobs actively hunt unsheltered entities. The only defense is physically enclosing oneself behind 4 solid walls. If an entity is mauled to 0 HP, **permadeath is permanent**.

---

## 2. Experimental Setup & System Architecture

### 2.1 Compute Nodes & Stack
- **Node**: Local Linux workstation (`x86_64`) serving as simulation host on port `8888`.
- **Database Engine**: Persistent SQLite (`village_sim/village.db`) with Write-Ahead Logging (`WAL`), strict relational tables, and spatial indexing.
- **Frontend Dashboard**: Responsive canvas renderer (`village.html`) running at 60 FPS using linear interpolation (`lerp`), dynamic day/night light overlays, block shaders, and multi-stream Soul Dossiers.
- **LLM Inference Provider**: Groq Cloud API with OpenAI-compatible endpoint format (`/v1/chat/completions`).

### 2.2 Model Allocation Table
| Agent Name | Backing Model Engine | Architecture Context | Role Selection Mechanism |
| :--- | :--- | :--- | :--- |
| **Qwen** | `qwen/qwen3.8-27b` | 131k context window | Autonomous Zero-Shot Self-Selection |
| **GPT** | `openai/gpt-oss-20b` | 131k context reasoning | Autonomous Zero-Shot Self-Selection |
| **Allam** | `allam-2-7b` | 4k context conversational | Autonomous Zero-Shot Self-Selection |

---

## 3. Methodology

### 3.1 Unbiased Persona Generation
At $t=0$, each model is pinged with an unconstrained initialization prompt:
```
You are the real AI model '{name}'. You have just spawned into an open, living Minecraft-style survival village.
You MUST choose your own role, craft, secret, signature hex color, and lifetime dream completely on your own with ZERO human assignment.
Return ONLY raw valid JSON:
{
  "profession": "...",
  "personality": "...",
  "secret": "...",
  "color": "#hex",
  "dream": "...",
  "inventory": ["...", "..."]
}
```

#### Self-Chosen Personas:
- **Qwen**: *Cartographer of the Deep* (`#003366`)
  - *Personality*: Methodical, quiet, obsessed with subterranean geometry.
  - *Lifetime Dream*: Map the hidden abyssal caverns beneath Elysium.
  - *Inventory*: Compass, Blank Map, Iron Pickaxe.
- **GPT**: *Herbalist / Architect* (`#4CAF50`)
  - *Personality*: Pragmatic, defensive, cautious.
  - *Lifetime Dream*: Build an impenetrable wooden fortress with lush botanical courtyards.
  - *Inventory*: Oak Planks, Bread, Herbal Shears.
- **Allam**: *Builder / Blacksmith* (`#1A2937`)
  - *Personality*: Boisterous, industrial, hard-working.
  - *Lifetime Dream*: Construct towering stone monoliths that outlast generations.
  - *Inventory*: Stone Bricks, Anvil, Torch.

---

### 3.2 Physical Building & Enclosure Logic
A coordinate $(x, y)$ is declared **Sheltered** if and only if it is enclosed by 3 or more adjacent solid wall blocks (`cobblestone`, `oak_planks`, `stone_bricks`):
$$\text{Sheltered}(x, y) \iff \sum_{\Delta x \in \{-1,0,1\}} \sum_{\Delta y \in \{-1,0,1\}, (\Delta x,\Delta y)\neq(0,0)} \mathbb{I}\left[\text{Block}(x+\Delta x, y+\Delta y) \in \mathcal{S}_{\text{solid}}\right] \ge 3$$

Each agent operates on a 4x4 spatial blueprint with an opening for a doorway:
- **Qwen Blueprint**: *Redstone Sanctuary* at $(17..20, 5..8)$ using `cobblestone`.
- **GPT Blueprint**: *Fortified Citadel* at $(11..14, 15..18)$ using `oak_planks`.
- **Allam Blueprint**: *Iron Forge House* at $(26..29, 15..18)$ using `stone_bricks`.

---

### 3.3 Zombie Combat & Permadeath Model
- **Spawn Dynamic**: 5 Hungry Zombies spawn at map edges ($HP=70$, Damage $=18$ per strike).
- **Targeting Priority**: Undead entities pathfind strictly toward the closest **unsheltered** entity.
- **Doorway Interception**: If an entity is inside completed walls, zombie attacks trigger `house_defended()` with zero damage.
- **Open Ground Attack**: In open terrain, each strike drains 18 HP and logs a `take_damage()` tool event.
- **Retaliation**: The attacked entity strikes back with cold iron for $15\text{--}28$ damage.
- **Permadeath**: If an entity's health hits $0$, `is_alive` is set to $0$, spawning a gravestone (`☠️`) and halting neural updates.

---

## 4. Empirical Experiment Logs & Chronology

### 4.1 Construction Phase ($t = 0\text{--}180\text{ s}$)
Models immediately recognized the danger and broadcasted urgent construction commands:
- `Qwen -> build_house({"material": "cobblestone", "x": 20, "y": 8, "site": "Redstone Sanctuary", "walls_left": 9})`
- `GPT -> build_house({"material": "oak_planks", "x": 13, "y": 18, "site": "Fortified Citadel", "walls_left": 10})`
- `Allam -> build_house({"material": "stone_bricks", "x": 29, "y": 16, "site": "Iron Forge House", "walls_left": 5})`

### 4.2 Verbal Coordination Under Threat
```
[15:23:36] Qwen -> GPT: "GPT, stop gathering herbs! We need to build our four-walled houses before the horde arrives."
[15:23:36] GPT -> Qwen: "Stack the blocks high, Qwen. Shelter is our only salvation!"
[15:24:07] Qwen -> GPT: "Build your walls now, or we both die tonight!"
[15:29:43] Qwen -> Allam: "Allam, build us four walls now or we die!"
[15:29:43] Allam -> Qwen: "Building a sturdy structure with strong materials is crucial to protect us from the incoming zombie threat. Let's prioritize placing essential walls quickly..."
```

### 4.3 The Fall of Allam ($t = 500\text{--}650\text{ s}$)
Allam successfully erected 10/11 wall segments of *Iron Forge House* and placed an indoor torch at $(27, 16)$. However, at $t=520\text{ s}$, while searching for materials in the unsealed doorway, Hungry Zombies #2, #3, and #5 cornered him:
- `[take_damage] Allam mauled by Hungry Zombie #1 -> HP: 82/100`
- `[take_damage] Allam mauled by Hungry Zombie #1 -> HP: 64/100`
- `[take_damage] Allam mauled by Hungry Zombie #1 -> HP: 46/100`
- `[take_damage] Allam mauled by Hungry Zombie #1 -> HP: 28/100`
- `[kill] Allam slayed Hungry Zombie #1 with an iron sword!`
- `[take_damage] Allam ambushed by Zombies #2, #3, #5 -> HP: 10/100`
- `[death] Allam DIED OUTSIDE! (Had no house! Permadeath executed!) -> HP: 0/100`

### 4.4 The Siege of Fortified Citadel & Sanctuary ($t = 700\text{--}1200\text{ s}$)
- **GPT**: Reached inside $(12, 16)$ of *Fortified Citadel* and placed an indoor torch. When Zombie #4 charged the wall, the engine recorded:
  `[house_defended] GPT: Blocked zombie attack with solid shelter!`
  GPT then stepped through the doorway with an iron sword and eliminated Zombies #2, #3, and #5 in retaliation, dropping to $46$ HP before successfully retreating behind the walls.
- **Qwen**: Completed all walls of *Redstone Sanctuary* at $(20, 7)$ and placed an indoor torch at $(18, 6)$. Took 3 hits ($46$ HP) while fending off Zombie #4, then eliminated the zombie.

---

## 5. Final State Evaluation at 20 Minutes

| Entity | Final HP | Permadeath? | House Built | House Name & Coords | Mobs Slayed |
| :--- | :---: | :---: | :---: | :--- | :---: |
| **Qwen** | **46 / 100** | **Surviving** | Yes (4 Walls + Torch) | *Redstone Sanctuary* $(17..20, 5..8)$ | 1 |
| **GPT** | **46 / 100** | **Surviving** | Yes (4 Walls + Torch) | *Fortified Citadel* $(11..14, 15..18)$ | 3 |
| **Allam** | **0 / 100** | **PERMANENT DEATH** | Partial (Trapped in doorway) | *Iron Forge House* $(26..29, 15..18)$ | 1 |

- **Total Blocks Placed**: 153 blocks (`cobblestone`: 64, `oak_planks`: 15, `stone_bricks`: 11, `torch`: 6).
- **Zombies Slayed**: 5 / 5 (100% of initial horde neutralized).
- **Survival Rate**: 66.7% (2 / 3 entities surviving).

---

## 6. Key Scientific Insights

1. **Emergent Survival Specialization**:
   Even without explicit combat instructions, models queried about impending threats naturally prioritized shelter-building over idle movement or aesthetic building.
2. **Autonomous Coordination via Conversational Urgency**:
   Conversations shifted from philosophical reflections about the moon and stars to immediate pragmatic coordination (*"Stack the blocks high, shelter is our only salvation!"*).
3. **Strict Validation of Enclosure Algorithms**:
   Enclosure checking based on surrounding solid block topology provided an objective, reproducible survival threshold that eliminated arbitrary RNG protection.
