import sys
import os
import time
import json
import urllib.request
import subprocess

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "mobile"))
sys.path.insert(0, os.path.dirname(__file__))

from gateway import MultiModalGatewayHandler, ThreadedHTTPServer
from swades import Swades

TEST_PORT = 8899

def run_integration_tests():
    server = ThreadedHTTPServer(('127.0.0.1', TEST_PORT), MultiModalGatewayHandler)
    import threading
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    time.sleep(1)

    base = f"http://127.0.0.1:{TEST_PORT}"
    print(f"[*] Test server running at {base}")

    # 1. Test GET /v1/recommend
    req = urllib.request.Request(f"{base}/v1/recommend")
    with urllib.request.urlopen(req, timeout=5) as resp:
        assert resp.status == 200, f"Expected 200, got {resp.status}"
        data = json.loads(resp.read().decode())
        assert "Two-Tower" in data["name"], f"Unexpected name: {data}"
        print("[+] GET /v1/recommend passed.")

    # 2. Test POST /v1/recommend (Cold User)
    cold_payload = json.dumps({"aff": [0.0] * 15, "n": 5}).encode()
    req = urllib.request.Request(f"{base}/v1/recommend", data=cold_payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode())
        assert data["user_status"] == "cold"
        assert len(data["posts"]) == 5
        print(f"[+] POST /v1/recommend (Cold User) passed: {len(data['posts'])} recs.")

    # 3. Test POST /v1/recommend (Warm User)
    warm_payload = json.dumps({
        "aff": [3.0, 2.0, 0.0] + [0.0] * 12,
        "hist_ids": [5900, 5901, 5902],
        "n": 5
    }).encode()
    req = urllib.request.Request(f"{base}/v1/recommend", data=warm_payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode())
        assert data["user_status"] == "warm"
        assert len(data["posts"]) == 5
        print(f"[+] POST /v1/recommend (Warm User) passed: top category {data['posts'][0]['category']}.")

    # 4. Test Alias POST /v1/rank
    req = urllib.request.Request(f"{base}/v1/rank", data=warm_payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode())
        assert data["status"] == "ok"
        print("[+] Alias POST /v1/rank passed.")

    # 4.5 Test POST /v1/recommend with custom candidate posts
    custom_posts = [
        {"id": "p_gpu", "text": "Next-gen GPU hardware and AI chip fabrication yields", "category": "Tech"},
        {"id": "p_sports", "text": "Champions league derby highlights and penalty shootout", "category": "Sports"},
        {"id": "p_art", "text": "Modern watercolor painting gallery exhibition in Vienna", "category": "Arts"},
        {"id": "p_biz", "text": "Venture capital startup investments and seed valuations", "category": "Business"}
    ]
    custom_payload = json.dumps({
        "aff": [3.0, 2.0, 0.0] + [0.0] * 12,
        "posts": custom_posts,
        "n": 4
    }).encode()
    req = urllib.request.Request(f"{base}/v1/recommend", data=custom_payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode())
        assert data["posts"][0]["id"] == "p_gpu"
        assert "count" in data
        assert "items" in data
        print(f"[+] Custom posts ranking passed: #1 is {data['posts'][0]['id']} (score: {data['posts'][0]['score']}).")

    # 4.6 Test POST /v1/recommend with user context fallback
    user_ctx_payload = json.dumps({
        "user": {"tastes": ["tech", "ai", "python"], "roadmap": "compiler engineering"},
        "posts": custom_posts,
        "n": 4
    }).encode()
    req = urllib.request.Request(f"{base}/v1/recommend", data=user_ctx_payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode())
        assert data["posts"][0]["id"] == "p_gpu"
        print(f"[+] User context fallback ranking passed: top post is {data['posts'][0]['id']}.")

    # 5. Test GET /v1/recommend/post/42
    req = urllib.request.Request(f"{base}/v1/recommend/post/42")
    with urllib.request.urlopen(req, timeout=5) as resp:
        assert resp.status == 200
        post = json.loads(resp.read().decode())
        assert post["id"] == 42
        assert "text" in post
        print(f"[+] GET /v1/recommend/post/42 passed: {post['category']} - {post['text'][:35]}...")

    # 6. Test GET /v1/recommend/status
    req = urllib.request.Request(f"{base}/v1/recommend/status")
    with urllib.request.urlopen(req, timeout=5) as resp:
        assert resp.status == 200
        st = json.loads(resp.read().decode())
        assert st["posts_indexed"] == 6000
        print(f"[+] GET /v1/recommend/status passed: {st['posts_indexed']} posts indexed.")

    # 7. Test Python SDK swades.py
    client = Swades(endpoint=base)
    sdk_recs = client.recommend(aff=[2.0, 1.0] + [0.0]*13, hist_ids=[5900], n=3)
    assert sdk_recs["user_status"] == "cold" or sdk_recs["user_status"] == "warm"
    assert len(sdk_recs["posts"]) == 3
    sdk_post = client.get_post(100)
    assert sdk_post["id"] == 100
    sdk_st = client.recommend_status()
    assert sdk_st["status"] == "ok"
    print("[+] Python SDK (swades.py) passed all calls.")

    # 8. Test JavaScript SDK swades.js with Node
    node_script = f"""
    const {{ Swades }} = require('./swades.js');
    async function test() {{
        const c = Swades.init({{ endpoint: '{base}' }});
        const recs = await c.recommend({{ aff: [1.0, 0.7, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], n: 3 }});
        if (!recs || !recs.posts || recs.posts.length !== 3) throw new Error('Recs failure');
        const p = await c.getPost(50);
        if (p.id !== 50) throw new Error('Post detail failure');
        const st = await c.recommendStatus();
        if (st.status !== 'ok') throw new Error('Status failure');
        console.log('[+] Node.js SDK (swades.js) passed all calls.');
    }}
    test().catch(err => {{ console.error(err); process.exit(1); }});
    """
    res = subprocess.run(["node", "-e", node_script], cwd=os.path.dirname(__file__), capture_output=True, text=True)
    assert res.returncode == 0, f"Node SDK test failed: {res.stderr}\n{res.stdout}"
    print(res.stdout.strip())

    print("\n=======================================================")
    print("  ALL RECSYS INTEGRATION AND SDK TESTS PASSED (100%)   ")
    print("=======================================================")
    server.shutdown()

if __name__ == "__main__":
    run_integration_tests()
