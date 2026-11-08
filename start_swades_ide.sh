#!/data/data/com.termux/files/usr/bin/bash
export HOME=/data/data/com.termux/files/home
export PATH=/data/data/com.termux/files/usr/bin:$PATH
export LD_LIBRARY_PATH=/data/data/com.termux/files/usr/lib:$LD_LIBRARY_PATH
export TMPDIR=/data/data/com.termux/files/usr/tmp

cd /data/data/com.termux/files/home/Swades
pkill -f "swades_server.py 8088" 2>/dev/null || true
sleep 1
nohup python3 swades_server.py 8088 > /data/data/com.termux/files/home/Swades/swades_server.log 2>&1 &
PID=$!
echo $PID > /data/data/com.termux/files/home/Swades/swades_server.pid
echo "Swades IDE started on phone with PID $PID"
