import json
import urllib.request
import threading
import time
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "mobile"))
sys.path.insert(0, os.path.dirname(__file__))

from gateway import MultiModalGatewayHandler, ThreadedHTTPServer
from recsys.engine import get_recsys_engine

# Pre-warm recsys engine in main process so embedder weights are in cache
print("[*] Warming up recsys engine...")
engine = get_recsys_engine()
# Call rank_posts once to warm up embedder
engine.rank_posts([{"text": "warmup", "category": "Tech"}], aff=[0.0]*15)
print("[+] Recsys engine pre-warmed.")

TEST_PORT = 8910
server = ThreadedHTTPServer(('127.0.0.1', TEST_PORT), MultiModalGatewayHandler)
t = threading.Thread(target=server.serve_forever, daemon=True)
t.start()
time.sleep(1)

base = f"http://127.0.0.1:{TEST_PORT}"

# Candidate pool of 10 real-world diverse posts across all 5 categories
CANDIDATE_POSTS = [
    {"id": "post_gpu_cuda", "category": "Tech", "text": "Deep dive into Nvidia Blackwell GPU architecture, wafer packaging, and FP8 kernel compilation."},
    {"id": "post_cricket_ipl", "category": "Sports", "text": "IPL playoffs auction analysis: strike rates, bowling records, and death-over yorker analysis."},
    {"id": "post_vc_seed", "category": "Business", "text": "How B2B SaaS startups raise seed rounds during high interest rates and macro inflation."},
    {"id": "post_ai_agents", "category": "Tech", "text": "Building autonomous multi-agent coding assistants with local LLMs and function calling."},
    {"id": "post_monet_art", "category": "Arts", "text": "Impressionist brushwork techniques, oil paint layering, and palette knife composition in Paris."},
    {"id": "post_f1_monaco", "category": "Sports", "text": "Formula 1 pit stop strategies, aerodynamic downforce balance, and Monaco lap records."},
    {"id": "post_box_office", "category": "Entertainment", "text": "Summer blockbuster sequels break global box office records with IMAX 70mm re-releases."},
    {"id": "post_real_estate", "category": "Business", "text": "Commercial real estate cap rates and mortgage debt refinancing in urban metro markets."},
    {"id": "post_anime_film", "category": "Entertainment", "text": "Behind the scenes of studio hand-drawn anime keyframes, compositing, and voice acting."},
    {"id": "post_poetry_novel", "category": "Arts", "text": "Contemporary literary fiction awards, poetic meter structures, and creative writing prompts."}
]

PROFILES = {
    "1. Brand New Cold User": {
        "aff": [0.0] * 15,
        "hist_ids": [],
        "demo": [0.0, 1.0, 0.0, 0.0]
    },
    "2. Hardcore Tech Enthusiast (Heavy Tech Likes & Watch)": {
        "aff": [3.5, 2.0, 1.0] + [0.0] * 12,
        "hist_ids": [5900, 5901, 5902],
        "demo": [0.0, 1.0, 0.0, 0.0]
    },
    "3. Sports Fanatic (Cricket + F1)": {
        "aff": [0.0] * 12 + [4.0, 2.5, 1.0],
        "hist_ids": [5910, 5911, 5912],
        "demo": [1.0, 0.0, 0.0, 0.0]
    },
    "4. Arts & Culture Connoisseur": {
        "aff": [0.0] * 6 + [3.8, 2.2, 0.5] + [0.0] * 6,
        "hist_ids": [5920, 5921, 5922],
        "demo": [0.0, 0.0, 1.0, 0.0]
    },
    "5. Hybrid User (Tech + Business)": {
        "aff": [2.5, 1.5, 0.0,  2.5, 1.5, 0.0] + [0.0] * 9,
        "hist_ids": [5900, 5901, 5930],
        "demo": [0.0, 1.0, 0.0, 0.0]
    }
}

results_summary = {}

for name, profile in PROFILES.items():
    t_start = time.time()
    payload = {
        "aff": profile["aff"],
        "hist_ids": profile["hist_ids"],
        "demo": profile["demo"],
        "posts": CANDIDATE_POSTS,
        "n": len(CANDIDATE_POSTS)
    }
    req = urllib.request.Request(
        f"{base}/v1/recommend",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode())
        latency = (time.time() - t_start) * 1000
        results_summary[name] = {
            "latency_ms": round(latency, 2),
            "user_status": data.get("user_status"),
            "ranking": [
                {
                    "rank": p["rank"],
                    "id": p["id"],
                    "category": p["category"],
                    "score": p["score"],
                    "text_snippet": p["text"][:45] + "..."
                }
                for p in data["posts"]
            ]
        }

server.shutdown()

with open("/tmp/experiment_results.json", "w") as f:
    json.dump(results_summary, f, indent=2)

print("\n--- EXPERIMENT SUMMARY ---")
for name, data in results_summary.items():
    print(f"\n>>> {name} ({data['user_status']}, {data['latency_ms']}ms):")
    for r in data["ranking"][:4]:
        print(f"  #{r['rank']} [{r['category']:13s}] (score: {r['score']:+.4f}) {r['id']}: {r['text_snippet']}")
