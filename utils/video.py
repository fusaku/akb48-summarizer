#!/usr/bin/env python3
"""
视频处理工具
"""

import os
import subprocess
import tempfile
from typing import Optional


class VideoInfo:
    """视频信息类"""
    
    def __init__(self, filepath: str):
        """
        初始化视频信息
        
        Args:
            filepath: 视频文件路径
        """
        self.filepath = filepath
        self.duration = self._get_duration()
        self.file_size = os.path.getsize(filepath) if os.path.exists(filepath) else 0
    
    def _get_duration(self) -> float:
        """
        获取视频时长（秒）
        
        Returns:
            时长（秒），失败返回 0
        """
        try:
            result = subprocess.run(
                ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                 '-of', 'default=noprint_wrappers=1:nokey=1', self.filepath],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=10
            )
            return float(result.stdout.strip())
        except Exception as e:
            print(f"⚠️  无法获取视频时长: {e}")
            return 0.0
    
    @property
    def duration_minutes(self) -> float:
        """时长（分钟）"""
        return self.duration / 60
    
    @property
    def file_size_mb(self) -> float:
        """文件大小（MB）"""
        return self.file_size / (1024 * 1024)
    
    def should_segment(self, threshold_minutes: int = 75) -> bool:
        """
        判断是否需要分段
        
        Args:
            threshold_minutes: 时长阈值（分钟）
            
        Returns:
            是否需要分段
        """
        return self.duration_minutes > threshold_minutes
    
    def __repr__(self):
        return (f"VideoInfo(filepath='{os.path.basename(self.filepath)}', "
                f"duration={self.duration_minutes:.1f}min, "
                f"size={self.file_size_mb:.1f}MB)")


def speed_up_video(input_path: str, speedup: float) -> str:
    """
    使用 ffmpeg 加速视频
    
    Args:
        input_path: 原始视频路径
        speedup: 加速倍数（例如 2.0 表示 2 倍速）
    
    Returns:
        加速后的视频路径（临时文件），失败则返回原路径
    """
    if speedup == 1.0:
        return input_path
    
    print(f"⚡ 视频加速中: {speedup}x")
    
    # 创建临时文件
    temp_file = tempfile.NamedTemporaryFile(
        suffix='.mp4', 
        delete=False
    )
    output_path = temp_file.name
    temp_file.close()
    
    # 计算 PTS 和 atempo
    pts_factor = 1.0 / speedup
    
    # 构建 ffmpeg 命令
    # 注意：atempo 最大 2.0，如果需要更大倍数需要链式
    if speedup <= 2.0:
        audio_filter = f"atempo={speedup}"
    else:
        # 例如 2.5x = 2.0 * 1.25
        audio_filter = f"atempo=2.0,atempo={speedup/2.0}"
    
    cmd = [
        'ffmpeg',
        '-i', input_path,
        '-filter:v', f'setpts={pts_factor}*PTS',
        '-filter:a', audio_filter,
        '-y',  # 覆盖输出文件
        output_path
    ]
    
    # 执行命令（静默模式）
    result = subprocess.run(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False
    )
    
    if result.returncode != 0:
        print(f"⚠️  视频加速失败，使用原始视频")
        try:
            os.unlink(output_path)
        except:
            pass
        return input_path
    
    print(f"✅ 视频加速完成")
    return output_path


def check_ffmpeg_available() -> bool:
    """
    检查 ffmpeg 是否可用
    
    Returns:
        是否可用
    """
    try:
        subprocess.run(
            ['ffmpeg', '-version'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=5
        )
        return True
    except:
        return False


def check_ffprobe_available() -> bool:
    """
    检查 ffprobe 是否可用
    
    Returns:
        是否可用
    """
    try:
        subprocess.run(
            ['ffprobe', '-version'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=5
        )
        return True
    except:
        return False

def extract_audio(input_path: str, speedup: float = 1.0) -> str:
    """
    提取视频的音频轨道（可选加速）
    
    Args:
        input_path: 原始视频路径
        speedup: 音频加速倍数（例如 2.0 表示 2 倍速）
    
    Returns:
        音频文件路径（临时文件），失败则返回原路径
    """
    print(f"🎵 提取音频轨道...")
    if speedup != 1.0:
        print(f"   加速倍数: {speedup}x")
    
    # 创建临时文件
    temp_file = tempfile.NamedTemporaryFile(
        suffix='.mp3', 
        delete=False
    )
    output_path = temp_file.name
    temp_file.close()
    
    # 构建 ffmpeg 命令
    cmd = [
        'ffmpeg',
        '-i', input_path,
        '-vn',  # 不要视频轨道
        '-acodec', 'libmp3lame',
        '-q:a', '2',  # 高质量音频
    ]
    
    # 如果需要加速
    if speedup != 1.0:
        if speedup <= 2.0:
            audio_filter = f"atempo={speedup}"
        else:
            # 链式 atempo（> 2.0 需要多次）
            audio_filter = f"atempo=2.0,atempo={speedup/2.0}"
        cmd.extend(['-af', audio_filter])
    
    cmd.extend(['-y', output_path])
    
    # 执行命令（静默模式）
    result = subprocess.run(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False
    )
    
    if result.returncode != 0:
        print(f"⚠️  音频提取失败，使用原始视频")
        try:
            os.unlink(output_path)
        except:
            pass
        return input_path
    
    # 检查输出文件
    if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
        print(f"⚠️  音频文件无效，使用原始视频")
        try:
            os.unlink(output_path)
        except:
            pass
        return input_path
    
    file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"✅ 音频提取完成")
    print(f"   大小: {file_size_mb:.1f} MB")
    
    return output_path