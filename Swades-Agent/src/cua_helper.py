#!/usr/bin/env python3
# cua_helper.py — Python bridge for CUA actions + screenshot capture
#modified  cua flow : 
import os
import sys
import json
import base64
import time
import subprocess
import io

from PIL import Image, ImageDraw, ImageFont

WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL_BIN_DIR = os.path.join(WORKSPACE_DIR, "bin_local", "usr", "bin")
LOCAL_LIB_DIR = os.path.join(WORKSPACE_DIR, "bin_local", "usr", "lib", "x86_64-linux-gnu")
LOCAL_SHARE_DIR = os.path.join(WORKSPACE_DIR, "bin_local", "usr", "share")
LOADERS_DIR = os.path.join(LOCAL_LIB_DIR, "imlib2", "loaders")

os.environ["PATH"] = LOCAL_BIN_DIR + os.pathsep + os.environ.get("PATH", "")
os.environ["LD_LIBRARY_PATH"] = LOCAL_LIB_DIR + os.pathsep + os.environ.get("LD_LIBRARY_PATH", "")
os.environ["XDG_DATA_DIRS"] = LOCAL_SHARE_DIR + os.pathsep + os.environ.get("XDG_DATA_DIRS", "")
os.environ["IMLIB2_LOADER_PATH"] = LOADERS_DIR

# Ensure display environment is set BEFORE importing pyautogui (which loads Xlib at import time)
if "DISPLAY" not in os.environ:
    os.environ["DISPLAY"] = ":0"
if "XAUTHORITY" not in os.environ:
    # Auto-detect mutter Xwayland auth file (GNOME on Wayland)
    import glob
    uid = os.getuid()
    auth_files = glob.glob(f"/run/user/{uid}/.mutter-Xwaylandauth.*")
    if auth_files:
        os.environ["XAUTHORITY"] = auth_files[0]
    elif os.path.exists(os.path.expanduser("~/.Xauthority")):
        os.environ["XAUTHORITY"] = os.path.expanduser("~/.Xauthority")
if "WAYLAND_DISPLAY" not in os.environ and os.environ.get("XDG_SESSION_TYPE") == "wayland":
    os.environ["WAYLAND_DISPLAY"] = "wayland-0"

# Fix python-xlib 0.15 auth bug: it can't read mutter Xwayland auth files properly.
# Allow local connections so Xlib works without auth negotiation.
try:
    subprocess.run(["xhost", "+local:"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
except Exception:
    pass

IS_WAYLAND = "WAYLAND_DISPLAY" in os.environ or os.environ.get("XDG_SESSION_TYPE") == "wayland"
STATE_FILE = os.path.join(WORKSPACE_DIR, ".mouse_position.json")

if IS_WAYLAND:
    try:
        import gi
        gi.require_version('Gio', '2.0')
        from gi.repository import Gio, GLib
    except ImportError:
        pass

def read_mouse_pos():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
                return int(data.get("x", 960)), int(data.get("y", 540))
        except Exception:
            pass
    return 960, 540

def write_mouse_pos(x, y):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump({"x": int(x), "y": int(y)}, f)
    except Exception:
        pass

def run_xdotool(args):
    """Run local xdotool command."""
    cmd = ["xdotool"] + [str(a) for a in args]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def get_mouse_position():
    if IS_WAYLAND:
        return read_mouse_pos()
    try:
        res = subprocess.run(["xdotool", "getmouselocation"], capture_output=True, text=True, check=True)
        parts = res.stdout.strip().split()
        mx = int(parts[0].split(":")[1])
        my = int(parts[1].split(":")[1])
        write_mouse_pos(mx, my)
        return mx, my
    except Exception:
        try:
            import pyautogui
            x, y = pyautogui.position()
            write_mouse_pos(x, y)
            return x, y
        except Exception:
            return read_mouse_pos()

# --- Screenshot ---

MAX_WIDTH = 1280
JPEG_QUALITY = 70

def _capture_raw(temp_raw):
    """Try multiple capture methods. Returns True on success."""
    scrot_path = os.path.join(LOCAL_BIN_DIR, "scrot")
    gnome_path = os.path.join(LOCAL_BIN_DIR, "gnome-screenshot")
    is_wayland = "WAYLAND_DISPLAY" in os.environ or os.environ.get("XDG_SESSION_TYPE") == "wayland"

    # 1. Wayland portal
    if is_wayland:
        try:
            portal_script = os.path.join(WORKSPACE_DIR, "src", "take_portal_screenshot.py")
            res = subprocess.run(["/usr/bin/python3", portal_script, temp_raw],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
            if res.returncode == 0 and os.path.exists(temp_raw):
                return True
        except Exception:
            pass

    # 2. scrot (X11 only)
    if not is_wayland and os.path.exists(scrot_path):
        try:
            res = subprocess.run([scrot_path, "-z", temp_raw],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
            if res.returncode == 0 and os.path.exists(temp_raw):
                return True
        except Exception:
            pass

    # 3. gnome-screenshot
    if os.path.exists(gnome_path):
        try:
            pic_dir = os.path.expanduser("~/Pictures")
            shots_dir = os.path.expanduser("~/Pictures/Screenshots")

            def latest_png(d):
                if not os.path.exists(d): return None
                pngs = [os.path.join(d, f) for f in os.listdir(d) if f.lower().endswith(".png")]
                return max(pngs, key=os.path.getmtime) if pngs else None

            before_pic = latest_png(pic_dir)
            before_shot = latest_png(shots_dir)

            env = os.environ.copy()
            env["GDK_BACKEND"] = "wayland"
            if "WAYLAND_DISPLAY" not in env:
                env["WAYLAND_DISPLAY"] = "wayland-0"

            subprocess.run([gnome_path], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)

            for _ in range(30):
                time.sleep(0.1)
                new_pic = latest_png(pic_dir)
                new_shot = latest_png(shots_dir)
                new_file = None
                if new_pic and new_pic != before_pic: new_file = new_pic
                elif new_shot and new_shot != before_shot: new_file = new_shot
                if new_file:
                    with open(new_file, "rb") as f_in:
                        with open(temp_raw, "wb") as f_out:
                            f_out.write(f_in.read())
                    try: os.remove(new_file)
                    except: pass
                    return True
        except Exception:
            pass

    # 4. PIL ImageGrab fallback
    try:
        from PIL import ImageGrab
        im = ImageGrab.grab()
        im.save(temp_raw)
        return True
    except Exception:
        return False


def take_screenshot(zoom_x1=None, zoom_y1=None, zoom_x2=None, zoom_y2=None):
    temp_raw = os.path.join(WORKSPACE_DIR, "screenshot_raw.png")

    if os.path.exists(temp_raw):
        try: os.remove(temp_raw)
        except: pass

    if not _capture_raw(temp_raw):
        print(json.dumps({"error": "All screenshot methods failed"}))
        return

    try:
        im = Image.open(temp_raw)
        orig_w, orig_h = im.size

        # Get mouse position before any crop/resize
        mx, my = get_mouse_position()

        # Apply crop/zoom if specified
        is_zoomed = zoom_x1 is not None and zoom_y1 is not None and zoom_x2 is not None and zoom_y2 is not None
        if is_zoomed:
            # Clamp bounds
            zx1 = max(0, min(orig_w - 1, int(zoom_x1)))
            zy1 = max(0, min(orig_h - 1, int(zoom_y1)))
            zx2 = max(zx1 + 1, min(orig_w, int(zoom_x2)))
            zy2 = max(zy1 + 1, min(orig_h, int(zoom_y2)))
            im = im.crop((zx1, zy1, zx2, zy2))
            crop_w = zx2 - zx1
            crop_h = zy2 - zy1
            mx = mx - zx1
            my = my - zy1
        else:
            crop_w, crop_h = orig_w, orig_h

        # Downscale if crop region is wider than MAX_WIDTH
        if crop_w > MAX_WIDTH:
            scale = MAX_WIDTH / crop_w
            new_w = MAX_WIDTH
            new_h = int(crop_h * scale)
            im = im.resize((new_w, new_h), Image.LANCZOS)
            # Scale mouse coords to match
            mx = int(mx * scale)
            my = int(my * scale)
        
        w, h = im.size
        draw = ImageDraw.Draw(im)

        # Red cursor crosshair (only draw if inside crop bounds)
        if 0 <= mx < w and 0 <= my < h:
            draw.line([(mx - 12, my), (mx + 12, my)], fill="red", width=2)
            draw.line([(mx, my - 12), (mx, my + 12)], fill="red", width=2)
            draw.ellipse([(mx - 3, my - 3), (mx + 3, my + 3)], outline="white", fill="red")

        # Save the exact annotated image that the model sees to screenshot_raw.png
        try:
            im.save(temp_raw, format="PNG")
        except Exception:
            pass

        # Convert to JPEG, compress, base64
        buf = io.BytesIO()
        im = im.convert("RGB")  # JPEG needs RGB
        im.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
        encoded = base64.b64encode(buf.getvalue()).decode("utf-8")

        # Scale factor relative to the crop region size
        scale_factor = crop_w / w if crop_w > MAX_WIDTH else 1.0

        # Return coordinates relative to the crop region
        # This keeps the math clean for both the orchestrator and python helper
        print(json.dumps({
            "width": crop_w,
            "height": crop_h,
            "mouse": {"x": int(mx * scale_factor), "y": int(my * scale_factor)},
            "scale": round(scale_factor, 3),
            "base64": encoded
        }))

    except Exception as e:
        print(json.dumps({"error": f"Screenshot processing failed: {e}"}))


# --- Actions ---

def ok(action, **extra):
    print(json.dumps({"status": "ok", "action": action, **extra}))

def err(msg):
    print(json.dumps({"error": str(msg)}))

KEYSYM_MAP = {
    "enter": 0xff0d,
    "return": 0xff0d,
    "tab": 0xff09,
    "escape": 0xff1b,
    "backspace": 0xff08,
    "space": 0x0020,
    "super": 0xffeb,
    "win": 0xffeb,
    "up": 0xff52,
    "down": 0xff54,
    "left": 0xff51,
    "right": 0xff53,
    "ctrl": 0xffe3,
    "control": 0xffe3,
    "alt": 0xffe9,
    "shift": 0xffe1,
}

def get_keysym(k):
    k_lower = k.lower()
    if k_lower in KEYSYM_MAP:
        return KEYSYM_MAP[k_lower]
    if k_lower.startswith('f') and k_lower[1:].isdigit():
        f_num = int(k_lower[1:])
        if 1 <= f_num <= 12:
            return 0xffbe + (f_num - 1)
    if len(k) == 1:
        return ord(k)
    raise ValueError(f"Unknown key: {k}")

def run_with_mutter_session(callback):
    import gi
    gi.require_version('Gio', '2.0')
    from gi.repository import Gio, GLib

    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)

    # 1. Get primary monitor connector dynamically
    res_state = bus.call_sync(
        "org.gnome.Mutter.DisplayConfig",
        "/org/gnome/Mutter/DisplayConfig",
        "org.gnome.Mutter.DisplayConfig",
        "GetCurrentState",
        None,
        GLib.VariantType('(ua((ssss)a(siiddada{sv})a{sv})a(iiduba(ssss)a{sv})a{sv})'),
        Gio.DBusCallFlags.NONE,
        -1,
        None
    )
    _, _, logical_monitors, _ = res_state.unpack()
    connector = None
    for lm in logical_monitors:
        primary = lm[4]
        if primary:
            monitors_list = lm[5]
            if monitors_list:
                connector = monitors_list[0][0]
                break
    if not connector:
        connector = "eDP-1"

    # 2. Create RemoteDesktop session
    res_rd = bus.call_sync(
        "org.gnome.Mutter.RemoteDesktop",
        "/org/gnome/Mutter/RemoteDesktop",
        "org.gnome.Mutter.RemoteDesktop",
        "CreateSession",
        None,
        GLib.VariantType('(o)'),
        Gio.DBusCallFlags.NONE,
        -1,
        None
    )
    rd_session_path = res_rd.unpack()[0]
    
    # Get SessionId
    val = bus.call_sync(
        "org.gnome.Mutter.RemoteDesktop",
        rd_session_path,
        "org.freedesktop.DBus.Properties",
        "Get",
        GLib.Variant('(ss)', ("org.gnome.Mutter.RemoteDesktop.Session", "SessionId")),
        GLib.VariantType('(v)'),
        Gio.DBusCallFlags.NONE,
        -1,
        None
    )
    session_id = val.unpack()[0]
    
    # 3. Create ScreenCast session
    res_sc = bus.call_sync(
        "org.gnome.Mutter.ScreenCast",
        "/org/gnome/Mutter/ScreenCast",
        "org.gnome.Mutter.ScreenCast",
        "CreateSession",
        GLib.Variant('(a{sv})', ({"remote-desktop-session-id": GLib.Variant('s', session_id)},)),
        GLib.VariantType('(o)'),
        Gio.DBusCallFlags.NONE,
        -1,
        None
    )
    sc_session_path = res_sc.unpack()[0]
    
    # 4. Record Monitor
    res_record = bus.call_sync(
        "org.gnome.Mutter.ScreenCast",
        sc_session_path,
        "org.gnome.Mutter.ScreenCast.Session",
        "RecordMonitor",
        GLib.Variant('(sa{sv})', (connector, {"cursor-mode": GLib.Variant('u', 1)})),
        GLib.VariantType('(o)'),
        Gio.DBusCallFlags.NONE,
        -1,
        None
    )
    stream_path = res_record.unpack()[0]

    # 5. Start RemoteDesktop session
    bus.call_sync(
        "org.gnome.Mutter.RemoteDesktop",
        rd_session_path,
        "org.gnome.Mutter.RemoteDesktop.Session",
        "Start",
        None,
        None,
        Gio.DBusCallFlags.NONE,
        -1,
        None
    )

    try:
        callback(bus, rd_session_path, stream_path)
    finally:
        # Stop RD session
        try:
            bus.call_sync(
                "org.gnome.Mutter.RemoteDesktop",
                rd_session_path,
                "org.gnome.Mutter.RemoteDesktop.Session",
                "Stop",
                None,
                None,
                Gio.DBusCallFlags.NONE,
                -1,
                None
            )
        except Exception:
            pass
        # Stop SC session
        try:
            bus.call_sync(
                "org.gnome.Mutter.ScreenCast",
                sc_session_path,
                "org.gnome.Mutter.ScreenCast.Session",
                "Stop",
                None,
                None,
                Gio.DBusCallFlags.NONE,
                -1,
                None
            )
        except Exception:
            pass

def perform_click(x, y, button="left", clicks=1):
    if IS_WAYLAND:
        try:
            from gi.repository import GLib
            btn_map = {"left": 272, "right": 273, "middle": 274}
            btn_code = btn_map.get(button.lower(), 272)
            
            def cb(bus, rd_session_path, stream_path):
                bus.call_sync(
                    "org.gnome.Mutter.RemoteDesktop",
                    rd_session_path,
                    "org.gnome.Mutter.RemoteDesktop.Session",
                    "NotifyPointerMotionAbsolute",
                    GLib.Variant('(sdd)', (stream_path, float(x), float(y))),
                    None, Gio.DBusCallFlags.NONE, -1, None
                )
                time.sleep(0.05)
                for _ in range(clicks):
                    bus.call_sync(
                        "org.gnome.Mutter.RemoteDesktop",
                        rd_session_path,
                        "org.gnome.Mutter.RemoteDesktop.Session",
                        "NotifyPointerButton",
                        GLib.Variant('(ib)', (btn_code, True)),
                        None, Gio.DBusCallFlags.NONE, -1, None
                    )
                    time.sleep(0.05)
                    bus.call_sync(
                        "org.gnome.Mutter.RemoteDesktop",
                        rd_session_path,
                        "org.gnome.Mutter.RemoteDesktop.Session",
                        "NotifyPointerButton",
                        GLib.Variant('(ib)', (btn_code, False)),
                        None, Gio.DBusCallFlags.NONE, -1, None
                    )
                    time.sleep(0.05)
            run_with_mutter_session(cb)
            write_mouse_pos(x, y)
            ok("click", x=x, y=y)
        except Exception as e:
            err(e)
    else:
        try:
            btn_map = {"left": 1, "middle": 2, "right": 3}
            btn_num = btn_map.get(button, 1)
            run_xdotool(["mousemove", str(x), str(y), "click", "--repeat", str(clicks), str(btn_num)])
            time.sleep(0.15)
            ok("click", x=x, y=y)
        except Exception as e: err(e)

def perform_move(x, y):
    if IS_WAYLAND:
        try:
            from gi.repository import GLib
            def cb(bus, rd_session_path, stream_path):
                bus.call_sync(
                    "org.gnome.Mutter.RemoteDesktop",
                    rd_session_path,
                    "org.gnome.Mutter.RemoteDesktop.Session",
                    "NotifyPointerMotionAbsolute",
                    GLib.Variant('(sdd)', (stream_path, float(x), float(y))),
                    None, Gio.DBusCallFlags.NONE, -1, None
                )
            run_with_mutter_session(cb)
            write_mouse_pos(x, y)
            ok("move", x=x, y=y)
        except Exception as e:
            err(e)
    else:
        try:
            run_xdotool(["mousemove", str(x), str(y)])
            ok("move", x=x, y=y)
        except Exception as e: err(e)

def perform_type(text):
    if IS_WAYLAND:
        try:
            from gi.repository import GLib
            def cb(bus, rd_session_path, stream_path):
                for char in text:
                    keysym = ord(char)
                    bus.call_sync(
                        "org.gnome.Mutter.RemoteDesktop",
                        rd_session_path,
                        "org.gnome.Mutter.RemoteDesktop.Session",
                        "NotifyKeyboardKeysym",
                        GLib.Variant('(ub)', (keysym, True)),
                        None, Gio.DBusCallFlags.NONE, -1, None
                    )
                    time.sleep(0.01)
                    bus.call_sync(
                        "org.gnome.Mutter.RemoteDesktop",
                        rd_session_path,
                        "org.gnome.Mutter.RemoteDesktop.Session",
                        "NotifyKeyboardKeysym",
                        GLib.Variant('(ub)', (keysym, False)),
                        None, Gio.DBusCallFlags.NONE, -1, None
                    )
                    time.sleep(0.01)
            run_with_mutter_session(cb)
            ok("type", length=len(text))
        except Exception as e:
            err(e)
    else:
        try:
            try:
                subprocess.run(["xdotool", "type", "--clearmodifiers", "--delay", "10", text],
                              timeout=10, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except (FileNotFoundError, subprocess.CalledProcessError):
                import pyautogui
                pyautogui.write(text, interval=0.02)
            time.sleep(0.1)
            ok("type", length=len(text))
        except Exception as e: err(e)

def perform_press(key):
    if IS_WAYLAND:
        try:
            from gi.repository import GLib
            keysym = get_keysym(key)
            def cb(bus, rd_session_path, stream_path):
                bus.call_sync(
                    "org.gnome.Mutter.RemoteDesktop",
                    rd_session_path,
                    "org.gnome.Mutter.RemoteDesktop.Session",
                    "NotifyKeyboardKeysym",
                    GLib.Variant('(ub)', (keysym, True)),
                    None, Gio.DBusCallFlags.NONE, -1, None
                )
                time.sleep(0.02)
                bus.call_sync(
                    "org.gnome.Mutter.RemoteDesktop",
                    rd_session_path,
                    "org.gnome.Mutter.RemoteDesktop.Session",
                    "NotifyKeyboardKeysym",
                    GLib.Variant('(ub)', (keysym, False)),
                    None, Gio.DBusCallFlags.NONE, -1, None
                )
            run_with_mutter_session(cb)
            ok("press", key=key)
        except Exception as e:
            err(e)
    else:
        try:
            KEY_MAP = {
                "enter": "Return",
                "tab": "Tab",
                "escape": "Escape",
                "backspace": "BackSpace",
                "space": "space",
                "super": "super",
                "up": "Up",
                "down": "Down",
                "left": "Left",
                "right": "Right"
            }
            translated_key = KEY_MAP.get(key.lower(), key)
            run_xdotool(["key", translated_key])
            time.sleep(0.1)
            ok("press", key=key)
        except Exception as e: err(e)

def perform_hotkey(*keys):
    if IS_WAYLAND:
        try:
            from gi.repository import GLib
            keysyms = [get_keysym(k) for k in keys]
            def cb(bus, rd_session_path, stream_path):
                for keysym in keysyms:
                    bus.call_sync(
                        "org.gnome.Mutter.RemoteDesktop",
                        rd_session_path,
                        "org.gnome.Mutter.RemoteDesktop.Session",
                        "NotifyKeyboardKeysym",
                        GLib.Variant('(ub)', (keysym, True)),
                        None, Gio.DBusCallFlags.NONE, -1, None
                    )
                    time.sleep(0.02)
                time.sleep(0.05)
                for keysym in reversed(keysyms):
                    bus.call_sync(
                        "org.gnome.Mutter.RemoteDesktop",
                        rd_session_path,
                        "org.gnome.Mutter.RemoteDesktop.Session",
                        "NotifyKeyboardKeysym",
                        GLib.Variant('(ub)', (keysym, False)),
                        None, Gio.DBusCallFlags.NONE, -1, None
                    )
                    time.sleep(0.02)
            run_with_mutter_session(cb)
            ok("hotkey", keys=list(keys))
        except Exception as e:
            err(e)
    else:
        try:
            KEY_MAP = {
                "enter": "Return",
                "tab": "Tab",
                "escape": "Escape",
                "backspace": "BackSpace",
                "space": "space",
                "super": "super",
                "up": "Up",
                "down": "Down",
                "left": "Left",
                "right": "Right",
                "ctrl": "ctrl",
                "alt": "alt",
                "shift": "shift"
            }
            translated_keys = [KEY_MAP.get(k.lower(), k) for k in keys]
            combo = "+".join(translated_keys)
            run_xdotool(["key", combo])
            time.sleep(0.1)
            ok("hotkey", keys=list(keys))
        except Exception as e: err(e)

def perform_scroll(clicks):
    if IS_WAYLAND:
        try:
            from gi.repository import GLib
            steps = -1 if clicks > 0 else 1
            def cb(bus, rd_session_path, stream_path):
                for _ in range(abs(clicks)):
                    bus.call_sync(
                        "org.gnome.Mutter.RemoteDesktop",
                        rd_session_path,
                        "org.gnome.Mutter.RemoteDesktop.Session",
                        "NotifyPointerAxisDiscrete",
                        GLib.Variant('(ui)', (0, steps)),
                        None, Gio.DBusCallFlags.NONE, -1, None
                    )
                    time.sleep(0.05)
            run_with_mutter_session(cb)
            ok("scroll", clicks=clicks)
        except Exception as e:
            err(e)
    else:
        try:
            button = 4 if clicks > 0 else 5
            count = abs(clicks)
            run_xdotool(["click", "--repeat", str(count), str(button)])
            time.sleep(0.1)
            ok("scroll", clicks=clicks)
        except Exception as e: err(e)

def perform_drag(x1, y1, x2, y2, duration=0.5):
    if IS_WAYLAND:
        try:
            from gi.repository import GLib
            def cb(bus, rd_session_path, stream_path):
                bus.call_sync(
                    "org.gnome.Mutter.RemoteDesktop",
                    rd_session_path,
                    "org.gnome.Mutter.RemoteDesktop.Session",
                    "NotifyPointerMotionAbsolute",
                    GLib.Variant('(sdd)', (stream_path, float(x1), float(y1))),
                    None, Gio.DBusCallFlags.NONE, -1, None
                )
                time.sleep(0.1)
                bus.call_sync(
                    "org.gnome.Mutter.RemoteDesktop",
                    rd_session_path,
                    "org.gnome.Mutter.RemoteDesktop.Session",
                    "NotifyPointerButton",
                    GLib.Variant('(ib)', (272, True)),
                    None, Gio.DBusCallFlags.NONE, -1, None
                )
                time.sleep(0.1)
                bus.call_sync(
                    "org.gnome.Mutter.RemoteDesktop",
                    rd_session_path,
                    "org.gnome.Mutter.RemoteDesktop.Session",
                    "NotifyPointerMotionAbsolute",
                    GLib.Variant('(sdd)', (stream_path, float(x2), float(y2))),
                    None, Gio.DBusCallFlags.NONE, -1, None
                )
                time.sleep(0.1)
                bus.call_sync(
                    "org.gnome.Mutter.RemoteDesktop",
                    rd_session_path,
                    "org.gnome.Mutter.RemoteDesktop.Session",
                    "NotifyPointerButton",
                    GLib.Variant('(ib)', (272, False)),
                    None, Gio.DBusCallFlags.NONE, -1, None
                )
                time.sleep(0.1)
            run_with_mutter_session(cb)
            write_mouse_pos(x2, y2)
            ok("drag", x1=x1, y1=y1, x2=x2, y2=y2)
        except Exception as e:
            err(e)
    else:
        try:
            run_xdotool(["mousemove", str(x1), str(y1), "mousedown", "1", "mousemove", str(x2), str(y2), "mouseup", "1"])
            time.sleep(0.1)
            ok("drag", x1=x1, y1=y1, x2=x2, y2=y2)
        except Exception as e: err(e)


def main():
    if len(sys.argv) < 2:
        err("No action specified")
        return

    action = sys.argv[1]

    if action == "screenshot":
        zoom_x1 = int(sys.argv[2]) if len(sys.argv) > 2 else None
        zoom_y1 = int(sys.argv[3]) if len(sys.argv) > 3 else None
        zoom_x2 = int(sys.argv[4]) if len(sys.argv) > 4 else None
        zoom_y2 = int(sys.argv[5]) if len(sys.argv) > 5 else None
        take_screenshot(zoom_x1, zoom_y1, zoom_x2, zoom_y2)
    elif action == "click":
        perform_click(int(float(sys.argv[2])), int(float(sys.argv[3])),
                      sys.argv[4] if len(sys.argv) > 4 else "left",
                      int(float(sys.argv[5])) if len(sys.argv) > 5 else 1)
    elif action == "move":
        perform_move(int(float(sys.argv[2])), int(float(sys.argv[3])))
    elif action == "type":
        perform_type(" ".join(sys.argv[2:]))
    elif action == "press":
        perform_press(sys.argv[2])
    elif action == "hotkey":
        perform_hotkey(*sys.argv[2:])
    elif action == "scroll":
        perform_scroll(int(float(sys.argv[2])))
    elif action == "drag":
        perform_drag(int(float(sys.argv[2])), int(float(sys.argv[3])),
                     int(float(sys.argv[4])), int(float(sys.argv[5])))
    else:
        err(f"Unknown action: {action}")

if __name__ == "__main__":
    main()
