#!/bin/bash
set -e

SDK_DIR="/home/soham/Android/Sdk"
BUILD_TOOLS="$SDK_DIR/build-tools/36.0.0"
PLATFORM_JAR="$SDK_DIR/platforms/android-37.0/android.jar"
ROOT_DIR="$(pwd)/touchbridge"

rm -rf "$ROOT_DIR/build" "$ROOT_DIR/gen" "$ROOT_DIR/classes" "$ROOT_DIR/dex"
mkdir -p "$ROOT_DIR/build" "$ROOT_DIR/gen" "$ROOT_DIR/classes" "$ROOT_DIR/dex"

echo "[1/6] Compiling XML resources..."
"$BUILD_TOOLS/aapt2" compile --dir "$ROOT_DIR/res" -o "$ROOT_DIR/build/compiled_res.zip"

echo "[2/6] Linking resources..."
"$BUILD_TOOLS/aapt2" link -I "$PLATFORM_JAR" \
    "$ROOT_DIR/build/compiled_res.zip" \
    --manifest "$ROOT_DIR/AndroidManifest.xml" \
    --java "$ROOT_DIR/gen" \
    --auto-add-overlay \
    -o "$ROOT_DIR/build/base.apk"

echo "[3/6] Compiling Java classes..."
javac -source 8 -target 8 -cp "$PLATFORM_JAR" \
    -d "$ROOT_DIR/classes" \
    "$ROOT_DIR/src/com/whisper/touchbridge"/*.java \
    "$ROOT_DIR/gen/com/whisper/touchbridge"/*.java

echo "[4/6] Compiling DEX with d8 (min-api 24)..."
"$BUILD_TOOLS/d8" --min-api 24 "$ROOT_DIR/classes/com/whisper/touchbridge"/*.class \
    --lib "$PLATFORM_JAR" \
    --output "$ROOT_DIR/dex"

echo "[5/6] Adding classes.dex..."
cd "$ROOT_DIR/dex"
zip -uj "$ROOT_DIR/build/base.apk" classes.dex
cd "$ROOT_DIR"

echo "[6/6] Zipalign and signing with v1+v2..."
"$BUILD_TOOLS/zipalign" -f -p 4 "$ROOT_DIR/build/base.apk" "$ROOT_DIR/build/TouchBridge-aligned.apk"
"$BUILD_TOOLS/apksigner" sign \
    --ks "$ROOT_DIR/debug.keystore" \
    --ks-pass pass:android \
    --key-pass pass:android \
    --ks-key-alias androiddebugkey \
    --v1-signing-enabled true \
    --v2-signing-enabled true \
    --v3-signing-enabled false \
    --v4-signing-enabled false \
    --out "$ROOT_DIR/TouchBridge.apk" \
    "$ROOT_DIR/build/TouchBridge-aligned.apk"

echo "BUILD SUCCESSFUL! Verified signature:"
"$BUILD_TOOLS/apksigner" verify -v "$ROOT_DIR/TouchBridge.apk"
