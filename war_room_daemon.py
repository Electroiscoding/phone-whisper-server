#!/usr/bin/env python3
import time
import sys
sys.path.insert(0, "/data/data/com.termux/files/home")
from war_room_engine import WarRoomEngine

engine = WarRoomEngine()
print("[Phone War Room Daemon] Starting autonomous SEO loop on phone silicon...")
while True:
    try:
        step = engine.run_cycle()
        print(f"[Daemon] #{step['cycle']} | {step['surface']} | {step['verdict']}")
    except Exception as e:
        print(f"[Daemon ERROR]: {e}")
    time.sleep(8)
