import os, sys, subprocess, time

HOME = "/data/data/com.termux/files/home"
BIN = "/data/data/com.termux/files/usr/bin"
LIB = "/data/data/com.termux/files/usr/lib"
PYTHON_BIN = f"{BIN}/python3"

env = os.environ.copy()
env["HOME"] = HOME
env["PREFIX"] = "/data/data/com.termux/files/usr"
env["PATH"] = f"{BIN}:{env.get('PATH', '')}"
env["LD_LIBRARY_PATH"] = f"{LIB}:{env.get('LD_LIBRARY_PATH', '')}"

def is_running(pat):
    r = subprocess.run(["pgrep", "-f", pat], stdout=subprocess.PIPE)
    return r.returncode == 0

if not is_running("gateway.py"):
    print("Spawning gateway.py...")
    subprocess.Popen([PYTHON_BIN, "-u", f"{HOME}/gateway.py"], cwd=HOME, env=env,
                     stdout=open(f"{HOME}/gateway.log", "a"), stderr=subprocess.STDOUT)

if not is_running("tunnel_supervisor.py"):
    print("Spawning tunnel_supervisor.py...")
    subprocess.Popen([PYTHON_BIN, "-u", f"{HOME}/tunnel_supervisor.py"], cwd=HOME, env=env,
                     stdout=open(f"{HOME}/tunnel_supervisor.log", "a"), stderr=subprocess.STDOUT)

if not is_running("qwen_experimenter.py.*--daemon"):
    print("Spawning qwen_experimenter.py daemon...")
    subprocess.Popen([PYTHON_BIN, "-u", f"{HOME}/qwen_experimenter.py", "--daemon", "--interval", "60"],
                     cwd=HOME, env=env, stdout=open(f"{HOME}/qwen_daemon.log", "a"), stderr=subprocess.STDOUT)

time.sleep(3)
print("Launcher complete.")
