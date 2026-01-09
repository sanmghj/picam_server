"""
PiCam Server API 테스트 프로그램 (리팩토링 버전)
여러 테스트 케이스를 확인할 수 있는 테스트 도구
"""

import os
import requests
import time
import json
from datetime import datetime
from typing import Dict, Any, List, Tuple
from dataclasses import dataclass, asdict


@dataclass
class TestConfig:
    """테스트 설정"""
    width: int = 1280
    height: int = 720
    fps: int = 30

    @property
    def resolution_label(self) -> str:
        """해상도 라벨 반환"""
        resolution_map = {
            (640, 480): "480p",
            (1280, 720): "720p",
            (1920, 1080): "1080p"
        }
        return resolution_map.get((self.width, self.height), f"{self.width}x{self.height}")


@dataclass
class TestResult:
    """테스트 결과"""
    duration_min: int
    resolution: str
    width: int
    height: int
    fps: int
    total_time_sec: float
    record_time_sec: float
    convert_time_sec: float
    download_time_sec: float
    file_size_bytes: int
    success: bool

    def to_dict(self) -> Dict:
        """딕셔너리로 변환"""
        return {
            "duration_min": self.duration_min,
            "resolution": self.resolution,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "total_time_sec": round(self.total_time_sec, 2),
            "record_time_sec": round(self.record_time_sec, 2),
            "convert_time_sec": round(self.convert_time_sec, 2),
            "download_time_sec": round(self.download_time_sec, 2),
            "file_size_bytes": self.file_size_bytes,
            "success": self.success
        }


class PiCamTester:
    """PiCam Server API 테스트 클래스"""

    # 상수 정의
    DEFAULT_TIMEOUT = 5
    DOWNLOAD_TIMEOUT = 30
    MAX_CONVERT_WAIT = 300
    STATUS_CHECK_INTERVAL = 10
    CONVERT_CHECK_INTERVAL = 5
    FILE_STABILIZE_WAIT = 2

    def __init__(self, server_ip: str, port: int = 5000):
        self.base_url = f"http://{server_ip}:{port}"
        self.server_ip = server_ip
        self.port = port
        self.test_results = []

        # 경로 설정
        self._setup_paths()

        # 로그 파일 초기화
        self._init_log_file()

    def _setup_paths(self):
        """경로 설정 초기화"""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.project_root = os.path.dirname(script_dir)
        self.log_dir = os.path.join(self.project_root, "log")
        self.temp_dir = os.path.join(self.project_root, "temp")

        # 디렉토리 생성
        os.makedirs(self.log_dir, exist_ok=True)
        os.makedirs(self.temp_dir, exist_ok=True)

    def _init_log_file(self):
        """로그 파일 초기화"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file_path = os.path.join(self.log_dir, f"test_{self.server_ip}_{timestamp}.log")
        self.log_file = open(self.log_file_path, 'w', encoding='utf-8')
        self._log_to_file_only(f"테스트 프로그램 시작 - 서버: {self.server_ip}:{self.port}")
        self._log_to_file_only(f"로그 파일: {self.log_file_path}")
        self._log_to_file_only("=" * 60)

    def __del__(self):
        """소멸자 - 로그 파일 닫기"""
        if hasattr(self, 'log_file') and self.log_file and not self.log_file.closed:
            self._log_to_file_only("=" * 60)
            self._log_to_file_only("테스트 프로그램 종료")
            self.log_file.close()

    # ========== 유틸리티 메서드 ==========

    def _log_to_file_only(self, message: str):
        """파일에만 로그 기록 (내부용)"""
        if hasattr(self, 'log_file') and self.log_file and not self.log_file.closed:
            self.log_file.write(f"{message}\n")
            self.log_file.flush()

    def log(self, message: str, level: str = "INFO"):
        """로그 메시지 출력 (콘솔 + 파일)"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_message = f"[{timestamp}] [{level}] {message}"

        # 콘솔 출력
        print(log_message)

        # 파일 출력
        self._log_to_file_only(log_message)

    def print_separator(self, char: str = "=", length: int = 60):
        """구분선 출력"""
        self.log(char * length)

    def format_file_size(self, size_bytes: int) -> str:
        """파일 크기를 읽기 쉬운 형식으로 변환"""
        return f"{size_bytes:,} bytes ({size_bytes/1024/1024:.2f} MB)"

    def get_temp_filename(self, duration_min: int, resolution: str) -> str:
        """임시 파일명 생성"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return os.path.join(self.temp_dir, f"test_{self.server_ip}_{duration_min}min_{resolution}_{timestamp}.mp4")

    def ensure_directory(self, path: str):
        """디렉토리 생성 (존재하지 않으면)"""
        os.makedirs(path, exist_ok=True)

    # ========== API 호출 메서드 ==========

    def call_api(self, endpoint: str, method: str = "GET", data: Dict = None,
                 timeout: int = None) -> Dict[str, Any]:
        """API 호출 헬퍼 함수"""
        url = f"{self.base_url}{endpoint}"
        timeout = timeout or self.DEFAULT_TIMEOUT

        try:
            if method == "GET":
                response = requests.get(url, timeout=timeout)
            elif method == "POST":
                response = requests.post(url, json=data, timeout=timeout)
            else:
                raise ValueError(f"Unsupported method: {method}")

            result = {
                "success": True,
                "status_code": response.status_code,
                "data": response.json() if response.headers.get('content-type') == 'application/json' else response.text
            }
            self.log(f"{method} {endpoint} -> {response.status_code}: {result['data']}")
            return result
        except requests.exceptions.RequestException as e:
            result = {
                "success": False,
                "error": str(e)
            }
            self.log(f"{method} {endpoint} -> ERROR: {e}", "ERROR")
            return result

    def check_status(self) -> Dict[str, Any]:
        """상태 확인 (/status)"""
        return self.call_api("/status", "GET")

    def start_recording(self) -> Dict[str, Any]:
        """녹화 시작 (/start)"""
        return self.call_api("/start", "POST")

    def stop_recording(self) -> Dict[str, Any]:
        """녹화 중지 (/stop)"""
        return self.call_api("/stop", "POST")

    def get_config(self) -> Dict[str, Any]:
        """설정 조회 (/getconfig)"""
        return self.call_api("/getconfig", "GET")

    def set_config(self, width: int, height: int, fps: int = 30) -> Dict[str, Any]:
        """설정 변경 (/setconfig)"""
        return self.call_api("/setconfig", "POST", {
            "width": width,
            "height": height,
            "fps": fps
        })

    def download_video(self, save_path: str = None) -> Dict[str, Any]:
        """비디오 다운로드 (/download)"""
        url = f"{self.base_url}/download"
        try:
            response = requests.get(url, timeout=self.DOWNLOAD_TIMEOUT)
            if response.status_code == 200:
                file_size = len(response.content)
                if save_path:
                    with open(save_path, 'wb') as f:
                        f.write(response.content)
                    self.log(f"다운로드 완료: {self.format_file_size(file_size)}")
                    return {"success": True, "file_size": file_size, "path": save_path}
                return {"success": True, "file_size": file_size}
            else:
                data = response.json() if response.headers.get('content-type') == 'application/json' else response.text
                self.log(f"다운로드 실패: {data}", "ERROR")
                return {"success": False, "error": data}
        except Exception as e:
            self.log(f"다운로드 에러: {e}", "ERROR")
            return {"success": False, "error": str(e)}

    # ========== 상태 관리 메서드 ==========

    def wait_for_idle_status(self, max_wait: int = None) -> Tuple[bool, float]:
        """idle 상태가 될 때까지 대기"""
        max_wait = max_wait or self.MAX_CONVERT_WAIT
        start_time = time.time()
        waited = 0

        while waited < max_wait:
            status = self.check_status()
            status_msg = status.get("data", {}).get("msg", "unknown")

            if status_msg == "idle":
                elapsed = time.time() - start_time
                return True, elapsed
            elif status_msg == "converting video":
                self.log(f"변환 중... ({waited}초 경과)")
            else:
                self.log(f"현재 상태: {status_msg}")

            time.sleep(self.CONVERT_CHECK_INTERVAL)
            waited += self.CONVERT_CHECK_INTERVAL

        return False, time.time() - start_time

    def ensure_idle_state(self) -> bool:
        """서버가 idle 상태인지 확인하고, 아니면 idle로 만듦"""
        status_result = self.check_status()
        status_msg = status_result.get("data", {}).get("msg", "unknown")

        if status_msg == "idle":
            return True

        self.log(f"서버가 idle 상태가 아닙니다 (현재: {status_msg})", "WARN")

        # converting 상태인 경우 idle이 될 때까지 대기
        if status_msg == "converting video":
            self.log("변환 완료 대기 중...", "WARN")
            success, elapsed = self.wait_for_idle_status(max_wait=self.MAX_CONVERT_WAIT)
            if success:
                self.log(f"변환 완료 ({elapsed:.1f}초 소요)", "SUCCESS")
                return True
            else:
                self.log("변환 대기 시간 초과", "ERROR")
                return False

        # recording 상태인 경우 중지 시도
        if status_msg == "recording":
            self.log("녹화 중지 시도...", "WARN")
            self.stop_recording()
            time.sleep(3)

            # 중지 후 idle 대기
            success, elapsed = self.wait_for_idle_status(max_wait=60)
            if success:
                self.log(f"녹화 중지 및 변환 완료 ({elapsed:.1f}초 소요)", "SUCCESS")
                return True
            else:
                self.log("중지 후 변환 대기 시간 초과", "ERROR")
                return False

        return False

    def monitor_recording_progress(self, duration_min: int):
        """녹화 진행 상황 모니터링"""
        target_duration = duration_min * 60
        elapsed = 0

        while elapsed < target_duration:
            sleep_time = min(self.STATUS_CHECK_INTERVAL, target_duration - elapsed)
            time.sleep(sleep_time)
            elapsed += sleep_time

            status = self.check_status()
            actual_duration = status.get("data", {}).get("duration_seconds", 0)
            progress = (elapsed / target_duration) * 100
            remaining = target_duration - elapsed

            self.log(
                f"진행: {progress:.1f}% | 경과: {elapsed}s / {target_duration}s | "
                f"실제 녹화: {actual_duration:.1f}s | 남은 시간: {remaining}s"
            )

    # ========== 테스트 실행 메서드 ==========

    def _run_single_recording_test(self, duration_min: int, config: TestConfig) -> TestResult:
        """단일 녹화 테스트 실행 (내부 메서드)"""
        self.print_separator()
        self.log(f"녹화 시간 {duration_min}분 테스트 시작")
        self.print_separator()

        test_start_time = time.time()

        # 1. 설정 변경
        self.log(f"\n[Step 1] 해상도 설정: {config.width}x{config.height}@{config.fps}fps")
        if not self.set_config(config.width, config.height, config.fps).get("success"):
            raise Exception("설정 변경 실패")
        time.sleep(1)

        # 2. 초기 상태 확인 및 idle로 변경
        self.log("\n[Step 2] 초기 상태 확인 및 대기")
        if not self.ensure_idle_state():
            raise Exception("서버를 idle 상태로 만들 수 없습니다")

        # idle 상태 재확인
        final_status = self.check_status()
        final_msg = final_status.get("data", {}).get("msg", "unknown")
        if final_msg != "idle":
            raise Exception(f"서버가 여전히 idle 상태가 아닙니다 (현재: {final_msg})")

        self.log("서버가 idle 상태로 준비되었습니다", "SUCCESS")

        # 3. 녹화 시작
        self.log(f"\n[Step 3] 녹화 시작 ({duration_min}분)")
        record_start_time = time.time()
        start_result = self.start_recording()

        if start_result.get("status_code") != 200:
            raise Exception("녹화 시작 실패")

        self.log(f"녹화 시작 성공, {duration_min}분 동안 녹화합니다...", "SUCCESS")

        # 녹화가 실제로 시작되었는지 확인 (2초 후)
        time.sleep(2)
        verify_status = self.check_status()
        verify_msg = verify_status.get("data", {}).get("msg", "unknown")
        if verify_msg != "recording":
            raise Exception(f"녹화가 시작되지 않았습니다 (현재 상태: {verify_msg})")

        self.log("녹화 진행 중 확인됨", "SUCCESS")

        # 4. 녹화 진행 모니터링
        self.log(f"\n[Step 4] 녹화 진행 중 (목표: {duration_min * 60}초)")
        self.monitor_recording_progress(duration_min)

        record_duration = time.time() - record_start_time
        self.log(f"\n녹화 완료 (실제 시간: {record_duration:.1f}초)", "SUCCESS")

        # 5. 녹화 중지
        self.log("\n[Step 5] 녹화 중지")
        if self.stop_recording().get("status_code") != 200:
            raise Exception("녹화 중지 실패")

        # 6. 변환 대기
        self.log("\n[Step 6] 비디오 변환 대기...")
        convert_success, convert_duration = self.wait_for_idle_status()

        if not convert_success:
            raise Exception("변환 대기 시간 초과")

        self.log(f"변환 완료 (소요 시간: {convert_duration:.1f}초)", "SUCCESS")

        # 파일 안정화 대기
        self.log(f"파일 안정화 대기 ({self.FILE_STABILIZE_WAIT}초)...")
        time.sleep(self.FILE_STABILIZE_WAIT)

        # 7. 다운로드
        self.log("\n[Step 7] 비디오 다운로드")
        download_start_time = time.time()

        temp_file = self.get_temp_filename(duration_min, config.resolution_label)

        download_result = self.download_video(temp_file)
        download_duration = time.time() - download_start_time

        file_size = 0
        if download_result.get("success"):
            file_size = download_result.get("file_size", 0)
            self.log(
                f"다운로드 완료: {self.format_file_size(file_size)} in {download_duration:.1f}s",
                "SUCCESS"
            )

            # 다운로드 후 파일 삭제
            if os.path.exists(temp_file):
                os.remove(temp_file)
                self.log(f"임시 파일 삭제: {temp_file}")
        else:
            self.log(f"다운로드 실패: {download_result.get('error')}", "ERROR")

        # 8. 결과 생성
        total_time = time.time() - test_start_time

        return TestResult(
            duration_min=duration_min,
            resolution=config.resolution_label,
            width=config.width,
            height=config.height,
            fps=config.fps,
            total_time_sec=total_time,
            record_time_sec=record_duration,
            convert_time_sec=convert_duration,
            download_time_sec=download_duration,
            file_size_bytes=file_size,
            success=download_result.get("success", False)
        )

    def _print_test_summary(self, result: TestResult):
        """테스트 결과 요약 출력"""
        self.print_separator()
        self.log(f"{result.duration_min}분 테스트 완료")
        self.print_separator()
        self.log(f"총 소요 시간: {result.total_time_sec:.1f}초 ({result.total_time_sec/60:.1f}분)")
        self.log(f"녹화 시간: {result.record_time_sec:.1f}초")
        self.log(f"변환 시간: {result.convert_time_sec:.1f}초")
        self.log(f"다운로드 시간: {result.download_time_sec:.1f}초")
        self.log(f"파일 크기: {self.format_file_size(result.file_size_bytes)}")

    def _save_results_to_json(self, results: List[TestResult]):
        """테스트 결과를 JSON 파일로 저장"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_file = os.path.join(self.log_dir, f"picamtest_python_{self.server_ip}_{timestamp}.json")

        results_dict = [r.to_dict() for r in results]

        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(results_dict, f, indent=2, ensure_ascii=False)

        self.log(f"\n테스트 결과가 {json_file}에 저장되었습니다.")
        self.log(f"테스트 로그가 {self.log_file_path}에 저장되었습니다.")

    # ========== 테스트 시나리오 메서드 ==========

    def test_already_recording_bug(self):
        """
        테스트 시나리오: Already Recording 버그 재현

        시나리오:
        1. 상태확인 → idle
        2. 녹화 시작 요청 → 성공
        3. 상태확인 → recording
        4. 녹화 시작 요청 → "already recording" 에러 (정상)
        5. 상태확인 → recording (여전히)
        6. 녹화 시작 요청 → 버그: 녹화가 다시 시작될 수 있음 (비정상)
        """
        self.print_separator()
        self.log("테스트 시작: Already Recording 버그 재현")
        self.print_separator()

        results = []

        # Step 1-6: 테스트 단계 실행
        steps = [
            ("Step 1", "초기 상태 확인", lambda: self.check_status()),
            ("Step 2", "첫 번째 녹화 시작 요청", lambda: self.start_recording()),
            ("Step 3", "녹화 중 상태 확인", lambda: self.check_status()),
            ("Step 4", "두 번째 녹화 시작 시도", lambda: self.start_recording()),
            ("Step 5", "상태 재확인", lambda: self.check_status()),
            ("Step 6", "세 번째 녹화 시작 시도", lambda: self.start_recording()),
        ]

        step_results = []
        for step_num, step_desc, step_func in steps:
            self.log(f"\n[{step_num}] {step_desc}")
            result = step_func()
            step_results.append(result)
            results.append((step_desc, result))

            # Step 2 검증
            if step_num == "Step 2":
                if result.get("status_code") == 200:
                    self.log("✓ 첫 번째 녹화 시작 성공 (예상대로)", "SUCCESS")
                else:
                    self.log("✗ 첫 번째 녹화 시작 실패 (예상과 다름)", "FAIL")
                time.sleep(2)
            # Step 3 검증
            elif step_num == "Step 3":
                is_recording = result.get("data", {}).get("msg") == "recording"
                if is_recording:
                    self.log("✓ 녹화 중 상태 확인됨 (예상대로)", "SUCCESS")
                else:
                    self.log("✗ 녹화 중이 아님 (예상과 다름)", "FAIL")
            # Step 4, 6 검증
            elif step_num in ["Step 4", "Step 6"]:
                is_already_recording_error = (
                    result.get("status_code") == 400 and
                    "already recording" in str(result.get("data", {})).lower()
                )
                if is_already_recording_error:
                    self.log("✓ 'already recording' 에러 발생 (예상대로)", "SUCCESS")
                elif result.get("status_code") == 200 and step_num == "Step 6":
                    self.log("✗✗✗ 버그 발견! 세 번째 시도에서 녹화가 시작됨 (비정상)", "BUG")
                else:
                    self.log("✗ 예상과 다른 응답 (버그 가능성)", "FAIL")

            time.sleep(1)

        # 최종 상태 확인
        self.log("\n[Step 7] 최종 상태 확인")
        final_status = self.check_status()
        results.append(("최종 상태 확인", final_status))

        # 테스트 정리: 녹화 중지
        self.log("\n[Cleanup] 녹화 중지 (테스트 정리)")
        self.stop_recording()
        time.sleep(2)

        # 결과 요약
        self.print_separator()
        self.log("테스트 결과 요약")
        self.print_separator()
        for step_name, result in results:
            status = "SUCCESS" if result.get("success") else "FAIL"
            self.log(f"{step_name}: {status} (HTTP {result.get('status_code', 'N/A')})")

        return results

    def test_basic_workflow(self):
        """기본 워크플로우 테스트"""
        self.print_separator()
        self.log("테스트 시작: 기본 워크플로우")
        self.print_separator()

        workflow = [
            ("설정 조회", lambda: self.get_config()),
            ("초기 상태 확인", lambda: self.check_status()),
            ("녹화 시작", lambda: self.start_recording()),
            ("녹화 중 상태 확인", lambda: (time.sleep(3), self.check_status())[1]),
            ("녹화 중지", lambda: (time.sleep(2), self.stop_recording())[1]),
            ("최종 상태 확인", lambda: self.check_status()),
        ]

        for test_name, test_func in workflow:
            self.log(f"\n[Test] {test_name}")
            test_func()
            time.sleep(1)

        self.log("\n기본 워크플로우 테스트 완료")

    def test_picamtest_sh_scenario(self):
        """
        picamtest.sh 시나리오 테스트
        사전 정의된 시간(10, 30, 60분)과 해상도(720p)로 테스트 진행
        """
        self.print_separator()
        self.log("테스트 시작: picamtest.sh 시나리오")
        self.print_separator()

        # picamtest.sh의 설정값
        durations = [10, 30, 60]  # 분 단위
        config = TestConfig(width=1280, height=720, fps=30)

        self.log(f"\n테스트 설정: {config.resolution_label} ({config.width}x{config.height}@{config.fps}fps)")
        self.log(f"테스트 시간: {durations} 분")

        # 사용자에게 테스트 시간 선택하도록 함
        print("\n테스트할 녹화 시간을 선택하세요:")
        for i, dur in enumerate(durations, 1):
            print(f"{i}. {dur}분")
        print("0. 모든 시간 테스트 (순차 실행)")

        choice = input("\n선택하세요: ").strip()

        selected_durations = []
        if choice == "0":
            selected_durations = durations
        elif choice.isdigit() and 1 <= int(choice) <= len(durations):
            selected_durations = [durations[int(choice) - 1]]
        else:
            self.log("잘못된 선택입니다.", "ERROR")
            return

        results = []

        for duration_min in selected_durations:
            try:
                result = self._run_single_recording_test(duration_min, config)
                results.append(result)
                self._print_test_summary(result)

                # 다음 테스트 전 대기
                if duration_min != selected_durations[-1]:
                    self.log("\n다음 테스트까지 5초 대기...")
                    time.sleep(5)

            except Exception as e:
                self.log(f"테스트 실패: {e}", "ERROR")
                continue

        # 전체 결과 요약
        if results:
            self.print_separator()
            self.log("전체 테스트 결과 요약")
            self.print_separator()

            for i, result in enumerate(results, 1):
                self.log(f"\n테스트 {i}: {result.duration_min}분")
                self.log(f"  - 총 시간: {result.total_time_sec}초")
                self.log(f"  - 파일 크기: {self.format_file_size(result.file_size_bytes)}")
                self.log(f"  - 성공 여부: {'✓' if result.success else '✗'}")

            self._save_results_to_json(results)


def main():
    """메인 함수"""
    print("\n")
    print("=" * 60)
    print("PiCam Server API 테스트 프로그램")
    print("=" * 60)

    # 서버 IP 입력
    server_ip = input("\n라즈베리파이 IP 주소를 입력하세요 (기본값: 192.168.1.50): ").strip()
    if not server_ip:
        server_ip = "192.168.1.50"

    # 테스트 객체 생성
    tester = PiCamTester(server_ip)
    print(f"\n로그 파일: {tester.log_file_path}")

    # 테스트 메뉴
    while True:
        print("\n" + "=" * 60)
        print("테스트 메뉴")
        print("=" * 60)
        print("1. Already Recording 버그 테스트")
        print("2. 기본 워크플로우 테스트")
        print("3. picamtest.sh 시나리오 테스트 (10/30/60분)")
        print("4. 상태 확인만")
        print("5. 서버 IP 변경")
        print("0. 종료")
        print("=" * 60)

        choice = input("\n선택하세요: ").strip()

        if choice == "1":
            tester.test_already_recording_bug()
        elif choice == "2":
            tester.test_basic_workflow()
        elif choice == "3":
            tester.test_picamtest_sh_scenario()
        elif choice == "4":
            tester.check_status()
        elif choice == "5":
            server_ip = input("새로운 IP 주소를 입력하세요: ").strip()
            # 기존 tester 정리
            if hasattr(tester, 'log_file') and tester.log_file and not tester.log_file.closed:
                tester.log("서버 IP 변경으로 인한 테스터 종료")
                tester.log_file.close()
            # 새 tester 생성
            tester = PiCamTester(server_ip)
            print(f"서버 IP가 {server_ip}로 변경되었습니다.")
        elif choice == "0":
            print("\n테스트 프로그램을 종료합니다.")
            # 로그 파일 정리
            if hasattr(tester, 'log_file') and tester.log_file and not tester.log_file.closed:
                tester._log_to_file_only("=" * 60)
                tester._log_to_file_only("테스트 프로그램 종료")
                tester.log_file.close()
            break
        else:
            print("올바른 번호를 선택하세요.")


if __name__ == "__main__":
    main()
