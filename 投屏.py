import subprocess
import cv2
import numpy as np
import threading
import time
from PIL import Image
import io
import re
import sys

# ADB 路径和设备序列号（如果有多个设备）
ADB_PATH = "adb"  # 如果 ADB 未加入 PATH，需指定完整路径
DEVICE_SERIAL = None  # 如果有多个设备，填入设备序列号，例如 "12345678"

# 全局变量
current_frame = None
running = True
SCREEN_WIDTH = None
SCREEN_HEIGHT = None

def get_screen_resolution():
    """通过 ADB 获取设备屏幕分辨率"""
    global SCREEN_WIDTH, SCREEN_HEIGHT
    cmd = [ADB_PATH]
    if DEVICE_SERIAL:
        cmd.extend(["-s", DEVICE_SERIAL])
    cmd.extend(["shell", "wm", "size"])
    
    try:
        output = subprocess.check_output(cmd).decode().strip()
        match = re.search(r'Physical size: (\d+)x(\d+)', output)
        if match:
            SCREEN_WIDTH, SCREEN_HEIGHT = int(match.group(1)), int(match.group(2))
            print(f"动态获取屏幕分辨率: {SCREEN_WIDTH}x{SCREEN_HEIGHT}")
        else:
            raise ValueError("无法解析屏幕分辨率")
    except Exception as e:
        print(f"获取屏幕分辨率失败: {e}")
        # 默认值
        SCREEN_WIDTH, SCREEN_HEIGHT = 1080, 1920

def get_screen():
    """通过 ADB 获取设备屏幕截图"""
    global current_frame
    cmd = [ADB_PATH]
    if DEVICE_SERIAL:
        cmd.extend(["-s", DEVICE_SERIAL])
    cmd.extend(["exec-out", "screencap", "-p"])
    
    while running:
        try:
            # 获取屏幕截图
            result = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = result.communicate()
            if stderr:
                print(f"错误: {stderr.decode()}")
                continue
            
            # 将 PNG 数据转换为图像
            img = Image.open(io.BytesIO(stdout))
            frame = np.array(img)
            # 转换为 BGR 格式（OpenCV 使用）
            if frame.shape[-1] == 4:  # RGBA
                frame = cv2.cvtColor(frame, cv2.COLOR_RGBA2BGR)
            else:  # RGB
                frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            current_frame = frame
        except Exception as e:
            print(f"获取屏幕失败: {e}")
        time.sleep(0.1)  # 控制帧率

def tap_screen(x, y):
    """通过 ADB 模拟屏幕点击"""
    cmd = [ADB_PATH]
    if DEVICE_SERIAL:
        cmd.extend(["-s", DEVICE_SERIAL])
    cmd.extend(["shell", "input", "tap", str(x), str(y)])
    subprocess.run(cmd)

def mouse_callback(event, x, y, flags, param):
    """鼠标事件回调函数"""
    if event == cv2.EVENT_LBUTTONDOWN:
        # 将窗口坐标映射到设备屏幕坐标
        scale_x = SCREEN_WIDTH / window_width
        scale_y = SCREEN_HEIGHT / window_height
        device_x = int(x * scale_x)
        device_y = int(y * scale_y)
        print(f"点击坐标: ({device_x}, {device_y})")
        tap_screen(device_x, device_y)

def main():
    global running, window_width, window_height
    
    # 动态获取屏幕分辨率
    get_screen_resolution()
    if SCREEN_WIDTH is None or SCREEN_HEIGHT is None:
        print("无法获取屏幕分辨率，使用默认值")
        SCREEN_WIDTH, SCREEN_HEIGHT = 1080, 1920

    # 启动屏幕采集线程
    screen_thread = threading.Thread(target=get_screen)
    screen_thread.daemon = True
    screen_thread.start()

    # 创建显示窗口
    cv2.namedWindow("Android Screen", cv2.WINDOW_NORMAL)
    cv2.setMouseCallback("Android Screen", mouse_callback)

    # 主循环
    while True:
        if current_frame is not None:
            # 显示屏幕内容（按比例缩放）
            resized_frame = cv2.resize(current_frame, (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2))
            window_width, window_height = resized_frame.shape[1], resized_frame.shape[0]
            cv2.imshow("Android Screen", resized_frame)
        
        # 处理按键退出
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            running = False
            break

    cv2.destroyAllWindows()

if __name__ == "__main__":
    # 检查设备连接
    try:
        devices = subprocess.check_output([ADB_PATH, "devices"]).decode().strip()
        if "device" not in devices:
            print("未检测到设备，请检查 ADB 连接！")
            sys.exit(1)
    except Exception as e:
        print(f"ADB 初始化失败: {e}")
        sys.exit(1)

    main()