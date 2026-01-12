"""
설정 관리 및 로깅 초기화 모듈
"""
import os
import logging
from logging.handlers import TimedRotatingFileHandler


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
