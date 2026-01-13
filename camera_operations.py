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
import gc
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
        self.stream_lock = False  # 카메라 초기화 중 플래그

        # 기본 설정
        self.width = 1280
        self.height = 720
        self.fps = 30

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
        if height is not None:
            self.height = height
        if fps is not None:
            self.fps = fps

        logger.info(f"Config updated: {self.width}x{self.height}@{self.fps}fps")


    def start_recording_session(self):
        """녹화 시작"""
        if self.recording:
            raise ValueError("Already recording")

        if not os.path.exists(self.video_dir):
            os.mkdir(self.video_dir)
            logger.info(f"Created video directory: {self.video_dir}")

        logger.info(f"Initializing camera with config: {self.width}x{self.height}@{self.fps}fps")

        # 카메라가 없으면 생성, 있으면 재사용
        if self.camera is None:
            self.camera = Picamera2()
            logger.info("Created new Picamera2 instance for recording")
        else:
            logger.info("Reusing existing Picamera2 instance for recording")

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

    def start_recording_thread(self):
        """스레드에서 녹화를 시작하고 완료까지 관리"""
        import threading

        def record_video_thread():
            try:
                self.start_recording_session()

                # 녹화가 중지될 때까지 대기
                while self.is_recording():
                    time.sleep(0.1)

                # 녹화 종료 후 정리 및 변환
                self.finalize_recording()

            except Exception as e:
                logger.error(f"Video recording error: {e}", exc_info=True)
                self.cleanup()

        threading.Thread(target=record_video_thread, daemon=True).start()
        time.sleep(0.5)  # 카메라 초기화 대기

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
            self.camera.stop()  # 녹화 중지하되 인스턴스는 유지
            logger.info("Camera stopped (instance preserved for reuse)")
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
                self.camera.stop()
                self.camera.close()
                self.camera = None
                logger.info("Camera closed and released")
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
        """실시간 MJPEG 스트림 생성 (멀티 클라이언트 지원)"""
        logger.info("Starting live stream")

        try:
            # 카메라가 아직 없거나 초기화 중이 아니면 카메라 시작
            if self.stream_camera is None and not self.stream_lock:
                self.stream_lock = True
                try:
                    logger.info("Initializing stream camera")

                    # 스트리밍용 카메라 초기화
                    self.stream_camera = Picamera2()

                    # 비디오 설정 (색상 및 화질 개선)
                    config = self.stream_camera.create_video_configuration(
                        main={"size": (self.width, self.height), "format": "RGB888"},
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

                    logger.info(f"Live stream camera initialized ({self.width}x{self.height})")
                finally:
                    self.stream_lock = False
            else:
                # 카메라가 이미 있으면 초기화 대기
                wait_count = 0
                while self.stream_lock and wait_count < 50:  # 최대 5초 대기
                    time.sleep(0.1)
                    wait_count += 1

                if self.stream_camera is None:
                    logger.error("Failed to initialize camera within timeout")
                    return

                logger.info("Reusing existing stream camera")

            # 프레임 생성 루프
            frame_count = 0
            gc_interval = 300  # 300프레임마다 GC 실행 (30fps 기준 10초)
            total_buffer_size = 0  # 누적 버퍼 사용량
            buffer_log_interval = 900  # 900프레임마다 버퍼 통계 로깅 (30초)

            while self.streaming and self.stream_camera is not None:
                buffer = None  # 명시적 초기화
                try:
                    # 카메라 객체가 None이 아닌지 다시 확인
                    if self.stream_camera is None:
                        logger.warning("Stream camera became None during operation")
                        break

                    # JPEG로 직접 캡처 (Picamera2의 네이티브 방식)
                    buffer = io.BytesIO()
                    self.stream_camera.capture_file(buffer, format='jpeg')
                    frame_bytes = buffer.getvalue()

                    # 버퍼 크기 추적
                    buffer_size = len(frame_bytes)
                    total_buffer_size += buffer_size

                    buffer.close()  # 명시적 메모리 해제
                    buffer = None

                    # MJPEG 형식으로 전송
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

                    frame_count += 1

                    # 주기적 버퍼 통계 로깅
                    if frame_count % buffer_log_interval == 0:
                        avg_buffer_size = total_buffer_size / buffer_log_interval
                        logger.info(f"Buffer stats - Frames: {frame_count}, Avg size: {avg_buffer_size/1024:.1f}KB, Last: {buffer_size/1024:.1f}KB")
                        total_buffer_size = 0  # 통계 리셋

                    # 주기적 가비지 컬렉션 강제 실행
                    if frame_count % gc_interval == 0:
                        collected = gc.collect()
                        logger.debug(f"GC executed at frame {frame_count}, collected {collected} objects")

                    # 30분마다 메모리 상태 로깅
                    if frame_count % 54000 == 0:  # 30fps * 60s * 30m
                        import psutil
                        mem = psutil.virtual_memory()
                        logger.info(f"Memory usage: {mem.percent}% (Available: {mem.available / 1024 / 1024:.1f}MB, Used: {mem.used / 1024 / 1024:.1f}MB)")

                except GeneratorExit:
                    # 클라이언트 연결 종료
                    logger.info("Client disconnected from stream")
                    break
                except Exception as e:
                    logger.error(f"Frame capture error: {e}")
                    # 에러가 계속되면 중단
                    if not self.streaming or self.stream_camera is None:
                        break
                    time.sleep(0.1)  # 에러 시 잠시 대기
                    continue
                finally:
                    # 예외 발생 시에도 buffer 해제 보장
                    if buffer is not None:
                        try:
                            buffer.close()
                        except:
                            pass

        except RuntimeError as e:
            if "Device or resource busy" in str(e):
                logger.error("Camera is busy. Attempting to force cleanup...")
                # 강제 정리 시도
                self._force_cleanup_camera()
            else:
                logger.error(f"Stream error: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Stream error: {e}", exc_info=True)
        finally:
            logger.info("Stream generator finished for this client")

    def _force_cleanup_camera(self):
        """카메라 강제 정리"""
        try:
            # 모든 카메라 인스턴스 정리 시도
            if self.stream_camera:
                try:
                    self.stream_camera.stop()
                except:
                    pass
                try:
                    self.stream_camera.close()
                except:
                    pass
                self.stream_camera = None

            # 녹화 카메라도 확인
            if self.camera:
                try:
                    self.camera.stop()
                except:
                    pass
                try:
                    self.camera.close()
                except:
                    pass
                self.camera = None

            logger.info("Force cleanup completed")
            time.sleep(1)  # 리소스 해제 대기
        except Exception as e:
            logger.error(f"Force cleanup error: {e}")

    def stop_stream(self):
        """스트림 중지 (모든 클라이언트가 종료되면 카메라 정리)"""
        self.streaming = False

        if self.stream_camera:
            try:
                logger.info("Stopping stream camera")
                self.stream_camera.stop()
                self.stream_camera.close()
                logger.info("Stream camera closed successfully")
            except Exception as e:
                logger.error(f"Error stopping stream camera: {e}")
            finally:
                self.stream_camera = None
                self.stream_lock = False
                logger.info("Live stream stopped")

    def force_stop_stream(self):
        """스트림 강제 종료 (API 호출용)"""
        logger.info("Force stopping stream")
        self.streaming = False

        if self.stream_camera:
            try:
                self.stream_camera.stop()
                self.stream_camera.close()
            except Exception as e:
                logger.error(f"Error force stopping stream: {e}")
            finally:
                self.stream_camera = None
                self.stream_lock = False

        logger.info("Stream force stopped")

    def is_streaming(self):
        """스트리밍 중인지 확인"""
        return self.streaming
