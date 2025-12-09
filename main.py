from flask import Flask, send_file, jsonify, request
from picamera2 import Picamera2
from picamera2.encoders import H264Encoder
from picamera2.outputs import FfmpegOutput
import os
import subprocess
import threading
import time

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

def record_video():
    global camera, recording
    try:
        if not os.path.exists(VIDEO_DIR):
            os.mkdir(VIDEO_DIR)

        camera = Picamera2()
        config = camera.create_video_configuration(
            main={"size": (VIDEO_WIDTH, VIDEO_HEIGHT)}
        )
        camera.configure(config)

        encoder = H264Encoder()
        camera.start()
        camera.start_recording(encoder, TEMP_PATH)
        recording = True

        while recording:
            time.sleep(0.1)

        camera.stop_recording()
        camera.close()

        subprocess.run(
            [
                'ffmpeg',
                '-i',
                TEMP_PATH,
                '-c:v',
                'copy',
                VIDEO_PATH,
                '-y'
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        if os.path.exists(TEMP_PATH):
            os.remove(TEMP_PATH)

    except Exception as e:
        print(f"video recording error: {e}")
        recording = False
    finally:
        recording = False
        if camera:
            try:
                camera.close()
            except:
                pass

@app.route('/start', methods=['POST'])
def start_recording():
    global recording
    if not recording:
        recording = True  # 먼저 플래그 설정
        threading.Thread(target=record_video, daemon=True).start()
        time.sleep(0.5)  # 카메라 초기화 대기
        return jsonify({"status":0, "msg":{"size":f"{VIDEO_WIDTH}x{VIDEO_HEIGHT}", "fps":f"{VIDEO_FPS}"}}),200
    return jsonify({"status":1, "msg":"already recording"}),400

@app.route('/stop', methods=['POST'])
def stop_recording():
    global recording
    if recording:
        recording = False
        time.sleep(1)
        return jsonify({"status":0, "msg":"stopped"}),200
    return jsonify({"status":1, "msg":"not recording"}),400

@app.route('/download', methods=['GET'])
def download_video():
    if os.path.exists(VIDEO_PATH):
        return send_file(
            VIDEO_PATH,
            as_attachment=True,
            download_name=f"camera_video.{VIDEO_FORMAT}"
        )
    return jsonify({"status":1, "msg":"no video"}),400

@app.route('/getconfig', methods=['GET'])
def get_config():
    return jsonify({
        "format":VIDEO_FORMAT,
        "resolution":f"{VIDEO_WIDTH}x{VIDEO_HEIGHT}",
        "fps":VIDEO_FPS
    })

@app.route('/setconfig', methods=['POST'])
def set_config():
    global VIDEO_WIDTH, VIDEO_HEIGHT, VIDEO_FPS

    if recording:
        return jsonify({"error": "stop recording first"}), 400

    data = request.get_json()

    new_width = data.get('width', VIDEO_WIDTH)
    new_height = data.get('height', VIDEO_HEIGHT)
    new_fps = data.get('fps', VIDEO_FPS)

    valid_resolutions = [(640,480), (1280,720), (1920,1080)]
    if (new_width, new_height) not in valid_resolutions:
        return jsonify({"error": "invalid resolution, use: 640x480, 1280x720, 1920x1080"}), 400

    if new_fps not in [25, 30]:
        return jsonify({"error": "fps must be 25 or 30"}), 400

    VIDEO_WIDTH, VIDEO_HEIGHT, VIDEO_FPS = new_width, new_height, new_fps
    return jsonify({
        "status": "config updated",
        "new_config": f"{VIDEO_WIDTH}x{VIDEO_HEIGHT}@{VIDEO_FPS}fps"
    }), 200

@app.route('/status', methods=['POST'])
def get_status():
    return jsonify({"status": 0, "msg": "server alive"}), 200

@app.route('/test', methods=['GET'])
def test_camera():
    try:
        picam2 = Picamera2()
        config = picam2.create_still_configuration()
        picam2.configure(config)
        picam2.start()
        time.sleep(2)
        picam2.capture_file("test.jpg")
        picam2.stop()
        picam2.close()
        return send_file("test.jpg", as_attachment=True)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__=='__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)