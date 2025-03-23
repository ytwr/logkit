import subprocess
import os
import re
import time
import argparse
import matplotlib.pyplot as plt
import numpy as np
from bs4 import BeautifulSoup  # 用于解析 HTML

# 默认配置
ADB_PATH = "adb"  # 如果 ADB 未加入 PATH，需指定完整路径
SYSTRACE_PATH = "path/to/android-sdk/platform-tools/systrace/systrace.py"  # 替换为实际路径
OUTPUT_FILE = "trace.html"
FRAME_THRESHOLD = 16.6  # 每帧 16.6ms 对应 60 FPS

def run_systrace(duration, output_file, categories="sched freq load gfx view"):
    """运行 Systrace 采集数据"""
    cmd = [
        "python", SYSTRACE_PATH,
        "--time", str(duration),
        "-o", output_file,
    ] + categories.split()
    try:
        subprocess.run(cmd, check=True)
        print(f"Systrace 数据采集完成，保存至 {output_file}")
    except subprocess.CalledProcessError as e:
        print(f"运行 Systrace 失败: {e}")
        sys.exit(1)

def parse_systrace_html(html_file):
    """解析 Systrace HTML 文件，提取 CPU 负载和帧时间"""
    if not os.path.exists(html_file):
        print(f"文件 {html_file} 不存在")
        return None, None

    with open(html_file, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f, 'html.parser')

    # 提取脚本数据（Systrace 将数据嵌入在 <script> 标签中）
    script = soup.find('script', text=re.compile('var traceEvents'))
    if not script:
        print("未找到 traceEvents 数据")
        return None, None

    # 提取 traceEvents JSON 数据
    match = re.search(r'var traceEvents = (\[.*?\]);', script.text, re.DOTALL)
    if not match:
        print("无法解析 traceEvents")
        return None, None

    events = eval(match.group(1))  # 安全起见可用 json.loads，但此处简化为 eval

    # 解析 CPU 负载和帧时间
    cpu_load = []
    frame_times = []
    timestamps = []

    for event in events:
        if 'ts' not in event or 'dur' not in event:
            continue
        timestamp = event['ts'] / 1000  # 微秒转毫秒
        duration = event['dur'] / 1000  # 微秒转毫秒

        # CPU 负载（示例：假设 'load' 类别记录 CPU 活动）
        if event.get('cat') == 'load':
            cpu_load.append((timestamp, duration))
            timestamps.append(timestamp)

        # 帧时间（假设 'gfx' 或 'view' 类别记录帧渲染）
        if event.get('cat') in ['gfx', 'view'] and event.get('name') == 'Frame':
            frame_times.append((timestamp, duration))

    return cpu_load, frame_times

def analyze_jank(frame_times):
    """分析卡顿帧"""
    jank_frames = [(ts, dur) for ts, dur in frame_times if dur > FRAME_THRESHOLD]
    return jank_frames

def visualize_data(cpu_load, frame_times, jank_frames):
    """可视化 CPU 负载和帧时间"""
    if not cpu_load or not frame_times:
        print("无数据可供可视化")
        return

    # 准备数据
    cpu_ts, cpu_dur = zip(*cpu_load) if cpu_load else ([], [])
    frame_ts, frame_dur = zip(*frame_times)
    jank_ts, jank_dur = zip(*jank_frames) if jank_frames else ([], [])

    # 创建图表
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))

    # CPU 负载图
    if cpu_load:
        ax1.plot(cpu_ts, cpu_dur, label="CPU Load (ms)", color="blue")
        ax1.set_title("CPU Load Over Time")
        ax1.set_xlabel("Time (ms)")
        ax1.set_ylabel("Duration (ms)")
        ax1.legend()

    # 帧时间图
    ax2.plot(frame_ts, frame_dur, label="Frame Time (ms)", color="green")
    if jank_frames:
        ax2.scatter(jank_ts, jank_dur, color="red", label="Jank Frames (>16.6ms)", zorder=5)
    ax2.axhline(y=FRAME_THRESHOLD, color="orange", linestyle="--", label="60 FPS Threshold")
    ax2.set_title("Frame Rendering Time")
    ax2.set_xlabel("Time (ms)")
    ax2.set_ylabel("Duration (ms)")
    ax2.legend()

    plt.tight_layout()
    plt.show()

def main():
    # 命令行参数
    parser = argparse.ArgumentParser(description="Systrace CPU 负载和卡顿分析工具")
    parser.add_argument("--duration", type=int, default=10, help="采集时间（秒）")
    parser.add_argument("--output", type=str, default=OUTPUT_FILE, help="输出文件路径")
    parser.add_argument("--device", type=str, help="指定设备序列号")
    args = parser.parse_args()

    # 设置设备（如果指定）
    if args.device:
        subprocess.run([ADB_PATH, "devices"])  # 检查设备
        os.environ["ANDROID_SERIAL"] = args.device

    # 运行 Systrace
    run_systrace(args.duration, args.output)

    # 解析数据
    cpu_load, frame_times = parse_systrace_html(args.output)
    if cpu_load is None or frame_times is None:
        return

    # 分析卡顿
    jank_frames = analyze_jank(frame_times)
    print(f"检测到 {len(jank_frames)} 个卡顿帧（> {FRAME_THRESHOLD}ms）")

    # 可视化
    visualize_data(cpu_load, frame_times, jank_frames)

if __name__ == "__main__":
    import sys
    if not os.path.exists(SYSTRACE_PATH):
        print(f"请设置正确的 SYSTRACE_PATH，目前为: {SYSTRACE_PATH}")
        sys.exit(1)
    main()