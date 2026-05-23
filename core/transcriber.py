#!/usr/bin/env python3
"""
转录模块 - 使用 Whisper 进行高质量语音转录
"""

import os
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Tuple
from faster_whisper import WhisperModel
logger = logging.getLogger(__name__)

class Transcriber:
    """Whisper 转录器"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化转录器
        
        Args:
            config: 配置字典
        """
        self.config = config
        self.whisper_config = config['whisper']
        self.model = None
    
    def _load_vocabulary(self) -> str:
        """
        加载自定义词汇表
        
        Returns:
            提示文本
        """
        custom_vocab = self.whisper_config.get('custom_vocabulary', {})
        
        if not custom_vocab.get('enabled', False):
            return '以下は日本語の音声です。'
        
        vocab_file = custom_vocab.get('file', 'vocabulary.txt')
        
        # 相对于 config/ 目录
        config_dir = Path(__file__).parent.parent / "config"
        vocab_path = config_dir / vocab_file
        
        # 检查文件是否存在
        if not os.path.exists(vocab_path):
            logger.warning(f"⚠️  词汇表文件不存在: {vocab_path}")
            return '以下は日本語の音声です。'
        
        # 读取词汇
        try:
            with open(vocab_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # 过滤空行和注释
            terms = []
            for line in lines:
                line = line.strip()
                if line and not line.startswith('#'):
                    terms.append(line)
            
            if terms:
                vocab_text = '、'.join(terms)
                prompt = f"以下は日本語の音声です。\n{vocab_text}"
                logger.info(f"✅ 加载自定义词汇表: {len(terms)} 个词")
                return prompt
            else:
                logger.warning(f"⚠️  词汇表为空")
                return '以下は日本語の音声です。'
                
        except Exception as e:
            logger.error(f"⚠️  读取词汇表失败: {e}")
            return '以下は日本語の音声です。'
    
    def transcribe(self, video_path: str) -> Tuple[str, List[Dict[str, Any]]]:
        """
        转录视频
        
        Args:
            video_path: 视频文件路径
            
        Returns:
            (转录文本, 片段列表)
        """
        logger.info(f"\n📝 步骤 1: 高精度转录")
        logger.info(f"{'='*70}")
        
        # 加载模型
        if self.model is None:
            logger.info(f"⏳ 加载Whisper模型: {self.whisper_config['model']}")
            logger.info(f"   设备: {self.whisper_config['device']}")
            logger.info(f"   量化: {self.whisper_config['compute_type']}")
            logger.info(f"   (首次运行会下载~3GB模型)\n")
            
            self.model = WhisperModel(
                self.whisper_config['model'],
                device=self.whisper_config['device'],
                compute_type=self.whisper_config['compute_type']
            )
        
        # 准备参数
        quality = self.whisper_config['quality']
        vad = self.whisper_config['vad']
        
        vad_params = {
            'threshold': vad['threshold'],
            'min_silence_duration_ms': vad['min_silence_duration_ms']
        } if vad['enabled'] else None
        
        # 加载自定义词汇表
        initial_prompt = self._load_vocabulary()
        
        logger.info(f"⏳ 开始转录（最高质量参数）")
        logger.info(f"   - beam_size: {quality.get('beam_size', 5)}")
        logger.info(f"   - word_timestamps: 启用")
        logger.info(f"   - VAD过滤: {'启用' if vad['enabled'] else '禁用'}")
        logger.info(f"\n   请耐心等待...\n")
        
        start_time = datetime.now()
        
        # 准备转录参数
        transcribe_params = {
            'language': 'ja',
            'word_timestamps': True,
            'initial_prompt': initial_prompt,
            'beam_size': quality.get('beam_size', 5),
            'temperature': quality.get('temperature', [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]),
            'vad_filter': vad['enabled'],
        }
        
        # 添加可选参数（如果配置中有的话）
        if 'best_of' in quality:
            transcribe_params['best_of'] = quality['best_of']
        if 'patience' in quality:
            transcribe_params['patience'] = quality['patience']
        if 'compression_ratio_threshold' in quality:
            transcribe_params['compression_ratio_threshold'] = quality['compression_ratio_threshold']
        if vad_params:
            transcribe_params['vad_parameters'] = vad_params
        
        # 执行转录
        segments, info = self.model.transcribe(video_path, **transcribe_params)
        
        # 收集结果
        transcript = ""
        segments_list = []
        
        for segment in segments:
            transcript += segment.text
            segments_list.append({
                'start': segment.start,
                'end': segment.end,
                'text': segment.text
            })
        
        elapsed = (datetime.now() - start_time).total_seconds()
        
        # 显示统计
        logger.info(f"✅ 转录完成！\n")
        logger.info(f"📊 转录统计:")
        logger.info(f"   - 语言: {info.language} (置信度: {info.language_probability:.1%})")
        logger.info(f"   - 时长: {info.duration:.1f}秒 ({info.duration/60:.1f}分钟)")
        logger.info(f"   - 字符数: {len(transcript):,}")
        logger.info(f"   - 片段数: {len(segments_list)}")
        logger.info(f"   - 耗时: {elapsed:.1f}秒 ({elapsed/60:.1f}分钟)")
        
        logger.info(f"\n--- 转录预览 ---")
        preview = transcript[:300] + "..." if len(transcript) > 300 else transcript
        logger.info(preview)
        logger.info(f"--- 预览结束 ---\n")
        
        return transcript, segments_list
