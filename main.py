import time
import tellopy
import os
import cv2
import numpy as np
import pyautogui as pg
import win32gui
from pynput import keyboard
from PIL import ImageGrab
from time import sleep
from subprocess import Popen, PIPE
import threading

rect = None
auto = True

prev_flight_data = None
flight_data = None
video_player = None


def update(old, new, max_delta=0.3):
    if abs(old-new) <= max_delta:
        res = new
    else:
        res = 0.0
    return res

def handler(event, sender, data, **args):
    global prev_flight_data
    global flight_data
    global video_player
    
    drone = sender
    
    if event is drone.EVENT_FLIGHT_DATA:
        if prev_flight_data != str(data):
            print(data)
            prev_flight_data = str(data)
        flight_data = data
    elif event is drone.EVENT_VIDEO_FRAME:
        if video_player is None:
            video_player = Popen(['mplayer', '-fps', '35', '-', 'libx264'], stdin=PIPE)
        try:
            video_player.stdin.write(data)
        except IOError as e:
            print("No video player")
            print(e)
            video_player = None
    else:
        print(f"event='{event.getname()}' data={data}")
        
def detect_object():
    CONFIDENCE_THRESHOLD = 0.3
    NMS_THRESHOLD = 0.4
    class_names = []
    with open("darknet_cfg/coco_classes.txt", "r") as f:
        class_names = [cname.strip() for cname in f.readlines()]
    COLORS = [np.random.randint(0, 256, [3]).astype(np.uint8).tolist() for _ in range(len(class_names))]
    # print(COLORS)
    # net = cv2.dnn.readNet("yolov3-tiny_face_best.weights", "yolov3-tiny_face.cfg")
    net = cv2.dnn.readNet("darknet_cfg/yolov3-tiny.weights", "darknet_cfg/yolov3-tiny.cfg")
    net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)

    model = cv2.dnn_DetectionModel(net)
    model.setInputParams(size=(416, 416), scale=1/255, swapRB=True) # 入力サイズ，スケールファクター，チャンネルの順番（True:RGB，False:BGR）
    global rect
    while(1):
        if not rect:
            continue
        # print(f'rect={rect}') # 画像の横，縦の長さをチェックする
        take_screenshot(rect, './imgs/tello.png')
        img_folder_path = './imgs'
        file_list = os.listdir(img_folder_path)
        
        for img_file in file_list:
            if (img_file.endswith(".png")):
                frame = cv2.imread(img_folder_path + '/' + img_file)
                class_ids, confidences, boxes = model.detect(frame, CONFIDENCE_THRESHOLD, NMS_THRESHOLD)
                
                person = None   # 人が検出されたかどうか（None:検出されていない，(x,y,w,h):人のバウンディングボックス）
                
                start_drawing = time.time()
                for (class_id, confidence, box) in zip(class_ids, confidences, boxes):
                    class_name = class_names[class_id]
                    color = COLORS[class_id]
                    label = f"{class_name} : {confidence}"
                    cv2.rectangle(frame, box, color, 2)
                    cv2.putText(frame, label, (box[0], box[1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
                    # print(f'{class_name} : {box}')
                    
                    if class_names[class_id] == 'person':   # 検出された物体が人だった場合
                        x, y, h, w = box
                        if not person or person[2]*person[3] <= w*h:    # バウンディングボックスの面積が大きければ更新
                            person = (x, y, w, h)
                
                cv2.imshow('YOLOv3-tiny', frame)
                os.remove(img_folder_path + '/' + img_file)
                
                global auto
                if not auto:
                    break
                if person:  # フレームから人が検出された場合
                    x, y, w, h = person # 人のバウンディングボックス
                    W, H = 976, 759 # 画像の横，縦の長さ
                    cx, cy = x+w/2, y+h/2   # バウンディングボックスの中心座標
                    
                    dx = abs(cx-W/2)    # バウンディングボックスの中心x座標と画像の中心x座標の差分
                    if cx < W/3:    # 画像の左側に人がいる場合
                        # 左に進む
                        pg.keyDown('a')
                        sleep(0.2 + 0.1*(dx/W))
                        pg.keyUp('a')
                    elif cx > (W/3)*2:  # 画像の右側に人がいる場合
                        # 右に進む
                        pg.keyDown('d')
                        sleep(0.2 + 0.1*(dx/W))
                        pg.keyUp('d')

                    if h*w < W*H/10:
                        pg.keyDown('w')
                        sleep(0.05)
                        pg.keyUp('w')
                    elif h*w > W*H/3:
                        pg.keyDown('s')
                        sleep(0.05)
                        pg.keyUp('w')
                
                cv2.waitKey(1)

            if img_file is None:
                cv2.destroyAllWindows()



def take_screenshot(rect, image_path):
    """指定範囲rectのスクリーンショットを取得・保存する
    """
    screenshot = ImageGrab.grab()
    cropped_screenshot = screenshot.crop(rect)
    cropped_screenshot.save(image_path)


def set_screen_position():
    """Mplayerのスクリーンの位置を左上に自動調節する
    """
    global rect
    while True:
        try:
            mplayer_app = win32gui.FindWindow(None, 'MPlayer - The Movie Player')
            sleep(1)
            win32gui.SetForegroundWindow(mplayer_app)
            hwnd = win32gui.GetForegroundWindow()
            l, t, r, b = win32gui.GetWindowRect(hwnd)
            win32gui.MoveWindow(hwnd, 0, 0, r-l, b-t, True)
            l, t, r, b = win32gui.GetWindowRect(hwnd)
            rect = (l, t, r, b) # スクリーンショット範囲を示すグローバル変数rectの更新
            print('Setting screen position done')
            break
        except:
            continue

def main():
    drone = tellopy.Tello()
    drone.connect()
    drone.start_video()
    drone.subscribe(drone.EVENT_FLIGHT_DATA, handler)
    drone.subscribe(drone.EVENT_VIDEO_FRAME, handler)
    
    def on_press(key):
        """キーが押された時に呼ばれるコールバック
        """
        print(f'{key} pressed')
        speed = 25
        
        if key in [keyboard.Key.esc, keyboard.Key.space]:
            return
        
        if key == keyboard.Key.tab:
            drone.takeoff()
            print("Take off")
        elif key == keyboard.Key.backspace:
            drone.land()
            print("Land")
        elif key == keyboard.Key.up:    # 上昇
            drone.up(speed)
        elif key == keyboard.Key.down: # 下降
            drone.down(speed)
        elif key == keyboard.Key.left: # 左旋回
            drone.counter_clockwise(speed)
        elif key == keyboard.Key.right: # 右旋回
            drone.clockwise(speed)
        elif key.char == 'w': # 前方
            drone.forward(speed)
        elif key.char == 's': # 後方
            drone.backward(speed)
        elif key.char == 'a': # 左
            drone.left(speed)
        elif key.char == 'd': # 右
            drone.right(speed)
        else:
            return
        return False    # 検知終了

    def on_release(key):
        """キーが離された時に呼ばれるコールバック
        """
        print(f'{key} release')
        if key == keyboard.Key.esc: # escが押された場合
            return False    # 検知を終了する
        if key == keyboard.Key.space:
            global auto
            auto = not auto
            sleep(1)
            return False
        
        if key == keyboard.Key.tab:
            drone.takeoff()
            print("Take off")
        elif key == keyboard.Key.backspace:
            drone.land()
            print("Land")
        elif key == keyboard.Key.up:    # 上昇
            drone.up(0)
        elif key == keyboard.Key.down: # 下降
            drone.down(0)
        elif key == keyboard.Key.left: # 左旋回
            drone.counter_clockwise(0)
        elif key == keyboard.Key.right: # 右旋回
            drone.clockwise(0)
        elif key.char == 'w': # 前方
            drone.forward(0)
        elif key.char == 's': # 後方
            drone.backward(0)
        elif key.char == 'a': # 左
            drone.left(0)
        elif key.char == 'd': # 右
            drone.right(0)
        else:
            return
        return False    # 検知終了

    while True:
        with keyboard.Listener(
            on_press=on_press,
            on_release=on_release) as listener:
            listener.join()
    drone.quit()

    
    
if __name__ == '__main__':
    t1 = threading.Thread(target=main)
    t2 = threading.Thread(target=detect_object)
    t3 = threading.Thread(target=set_screen_position)
    t1.start()
    t2.start()
    t3.start()
    t1.join()
    t2.join()
    t3.join()
