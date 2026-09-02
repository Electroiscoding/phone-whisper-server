import urllib.request
import tarfile
import os

url = "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/kokoro-en-v0_19.tar.bz2"
target_dir = "/data/data/com.termux/files/home/kokoro_native"
os.makedirs(target_dir, exist_ok=True)
archive_path = os.path.join(target_dir, "kokoro.tar.bz2")

print("Downloading Kokoro-82M ONNX model package...")
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req, timeout=120) as resp, open(archive_path, "wb") as f:
    f.write(resp.read())

print(f"Downloaded {os.path.getsize(archive_path)} bytes. Extracting...")
with tarfile.open(archive_path, "r:bz2") as tar:
    tar.extractall(target_dir)

try:
    os.remove(archive_path)
except Exception:
    pass

print("Kokoro Model Setup Complete!")
