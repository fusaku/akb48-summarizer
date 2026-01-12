#!/usr/bin/env python3
"""
格式化输出工具
"""

import re
from typing import List, Dict


def create_timeline(segments: List[Dict], num_points: int = 10) -> List[Dict]:
    """
    生成时间轴
    
    Args:
        segments: 转录片段列表 [{'start': float, 'end': float, 'text': str}, ...]
        num_points: 生成的时间点数量
        
    Returns:
        时间轴列表 [{'time': str, 'seconds': int, 'text': str}, ...]
    """
    if not segments:
        return []
    
    total = len(segments)
    step = max(1, total // num_points)
    
    timeline = []
    for i in range(0, total, step):
        if i < total:
            seg = segments[i]
            seconds = int(seg['start'])
            
            h = seconds // 3600
            m = (seconds % 3600) // 60
            s = seconds % 60
            
            time_str = f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"
            
            timeline.append({
                'time': time_str,
                'seconds': seconds,
                'text': seg['text'].strip()
            })
    
    return timeline


def generate_youtube_comment(summary: str, timeline: List[Dict]) -> str:
    """
    生成 YouTube 评论
    
    Args:
        summary: 总结文本
        timeline: 时间轴列表
        
    Returns:
        YouTube 评论文本
    """
    comment = "📝 動画の要約\n\n"
    comment += summary + "\n\n"
    comment += "⏰ タイムスタンプ：\n"
    
    for item in timeline:
        text = item['text'][:60]
        comment += f"{item['time']} {text}\n"
    
    comment += "\n---\n"
    comment += "※この要約は自動生成されました"
    
    return comment


def generate_youtube_simple(summary: str) -> str:
    """
    从详细总结生成 YouTube 简洁版（备用方案）
    
    Args:
        summary: 详细总结文本
        
    Returns:
        YouTube 简洁版文本
    """
    # 提取主要话题
    topics = []
    lines = summary.split('\n')
    
    for line in lines:
        # 匹配 "1. **话题**" 或 "**话题**" 格式
        match = re.search(r'\*\*([^*]+)\*\*', line)
        if match and len(topics) < 5:
            topic = match.group(1).strip()
            if len(topic) > 3:
                topics.append(topic)
    
    # 提取概要
    overview = ""
    capture = False
    for line in lines:
        if '## 概要' in line or '概要' in line:
            capture = True
            continue
        if capture:
            if line.startswith('#'):
                break
            if line.strip():
                overview += line.strip() + " "
    
    # 如果没提取到，用前两句
    if not overview:
        sentences = summary.split('。')
        overview = '。'.join(sentences[:2]) + '。'
    
    # 生成话题列表
    if topics:
        topics_text = '\n'.join(f"• {topic}" for topic in topics[:5])
    else:
        topics_text = "• 配信の内容をお楽しみください"
    
    # 固定模板
    youtube = f"""📝 はるpyonの配信まとめ

{overview.strip()[:150]}{'...' if len(overview) > 150 else ''}

💡 この配信の見どころ：
{topics_text}

ぜひご覧ください✨

※ この要約は自動生成されました"""
    
    return youtube
