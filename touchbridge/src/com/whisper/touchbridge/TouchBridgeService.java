package com.whisper.touchbridge;

import android.accessibilityservice.AccessibilityService;
import android.accessibilityservice.GestureDescription;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.graphics.Path;
import android.util.Log;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;

public class TouchBridgeService extends AccessibilityService {
    private static final String TAG = "TouchBridge";
    private static final int PORT = 9876;
    private static TouchBridgeService instance;
    private ServerSocket serverSocket;
    private boolean isRunning = false;

    private final BroadcastReceiver receiver = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            if (intent == null || intent.getAction() == null) return;
            String action = intent.getAction();
            if ("com.whisper.touchbridge.TAP".equals(action)) {
                float x = intent.getFloatExtra("x", 0f);
                float y = intent.getFloatExtra("y", 0f);
                if (x == 0f && intent.hasExtra("px")) x = intent.getIntExtra("px", 0);
                if (y == 0f && intent.hasExtra("py")) y = intent.getIntExtra("py", 0);
                performTap(x, y);
            } else if ("com.whisper.touchbridge.SWIPE".equals(action)) {
                float x1 = intent.getFloatExtra("x1", 0f);
                float y1 = intent.getFloatExtra("y1", 0f);
                float x2 = intent.getFloatExtra("x2", 0f);
                float y2 = intent.getFloatExtra("y2", 0f);
                int dur = intent.getIntExtra("duration", 250);
                performSwipe(x1, y1, x2, y2, dur);
            } else if ("com.whisper.touchbridge.KEY".equals(action)) {
                String key = intent.getStringExtra("key");
                performKeyAction(key);
            } else if ("com.whisper.touchbridge.GLOBAL".equals(action)) {
                int gAction = intent.getIntExtra("action", 1);
                performGlobalAction(gAction);
            }
        }
    };

    @Override
    public void onServiceConnected() {
        super.onServiceConnected();
        instance = this;
        Log.i(TAG, "TouchBridge Accessibility Service Connected!");

        IntentFilter filter = new IntentFilter();
        filter.addAction("com.whisper.touchbridge.TAP");
        filter.addAction("com.whisper.touchbridge.SWIPE");
        filter.addAction("com.whisper.touchbridge.KEY");
        filter.addAction("com.whisper.touchbridge.GLOBAL");
        registerReceiver(receiver, filter);

        startTcpServer();
    }

    private void startTcpServer() {
        isRunning = true;
        new Thread(() -> {
            try {
                serverSocket = new ServerSocket(PORT, 10, InetAddress.getByName("127.0.0.1"));
                Log.i(TAG, "TouchBridge TCP socket listening on 127.0.0.1:" + PORT);
                while (isRunning) {
                    try {
                        Socket client = serverSocket.accept();
                        handleClient(client);
                    } catch (Exception e) {
                        if (!isRunning) break;
                    }
                }
            } catch (Exception e) {
                Log.e(TAG, "Error starting TCP socket: " + e.getMessage());
            }
        }, "TouchBridge-TCP").start();
    }

    private void handleClient(Socket socket) {
        new Thread(() -> {
            try (BufferedReader reader = new BufferedReader(new InputStreamReader(socket.getInputStream()));
                 OutputStream out = socket.getOutputStream()) {
                String line;
                while ((line = reader.readLine()) != null) {
                    line = line.trim();
                    if (line.isEmpty()) continue;
                    String[] parts = line.split("\\s+");
                    String cmd = parts[0].toUpperCase();
                    boolean ok = false;
                    if ("TAP".equals(cmd) && parts.length >= 3) {
                        float x = Float.parseFloat(parts[1]);
                        float y = Float.parseFloat(parts[2]);
                        ok = performTap(x, y);
                    } else if ("SWIPE".equals(cmd) && parts.length >= 5) {
                        float x1 = Float.parseFloat(parts[1]);
                        float y1 = Float.parseFloat(parts[2]);
                        float x2 = Float.parseFloat(parts[3]);
                        float y2 = Float.parseFloat(parts[4]);
                        int dur = parts.length >= 6 ? Integer.parseInt(parts[5]) : 250;
                        ok = performSwipe(x1, y1, x2, y2, dur);
                    } else if ("KEY".equals(cmd) && parts.length >= 2) {
                        ok = performKeyAction(parts[1]);
                    } else if ("GLOBAL".equals(cmd) && parts.length >= 2) {
                        try {
                            ok = performGlobalAction(Integer.parseInt(parts[1]));
                        } catch (Exception ignored) {}
                    } else if ("PING".equals(cmd)) {
                        ok = true;
                    }
                    out.write((ok ? "OK\n" : "FAIL\n").getBytes());
                    out.flush();
                }
            } catch (Exception ignored) {
            } finally {
                try { socket.close(); } catch (Exception ignored) {}
            }
        }).start();
    }

    public boolean performKeyAction(String key) {
        if (key == null) return false;
        String k = key.toUpperCase().trim();
        switch (k) {
            case "BACK":
                return performGlobalAction(GLOBAL_ACTION_BACK);
            case "HOME":
                return performGlobalAction(GLOBAL_ACTION_HOME);
            case "RECENTS":
            case "APP_SWITCH":
                return performGlobalAction(GLOBAL_ACTION_RECENTS);
            case "NOTIFICATIONS":
                return performGlobalAction(GLOBAL_ACTION_NOTIFICATIONS);
            case "QUICK_SETTINGS":
                return performGlobalAction(GLOBAL_ACTION_QUICK_SETTINGS);
            case "POWER":
            case "POWER_DIALOG":
                return performGlobalAction(GLOBAL_ACTION_POWER_DIALOG);
            case "LOCK":
                return performGlobalAction(8); // GLOBAL_ACTION_LOCK_SCREEN
            case "SCREENSHOT":
                return performGlobalAction(9); // GLOBAL_ACTION_TAKE_SCREENSHOT
            default:
                return false;
        }
    }

    public boolean performTap(float x, float y) {
        Path path = new Path();
        path.moveTo(x, y);
        GestureDescription.StrokeDescription stroke = new GestureDescription.StrokeDescription(path, 0, 45);
        GestureDescription.Builder builder = new GestureDescription.Builder();
        builder.addStroke(stroke);
        return dispatchGesture(builder.build(), null, null);
    }

    public boolean performSwipe(float x1, float y1, float x2, float y2, int duration) {
        Path path = new Path();
        path.moveTo(x1, y1);
        path.lineTo(x2, y2);
        int dur = Math.max(50, Math.min(2000, duration));
        GestureDescription.StrokeDescription stroke = new GestureDescription.StrokeDescription(path, 0, dur);
        GestureDescription.Builder builder = new GestureDescription.Builder();
        builder.addStroke(stroke);
        return dispatchGesture(builder.build(), null, null);
    }

    @Override
    public void onAccessibilityEvent(android.view.accessibility.AccessibilityEvent event) {}

    @Override
    public void onInterrupt() {}

    @Override
    public void onDestroy() {
        isRunning = false;
        try { if (serverSocket != null) serverSocket.close(); } catch (Exception ignored) {}
        try { unregisterReceiver(receiver); } catch (Exception ignored) {}
        instance = null;
        super.onDestroy();
    }
}
