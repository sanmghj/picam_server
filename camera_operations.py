"""
카메라 녹화 및 비디오 변환 처리 모듈
"""
from picamera2 import Picamera2
from picamera2.encoders import H264Encoder, MJPEGEncoder
from libcamera import Transform
import os
import subprocess
import time
import logging
import io
from datetime import datetime

logger = logging.getLogger(__name__)


class CameraManager:
    """카메라 녹화 및 변환을 관리하는 클래스"""

    def __init__(self, video_dir="video"):
        self.video_dir = video_dir
        self.video_format = "mp4"
        self.video_path = f"{video_dir}/camera_video.{self.video_format}"
        self.temp_path = f"{video_dir}/camera_video.h264"

        self.camera = None
        self.recording = False
        self.converting = False
        self.recording_start_time = None

        # 스트리밍 관련
        self.streaming = False
        self.stream_camera = None

        # 기본 설정
        self.width = 1280
        self.height = 720
        self.fps = 30

        # 스트리밍 해상도 (기본값은 녹화 해상도와 동일)
        self.stream_width = 1280
        self.stream_height = 720

    def is_recording(self):
        """녹화 중인지 확인"""
        return self.recording

    def is_converting(self):
        """변환 중인지 확인"""
        return self.converting

    def get_recording_duration(self):
        """녹화 시간 반환"""
        if self.recording_start_time:
            return time.time() - self.recording_start_time
        return 0

    def set_config(self, width=None, height=None, fps=None):
        """카메라 설정 변경"""
        if self.recording:
            raise ValueError("Cannot change config while recording")

        if width is not None:
            self.width = width
            self.stream_width = width  # 스트리밍 해상도도 함께 변경
        if height is not None:
            self.height = height
            self.stream_height = height  # 스트리밍 해상도도 함께 변경
        if fps is not None:
            self.fps = fps

        logger.info(f"Config updated: {self.width}x{self.height}@{self.fps}fps (stream: {self.stream_width}x{self.stream_height})")


    def start_recording(self):
        """녹화 시작"""
        if self.recording:
            raise ValueError("Already recording")

        if not os.path.exists(self.video_dir):
            os.mkdir(self.video_dir)
            logger.info(f"Created video directory: {self.video_dir}")

        logger.info(f"Initializing camera with config: {self.width}x{self.height}@{self.fps}fps")

        self.camera = Picamera2()
        config = self.camera.create_video_configuration(
            main={"size": (self.width, self.height)},
            transform=Transform(rotation=180)
        )
        self.camera.configure(config)

        encoder = H264Encoder()
        self.camera.start()
        self.recording_start_time = time.time()
        self.camera.start_recording(encoder, self.temp_path)
        self.recording = True

        logger.info(f"Recording started at {datetime.fromtimestamp(self.recording_start_time).strftime('%Y-%m-%d %H:%M:%S')}")

    def request_stop(self):
        """녹화 중지 요청 (플래그만 설정)"""
        if not self.recording:
            raise ValueError("Not recording")

        logger.info("Recording stop requested")
        self.recording = False

    def finalize_recording(self):
        """녹화 종료 후 정리 및 변환"""
        if self.recording:
            logger.warning("finalize_recording called while still recording")
            return

        if self.recording_start_time is not None:
            recording_duration = time.time() - self.recording_start_time
            logger.info(f"Recording stopped. Duration: {recording_duration:.2f} seconds ({recording_duration/60:.2f} minutes)")
        else:
            logger.warning("Recording stopped but start time was not recorded")

        try:
            self.camera.stop_recording()
            self.camera.close()
        except Exception as e:
            logger.error(f"Error stopping camera: {e}")

        # H264 파일 크기 확인
        if os.path.exists(self.temp_path):
            h264_size = os.path.getsize(self.temp_path)
            logger.info(f"H264 file size: {h264_size:,} bytes ({h264_size/1024/1024:.2f} MB)")
        else:
            logger.error(f"H264 file not found: {self.temp_path}")
            return

        # 변환 시작
        self._convert_video()

    def _convert_video(self):
        """H264를 MP4로 변환"""
        self.converting = True
        conversion_start = time.time()
        logger.info("Starting video conversion (H264 → MP4)...")

        result = subprocess.run(
            [
                'ffmpeg',
                '-i',
                self.temp_path,
                '-c:v',
                'copy',
                self.video_path,
                '-y'
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        conversion_duration = time.time() - conversion_start

        if result.returncode == 0:
            logger.info(f"Video conversion completed successfully in {conversion_duration:.2f} seconds")

            # 파일 크기 안정화 확인
            if os.path.exists(self.video_path):
                self._wait_for_file_stability()
            else:
                logger.error(f"MP4 file not found after conversion: {self.video_path}")

            self.converting = False
            logger.info("File is ready for download")
        else:
            self.converting = False
            logger.error(f"Video conversion failed with return code {result.returncode}")
            logger.error(f"FFmpeg stderr: {result.stderr}")

    def _wait_for_file_stability(self):
        """파일 쓰기 완료를 확인"""
        logger.info("Waiting for file system to stabilize...")
        stable_size = None
        stable_count = 0
        max_checks = 20
        check_count = 0

        while check_count < max_checks:
            current_size = os.path.getsize(self.video_path)

            if stable_size == current_size:
                stable_count += 1
                if stable_count >= 3:
                    mp4_size = current_size
                    logger.info(f"MP4 file size stabilized: {mp4_size:,} bytes ({mp4_size/1024/1024:.2f} MB)")
                    break
            else:
                stable_size = current_size
                stable_count = 1

            check_count += 1
            time.sleep(0.5)

        if check_count >= max_checks:
            logger.warning(f"File stabilization timeout after {max_checks * 0.5}s, proceeding anyway")
            mp4_size = os.path.getsize(self.video_path)
            logger.info(f"MP4 file size: {mp4_size:,} bytes ({mp4_size/1024/1024:.2f} MB)")

    def cleanup(self):
        """카메라 리소스 정리"""
        self.recording = False
        self.converting = False
        self.recording_start_time = None

        if self.camera:
            try:
                self.camera.close()
                logger.info("Camera closed")
            except Exception as e:
                logger.error(f"Error closing camera: {e}")

    def test_camera(self, output_path="test.jpg"):
        """카메라 테스트 (정지 이미지 캡처)"""
        logger.info("Starting camera test")

        picam2 = Picamera2()
        config = picam2.create_still_configuration()
        picam2.configure(config)
        picam2.start()
        time.sleep(2)
        picam2.capture_file(output_path)
        picam2.stop()
        picam2.close()

        logger.info(f"Test image captured successfully: {output_path}")
        return output_path

    def generate_stream(self):
        """실시간 MJPEG 스트림 생성"""
        logger.info("Starting live stream")

        try:
            # 스트리밍용 카메라 초기화
            self.stream_camera = Picamera2()

            # 비디오 설정 (색상 및 화질 개선)
            config = self.stream_camera.create_video_configuration(
                main={"size": (self.stream_width, self.stream_height), "format": "RGB888"},
                transform=Transform(rotation=180)
            )
            self.stream_camera.configure(config)

            # 자동 화이트 밸런스 및 노출 설정
            self.stream_camera.set_controls({
                "AwbEnable": True,  # 자동 화이트 밸런스
                "AeEnable": True,   # 자동 노출
            })

            self.stream_camera.start()
            time.sleep(2)  # 카메라 안정화 대기
            self.streaming = True

            logger.info(f"Live stream started ({self.stream_width}x{self.stream_height})")

            # 프레임 생성 루프
            while self.streaming:
                try:
                    # JPEG로 직접 캡처 (Picamera2의 네이티브 방식)
                    buffer = io.BytesIO()
                    self.stream_camera.capture_file(buffer, format='jpeg')
                    frame_bytes = buffer.getvalue()

                    # MJPEG 형식으로 전송
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

                except Exception as e:
                    logger.error(f"Frame capture error: {e}")
                    continue

        except Exception as e:
            logger.error(f"Stream error: {e}", exc_info=True)
        finally:
            self.stop_stream()

    def stop_stream(self):
        """스트림 중지"""
        if self.stream_camera:
            try:
                self.streaming = False
                self.stream_camera.stop()
                self.stream_camera.close()
                self.stream_camera = None
                logger.info("Live stream stopped")
            except Exception as e:
                logger.error(f"Error stopping stream: {e}")

    def is_streaming(self):
        """스트리밍 중인지 확인"""
        return self.streaming
