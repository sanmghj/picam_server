# Raspberry Pi Camera Flask API Server

라즈베리파이 카메라를 사용한 원격 비디오 녹화 및 제어 API 서버

## 시스템 요구사항

- Raspberry Pi (Camera Module 지원 모델)
- Raspberry Pi Camera Module
- Debian 13 이상 (카메라가 자동으로 활성화됨)

## 라즈베리파이 준비

### 1. 카메라 연결 확인

Debian 13부터는 카메라가 자동으로 활성화되므로 별도의 설정이 필요 없습니다.

### 2. 카메라 동작 테스트

```bash
python3 picam_test.py
```

## 패키지 설치

```bash
sudo apt update && sudo apt install -y \
  python3-picamera2 \
  python3-libcamera \
  python3-flask \
  ffmpeg \
  libcamera-apps
```

## 서버 실행

### 개발 모드

```bash
python3 main.py
```

### systemd 데몬으로 등록

1. 서비스 파일을 시스템 디렉토리에 복사:

```bash
sudo cp service/PicamServer.service /etc/systemd/system/
sudo chmod 644 /etc/systemd/system/PicamServer.service
```

2. 서비스 활성화 및 시작:

```bash
sudo systemctl daemon-reload
sudo systemctl enable PicamServer.service
sudo systemctl start PicamServer.service
```

3. 서비스 상태 확인:

```bash
sudo systemctl status PicamServer.service
```

## API 사용법

### IP 주소 확인

```bash
hostname -I
```

### API 테스트 예제

```bash
# 라즈베리파이 IP 주소 설정
IP=<YOUR_RASPBERRY_PI_IP>

# 1. 카메라 테스트 (정지 이미지 촬영)
curl http://$IP:5000/test -o test.jpg

# 2. 현재 설정 확인
curl http://$IP:5000/getconfig

# 3. 비디오 설정 변경
curl -X POST http://$IP:5000/setconfig \
  -H "Content-Type: application/json" \
  -d '{"width":640,"height":480,"fps":30}'

# 4. 녹화 시작
curl -X POST http://$IP:5000/start

# 5. 녹화 중지
curl -X POST http://$IP:5000/stop

# 6. 비디오 다운로드
curl http://$IP:5000/download -o camera_video.mp4
```

## API 명세서

### 1. GET `/test`

카메라 테스트용 정지 이미지 촬영

**요청:**
```
GET /test
```

**응답:**
- 성공: `test.jpg` 파일 다운로드
- 실패: `{"error": "error message"}`

---

### 2. GET `/getconfig`

현재 비디오 설정 조회

**요청:**
```
GET /getconfig
```

**응답:**
```json
{
  "format": "mp4",
  "resolution": "640x480",
  "fps": 30
}
```

---

### 3. POST `/setconfig`

비디오 설정 변경 (녹화 중에는 변경 불가)

**요청:**
```
POST /setconfig
Content-Type: application/json

{
  "width": 640,
  "height": 480,
  "fps": 30
}
```

**응답:**
```json
{
  "status": "config updated",
  "new_config": "640x480@30fps"
}
```

**에러:**
```json
{
  "error": "stop recording first"
}
```

---

### 4. POST `/start`

비디오 녹화 시작

**요청:**
```
POST /start
```

**응답:**
```json
{
  "status": 0,
  "msg": {
    "size": "640x480",
    "fps": "30"
  }
}
```

**에러:**
```json
{
  "status": 1,
  "msg": "already recording"
}
```

---

### 5. POST `/stop`

비디오 녹화 중지

**요청:**
```
POST /stop
```

**응답:**
```json
{
  "status": 0,
  "msg": "stopped"
}
```

**에러:**
```json
{
  "status": 1,
  "msg": "not recording"
}
```

---

### 6. GET `/download`

녹화된 비디오 다운로드

**요청:**
```
GET /download
```

**응답:**
- 성공: `camera_video.mp4` 파일 다운로드
- 실패: `{"status": 1, "msg": "no video"}`

---

### 7. GET `/status`

서버 동작 상태 확인

**요청:**
```
GET /status
```

**응답:**
- 성공: `{"msg": "idle","status": 0}`,
       `{"msg": "converting video","status": 0}`,
       `{"msg": "recording","status": 0}`
- 실패: `응답없음`

---

### 8. GET `/download/raw`

녹화된 비디오 다운로드

**요청:**
```
GET /download/raw
```

**응답:**
- 성공: `camera_video.h264` 파일 다운로드
- 실패: `{"status": 1, "msg": "no raw video"}`

---
