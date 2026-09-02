#!/usr/bin/env python3
# ============================================================
# take_portal_screenshot.py — Portal-based Screenshot for Wayland
# ============================================================

import sys
import os
import shutil
import urllib.parse
import gi
gi.require_version('Gio', '2.0')
from gi.repository import Gio, GLib

def main():
    if len(sys.argv) < 2:
        print("Error: No output path specified")
        sys.exit(1)
        
    out_path = sys.argv[1]
    loop = GLib.MainLoop()
    captured_uri = [None]

    def on_signal(connection, sender_name, object_path, interface_name, signal_name, parameters, user_data):
        try:
            unpacked = parameters.unpack()
            # The signal arguments are: (response_code, results)
            # results is a dictionary a{sv} containing keys like 'uri'
            if len(unpacked) >= 2 and isinstance(unpacked[1], dict):
                results = unpacked[1]
                if 'uri' in results:
                    captured_uri[0] = results['uri']
        except Exception as e:
            print("Error parsing signal:", e)
        loop.quit()

    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    
    # Subscribe to Request Response signal
    subscription_id = bus.signal_subscribe(
        "org.freedesktop.portal.Desktop",
        "org.freedesktop.portal.Request",
        "Response",
        None,
        None,
        Gio.DBusSignalFlags.NONE,
        on_signal,
        None
    )

    # Call org.freedesktop.portal.Screenshot.Screenshot
    # Use handle_token to make the request path unique
    import time
    token = f"swades_{int(time.time())}"
    options = {
        'interactive': GLib.Variant('b', False),
        'handle_token': GLib.Variant('s', token)
    }

    try:
        res = bus.call_sync(
            "org.freedesktop.portal.Desktop",
            "/org/freedesktop/portal/desktop",
            "org.freedesktop.portal.Screenshot",
            "Screenshot",
            GLib.Variant('(sa{sv})', ("", options)),
            GLib.VariantType('(o)'),
            Gio.DBusCallFlags.NONE,
            -1,
            None
        )
    except Exception as e:
        print("Portal D-Bus call failed:", e)
        sys.exit(1)

    # Run loop to wait for signal response
    loop.run()
    
    # Unsubscribe
    bus.signal_unsubscribe(subscription_id)

    if not captured_uri[0]:
        print("Error: No screenshot URI returned by portal")
        sys.exit(1)

    # Unpack URI to local file path
    uri = captured_uri[0]
    if uri.startswith("file://"):
        file_path = urllib.parse.unquote(uri[7:])
    else:
        file_path = uri

    if not os.path.exists(file_path):
        print(f"Error: Screenshot file does not exist at path: {file_path}")
        sys.exit(1)

    # Copy to target destination
    try:
        shutil.copy2(file_path, out_path)
        # Delete original to keep ~/Pictures clean
        try:
            os.remove(file_path)
        except Exception:
            pass
        print("Success")
        sys.exit(0)
    except Exception as e:
        print(f"Error copying file: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
