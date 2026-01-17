#!/usr/bin/env python3
"""
文件操作工具
"""

import yaml
import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any


def load_config(config_path: str = None) -> Dict[str, Any]:
    """
    加载配置文件
    
    Args:
        config_path: 配置文件路径，默认为 ../config/config.yaml（相对于脚本目录）
    """
    if config_path is None:
        # 假设从 scripts/ 目录运行
        script_dir = Path(__file__).parent.parent
        config_path = script_dir / "config" / "config.yaml"
    
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def get_video_files(config: Dict[str, Any]) -> List[str]:
    """
    获取视频文件列表
    
    Args:
        config: 配置字典
        
    Returns:
        视频文件路径列表
    """
    input_config = config['input']
    mode = input_config.get('mode', 'folder')
    
    if mode == 'single':
        # 单文件模式
        video_file = input_config.get('video_file')
        if video_file and os.path.exists(video_file):
            return [video_file]
        return []
    
    # 文件夹模式
    video_folder = input_config.get('video_folder', './videos')
    extensions = input_config.get('video_extensions', ['.mp4'])
    recursive = input_config.get('recursive', False)
    
    # 相对路径转换
    if not os.path.isabs(video_folder):
        script_dir = Path(__file__).parent.parent
        video_folder = script_dir / video_folder
    
    if not os.path.exists(video_folder):
        return []
    
    video_files = []
    
    if recursive:
        # 递归扫描
        for root, dirs, files in os.walk(video_folder):
            for file in files:
                if any(file.lower().endswith(ext) for ext in extensions):
                    video_files.append(os.path.join(root, file))
    else:
        # 只扫描当前目录
        for file in os.listdir(video_folder):
            file_path = os.path.join(video_folder, file)
            if os.path.isfile(file_path):
                if any(file.lower().endswith(ext) for ext in extensions):
                    video_files.append(file_path)
    
    # 排序
    video_files.sort()
    return video_files


def load_processed_log(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    加载已处理记录
    
    Args:
        config: 配置字典
        
    Returns:
        处理记录字典
    """
    processing_config = config.get('processing', {})
    log_file = processing_config.get('processed_log', './outputs/processed.json')
    
    # 相对路径转换
    if not os.path.isabs(log_file):
        script_dir = Path(__file__).parent.parent
        log_file = script_dir / log_file
    
    if os.path.exists(log_file):
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    
    return {
        'videos': {},
        'created_at': datetime.now().isoformat()
    }


def save_processed_log(log: Dict[str, Any], config: Dict[str, Any]) -> None:
    """
    保存已处理记录
    
    Args:
        log: 处理记录字典
        config: 配置字典
    """
    processing_config = config.get('processing', {})
    log_file = processing_config.get('processed_log', './outputs/processed.json')
    
    # 相对路径转换
    if not os.path.isabs(log_file):
        script_dir = Path(__file__).parent.parent
        log_file = script_dir / log_file
    
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    
    with open(log_file, 'w', encoding='utf-8') as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def save_results(
    video_path: str,
    transcript: str,
    summary: str,
    timeline: List[Dict],
    youtube_comment: str,
    model_name: str,
    output_dir: str = "./outputs"
) -> tuple[str, str]:
    """
    保存结果（包括视频名）
    
    Args:
        video_path: 视频路径
        transcript: 转录文本
        summary: 总结文本
        timeline: 时间轴列表
        youtube_comment: YouTube 评论
        model_name: 使用的模型名称
        output_dir: 输出目录
        
    Returns:
        (txt文件路径, json文件路径)
    """
    # 相对路径转换
    if not os.path.isabs(output_dir):
        script_dir = Path(__file__).parent.parent
        output_dir = script_dir / output_dir
    
    os.makedirs(output_dir, exist_ok=True)
    
    # 使用视频文件名作为前缀
    video_name = Path(video_path).stem
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # 文件1: 详细版
    detailed_txt = os.path.join(output_dir, f"{video_name}_{timestamp}_detailed.txt")
    with open(detailed_txt, 'w', encoding='utf-8') as f:
        f.write("="*70 + "\n")
        f.write(f"動画: {os.path.basename(video_path)}\n")
        f.write(f"生成時間: {datetime.now()}\n")
        f.write(f"使用モデル: {model_name}\n")
        f.write("="*70 + "\n\n")

        f.write("【AI要約（詳細版）】\n")
        f.write("-"*70 + "\n")
        f.write(summary + "\n\n")

        f.write("【タイムライン】\n")
        f.write("-"*70 + "\n")
        for item in timeline:
            f.write(f"{item['time']} - {item['text']}\n")
        f.write("\n")

        f.write("【完全な文字起こし】\n")
        f.write("-"*70 + "\n")
        f.write(transcript + "\n")

    # 文件2: YouTube版
    youtube_txt = os.path.join(output_dir, f"{video_name}_{timestamp}_youtube.txt")
    with open(youtube_txt, 'w', encoding='utf-8') as f:
        f.write(youtube_comment)
    
    # JSON文件
    json_file = os.path.join(output_dir, f"{video_name}_{timestamp}.json")
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump({
            'video': os.path.basename(video_path),
            'summary': summary,
            'timeline': timeline,
            'transcript': transcript,
            'youtube_comment': youtube_comment,
            'model': model_name,
            'stats': {
                'char_count': len(transcript),
                'segment_count': len(timeline),
                'generated_at': datetime.now().isoformat()
            }
        }, f, ensure_ascii=False, indent=2)
    
    return detailed_txt, youtube_txt, json_file
