from flask import Flask, send_file, jsonify, request
from picamera2 import Picamera2
from picamera2.encoders import H264Encoder
from picamera2.outputs import FfmpegOutput
from libcamera import Transform
import os
import subprocess
import threading
import time
import logging
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime

app = Flask(__name__)

VIDEO_FORMAT = "mp4"
VIDEO_DIR = "video"
VIDEO_PATH = f"video/camera_video.{VIDEO_FORMAT}"
TEMP_PATH = "video/camera_video.h264"

VIDEO_WIDTH = 1280
VIDEO_HEIGHT = 720
VIDEO_FPS = 30

camera = None
recording = False
converting = False  # 변환 상태 추가
recording_start_time = None

# 로깅 설정
LOG_DIR = "log"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# 날짜별 로그 파일 (하루에 하나의 파일)
log_filename = os.path.join(LOG_DIR, "picam_server.log")

# TimedRotatingFileHandler로 자정에 자동으로 새 파일 생성
file_handler = TimedRotatingFileHandler(
    log_filename,
    when='midnight',  # 자정에 로테이션
    interval=1,       # 1일마다
    backupCount=365,   # 최근 30일 유지
    encoding='utf-8'
)
file_handler.suffix = "%Y%m%d"  # 백업 파일 이름 형식 (picam_server.log.20251223)

console_handler = logging.StreamHandler()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[file_handler, console_handler]
)
logger = logging.getLogger(__name__)

logger.info("=== PiCam Server Started ===")
logger.info(f"Log file: {log_filename}")

def record_video():
    global camera, recording, converting, recording_start_time
    try:
        if not os.path.exists(VIDEO_DIR):
            os.mkdir(VIDEO_DIR)
            logger.info(f"Created video directory: {VIDEO_DIR}")

        logger.info(f"Initializing camera with config: {VIDEO_WIDTH}x{VIDEO_HEIGHT}@{VIDEO_FPS}fps")
        camera = Picamera2()
        config = camera.create_video_configuration(
            main={"size": (VIDEO_WIDTH, VIDEO_HEIGHT)},
            transform=Transform(rotation=180)
        )
        camera.configure(config)

        encoder = H264Encoder()
        camera.start()
        recording_start_time = time.time()
        camera.start_recording(encoder, TEMP_PATH)
        recording = True
        logger.info(f"Recording started at {datetime.fromtimestamp(recording_start_time).strftime('%Y-%m-%d %H:%M:%S')}")

        while recording:
            time.sleep(0.1)

        recording_duration = time.time() - recording_start_time
        logger.info(f"Recording stopped. Duration: {recording_duration:.2f} seconds ({recording_duration/60:.2f} minutes)")

        camera.stop_recording()
        camera.close()
        recording = False

        # H264 파일 크기 확인
        if os.path.exists(TEMP_PATH):
            h264_size = os.path.getsize(TEMP_PATH)
            logger.info(f"H264 file size: {h264_size:,} bytes ({h264_size/1024/1024:.2f} MB)")
        else:
            logger.error(f"H264 file not found: {TEMP_PATH}")
            return

        # 변환 시작
        converting = True
        conversion_start = time.time()
        logger.info("Starting video conversion (H264 → MP4)...")

        result = subprocess.run(
            [
                'ffmpeg',
                '-i',
                TEMP_PATH,
                '-c:v',
                'copy',
                VIDEO_PATH,
                '-y'
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        conversion_duration = time.time() - conversion_start

        if result.returncode == 0:
            converting = False
            logger.info(f"Video conversion completed successfully in {conversion_duration:.2f} seconds")

            # MP4 파일 크기 확인
            if os.path.exists(VIDEO_PATH):
                mp4_size = os.path.getsize(VIDEO_PATH)
                logger.info(f"MP4 file size: {mp4_size:,} bytes ({mp4_size/1024/1024:.2f} MB)")
            else:
                logger.error(f"MP4 file not found after conversion: {VIDEO_PATH}")
        else:
            converting = False
            logger.error(f"Video conversion failed with return code {result.returncode}")
            logger.error(f"FFmpeg stderr: {result.stderr}")

    except Exception as e:
        logger.error(f"Video recording error: {e}", exc_info=True)
        recording = False
        converting = False
    finally:
        recording = False
        converting = False
        recording_start_time = None
        if camera:
            try:
                camera.close()
                logger.info("Camera closed")
            except Exception as e:
                logger.error(f"Error closing camera: {e}")

@app.route('/start', methods=['POST'])
def start_recording():
    global recording
    logger.info(f"[/start] Request received from {request.remote_addr}")

    if not recording:
        recording = True  # 먼저 플래그 설정
        threading.Thread(target=record_video, daemon=True).start()
        time.sleep(0.5)  # 카메라 초기화 대기
        logger.info(f"[/start] Recording started: {VIDEO_WIDTH}x{VIDEO_HEIGHT}@{VIDEO_FPS}fps")
        return jsonify({"status":0, "msg":{"size":f"{VIDEO_WIDTH}x{VIDEO_HEIGHT}", "fps":f"{VIDEO_FPS}"}}),200

    logger.warning(f"[/start] Request rejected - already recording")
    return jsonify({"status":1, "msg":"already recording"}),400

@app.route('/stop', methods=['POST'])
def stop_recording():
    global recording, recording_start_time
    logger.info(f"[/stop] Request received from {request.remote_addr}")

    if recording:
        if recording_start_time:
            elapsed = time.time() - recording_start_time
            logger.info(f"[/stop] Stopping recording after {elapsed:.2f} seconds ({elapsed/60:.2f} minutes)")
        recording = False
        time.sleep(1)
        logger.info(f"[/stop] Recording stopped, conversion will start")
        return jsonify({"status":0, "msg":"stopped, converting..."}),200

    logger.warning(f"[/stop] Request rejected - not recording")
    return jsonify({"status":1, "msg":"not recording"}),400

@app.route('/download', methods=['GET'])
def download_video():
    """MP4 변환된 파일 다운로드 (변환 대기 필요)"""
    logger.info(f"[/download] Request received from {request.remote_addr}")

    if converting:
        logger.warning(f"[/download] Request rejected - video is still converting")
        return jsonify({"status":1, "msg":"video is converting, please wait"}),400

    if os.path.exists(VIDEO_PATH):
        file_size = os.path.getsize(VIDEO_PATH)
        logger.info(f"[/download] Serving MP4 file: {file_size:,} bytes ({file_size/1024/1024:.2f} MB)")

        try:
            response = send_file(
                VIDEO_PATH,
                as_attachment=True,
                download_name=f"camera_video.{VIDEO_FORMAT}",
                max_age=0  # 캐싱 방지
            )
            logger.info(f"[/download] File sent successfully to {request.remote_addr}")
            return response
        except Exception as e:
            logger.error(f"[/download] Error sending file: {e}", exc_info=True)
            return jsonify({"status":1, "msg":f"error sending file: {str(e)}"}),500

    logger.warning(f"[/download] Request rejected - no video file exists")
    return jsonify({"status":1, "msg":"no video"}),400

@app.route('/download/raw', methods=['GET'])
def download_raw_video():
    """H264 원본 파일 즉시 다운로드 (변환 불필요)"""
    logger.info(f"[/download/raw] Request received from {request.remote_addr}")

    if recording:
        logger.warning(f"[/download/raw] Request rejected - still recording")
        return jsonify({"status":1, "msg":"still recording"}),400

    if os.path.exists(TEMP_PATH):
        file_size = os.path.getsize(TEMP_PATH)
        logger.info(f"[/download/raw] Serving H264 file: {file_size:,} bytes ({file_size/1024/1024:.2f} MB)")

        try:
            response = send_file(
                TEMP_PATH,
                as_attachment=True,
                download_name="camera_video.h264",
                max_age=0  # 캐싱 방지
            )
            logger.info(f"[/download/raw] File sent successfully to {request.remote_addr}")
            return response
        except Exception as e:
            logger.error(f"[/download/raw] Error sending file: {e}", exc_info=True)
            return jsonify({"status":1, "msg":f"error sending file: {str(e)}"}),500

    logger.warning(f"[/download/raw] Request rejected - no raw video file exists")
    return jsonify({"status":1, "msg":"no raw video"}),400

@app.route('/getconfig', methods=['GET'])
def get_config():
    logger.info(f"[/getconfig] Request received from {request.remote_addr}")
    config = {
        "format":VIDEO_FORMAT,
        "resolution":f"{VIDEO_WIDTH}x{VIDEO_HEIGHT}",
        "fps":VIDEO_FPS
    }
    logger.info(f"[/getconfig] Returning config: {config}")
    return jsonify(config),200

@app.route('/setconfig', methods=['POST'])
def set_config():
    global VIDEO_WIDTH, VIDEO_HEIGHT, VIDEO_FPS

    logger.info(f"[/setconfig] Request received from {request.remote_addr}")

    if recording:
        logger.warning(f"[/setconfig] Request rejected - recording in progress")
        return jsonify({"error": "stop recording first"}), 400

    data = request.get_json()
    logger.info(f"[/setconfig] Requested config: {data}")

    new_width = data.get('width', VIDEO_WIDTH)
    new_height = data.get('height', VIDEO_HEIGHT)
    new_fps = data.get('fps', VIDEO_FPS)

    valid_resolutions = [(640,480), (1280,720), (1920,1080)]
    if (new_width, new_height) not in valid_resolutions:
        logger.warning(f"[/setconfig] Invalid resolution: {new_width}x{new_height}")
        return jsonify({"error": "invalid resolution, use: 640x480, 1280x720, 1920x1080"}), 400

    if new_fps not in [25, 30]:
        logger.warning(f"[/setconfig] Invalid fps: {new_fps}")
        return jsonify({"error": "fps must be 25 or 30"}), 400

    VIDEO_WIDTH, VIDEO_HEIGHT, VIDEO_FPS = new_width, new_height, new_fps
    logger.info(f"[/setconfig] Config updated: {VIDEO_WIDTH}x{VIDEO_HEIGHT}@{VIDEO_FPS}fps")

    return jsonify({
        "status": "config updated",
        "new_config": f"{VIDEO_WIDTH}x{VIDEO_HEIGHT}@{VIDEO_FPS}fps"
    }), 200

@app.route('/status', methods=['GET'])
def get_status():
    logger.info(f"[/status] Request received from {request.remote_addr}")

    if converting:
        logger.info(f"[/status] Current status: converting")
        return jsonify({"status": 0, "msg": "converting video"}), 200
    elif recording:
        elapsed = time.time() - recording_start_time if recording_start_time else 0
        logger.info(f"[/status] Current status: recording ({elapsed:.1f}s)")
        return jsonify({
            "status": 0,
            "msg": "recording",
            "duration": f"{elapsed:.1f}s",
            "duration_seconds": round(elapsed, 1),
            "start_time": recording_start_time
        }), 200
    else:
        logger.info(f"[/status] Current status: idle")
        return jsonify({"status": 0, "msg": "idle"}), 200

@app.route('/test', methods=['GET'])
def test_camera():
    logger.info(f"[/test] Camera test request received from {request.remote_addr}")

    try:
        picam2 = Picamera2()
        config = picam2.create_still_configuration()
        picam2.configure(config)
        picam2.start()
        time.sleep(2)
        picam2.capture_file("test.jpg")
        picam2.stop()
        picam2.close()
        logger.info(f"[/test] Test image captured successfully")
        return send_file("test.jpg", as_attachment=True)
    except Exception as e:
        logger.error(f"[/test] Camera test failed: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

if __name__=='__main__':
    logger.info(f"Starting Flask server on 0.0.0.0:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)
