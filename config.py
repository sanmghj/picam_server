"""
설정 관리 및 로깅 초기화 모듈
"""
import os
import logging
from logging.handlers import TimedRotatingFileHandler


# ========================================
# 카메라 기본 설정 상수 (C의 #define과 유사)
# ========================================

# 비디오 디렉토리 및 파일 형식
DEFAULT_VIDEO_DIR = "video"
DEFAULT_VIDEO_FORMAT = "mp4"

# 카메라 기본 설정
DEFAULT_WIDTH = 1280
DEFAULT_HEIGHT = 720
DEFAULT_FPS = 30

# 메모리 최적화 설정 (8GB RAM 기준)
GC_INTERVAL_RECORDING = 3000      # 녹화: 5분마다 GC (0.1초 * 3000)
GC_INTERVAL_STREAMING = 1800      # 스트리밍: 60초마다 GC (30fps * 60)
MEM_LOG_INTERVAL_RECORDING = 6000 # 녹화: 10분마다 메모리 로깅
MEM_LOG_INTERVAL_STREAMING = 54000 # 스트리밍: 30분마다 메모리 로깅
BUFFER_LOG_INTERVAL = 1800        # 60초마다 버퍼 통계 로깅

# 메모리 임계치 (퍼센트)
MEMORY_WARNING_THRESHOLD = 80     # 경고 레벨
MEMORY_CRITICAL_THRESHOLD = 90    # 위험 레벨


def setup_logging(log_dir="log"):
    """로깅 설정 초기화"""
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    log_filename = os.path.join(log_dir, "picam_server.log")

    # TimedRotatingFileHandler로 자정에 자동으로 새 파일 생성
    file_handler = TimedRotatingFileHandler(
        log_filename,
        when='midnight',
        interval=1,
        backupCount=365,
        encoding='utf-8'
    )
    file_handler.suffix = "%Y%m%d"

    console_handler = logging.StreamHandler()

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[file_handler, console_handler]
    )

    logger = logging.getLogger(__name__)
    logger.info("=== PiCam Server Started ===")
    logger.info(f"Log file: {log_filename}")

    return logger


class ConfigValidator:
    """설정 유효성 검사 클래스"""

    VALID_RESOLUTIONS = [(640, 480), (1280, 720), (1920, 1080)]
    VALID_FPS = [25, 30]

    @classmethod
    def validate_resolution(cls, width, height):
        """해상도 유효성 검사"""
        if (width, height) not in cls.VALID_RESOLUTIONS:
            raise ValueError(f"Invalid resolution. Valid options: {cls.VALID_RESOLUTIONS}")
        return True

    @classmethod
    def validate_fps(cls, fps):
        """FPS 유효성 검사"""
        if fps not in cls.VALID_FPS:
            raise ValueError(f"Invalid fps. Valid options: {cls.VALID_FPS}")
        return True

    @classmethod
    def validate_config(cls, width=None, height=None, fps=None):
        """전체 설정 유효성 검사"""
        if width is not None and height is not None:
            cls.validate_resolution(width, height)
        if fps is not None:
            cls.validate_fps(fps)
        return True
