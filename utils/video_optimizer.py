#!/usr/bin/env python3
"""
视频优化策略 - 根据视频时长决定最优处理方式
"""

import logging
from typing import Dict, Any, Optional
from .video import VideoInfo
logger = logging.getLogger(__name__)


class VideoOptimizer:
    """视频优化策略管理器"""
    
    # Token 消耗率（基于实测）
    TOKEN_RATE_VIDEO_FPS1 = 55      # 视频 fps=1.0 时，tokens/秒
    TOKEN_RATE_VIDEO_FPS05 = 27.5   # 视频 fps=0.5 时，tokens/秒
    TOKEN_RATE_VIDEO_FPS025 = 13.75  # 视频 fps=0.25 时，tokens/秒
    TOKEN_RATE_AUDIO = 32           # 音频固定 tokens/秒
    
    # 总消耗率
    RATE_FPS1 = TOKEN_RATE_VIDEO_FPS1 + TOKEN_RATE_AUDIO    # 87 tokens/秒
    RATE_FPS05 = TOKEN_RATE_VIDEO_FPS05 + TOKEN_RATE_AUDIO  # 59.5 tokens/秒
    RATE_FPS025 = TOKEN_RATE_VIDEO_FPS025 + TOKEN_RATE_AUDIO  # 45.75 tokens/秒
    RATE_AUDIO_ONLY = TOKEN_RATE_AUDIO                      # 32 tokens/秒
    
    # Token 限制
    TOKEN_LIMIT = 250000
    SAFETY_MARGIN = 0.95  # 留 5% 安全余量
    EFFECTIVE_LIMIT = TOKEN_LIMIT * SAFETY_MARGIN  # 237,500
    
    def __init__(self):
        """初始化优化器"""
        pass
    
    def get_strategy(self, video_path: str) -> Optional[Dict[str, Any]]:
        """
        根据视频时长获取最优处理策略
        
        Args:
            video_path: 视频文件路径
            
        Returns:
            策略字典，包含：
            - speedup: 加速倍数
            - fps: 视频采样率（None=默认1.0）
            - audio_only: 是否仅保留音频
            - description: 策略描述
            
            如果视频过长无法处理，返回 None
        """
        # 获取视频信息
        info = VideoInfo(video_path)
        duration_minutes = info.duration_minutes
        
        if duration_minutes == 0:
            logger.warning(f"⚠️  无法获取视频时长")
            return None
        
        logger.info(f"\n📊 视频分析:")
        logger.info(f"   时长: {duration_minutes:.1f} 分钟 ({info.duration:.0f} 秒)")
        logger.info(f"   大小: {info.file_size_mb:.1f} MB")
        
        # 根据时长选择策略
        if duration_minutes <= 40:
            strategy = self._strategy_tier1(info)
        elif duration_minutes <= 80:
            strategy = self._strategy_tier2(info)
        elif duration_minutes <= 120:
            strategy = self._strategy_tier3(info)
        elif duration_minutes <= 170:
            strategy = self._strategy_tier4(info)
        elif duration_minutes <= 240:
            strategy = self._strategy_tier5(info)
        else:
            return self._reject_too_long(info)
        
        # 验证策略
        estimated_tokens = self._estimate_tokens(info, strategy)
        strategy['estimated_tokens'] = estimated_tokens
        
        logger.info(f"\n🎯 优化策略:")
        logger.info(f"   {strategy['description']}")
        logger.info(f"   预计 Token 消耗: {estimated_tokens:,.0f}")
        
        if estimated_tokens > self.EFFECTIVE_LIMIT:
            logger.warning(f"   ⚠️  警告: 预计超出安全限制 ({self.EFFECTIVE_LIMIT:,.0f})")
        
        return strategy
    
    def _strategy_tier1(self, info: VideoInfo) -> Dict[str, Any]:
        """
        第 1 档：≤ 40 分钟
        不处理，直接上传
        """
        return {
            'speedup': 1.0,
            'fps': None,  # 使用默认 1.0
            'audio_only': False,
            'description': '第1档: 直接上传（不处理）'
        }
    
    def _strategy_tier2(self, info: VideoInfo) -> Dict[str, Any]:
        """
        第 2 档：40-80 分钟
        2倍速，保留视频
        """
        return {
            'speedup': 2.0,
            'fps': None,  # 使用默认 1.0
            'audio_only': False,
            'description': '第2档: 2倍速'
        }
    
    def _strategy_tier3(self, info: VideoInfo) -> Dict[str, Any]:
        """
        第 3 档：80-120 分钟
        2倍速 + 降低采样率
        """
        return {
            'speedup': 2.0,
            'fps': 0.5,  # 降低到 0.5 fps
            'audio_only': False,
            'description': '第3档: 2倍速 + fps=0.5'
        }
    
    def _strategy_tier4(self, info: VideoInfo) -> Dict[str, Any]:
        """
        第 4 档：120-240 分钟
        2倍速 + 纯音频
        """
        return {
            'speedup': 2.0,
            'fps': 0.25,    # 降到 0.25 fps
            'audio_only': False,
            'description': '第4档: 2倍速 + fps=0.25'
        }

    def _strategy_tier5(self, info: VideoInfo) -> Dict[str, Any]:
        """
        第 5 档：170-240 分钟
        2倍速 + 纯音频
        """
        return {
            'speedup': 2.0,
            'fps': None,
            'audio_only': True,
            'description': '第5档: 2倍速 + 纯音频'
        }
    
    def _reject_too_long(self, info: VideoInfo) -> None:
        """拒绝超长视频"""
        logger.error(f"\n❌ 视频过长，无法处理")
        logger.error(f"   当前时长: {info.duration_minutes:.1f} 分钟")
        logger.error(f"   最大支持: 240 分钟（4 小时）")
        logger.error(f"\n💡 建议:")
        logger.error(f"   1. 手动分割视频")
        logger.error(f"   2. 或使用视频编辑工具剪辑")
        return None
    
    def _estimate_tokens(self, info: VideoInfo, strategy: Dict[str, Any]) -> float:
        """
        估算 Token 消耗
        
        Args:
            info: 视频信息
            strategy: 处理策略
            
        Returns:
            预计 token 消耗
        """
        # 处理后的时长
        processed_duration = info.duration / strategy['speedup']
        
        # 根据策略计算 token
        if strategy['audio_only']:
            return processed_duration * self.RATE_AUDIO_ONLY
        elif strategy['fps'] == 0.25:  # 新增
            return processed_duration * self.RATE_FPS025  # 新增
        elif strategy['fps'] == 0.5:
            return processed_duration * self.RATE_FPS05
        else:
            return processed_duration * self.RATE_FPS1