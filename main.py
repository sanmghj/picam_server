"""
PiCam Server - Flask 웹 서버
카메라 녹화 및 비디오 스트리밍 서비스
"""
from flask import Flask, render_template
import logging

from config import setup_logging
from camera_operations import CameraManager
from api_handlers import APIHandlers

# 로깅 초기화
setup_logging()
logger = logging.getLogger(__name__)

# Flask 앱 초기화
app = Flask(__name__)

# 카메라 매니저 초기화
camera_manager = CameraManager(video_dir="video")

# ===== Flask 라우트 정의 =====

@app.route('/start', methods=['POST'])
def start_recording():
    """녹화 시작"""
    return APIHandlers.start_recording(camera_manager)


@app.route('/stop', methods=['POST'])
def stop_recording():
    """녹화 중지"""
    return APIHandlers.stop_recording(camera_manager)


@app.route('/download', methods=['GET'])
def download_video():
    """MP4 변환된 파일 다운로드"""
    return APIHandlers.download_video(camera_manager)


@app.route('/download/raw', methods=['GET'])
def download_raw_video():
    """H264 원본 파일 다운로드"""
    return APIHandlers.download_raw_video(camera_manager)


@app.route('/getconfig', methods=['GET'])
def get_config():
    """현재 설정 조회"""
    return APIHandlers.get_config(camera_manager)


@app.route('/setconfig', methods=['POST'])
def set_config():
    """설정 변경"""
    return APIHandlers.set_config(camera_manager)


@app.route('/status', methods=['GET'])
def get_status():
    """현재 상태 조회"""
    return APIHandlers.get_status(camera_manager)


@app.route('/test', methods=['GET'])
def test_camera():
    """카메라 테스트"""
    return APIHandlers.test_camera(camera_manager)


@app.route('/livestream', methods=['GET'])
def livestream():
    """실시간 비디오 스트림 (UI 없음, 동영상만)"""
    return render_template('stream_only.html')


@app.route('/stream', methods=['GET'])
def stream():
    """실시간 MJPEG 스트림 데이터"""
    return APIHandlers.get_stream(camera_manager)


@app.route('/stopstream', methods=['POST'])
def stop_stream():
    """스트림 강제 종료"""
    return APIHandlers.stop_stream(camera_manager)


@app.route('/viewer', methods=['GET'])
def viewer():
    """라이브 스트림 뷰어 페이지 (UI 포함)"""
    return render_template('livestream.html')


# ===== 서버 실행 =====

if __name__ == '__main__':
    logger.info("Starting Flask server on 0.0.0.0:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)
