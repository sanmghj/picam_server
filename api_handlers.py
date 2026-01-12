"""
Flask API 핸들러 모듈
각 엔드포인트에 대한 비즈니스 로직 처리
"""
from flask import send_file, jsonify, request
import os
import logging
import time
import threading

from config import ConfigValidator

logger = logging.getLogger(__name__)


class APIHandlers:
    """API 요청 처리 클래스"""

    def __init__(self, camera_manager):
        self.camera_manager = camera_manager

    def start_recording(self):
        """녹화 시작 핸들러"""
        logger.info(f"[/start] Request received from {request.remote_addr}")

        if not self.camera_manager.is_recording():
            try:
                # 스레드에서 녹화 실행
                def record_video_thread():
                    try:
                        self.camera_manager.start_recording()

                        # 녹화가 중지될 때까지 대기
                        while self.camera_manager.is_recording():
                            time.sleep(0.1)

                        # 녹화 종료 후 변환
                        self.camera_manager.stop_recording()

                    except Exception as e:
                        logger.error(f"Video recording error: {e}", exc_info=True)
                        self.camera_manager.cleanup()

                threading.Thread(target=record_video_thread, daemon=True).start()
                time.sleep(0.5)  # 카메라 초기화 대기

                config = self.camera_manager.get_config()
                logger.info(f"[/start] Recording started: {config['resolution']}@{config['fps']}fps")

                return jsonify({
                    "status": 0,
                    "msg": {
                        "size": config['resolution'],
                        "fps": str(config['fps'])
                    }
                }), 200

            except Exception as e:
                logger.error(f"[/start] Failed to start recording: {e}", exc_info=True)
                return jsonify({"status": 1, "msg": f"failed to start: {str(e)}"}), 500

        logger.warning(f"[/start] Request rejected - already recording")
        return jsonify({"status": 1, "msg": "already recording"}), 400

    def stop_recording(self):
        """녹화 중지 핸들러"""
        logger.info(f"[/stop] Request received from {request.remote_addr}")

        if self.camera_manager.is_recording():
            elapsed = self.camera_manager.get_recording_duration()
            logger.info(f"[/stop] Stopping recording after {elapsed:.2f} seconds ({elapsed/60:.2f} minutes)")

            # 녹화 플래그만 False로 설정 (스레드에서 처리)
            self.camera_manager.recording = False
            time.sleep(1)

            logger.info(f"[/stop] Recording stopped, conversion will start")
            return jsonify({"status": 0, "msg": "stopped, converting..."}), 200

        logger.warning(f"[/stop] Request rejected - not recording")
        return jsonify({"status": 1, "msg": "not recording"}), 400

    def download_video(self):
        """MP4 변환된 파일 다운로드"""
        logger.info(f"[/download] Request received from {request.remote_addr}")

        if self.camera_manager.is_converting():
            logger.warning(f"[/download] Request rejected - video is still converting")
            return jsonify({"status": 1, "msg": "video is converting, please wait"}), 400

        video_path = self.camera_manager.video_path

        if os.path.exists(video_path):
            file_size = os.path.getsize(video_path)
            logger.info(f"[/download] Serving MP4 file: {file_size:,} bytes ({file_size/1024/1024:.2f} MB)")

            try:
                response = send_file(
                    video_path,
                    as_attachment=True,
                    download_name=f"camera_video.{self.camera_manager.video_format}",
                    max_age=0
                )
                logger.info(f"[/download] File sent successfully to {request.remote_addr}")
                return response
            except Exception as e:
                logger.error(f"[/download] Error sending file: {e}", exc_info=True)
                return jsonify({"status": 1, "msg": f"error sending file: {str(e)}"}), 500

        logger.warning(f"[/download] Request rejected - no video file exists")
        return jsonify({"status": 1, "msg": "no video"}), 400

    def download_raw_video(self):
        """H264 원본 파일 즉시 다운로드"""
        logger.info(f"[/download/raw] Request received from {request.remote_addr}")

        if self.camera_manager.is_recording():
            logger.warning(f"[/download/raw] Request rejected - still recording")
            return jsonify({"status": 1, "msg": "still recording"}), 400

        temp_path = self.camera_manager.temp_path

        if os.path.exists(temp_path):
            file_size = os.path.getsize(temp_path)
            logger.info(f"[/download/raw] Serving H264 file: {file_size:,} bytes ({file_size/1024/1024:.2f} MB)")

            try:
                response = send_file(
                    temp_path,
                    as_attachment=True,
                    download_name="camera_video.h264",
                    max_age=0
                )
                logger.info(f"[/download/raw] File sent successfully to {request.remote_addr}")
                return response
            except Exception as e:
                logger.error(f"[/download/raw] Error sending file: {e}", exc_info=True)
                return jsonify({"status": 1, "msg": f"error sending file: {str(e)}"}), 500

        logger.warning(f"[/download/raw] Request rejected - no raw video file exists")
        return jsonify({"status": 1, "msg": "no raw video"}), 400

    def get_config(self):
        """현재 설정 조회"""
        logger.info(f"[/getconfig] Request received from {request.remote_addr}")

        config = self.camera_manager.get_config()
        logger.info(f"[/getconfig] Returning config: {config}")

        return jsonify(config), 200

    def set_config(self):
        """설정 변경"""
        logger.info(f"[/setconfig] Request received from {request.remote_addr}")

        if self.camera_manager.is_recording():
            logger.warning(f"[/setconfig] Request rejected - recording in progress")
            return jsonify({"error": "stop recording first"}), 400

        data = request.get_json()
        logger.info(f"[/setconfig] Requested config: {data}")

        try:
            new_width = data.get('width')
            new_height = data.get('height')
            new_fps = data.get('fps')

            # 유효성 검사
            if new_width and new_height:
                ConfigValidator.validate_resolution(new_width, new_height)
            if new_fps:
                ConfigValidator.validate_fps(new_fps)

            # 설정 업데이트
            self.camera_manager.set_config(
                width=new_width,
                height=new_height,
                fps=new_fps
            )

            config = self.camera_manager.get_config()
            logger.info(f"[/setconfig] Config updated: {config['resolution']}@{config['fps']}fps")

            return jsonify({
                "status": "config updated",
                "new_config": f"{config['resolution']}@{config['fps']}fps"
            }), 200

        except ValueError as e:
            logger.warning(f"[/setconfig] Invalid config: {e}")
            return jsonify({"error": str(e)}), 400
        except Exception as e:
            logger.error(f"[/setconfig] Error: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    def get_status(self):
        """현재 상태 조회"""
        logger.info(f"[/status] Request received from {request.remote_addr}")

        if self.camera_manager.is_converting():
            logger.info(f"[/status] Current status: converting")
            return jsonify({"status": 0, "msg": "converting video"}), 200
        elif self.camera_manager.is_recording():
            elapsed = self.camera_manager.get_recording_duration()
            logger.info(f"[/status] Current status: recording ({elapsed:.1f}s)")
            return jsonify({
                "status": 0,
                "msg": "recording",
                "duration": f"{elapsed:.1f}s",
                "duration_seconds": round(elapsed, 1),
                "start_time": self.camera_manager.recording_start_time
            }), 200
        else:
            logger.info(f"[/status] Current status: idle")
            return jsonify({"status": 0, "msg": "idle"}), 200

    def test_camera(self):
        """카메라 테스트"""
        logger.info(f"[/test] Camera test request received from {request.remote_addr}")

        try:
            output_path = self.camera_manager.test_camera()
            logger.info(f"[/test] Test image captured successfully")
            return send_file(output_path, as_attachment=True)
        except Exception as e:
            logger.error(f"[/test] Camera test failed: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500
