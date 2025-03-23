# LogKit - Android日志分析工具

## 项目简介
LogKit是一个用于Android设备日志分析的工具，提供了日志采集、内存监控、功耗分析等功能。同时集成了屏幕镜像功能，方便开发者进行设备调试。

## 主要功能
- 实时日志采集和过滤
- 内存使用监控
- 功耗数据分析
- 设备屏幕镜像
- 支持自定义关键字高亮
- 日志保存和加载
- Systrace性能分析

## 安装要求
- Python 3.6+
- Android Debug Bridge (ADB)
- 已启用USB调试的Android设备

## 安装步骤
1. 克隆仓库到本地
2. 安装依赖包：
   ```bash
   pip install -r requirements.txt
   ```
3. 确保ADB已添加到系统环境变量

## 使用说明
1. 运行主程序：
   ```bash
   python logkit_ui.py
   ```
2. 选择已连接的Android设备
3. 配置日志关键字和颜色（可选）
4. 点击"开始采集"按钮开始监控

## 屏幕镜像
运行屏幕镜像功能：
```bash
python copyscreen.py
```

## 配置说明
可以通过JSON文件配置关键字过滤规则，格式如下：
```json
{
    "keywords": [
        {"keyword": "error", "color": "red"},
        {"keyword": "warning", "color": "yellow"}
    ]
}
```

## 注意事项
- 使用前请确保Android设备已正确连接并启用USB调试
- 部分功能可能需要root权限
- 建议在分析大量日志时及时保存数据