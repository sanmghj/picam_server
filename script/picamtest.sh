#!/bin/bash

# RPi Camera 비교 테스트 스크립트 (WSL - 정확한 해상도 수정)
# 640x480, 1280x720, 1920x1080

# SERVERS=("192.168.1.50" "192.168.1.72")
SERVERS=("192.168.1.50")
DURATIONS=(10 30 60)
RESOLUTIONS=("720")  # 480p=640x480, 720p=1280x720
TOTAL_TESTS=$(( ${#DURATIONS[@]} * ${#RESOLUTIONS[@]} * ${#SERVERS[@]} ))
LOG_DIR="./log"

# 현재 작업폴더에 log 생성
mkdir -p "$LOG_DIR" "./temp"

# total 로그 파일 (스크립트 전체 실행 로그)
TOTAL_LOG="$LOG_DIR/total_$(date +%Y%m%d_%H%M%S).log"

# 이후의 모든 stdout/stderr을 콘솔 + total 로그로 동시에 출력
exec > >(tee -a "$TOTAL_LOG") 2>&1

# 해상도 매핑 함수
get_resolution() {
    local res_label=$1
    case $res_label in
        "480")  echo "640 480" ;;
        "720")  echo "1280 720" ;;
        "1080") echo "1920 1080" ;;
        *)      echo "640 480" ;;
    esac
}

# 진행도 표시 함수
print_progress() {
    local current=$1 total=$2 server=$3 duration=$4 res=$5
    local percent=$((current * 100 / total))
    local bar=$(printf "█%.0s" $(seq 1 $((percent / 2))))
    local space=$(printf "░%.0s" $(seq 1 $(((100-percent) / 2))))
    printf "\r🔄 진행: %3d%% [%s%s] %d/%d | %s %d분 %sp" \
        $percent "$bar" "$space" $current $total "$server" $duration "${res}p"
}

log_api_call() {
    local api=$1 response=$2 color=$3
    case $color in
        "green") echo -e "\e[32m  ✅ $api: $response\e[0m" ;;
        "yellow") echo -e "\e[33m  ⚠️  $api: $response\e[0m" ;;
        "red") echo -e "\e[31m  ❌ $api: $response\e[0m" ;;
        *) echo "  📡 $api: $response" ;;
    esac
}

test_video_recording() {
    local server_ip=$1 duration=$2 resolution=$3 server_idx=$4

    ((CURRENT_TEST++))
    print_progress $CURRENT_TEST $TOTAL_TESTS "$server_ip" $duration $resolution
    echo ""
    echo "📡 [$server_ip] $duration분 ${resolution}p 테스트 시작"

    local start_time=$(date +%s.%3N)

    # 1. 정확한 해상도 설정
    read width height <<< $(get_resolution $resolution)
    local port=5000

    echo "  📐 Config 설정: ${width}x${height}@30fps"
    local config_resp=$(curl -s -w "\n%{http_code}" -X POST "http://$server_ip:$port/setconfig" \
        -H "Content-Type: application/json" \
        -d "{\"width\":$width,\"height\":$height,\"fps\":30}")
    local config_status=$(echo "$config_resp" | tail -1)
    local config_body=$(echo "$config_resp" | head -n -1)
    log_api_call "POST /setconfig" "$config_body ($config_status)" green

    sleep 1

    # 2. 상태 확인
    local status_resp=$(curl -s -w "\n%{http_code}" "http://$server_ip:$port/status")
    local status=$(echo "$status_resp" | head -n -1)
    local status_code=$(echo "$status_resp" | tail -1)
    log_api_call "GET /status" "$status ($status_code)" $([[ "$status" == *"idle"* ]] && echo "green" || echo "yellow")

    # 3. 녹화 시작
    echo "  📹 녹화 시작 (${duration}분 = $((duration * 60))초)"
    local record_start=$(date +%s.%3N)
    local start_resp=$(curl -s -w "\n%{http_code}" -X POST "http://$server_ip:$port/start")
    local start_status=$(echo "$start_resp" | tail -1)
    local start_body=$(echo "$start_resp" | head -n -1)
    log_api_call "POST /start" "$start_body ($start_status)" green

    # 녹화 중 진행 상황 표시
    local target_duration=$((duration * 60))
    local check_interval=5  # 5초마다 체크
    local elapsed=0

    echo ""
    while [ $elapsed -lt $target_duration ]; do
        sleep $check_interval
        elapsed=$((elapsed + check_interval))

        # 실시간 상태 확인
        local status_resp=$(curl -s "http://$server_ip:$port/status" 2>/dev/null || echo '{"duration_seconds":0}')
        local actual_duration=$(echo "$status_resp" | jq -r '.duration_seconds // 0' 2>/dev/null || echo "0")

        # 진행률 계산
        local percent=$((elapsed * 100 / target_duration))
        [ $percent -gt 100 ] && percent=100

        # 프로그래스바 생성
        local filled=$((percent / 2))
        local empty=$((50 - filled))
        local bar=$(printf "█%.0s" $(seq 1 $filled))
        local space=$(printf "░%.0s" $(seq 1 $empty))

        # 남은 시간 계산
        local remaining=$((target_duration - elapsed))
        local remain_min=$((remaining / 60))
        local remain_sec=$((remaining % 60))

        printf "\r  🎬 녹화중: %3d%% [%s%s] %d/%ds (남은시간: %dm %ds)  " \
            $percent "$bar" "$space" $elapsed $target_duration $remain_min $remain_sec
    done
    echo ""  # 줄바꿈

    # 4. 녹화 중지
    echo "  🛑 녹화 중지"
    local record_stop=$(date +%s.%3N)
    local stop_resp=$(curl -s -w "\n%{http_code}" -X POST "http://$server_ip:$port/stop")
    local stop_status=$(echo "$stop_resp" | tail -1)
    log_api_call "POST /stop" "$(echo "$stop_resp" | head -n -1) ($stop_status)" green

    # 5. 변환 대기
    local convert_start=$(date +%s.%3N)
    echo "  🔄 변환 대기중..."
    local convert_count=0
    while true; do
        local status_resp=$(curl -s "http://$server_ip:$port/status" 2>/dev/null || echo '{"msg":"timeout"}')
        local status=$(echo "$status_resp" | jq -r '.msg // empty' 2>/dev/null || echo "$status_resp")
        if [[ "$status" == *"idle"* ]]; then
            echo "  ✅ 변환 완료 (idle)"
            break
        elif [[ "$status" == *"recording"* ]]; then
            echo -n "  ⚠️  아직 녹화중... "
        elif [[ "$status" == *"converting"* ]]; then
            ((convert_count++))
            printf "  🔄 변환중... (%ds)\r" $convert_count
        fi
        sleep 1
    done
    local convert_stop=$(date +%s.%3N)

    # 파일 안정화 대기 (변환 완료 직후 파일 쓰기 완료 보장)
    echo "  ⏳ 파일 안정화 대기 (2초)..."
    sleep 2

    # 6. 다운로드
    local download_start=$(date +%s.%3N)
    local temp_file="./temp/test_${server_ip}_${duration}min_${resolution}p.mp4"
    echo "  📥 다운로드 중... (${width}x${height})"
    curl -L --progress-bar "http://$server_ip:$port/download" -o "$temp_file"
    local download_resp_code=$?
    local download_stop=$(date +%s.%3N)

    if [ $download_resp_code -eq 0 ]; then
        local file_size=$(stat -c%s "$temp_file" 2>/dev/null || echo "0")
        echo "  ✅ 다운로드 완료 (${file_size} bytes)"
    else
        echo "  ❌ 다운로드 실패"
        file_size=0
    fi

    rm -f "$temp_file"

    # 7. 결과 계산
    local total_time=$(echo "$download_stop - $start_time" | bc -l)
    local record_time=$(echo "$record_stop - $record_start" | bc -l)
    local convert_time=$(echo "$convert_stop - $convert_start" | bc -l)
    local download_time=$(echo "$download_stop - $download_start" | bc -l)

    # 8. 개별 JSON 파일 생성
    local date_today=$(date +%Y%m%d)
    local json_file="$LOG_DIR/${server_ip}_${duration}min_${resolution}p_${date_today}.json"

    cat > "$json_file" <<EOF
{
    "server": "$server_ip:$port",
    "server_idx": $server_idx,
    "duration_min": $duration,
    "resolution": "${resolution}p",
    "width": $width,
    "height": $height,
    "total_time_sec": $(printf "%.3f" $total_time),
    "record_time_sec": $(printf "%.3f" $record_time),
    "convert_time_sec": $(printf "%.3f" $convert_time),
    "download_time_sec": $(printf "%.3f" $download_time),
    "file_size_bytes": $file_size,
    "test_timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF

    echo "  📊 결과: 총${total_time:0:5}s | 녹화${record_time:0:5}s | 변환${convert_time:0:5}s | 다운${download_time:0:5}s | ${file_size_mb}MB → $json_file"
    echo ""
}

echo "🚀 RPi Camera 비교 테스트 시작 (총 $TOTAL_TESTS개 = 1서버×3시간×1화질)"
echo "📐 해상도: 480p=640x480, 720p=1280x720, 1080p=1920x1080"
echo "📂 결과: ./log/ 폴더"
echo ""

CURRENT_TEST=0

# 메인 루프
for duration in "${DURATIONS[@]}"; do
    echo "⏱️  $duration분 테스트 시작"
    echo "----------------------------------------"
    for res in "${RESOLUTIONS[@]}"; do
        for idx in "${!SERVERS[@]}"; do
            server="${SERVERS[$idx]}"
            test_video_recording "$server" "$duration" "$res" $((idx+1))
        done
    done
    echo ""
done

echo "🎉 모든 테스트 완료! ✅ (총 $TOTAL_TESTS개)"
echo "📂 ./log 폴더 확인:"
ls -la "$LOG_DIR"/*.json 2>/dev/null || echo "파일 생성중..."
