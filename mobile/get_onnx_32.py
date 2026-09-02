import urllib.request
import zipfile
import io
import os

url = "https://repo1.maven.org/maven2/com/microsoft/onnxruntime/onnxruntime-android/1.19.2/onnxruntime-android-1.19.2.aar"
target_dir = "/data/data/com.termux/files/home/kokoro_native"
os.makedirs(target_dir, exist_ok=True)

print("Downloading onnxruntime AAR for armeabi-v7a...")
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req, timeout=90) as resp:
    data = resp.read()

print(f"Downloaded {len(data)} bytes. Extracting armeabi-v7a...")
with zipfile.ZipFile(io.BytesIO(data)) as zf:
    for name in zf.namelist():
        if "armeabi-v7a" in name:
            zf.extract(name, target_dir)
            print(f"Extracted {name}")

print("ONNX Runtime 32-bit armeabi-v7a Android Setup Complete!")
