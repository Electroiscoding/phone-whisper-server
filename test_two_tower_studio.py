import sys
import os
import time
import json
import threading
import urllib.request
from http.server import SimpleHTTPRequestHandler, HTTPServer
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "mobile"))
sys.path.insert(0, os.path.dirname(__file__))

from gateway import MultiModalGatewayHandler, ThreadedHTTPServer

GATEWAY_PORT = 8991
WEB_PORT = 8992

class SilentHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

def run_all_tests():
    print("=======================================================")
    print("  TWO-TOWER RECOMMENDATION STUDIO VERIFICATION SUITE   ")
    print("=======================================================")

    # 1. Start MultiModalGatewayHandler backend
    gw_server = ThreadedHTTPServer(('127.0.0.1', GATEWAY_PORT), MultiModalGatewayHandler)
    gw_thread = threading.Thread(target=gw_server.serve_forever, daemon=True)
    gw_thread.start()
    print(f"[*] Gateway running at http://127.0.0.1:{GATEWAY_PORT}")

    # 2. Start Web Server serving index.html
    web_server = HTTPServer(('127.0.0.1', WEB_PORT), SilentHandler)
    web_thread = threading.Thread(target=web_server.serve_forever, daemon=True)
    web_thread.start()
    print(f"[*] Web Server running at http://127.0.0.1:{WEB_PORT}")
    time.sleep(1)

    # 3. Test API GET /v1/recommend and POST /v1/recommend
    base_url = f"http://127.0.0.1:{GATEWAY_PORT}"
    req = urllib.request.Request(f"{base_url}/v1/recommend")
    with urllib.request.urlopen(req, timeout=5) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode())
        assert "Two-Tower" in data["name"]
        print("[+] Backend /v1/recommend GET endpoint verified.")

    # 4. Playwright Browser Verification
    # 2.5 Prewarm recsys engine in main process
    from recsys.engine import get_recsys_engine
    engine = get_recsys_engine()
    engine.rank_posts([{"text": "warmup", "category": "Tech"}], aff=[0.0]*15)

    console_errors = []
    page_errors = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        context.add_init_script(f"window.BASE_ENDPOINT = 'http://127.0.0.1:{GATEWAY_PORT}';")
        page = context.new_page()

        # Capture console errors and uncaught exceptions
        def handle_console(msg):
            if msg.type == "error":
                console_errors.append(msg.text)
        page.on("console", handle_console)
        page.on("pageerror", lambda err: page_errors.append(str(err)))

        print(f"[*] Loading http://127.0.0.1:{WEB_PORT}/index.html in Headless Chromium...")
        page.goto(f"http://127.0.0.1:{WEB_PORT}/index.html", wait_until="networkidle")

        # Filter out expected network drops from cloud trial endpoints if any
        critical_console_errors = [e for e in console_errors if "favicon" not in e and "trycloudflare" not in e and "net::ERR_" not in e]
        assert len(page_errors) == 0, f"Page had JavaScript errors: {page_errors}"
        print(f"[+] Page loaded without JavaScript syntax or runtime errors.")

        # Check section #feed-ranking-studio
        section = page.locator("#feed-ranking-studio")
        assert section.count() == 1, "Section #feed-ranking-studio not found"
        assert section.is_visible(), "Section #feed-ranking-studio is not visible"
        title_text = page.locator("#feed-ranking-studio h2.section-title").inner_text()
        assert "Two-Tower Neural Recommendation Studio" in title_text, f"Unexpected title: {title_text}"
        print(f"[+] Section #feed-ranking-studio is present with title '{title_text}'.")

        # Check all 4 quick presets exist
        for preset_id, label in [
            ("presetBtnCold", "Cold User"),
            ("presetBtnTech", "Tech Enthusiast"),
            ("presetBtnSports", "Sports Fanatic"),
            ("presetBtnArts", "Arts Connoisseur")
        ]:
            btn = page.locator(f"#{preset_id}")
            assert btn.count() == 1, f"Preset button #{preset_id} missing"
            assert label in btn.inner_text(), f"Preset button label mismatch: {btn.inner_text()}"
        print("[+] All 4 Quick Presets exist with correct labels.")

        # Test Presets clicking and dynamic input population
        # 1. Tech Enthusiast
        page.click("#presetBtnTech")
        time.sleep(0.1)
        assert page.locator("#val-tech-likes").inner_text() == "3.5", f"Expected 3.5, got {page.locator('#val-tech-likes').inner_text()}"
        assert page.locator("#val-tech-watch").inner_text() == "2.5"
        assert page.locator("#val-tech-shares").inner_text() == "1.5"
        assert "5900" in page.locator("#recHistIds").input_value()
        assert page.locator("#presetBtnTech").evaluate("el => el.classList.contains('active')")
        print("[+] 'Tech Enthusiast' preset populated inputs and sliders dynamically.")

        # 2. Sports Fanatic
        page.click("#presetBtnSports")
        time.sleep(0.1)
        assert page.locator("#val-sports-likes").inner_text() == "4.0"
        assert page.locator("#val-sports-watch").inner_text() == "3.0"
        assert page.locator("#val-sports-shares").inner_text() == "2.0"
        assert "5915" in page.locator("#recHistIds").input_value()
        print("[+] 'Sports Fanatic' preset populated inputs and sliders dynamically.")

        # 3. Arts Connoisseur
        page.click("#presetBtnArts")
        time.sleep(0.1)
        assert page.locator("#val-arts-likes").inner_text() == "4.0"
        assert page.locator("#val-arts-watch").inner_text() == "3.5"
        assert page.locator("#val-arts-shares").inner_text() == "1.8"
        assert "5906" in page.locator("#recHistIds").input_value()
        print("[+] 'Arts Connoisseur' preset populated inputs and sliders dynamically.")

        # 4. Cold User
        page.click("#presetBtnCold")
        time.sleep(0.1)
        assert page.locator("#val-tech-likes").inner_text() == "0.0"
        assert page.locator("#val-sports-likes").inner_text() == "0.0"
        assert page.locator("#val-arts-likes").inner_text() == "0.0"
        assert page.locator("#recHistIds").input_value() == ""
        print("[+] 'Cold User' preset reset all inputs and sliders to 0.0.")

        # Test Category Intensity Chip
        page.evaluate("setCategoryIntensity('biz', 3.5)")
        assert page.locator("#val-biz-likes").inner_text() == "3.5"
        assert page.locator("#val-biz-watch").inner_text() == "2.8"
        print("[+] Category intensity chip dynamically updated category signals.")

        # Test Slider Oninput event
        page.evaluate("document.getElementById('aff-biz-likes').value = '4.2'; document.getElementById('aff-biz-likes').dispatchEvent(new Event('input'));")
        assert page.locator("#val-biz-likes").inner_text() == "4.2"
        print("[+] Slider oninput dynamically updated value indicator.")

        # Test Mode Toggle
        page.click("#btnModeCatalog")
        assert page.locator("#catalogCorpusArea").is_visible()
        assert not page.locator("#dynamicCandidateArea").is_visible()
        print("[+] Mode toggle switched to Catalog Corpus Retrieval.")

        page.click("#btnModeDynamic")
        assert page.locator("#dynamicCandidateArea").is_visible()
        assert not page.locator("#catalogCorpusArea").is_visible()
        print("[+] Mode toggle switched back to Dynamic Candidate Ranking.")

        # Test Live Recommendation Execution in Dynamic Mode
        page.click("#presetBtnTech")
        exec_btn = page.locator("#executeRecBtn")
        assert "Execute Neural Recommendation" in exec_btn.inner_text()

        # Intercept request to ensure POST /v1/recommend is called with expected payload
        rec_requests = []
        def intercept_request(request):
            if "/v1/recommend" in request.url and request.method == "POST":
                rec_requests.append(request.post_data_json)
        page.on("request", intercept_request)

        print("[*] Clicking 'Execute Neural Recommendation' in Dynamic Mode...")
        page.click("#executeRecBtn")

        # Wait for results container to display complete status
        page.wait_for_selector("#recResultsContainer .fa-circle-check", timeout=25000)
        assert len(rec_requests) >= 1, "POST /v1/recommend request was not dispatched"
        payload = rec_requests[0]
        assert "aff" in payload and len(payload["aff"]) == 15, "Affinity vector length must be 15"
        assert "hist_ids" in payload and len(payload["hist_ids"]) >= 3, "Hist IDs must be passed"
        assert "posts" in payload and len(payload["posts"]) > 0, "Candidate posts must be passed in dynamic mode"
        print("[+] POST /v1/recommend dispatched with valid Two-Tower payload.")

        # Verify results DOM rendering
        container_text = page.locator("#recResultsContainer").inner_text()
        assert "Two-Tower Recommendation Complete" in container_text
        assert "WARM USER" in container_text or "warm user" in container_text.lower()
        assert "Latency:" in container_text

        # Verify ranked cards and badges
        rank1_badge = page.locator("#recResultsContainer").locator("text=#1").first
        assert rank1_badge.is_visible(), "#1 rank badge not visible"
        assert page.locator("#recResultsContainer").locator("text=Similarity Score").count() > 0, "Similarity score missing"
        print("[+] Results rendered with rank badges, category pills, similarity score meters, and latency telemetry.")

        # Test Live Recommendation Execution in Catalog Mode
        print("[*] Testing Catalog Corpus Retrieval mode live execution...")
        page.click("#btnModeCatalog")
        rec_requests.clear()
        page.click("#executeRecBtn")
        page.wait_for_selector("#recResultsContainer .fa-circle-check", timeout=25000)
        assert len(rec_requests) >= 1, "POST /v1/recommend for catalog not dispatched"
        cat_payload = rec_requests[0]
        assert "posts" not in cat_payload or cat_payload["posts"] is None, "posts should not be sent in catalog mode"
        assert "fresh" in cat_payload and "div" in cat_payload and "eps" in cat_payload
        cat_container_text = page.locator("#recResultsContainer").inner_text()
        assert "Two-Tower Recommendation Complete" in cat_container_text
        print("[+] Catalog Corpus Retrieval executed and rendered successfully.")

        # Test Error Handling
        print("[*] Testing error handling with unreachable endpoint...")
        page.evaluate("window.BASE_ENDPOINT = 'http://127.0.0.1:9999';")
        page.click("#executeRecBtn")
        page.wait_for_selector("#recResultsContainer .fa-triangle-exclamation", timeout=10000)
        err_text = page.locator("#recResultsContainer").inner_text()
        assert "Recommendation Request Failed" in err_text
        print("[+] Error alert rendered gracefully on failure.")

        browser.close()

    gw_server.shutdown()
    web_server.shutdown()

    print("\n=======================================================")
    print("  ALL VERIFICATION CHECKS PASSED SUCCESSFULLY (100%)   ")
    print("=======================================================")

if __name__ == "__main__":
    run_all_tests()
