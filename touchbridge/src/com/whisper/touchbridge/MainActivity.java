package com.whisper.touchbridge;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.provider.Settings;
import android.view.Gravity;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

public class MainActivity extends Activity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setGravity(Gravity.CENTER);
        layout.setPadding(48, 48, 48, 48);

        TextView title = new TextView(this);
        title.setText("Autonomous Touch Bridge");
        title.setTextSize(22);
        title.setGravity(Gravity.CENTER);
        title.setPadding(0, 0, 0, 32);
        layout.addView(title);

        TextView desc = new TextView(this);
        desc.setText("Tap the button below and toggle 'Touch Bridge' to ON.\nThis allows sovereign steering and clicks without requiring a SIM card or root.");
        desc.setTextSize(14);
        desc.setGravity(Gravity.CENTER);
        desc.setPadding(0, 0, 0, 48);
        layout.addView(desc);

        Button btn = new Button(this);
        btn.setText("Open Accessibility Settings");
        btn.setOnClickListener(v -> {
            Intent intent = new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS);
            startActivity(intent);
        });
        layout.addView(btn);

        setContentView(layout);
    }
}
