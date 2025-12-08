from picamera2 import Picamera2
import time

picam2 = Picamera2()
picam2.start()
time.sleep(5)
picam2.capture_file("picam_test.jpg")
picam2.stop()