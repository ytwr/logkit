import subprocess
import os
import time
import argparse
import matplotlib.pyplot as plt
import pandas as pd
from perfetto.trace_processor import TraceProcessor

# 默认配置
ADB_PATH = "adb"
TRACE_FILE = "trace.perfetto-trace"
OUTPUT_JSON = "trace.json"
FRAME_THRESHOLD = 16.6  # 60 FPS 阈值 (ms)

def capture_perfetto_trace(duration, output_file):
    """使用 Perfetto 捕获 trace 数据"""
    config = """
    buffers: {
        size_kb: 8960
        fill_policy: RING_BUFFER
    }
    data_sources: {
        config {
            name: "linux.process_stats"
            target_buffer: 0
        }
    }
    data_sources: {
        config {
            name: "linux.ftrace"
            ftrace_config {
                ftrace_events: "sched/sched_switch"
                ftrace_events: "sched/sched_wakeup"
                ftrace_events: "power/cpu_frequency"
                ftrace_events: "power/cpu_idle"
            }
        }
    }
    data_sources: {
        config {
            name: "android.surfaceflinger.framestats"
        }
    }
    duration_ms: {}
    """.format(duration * 1000)

    # 将配置写入临时文件
    with open("perfetto_config.pbtx", "w") as f:
        f.write(config)

    # 运行 Perfetto 采集
    cmd = [
        ADB_PATH, "shell", "perfetto", "-c", "-", "-o", f"/data/misc/perfetto-traces/{output_file}"
    ]
    try:
        process = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        process.communicate(input=config.encode())
        time.sleep(duration + 2)  # 等待采集完成
        subprocess.run([ADB_PATH, "pull", f"/data/misc/perfetto-traces/{output_file}", output_file], check=True)
        print(f"Perfetto trace 已保存至 {output_file}")
    except subprocess.CalledProcessError as e:
        print(f"采集 Perfetto trace 失败: {e}")
        sys.exit(1)

def parse_trace(trace_file):
    """解析 Perfetto trace 文件"""
    try:
        tp = TraceProcessor(trace_file)

        # 查询 CPU 调度事件
        sched_query = """
        SELECT ts, dur, cpu, process.name AS process_name, thread.name AS thread_name, 
               state
        FROM sched
        JOIN thread ON sched.utid = thread.utid
        JOIN process ON thread.upid = process.upid
        WHERE dur > 0
        """
        sched_df = tp.query(sched_query).as_pandas_dataframe()

        # 查询帧时间
        frame_query = """
        SELECT ts, dur
        FROM slice
        WHERE category = 'SurfaceFlinger' AND name = 'Frame'
        """
        frame_df = tp.query(frame_query).as_pandas_dataframe()

        return sched_df, frame_df
    except Exception as e:
        print(f"解析 trace 文件失败: {e}")
        return None, None

def analyze_cpu_load(sched_df):
    """分析 CPU 负载"""
    if sched_df is None or sched_df.empty:
        return None

    # 转换为毫秒
    sched_df['ts_ms'] = sched_df['ts'] / 1e6  # 纳秒转毫秒
    sched_df['dur_ms'] = sched_df['dur'] / 1e6

    # 计算每个 CPU 的负载
    cpu_load = {}
    for cpu in sched_df['cpu'].unique():
        cpu_events = sched_df[sched_df['cpu'] == cpu]
        total_time = cpu_events['dur_ms'].sum()
        start_time = cpu_events['ts_ms'].min()
        end_time = cpu_events['ts_ms'].max()
        active_time = total_time / (end_time - start_time) * 100  # 百分比
        cpu_load[cpu] = {'time': cpu_events['ts_ms'].tolist(), 'dur': cpu_events['dur_ms'].tolist(), 'load': active_time}

    return cpu_load

def analyze_jank(frame_df):
    """分析卡顿帧及其原因"""
    if frame_df is None or frame_df.empty:
        return None, None

    frame_df['ts_ms'] = frame_df['ts'] / 1e6
    frame_df['dur_ms'] = frame_df['dur'] / 1e6
    jank_frames = frame_df[frame_df['dur_ms'] > FRAME_THRESHOLD]
    return frame_df, jank_frames

def visualize_data(cpu_load, sched_df, frame_df, jank_frames):
    """可视化 CPU 负载、进程状态和帧时间"""
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(14, 10), sharex=True)

    # CPU 负载
    if cpu_load:
        for cpu, data in cpu_load.items():
            ax1.plot(data['time'], data['dur'], label=f"CPU {cpu} (Load: {data['load']:.1f}%)")
        ax1.set_title("CPU Load Over Time")
        ax1.set_ylabel("Duration (ms)")
        ax1.legend()

    # 进程状态（Runnable 和 Sleeping）
    if sched_df is not None and not sched_df.empty:
        runnable = sched_df[sched_df['state'] == 'R']
        sleeping = sched_df[sched_df['state'].isin(['S', 'D'])]  # S: Sleeping, D: Uninterruptible Sleep
        ax2.scatter(runnable['ts_ms'], [1] * len(runnable), label="Runnable", color="green", s=10)
        ax2.scatter(sleeping['ts_ms'], [0] * len(sleeping), label="Sleeping", color="blue", s=10)
        ax2.set_title("Process States (Runnable vs Sleeping)")
        ax2.set_ylabel("State (1=Runnable, 0=Sleeping)")
        ax2.set_ylim(-0.5, 1.5)
        ax2.legend()

    # 帧时间和卡顿
    if frame_df is not None and not frame_df.empty:
        ax3.plot(frame_df['ts_ms'], frame_df['dur_ms'], label="Frame Time (ms)", color="green")
        if not jank_frames.empty:
            ax3.scatter(jank_frames['ts_ms'], jank_frames['dur_ms'], color="red", label="Jank Frames", zorder=5)
        ax3.axhline(y=FRAME_THRESHOLD, color="orange", linestyle="--", label="60 FPS Threshold")
        ax3.set_title("Frame Rendering Time")
        ax3.set_xlabel("Time (ms)")
        ax3.set_ylabel("Duration (ms)")
        ax3.legend()

    plt.tight_layout()
    plt.show()

def main():
    parser = argparse.ArgumentParser(description="Perfetto Trace CPU 负载和卡顿分析工具")
    parser.add_argument("--duration", type=int, default=10, help="采集时间（秒）")
    parser.add_argument("--output", type=str, default=TRACE_FILE, help="输出 trace 文件路径")
    parser.add_argument("--device", type=str, help="指定设备序列号")
    args = parser.parse_args()

    # 设置设备
    if args.device:
        os.environ["ANDROID_SERIAL"] = args.device

    # 捕获 Perfetto trace
    capture_perfetto_trace(args.duration, args.output)

    # 解析 trace 数据
    sched_df, frame_df = parse_trace(args.output)
    if sched_df is None or frame_df is None:
        return

    # 分析 CPU 负载和卡顿
    cpu_load = analyze_cpu_load(sched_df)
    frame_times, jank_frames = analyze_jank(frame_df)

    # 输出分析结果
    if cpu_load:
        print("CPU 负载分析:")
        for cpu, data in cpu_load.items():
            print(f"CPU {cpu}: {data['load']:.1f}%")
    if jank_frames is not None:
        print(f"检测到 {len(jank_frames)} 个卡顿帧（> {FRAME_THRESHOLD}ms）")

    # 可视化
    visualize_data(cpu_load, sched_df, frame_times, jank_frames)

if __name__ == "__main__":
    import sys
    main()