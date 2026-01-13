#!/bin/bash
# 라즈베리파이 시스템 모니터링 스크립트

LOG_FILE="system_monitor_$(date +%Y%m%d_%H%M%S).log"
DURATION=18000  # 5시간 (초)
INTERVAL=300    # 5분마다 체크

echo "=== System Monitoring Started ===" | tee -a "$LOG_FILE"
echo "Duration: $((DURATION/3600)) hours" | tee -a "$LOG_FILE"
echo "Check interval: $((INTERVAL/60)) minutes" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

start_time=$(date +%s)
end_time=$((start_time + DURATION))

while [ $(date +%s) -lt $end_time ]; do
    elapsed=$(($(date +%s) - start_time))
    remaining=$((end_time - $(date +%s)))

    echo "======================================" | tee -a "$LOG_FILE"
    echo "Time: $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "$LOG_FILE"
    echo "Elapsed: $((elapsed/60)) min / Remaining: $((remaining/60)) min" | tee -a "$LOG_FILE"
    echo "" | tee -a "$LOG_FILE"

    # GPU 메모리
    echo "[GPU Memory]" | tee -a "$LOG_FILE"
    vcgencmd get_mem gpu | tee -a "$LOG_FILE"
    vcgencmd get_mem arm | tee -a "$LOG_FILE"
    echo "" | tee -a "$LOG_FILE"

    # 온도
    echo "[Temperature]" | tee -a "$LOG_FILE"
    vcgencmd measure_temp | tee -a "$LOG_FILE"
    echo "" | tee -a "$LOG_FILE"

    # 메모리 사용률
    echo "[Memory Usage]" | tee -a "$LOG_FILE"
    free -h | tee -a "$LOG_FILE"
    echo "" | tee -a "$LOG_FILE"

    # CPU 사용률
    echo "[CPU Usage]" | tee -a "$LOG_FILE"
    top -bn1 | grep "Cpu(s)" | tee -a "$LOG_FILE"
    echo "" | tee -a "$LOG_FILE"

    # 프로세스 확인
    echo "[Python Process]" | tee -a "$LOG_FILE"
    ps aux | grep -E "python.*main.py" | grep -v grep | tee -a "$LOG_FILE"
    echo "" | tee -a "$LOG_FILE"

    # 디스크 사용률
    echo "[Disk Usage]" | tee -a "$LOG_FILE"
    df -h / | tee -a "$LOG_FILE"
    echo "" | tee -a "$LOG_FILE"

    sleep $INTERVAL
done

echo "=== Monitoring Completed ===" | tee -a "$LOG_FILE"
echo "Log saved to: $LOG_FILE"
