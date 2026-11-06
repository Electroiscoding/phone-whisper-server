"""
test_tier3_combinations.py - Tier 3: Cross-Feature Combinations E2E Tests
Path: tests/e2e/test_tier3_combinations.py

Covers 7 Cross-Feature Pairwise Interaction Tests:
- T3.1: Screen Streaming with Concurrent Touch Injection
- T3.2: App Lifecycle Execution During Active AI Speech Synthesis
- T3.3: Rapid Consecutive Lifecycle Restarts & Stress
- T3.4: Gateway Inspection & Telemetry Queries During Background Currents News Cycle
- T3.5: Edge Proxy Request Routing Under Concurrent Direct Gateway Load
- T3.6: Screen Streaming During BGE Embeddings & Reranking Batch
- T3.7: Hardware Key Navigation While Sideloaded App Is Active
"""

import concurrent.futures
import time

import pytest
import requests


@pytest.mark.tier3
@pytest.mark.hardware
def test_t3_touch_during_active_screen_streaming(gateway_session, e2e_config, wake_screen, validate_jpeg_frame):
    """T3.1: Screen Streaming with Concurrent Touch Injection."""
    frame_url = f"{e2e_config.gateway_url}/v1/screen/frame"
    touch_url = f"{e2e_config.gateway_url}/v1/screen/touch"
    
    received_frames = []
    received_touches = []
    
    def stream_worker():
        for _ in range(4):
            r = requests.get(frame_url, timeout=e2e_config.gateway_timeout)
            if r.status_code == 200:
                received_frames.append(r.content)
            time.sleep(0.2)
            
    def touch_worker():
        for i in range(3):
            payload = {"x": 0.3 + (i * 0.1), "y": 0.4 + (i * 0.1), "action": "tap"}
            r = requests.post(touch_url, json=payload, timeout=e2e_config.gateway_timeout)
            if r.status_code == 200:
                received_touches.append(r.json())
            time.sleep(0.25)
            
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(stream_worker)
        f2 = executor.submit(touch_worker)
        f1.result()
        f2.result()
        
    assert len(received_frames) >= 3, f"Expected at least 3 frames, got {len(received_frames)}"
    for frame_bytes in received_frames:
        validate_jpeg_frame(frame_bytes, expected_dims=(360, 800))
        
    assert len(received_touches) >= 2, f"Expected at least 2 touch responses, got {len(received_touches)}"
    for t in received_touches:
        assert t.get("status") == "ok"


@pytest.mark.tier3
@pytest.mark.hardware
@pytest.mark.ai
def test_t3_app_lifecycle_during_speech_synthesis(e2e_config, cleanup_app_state):
    """T3.2: App Lifecycle Execution During Active AI Speech Synthesis."""
    tts_url = f"{e2e_config.gateway_url}/v1/audio/speech?input=Active+speech+synthesis+during+app+lifecycle"
    app_url = f"{e2e_config.gateway_url}/v1/screen/app"
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f_tts = executor.submit(requests.get, tts_url, timeout=e2e_config.ai_timeout)
        time.sleep(0.05)
        f_app = executor.submit(
            requests.post,
            app_url,
            json={"package": "com.netuark.app", "action": "launch"},
            timeout=e2e_config.gateway_timeout
        )
        
        r_tts = f_tts.result()
        r_app = f_app.result()
        
    assert r_tts.status_code == 200
    assert r_tts.headers.get("Content-Type") == "audio/wav"
    assert len(r_tts.content) >= 1000
    
    assert r_app.status_code == 200
    assert r_app.json().get("status") == "ok"


@pytest.mark.tier3
@pytest.mark.hardware
def test_t3_rapid_lifecycle_restart_stress(gateway_session, e2e_config, cleanup_app_state):
    """T3.3: Rapid Consecutive Lifecycle Restarts & Stress."""
    app_url = f"{e2e_config.gateway_url}/v1/screen/app"
    actions = ["launch", "restart", "status", "stop", "status", "launch"]
    
    for act in actions:
        r = gateway_session.post(
            app_url,
            json={"package": "com.netuark.app", "action": act},
            timeout=e2e_config.gateway_timeout
        )
        assert r.status_code == 200
        assert r.json().get("status") == "ok"
        time.sleep(0.1)


@pytest.mark.tier3
@pytest.mark.hardware
@pytest.mark.ai
def test_t3_gateway_queries_during_currents_cycle(gateway_session, e2e_config):
    """T3.4: Gateway Inspection & Telemetry Queries During Background Currents News Cycle."""
    # Query currents news bot status
    r_curr = gateway_session.get(f"{e2e_config.gateway_url}/v1/currents/status", timeout=e2e_config.gateway_timeout)
    assert r_curr.status_code == 200
    assert "Currents" in r_curr.json().get("service", "")
    
    # Interleaved app and telemetry inspections
    for _ in range(3):
        r_app = gateway_session.post(
            f"{e2e_config.gateway_url}/v1/screen/app",
            json={"action": "status", "package": "com.netuark.app"},
            timeout=e2e_config.gateway_timeout
        )
        r_tel = gateway_session.get(f"{e2e_config.gateway_url}/telemetry", timeout=e2e_config.gateway_timeout)
        
        assert r_app.status_code == 200
        assert r_tel.status_code == 200
        time.sleep(0.05)


@pytest.mark.tier3
@pytest.mark.edge
def test_t3_edge_proxy_vs_direct_concurrency(e2e_config):
    """T3.5: Edge Proxy Request Routing Under Concurrent Direct Gateway Load."""
    edge_frame_url = f"{e2e_config.pages_url}/v1/screen/frame"
    direct_frame_url = f"{e2e_config.gateway_url}/v1/screen/frame"
    direct_tel_url = f"{e2e_config.gateway_url}/telemetry"
    
    headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        f_edge = executor.submit(requests.get, edge_frame_url, headers=headers, timeout=e2e_config.pages_timeout)
        f_direct = executor.submit(requests.get, direct_frame_url, timeout=e2e_config.gateway_timeout)
        f_tel = executor.submit(requests.get, direct_tel_url, timeout=e2e_config.gateway_timeout)
        
        r_edge = f_edge.result()
        r_direct = f_direct.result()
        r_tel = f_tel.result()
        
    assert r_edge.status_code == 200
    assert r_direct.status_code == 200
    assert r_tel.status_code == 200


@pytest.mark.tier3
@pytest.mark.hardware
@pytest.mark.ai
def test_t3_streaming_during_embedding_rerank(e2e_config):
    """T3.6: Screen Streaming During BGE Embeddings & Reranking Batch."""
    embed_url = f"{e2e_config.gateway_url}/v1/embeddings"
    rerank_url = f"{e2e_config.gateway_url}/v1/rerank"
    frame_url = f"{e2e_config.gateway_url}/v1/screen/frame"
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        f_embed = executor.submit(requests.post, embed_url, json={"input": ["Cloud Phone NTA", "Edge Streaming"]}, timeout=e2e_config.ai_timeout)
        f_rerank = executor.submit(requests.post, rerank_url, json={"query": "low latency", "documents": ["stream pipeline", "car engine"]}, timeout=e2e_config.ai_timeout)
        f_frame = executor.submit(requests.get, frame_url, timeout=e2e_config.gateway_timeout)
        
        r_embed = f_embed.result()
        r_rerank = f_rerank.result()
        r_frame = f_frame.result()
        
    assert r_embed.status_code == 200
    assert r_rerank.status_code == 200
    assert r_frame.status_code == 200


@pytest.mark.tier3
@pytest.mark.hardware
def test_t3_key_navigation_during_app_active(gateway_session, e2e_config, cleanup_app_state):
    """T3.7: Hardware Key Navigation While Sideloaded App Is Active."""
    # Launch app
    r_launch = gateway_session.post(
        f"{e2e_config.gateway_url}/v1/screen/app",
        json={"package": "com.netuark.app", "action": "launch"},
        timeout=e2e_config.gateway_timeout
    )
    assert r_launch.status_code == 200
    
    # Send HOME key
    r_home = gateway_session.post(
        f"{e2e_config.gateway_url}/v1/screen/key",
        json={"key": "HOME"},
        timeout=e2e_config.gateway_timeout
    )
    assert r_home.status_code == 200
    assert r_home.json().get("status") == "ok"
    
    # Send BACK key
    r_back = gateway_session.post(
        f"{e2e_config.gateway_url}/v1/screen/key",
        json={"key": "BACK"},
        timeout=e2e_config.gateway_timeout
    )
    assert r_back.status_code == 200
    assert r_back.json().get("status") == "ok"
