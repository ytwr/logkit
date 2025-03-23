import sys
import json
import re
import subprocess
import threading
import time
from PyQt5.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget, QTextEdit, QPushButton, 
                             QFileDialog, QLabel, QLineEdit, QMessageBox, QComboBox)
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtGui import QColor
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

# 日志采集线程
class LogThread(QThread):
    log_signal = pyqtSignal(str)

    def __init__(self, keywords, device_serial=None):
        super().__init__()
        self.keywords = keywords
        self.device_serial = device_serial
        self.running = True

    def run(self):
        cmd = ['adb']
        if self.device_serial:
            cmd.extend(['-s', self.device_serial])
        cmd.extend(['logcat', '-v', 'time'])
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        while self.running:
            line = process.stdout.readline().decode('utf-8').strip()
            for keyword, color in self.keywords.items():
                if keyword in line.lower():
                    self.log_signal.emit(f'<span style="color:{color}">{line}</span>')
                    break
            time.sleep(0.01)

# 内存和功耗采集线程
class ResourceThread(QThread):
    memory_signal = pyqtSignal(int)
    power_signal = pyqtSignal(float)

    def __init__(self, package_name, device_serial=None):
        super().__init__()
        self.package_name = package_name
        self.device_serial = device_serial
        self.running = True

    def run(self):
        last_energy = 0
        while self.running:
            cmd_base = ['adb']
            if self.device_serial:
                cmd_base.extend(['-s', self.device_serial])
            # 内存采集
            try:
                cmd = cmd_base + ['shell', 'dumpsys', 'meminfo', self.package_name]
                output = subprocess.check_output(cmd).decode('utf-8')
                pss_match = re.search(r'TOTAL PSS:\s+(\d+)', output)
                if pss_match:
                    pss_kb = int(pss_match.group(1))
                    self.memory_signal.emit(pss_kb)
            except:
                pass
            # 功耗采集
            try:
                cmd = cmd_base + ['shell', 'dumpsys', 'batterystats', '--unplugged']
                output = subprocess.check_output(cmd).decode('utf-8')
                energy_match = re.search(rf'{self.package_name}.*?Estimated power use \(mAh\): (\d+\.\d+)', output)
                if energy_match:
                    current_energy = float(energy_match.group(1))
                    if last_energy:
                        self.power_signal.emit(current_energy - last_energy)
                    last_energy = current_energy
            except:
                pass
            time.sleep(5)

# 主窗口
class CameraAnalyzer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("安卓相机日志分析工具")
        self.setGeometry(100, 100, 1200, 800)

        # 初始化数据
        self.keywords = {}
        self.logs = []
        self.memory_data = []
        self.power_data = []
        self.timestamps = []
        self.device_serial = None

        # 设置布局
        self.init_ui()

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)

        # 设备选择区域
        device_layout = QHBoxLayout()
        device_label = QLabel("选择设备:")
        device_layout.addWidget(device_label)
        self.device_combo = QComboBox()
        self.device_combo.currentTextChanged.connect(self.on_device_selected)
        device_layout.addWidget(self.device_combo)
        refresh_btn = QPushButton("刷新设备")
        refresh_btn.clicked.connect(self.refresh_devices)
        device_layout.addWidget(refresh_btn)
        layout.addLayout(device_layout)

        # 日志显示区域
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        layout.addWidget(self.log_display)

        # 过滤配置区域
        filter_layout = QHBoxLayout()
        self.keyword_input = QLineEdit()
        self.keyword_input.setPlaceholderText("输入关键字（如 error:red,warning:yellow）")
        filter_layout.addWidget(self.keyword_input)
        load_json_btn = QPushButton("加载 JSON 配置")
        load_json_btn.clicked.connect(self.load_json_config)
        filter_layout.addWidget(load_json_btn)
        start_btn = QPushButton("开始采集")
        start_btn.clicked.connect(self.start_collection)
        filter_layout.addWidget(start_btn)
        layout.addLayout(filter_layout)

        # 保存和加载按钮
        save_load_layout = QHBoxLayout()
        save_btn = QPushButton("保存日志")
        save_btn.clicked.connect(self.save_logs)
        save_load_layout.addWidget(save_btn)
        load_btn = QPushButton("加载日志")
        load_btn.clicked.connect(self.load_logs)
        save_load_layout.addWidget(load_btn)
        layout.addLayout(save_load_layout)

        # 内存和功耗图表
        self.fig, (self.ax1, self.ax2) = plt.subplots(2, 1, figsize=(10, 5))
        self.canvas = FigureCanvas(self.fig)
        layout.addWidget(self.canvas)

        # Systrace 区域
        systrace_layout = QHBoxLayout()
        systrace_btn = QPushButton("启动 Systrace")
        systrace_btn.clicked.connect(self.start_systrace)
        systrace_layout.addWidget(systrace_btn)
        layout.addLayout(systrace_layout)

        # 初始化设备列表
        self.refresh_devices()

    def refresh_devices(self):
        """刷新设备列表"""
        self.device_combo.clear()
        try:
            output = subprocess.check_output(['adb', 'devices']).decode().strip()
            devices = [line.split('\t')[0] for line in output.splitlines()[1:] if '\t' in line]
            if devices:
                self.device_combo.addItems(devices)
                self.device_serial = devices[0]  # 默认选择第一个设备
            else:
                self.device_combo.addItem("无设备")
                self.device_serial = None
        except Exception as e:
            QMessageBox.warning(self, "错误", f"无法获取设备列表: {e}")
            self.device_serial = None

    def on_device_selected(self, device):
        """设备选择更改时更新全局变量"""
        if device and device != "无设备":
            self.device_serial = device
        else:
            self.device_serial = None

    def load_json_config(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "选择 JSON 配置文件", "", "JSON Files (*.json)")
        if file_name:
            with open(file_name, 'r') as f:
                config = json.load(f)
                for item in config['keywords']:
                    self.keywords[item['keyword'].lower()] = item['color']
            self.keyword_input.setText(','.join([f"{k}:{v}" for k, v in self.keywords.items()]))

    def start_collection(self):
        if not self.device_serial:
            QMessageBox.warning(self, "错误", "请先选择一个设备！")
            return

        if self.keyword_input.text():
            for pair in self.keyword_input.text().split(','):
                keyword, color = pair.split(':')
                self.keywords[keyword.lower()] = color

        if not self.keywords:
            QMessageBox.warning(self, "错误", "请先配置关键字！")
            return

        # 启动日志采集
        self.log_thread = LogThread(self.keywords, self.device_serial)
        self.log_thread.log_signal.connect(self.update_log_display)
        self.log_thread.start()

        # 启动内存和功耗采集
        package_name = "com.android.camera"  # 可改为用户输入
        self.resource_thread = ResourceThread(package_name, self.device_serial)
        self.resource_thread.memory_signal.connect(self.update_memory)
        self.resource_thread.power_signal.connect(self.update_power)
        self.resource_thread.start()

    def update_log_display(self, log):
        self.logs.append(log)
        self.log_display.append(log)

    def update_memory(self, memory):
        self.memory_data.append(memory)
        self.timestamps.append(time.time())
        self.update_plot()

    def update_power(self, power):
        self.power_data.append(power)
        self.update_plot()

    def update_plot(self):
        self.ax1.clear()
        self.ax2.clear()
        if self.memory_data:
            self.ax1.plot(self.timestamps[-50:], self.memory_data[-50:], 'b-', label='内存 (KB)')
            self.ax1.set_title("内存使用")
            self.ax1.legend()
        if self.power_data:
            self.ax2.plot(self.timestamps[-50:], self.power_data[-50:], 'r-', label='功耗变化 (mAh)')
            self.ax2.set_title("功耗变化")
            self.ax2.legend()
        self.canvas.draw()

    def save_logs(self):
        file_name, _ = QFileDialog.getSaveFileName(self, "保存日志", "", "Text Files (*.txt)")
        if file_name:
            with open(file_name, 'w') as f:
                f.write('\n'.join(self.logs))

    def load_logs(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "加载日志", "", "Text Files (*.txt)")
        if file_name:
            with open(file_name, 'r') as f:
                self.logs = f.readlines()
            self.log_display.clear()
            for log in self.logs:
                for keyword, color in self.keywords.items():
                    if keyword in log.lower():
                        self.log_display.append(f'<span style="color:{color}">{log}</span>')
                        break

    def start_systrace(self):
        if not self.device_serial:
            QMessageBox.warning(self, "错误", "请先选择一个设备！")
            return
        cmd_base = ['adb', '-s', self.device_serial]
        subprocess.run(cmd_base + ['shell', 'atrace', '--async_start', '-t', '10', 'gfx', '-b', '8192'])
        time.sleep(10)
        subprocess.run(cmd_base + ['shell', 'atrace', '--async_dump', '-o', '/data/local/tmp/trace.txt'])
        subprocess.run(cmd_base + ['pull', '/data/local/tmp/trace.txt', 'trace.txt'])
        QMessageBox.information(self, "Systrace", "Systrace 文件已保存为 trace.txt，请手动分析或扩展工具解析。")

    def closeEvent(self, event):
        if hasattr(self, 'log_thread'):
            self.log_thread.running = False
        if hasattr(self, 'resource_thread'):
            self.resource_thread.running = False
        event.accept()

# 主程序
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = CameraAnalyzer()
    window.show()
    sys.exit(app.exec_())