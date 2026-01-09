#!/bin/bash

# RPi Camera 재측정 스크립트
# RPI 4 (192.168.1.50): 1분 720p
# RPI Zero (192.168.1.72): 3분, 5분 720p

LOG_DIR="./log"
mkdir -p "$LOG_DIR" "./temp"
TOTAL_LOG="$LOG_DIR/retest_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee -a "$TOTAL_LOG") 2>&1

get_resolution() {
    local res_label=$1
    case $res_label in
        "480")  echo "640 480" ;;
        "720")  echo "1280 720" ;;
        "1080") echo "1920 1080" ;;
        *)      echo "640 480" ;;
    esac
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
    local server_ip=$1 duration=$2 resolution=$3 server_name=$4

    echo ""
    echo "📡 [$server_name - $server_ip] $duration분 ${resolution}p 재측정 시작"
    echo "=========================================="

    local start_time=$(date +%s.%3N)
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

    local status_resp=$(curl -s -w "\n%{http_code}" "http://$server_ip:$port/status")
    local status=$(echo "$status_resp" | head -n -1)
    local status_code=$(echo "$status_resp" | tail -1)
    log_api_call "GET /status" "$status ($status_code)" $([[ "$status" == *"idle"* ]] && echo "green" || echo "yellow")

    echo "  📹 녹화 시작 (${duration}분 = $((duration * 60))초)"
    local record_start=$(date +%s.%3N)
    local start_resp=$(curl -s -w "\n%{http_code}" -X POST "http://$server_ip:$port/start")
    local start_status=$(echo "$start_resp" | tail -1)
    local start_body=$(echo "$start_resp" | head -n -1)
    log_api_call "POST /start" "$start_body ($start_status)" green
    sleep $((duration * 60))

    echo "  🛑 녹화 중지"
    local record_stop=$(date +%s.%3N)
    local stop_resp=$(curl -s -w "\n%{http_code}" -X POST "http://$server_ip:$port/stop")
    local stop_status=$(echo "$stop_resp" | tail -1)
    log_api_call "POST /stop" "$(echo "$stop_resp" | head -n -1) ($stop_status)" green

    # 5. 변환 대기 (수정된 버전)
    local convert_start=$(date +%s.%3N)
    echo "  🔄 변환 대기중..."
    local convert_count=0
    local max_wait=600  # 최대 10분 대기
    while [ $convert_count -lt $max_wait ]; do
        sleep 1
        local status_resp=$(curl -s "http://$server_ip:$port/status" 2>/dev/null || echo '{"msg":"timeout"}')
        local status_msg=$(echo "$status_resp" | jq -r '.msg // empty' 2>/dev/null || echo "$status_resp")

        ((convert_count++))

        if [[ "$status_msg" == "idle" ]]; then
            echo ""
            echo "  ✅ 변환 완료 (idle) - ${convert_count}초 소요"
            break
        elif [[ "$status_msg" == "converting"* ]] || [[ "$status_msg" == *"converting"* ]]; then
            printf "  🔄 변환중... (%ds) [상태: %s]\r" $convert_count "$status_msg"
        elif [[ "$status_msg" == "recording" ]]; then
            printf "  ⚠️  아직 녹화중... (%ds)\r" $convert_count
        else
            printf "  ⏳ 대기중... (%ds) [상태: %s]\r" $convert_count "$status_msg"
        fi
    done

    if [ $convert_count -ge $max_wait ]; then
        echo ""
        echo "  ⚠️ 변환 대기 시간 초과 (${max_wait}초)"
    fi

    local convert_stop=$(date +%s.%3N)

    local download_start=$(date +%s.%3N)
    local temp_file="./temp/RETEST_${server_ip}_${duration}min_${resolution}p.mp4"
    echo "  📥 다운로드 중... (${width}x${height})"
    curl -L --progress-bar "http://$server_ip:$port/download" -o "$temp_file"
    local download_resp_code=$?
    local download_stop=$(date +%s.%3N)

    if [ $download_resp_code -eq 0 ]; then
        local file_size=$(stat -c%s "$temp_file" 2>/dev/null || echo "0")
        local file_size_mb=$(echo "scale=1; $file_size / 1024 / 1024" | bc -l)
        echo "  ✅ 다운로드 완료 (${file_size_mb} MB)"
    else
        echo "  ❌ 다운로드 실패"
        file_size=0
        file_size_mb=0
    fi

    rm -f "$temp_file"

    local total_time=$(echo "$download_stop - $start_time" | bc -l)
    local record_time=$(echo "$record_stop - $record_start" | bc -l)
    local convert_time=$(echo "$convert_stop - $convert_start" | bc -l)
    local download_time=$(echo "$download_stop - $download_start" | bc -l)

    local date_today=$(date +%Y%m%d)
    local json_file="$LOG_DIR/RETEST_${server_ip}_${duration}min_${resolution}p_${date_today}.json"

    cat > "$json_file" <<EOF
{
    "server": "$server_ip:$port",
    "server_name": "$server_name",
    "duration_min": $duration,
    "resolution": "${resolution}p",
    "width": $width,
    "height": $height,
    "total_time_sec": $(printf "%.3f" $total_time),
    "record_time_sec": $(printf "%.3f" $record_time),
    "convert_time_sec": $(printf "%.3f" $convert_time),
    "download_time_sec": $(printf "%.3f" $download_time),
    "file_size_bytes": $file_size,
    "file_size_mb": $(printf "%.1f" $file_size_mb),
    "test_timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF

    echo "  📊 결과: 총${total_time:0:5}s | 녹화${record_time:0:5}s | 변환${convert_time:0:5}s | 다운${download_time:0:5}s | ${file_size_mb}MB"
    echo "  💾 저장: $json_file"
    echo ""
}

echo "🔄 RPi Camera 재측정 시작 (총 3개 테스트)"
echo "=========================================="
echo "📡 RPI 4 (192.168.1.50 - 5G): 1분 720p"
echo "📡 RPI Zero (192.168.1.72 - 2.4G): 3분, 5분 720p"
echo "📂 결과: ./log/ 폴더"
echo ""

CURRENT_TEST=0
TOTAL_TESTS=2

# 2. RPI Zero: 3분 720p
((CURRENT_TEST++))
echo "🔄 진행: $CURRENT_TEST/$TOTAL_TESTS"
test_video_recording "192.168.1.72" 3 "720" "RPI Zero (2.4G)"

# 3. RPI Zero: 5분 720p
((CURRENT_TEST++))
echo "🔄 진행: $CURRENT_TEST/$TOTAL_TESTS"
test_video_recording "192.168.1.72" 5 "720" "RPI Zero (2.4G)"

echo "🎉 재측정 완료! ✅ (총 $TOTAL_TESTS개)"
echo "=========================================="
echo "📂 결과 파일:"
ls -lh "$LOG_DIR"/RETEST_*.json 2>/dev/null || echo "파일 생성중..."