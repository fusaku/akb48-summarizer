#!/usr/bin/env python3
"""
视频自动处理守护进程
实时监控 videos/ 目录，自动处理新上传的视频
"""

import time
import subprocess
import os
import sys
from datetime import datetime
from pathlib import Path

# 添加父目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

# 尝试导入 watchdog
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
except ImportError:
    print("❌ 缺少依赖: watchdog")
    print("请运行: pip3 install --break-system-packages watchdog")
    sys.exit(1)

from utils import load_config


class VideoHandler(FileSystemEventHandler):
    """视频文件监控处理器"""
    
    def __init__(self, video_folder, extensions, script_path):
        self.video_folder = video_folder
        self.extensions = [ext.lower() for ext in extensions]
        self.script_path = script_path
        self.processing = False
        self.pending_files = set()
        self.last_process_time = 0
        self.cooldown_seconds = 10
        
    def is_video_file(self, filepath):
        """检查是否是视频文件"""
        return any(filepath.lower().endswith(ext) for ext in self.extensions)
    
    def is_file_complete(self, filepath, wait_seconds=5):
        """检查文件是否完全写入"""
        try:
            if not os.path.exists(filepath):
                return False
            
            size1 = os.path.getsize(filepath)
            time.sleep(wait_seconds)
            
            if not os.path.exists(filepath):
                return False
            
            size2 = os.path.getsize(filepath)
            return size1 == size2 and size2 > 0
        except Exception as e:
            print(f"⚠️  检查文件失败: {e}")
            return False
    
    def on_created(self, event):
        """文件创建事件"""
        if event.is_directory:
            return
        
        if self.is_video_file(event.src_path):
            self.log(f"检测到新文件: {os.path.basename(event.src_path)}")
            self.pending_files.add(event.src_path)
            self.schedule_processing()
    
    def on_moved(self, event):
        """文件移动事件"""
        if event.is_directory:
            return
        
        if self.is_video_file(event.dest_path):
            self.log(f"检测到新文件（移动）: {os.path.basename(event.dest_path)}")
            self.pending_files.add(event.dest_path)
            self.schedule_processing()
    
    def schedule_processing(self):
        """调度处理任务"""
        if self.processing:
            return
        
        current_time = time.time()
        if current_time - self.last_process_time < self.cooldown_seconds:
            return
        
        self.process_videos()
    
    def schedule_retry(self, delay=30):
        """延迟重试"""
        import threading

        def retry():
            time.sleep(delay)
            if self.pending_files and not self.processing:
                self.log(f"🔄 自动重试处理 {len(self.pending_files)} 个待处理文件")
                self.process_videos()

        threading.Thread(target=retry, daemon=True).start()

    def process_videos(self):
        """处理待处理的视频"""
        if self.processing:
            self.log("⏳ 已有任务正在处理中，跳过")
            return
        
        if not self.pending_files:
            return
        
        self.processing = True
        self.last_process_time = time.time()
        
        try:
            self.log(f"等待文件完全写入...")
            time.sleep(5)
            
            # 检查文件完整性
            incomplete_files = []
            for filepath in list(self.pending_files):
                if not os.path.exists(filepath):
                    self.pending_files.remove(filepath)
                    self.log(f"⚠️  文件已不存在: {os.path.basename(filepath)}")
                elif not self.is_file_complete(filepath, wait_seconds=3):
                    incomplete_files.append(filepath)
            
            if incomplete_files:
                self.log(f"⚠️  {len(incomplete_files)} 个文件尚未完全写入,30秒后重试")
                self.processing = False
                self.schedule_retry(delay=30)
                return
            
            self.log("="*70)
            self.log(f"🚀 开始处理新视频")
            self.log(f"待处理文件: {len(self.pending_files)} 个")
            for f in self.pending_files:
                self.log(f"  - {os.path.basename(f)}")
            self.log("="*70)
            
            # 运行主程序
            result = subprocess.run(
                [sys.executable, self.script_path],
                capture_output=False,
                text=True
            )
            
            if result.returncode == 0:
                self.log("✅ 处理完成！")
                self.pending_files.clear()
            else:
                self.log(f"❌ 处理失败 (退出码: {result.returncode})")
        
        except KeyboardInterrupt:
            raise
        except Exception as e:
            self.log(f"❌ 发生错误: {e}")
            import traceback
            self.log(traceback.format_exc())
        
        finally:
            self.processing = False
            self.log("="*70)
            self.log("⏳ 继续监控中...")
            self.log("")
    
    def log(self, message):
        """日志输出"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {message}", flush=True)


def main():
    """主函数"""
    script_dir = Path(__file__).parent.parent
    os.chdir(script_dir)
    
    print("="*70)
    print("🎬 视频自动处理服务 v2.0")
    print("="*70)
    print(f"工作目录: {script_dir}")
    
    # 加载配置
    try:
        config = load_config()
    except Exception as e:
        print(f"❌ 加载配置失败: {e}")
        sys.exit(1)
    
    video_folder = config['input']['video_folder']
    extensions = config['input']['video_extensions']
    
    # 转换为绝对路径
    if not os.path.isabs(video_folder):
        video_folder = script_dir / video_folder
    
    os.makedirs(video_folder, exist_ok=True)
    
    main_script = script_dir / "scripts" / "main.py"
    
    print(f"监控目录: {video_folder}")
    print(f"视频格式: {', '.join(extensions)}")
    print(f"启动时间: {datetime.now()}")
    print("="*70)
    print("\n⏳ 正在监控中...")
    print("💡 上传新视频到 videos/ 目录，系统将自动处理")
    print("💡 按 Ctrl+C 停止服务\n")
    
    # 创建监控器
    event_handler = VideoHandler(video_folder, extensions, str(main_script))
    observer = Observer()
    observer.schedule(event_handler, str(video_folder), recursive=False)
    observer.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n⚠️  收到停止信号")
        observer.stop()
    
    observer.join()
    print("✅ 监控服务已停止")


if __name__ == "__main__":
    main()
