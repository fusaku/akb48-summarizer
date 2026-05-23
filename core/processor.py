#!/usr/bin/env python3
"""
视频处理器 - 协调转录、总结、输出等所有流程
"""

import os
import threading
import logging
from typing import Dict, Any, Tuple
from pathlib import Path

from utils import (
    save_results, 
    create_timeline, 
    generate_youtube_simple, 
    VideoInfo, 
    speed_up_video,
    extract_audio
    )
from utils.video_optimizer import VideoOptimizer
from .transcriber import Transcriber
from .summarizer import Summarizer
from models import ModelManager
logger = logging.getLogger(__name__)

class VideoProcessor:
    """视频处理协调器"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化处理器
        
        Args:
            config: 配置字典
        """
        self.config = config
        self.use_video_mode = config.get('processing', {}).get('use_video_direct_analysis', False)
        
        # 初始化模块
        self.model_manager = ModelManager(config)
        self.optimizer = VideoOptimizer() # 🆕 添加优化器
        
        # 只在 Whisper 模式下初始化转录器
        self.transcriber = None
        if not self.use_video_mode:
            self.transcriber = Transcriber(config)
    
    def process(self, video_path: str) -> bool:
        """
        处理单个视频
        
        Args:
            video_path: 视频文件路径
            
        Returns:
            是否成功
        """
        video_name = os.path.basename(video_path)
        
        logger.info(f"\n{'='*70}")
        logger.info(f"📹 处理视频: {video_name}")
        logger.info(f"{'='*70}")
        
        # 检查视频信息
        info = VideoInfo(video_path)
        logger.info(f"\n📊 视频信息:")
        logger.info(f"   时长: {info.duration_minutes:.1f} 分钟")
        logger.info(f"   大小: {info.file_size_mb:.1f} MB")
        
        # 检查是否需要分段（目前只警告）
        segment_threshold = self.config.get('processing', {}).get('segment_threshold', 90)
        if info.should_segment(segment_threshold):
            logger.warning(f"\n⚠️  视频时长 ({info.duration_minutes:.1f} 分钟) 超过阈值 ({segment_threshold} 分钟)")
            logger.warning(f"⚠️  当前版本暂不支持自动分段，可能会失败")
            logger.warning(f"⚠️  建议手动分割视频或等待后续更新")
        
        # 根据模式处理
        if self.use_video_mode:
            logger.info(f"\n🎬 模式: 视频直传（Gemini 直接分析）")
            return self._process_video_direct(video_path)
        else:
            logger.info(f"\n📝 模式: Whisper 转录 + AI 总结")
            return self._process_whisper(video_path)
    
    def _process_video_direct(self, video_path: str) -> bool:
        """视频直传模式（极简闪电保底版：不重压视频，云端报错秒切纯音频）"""
        try:
            # 1. 获取优化策略
            strategy = self.optimizer.get_strategy(video_path)
            if strategy is None:
                logger.error(f"\n❌ 视频过长，无法处理")
                return False
            
            original_path = video_path
            video_name = Path(video_path).stem
            output_dir = self.config['output_dir']
            os.makedirs(output_dir, exist_ok=True)

            # 文字起こし（转录）缓存处理路径
            transcript_cache_path = os.path.join(output_dir, f"{video_name}_transcript_cache.txt")
            transcript_result = None
            transcribe_enabled = self.config.get('processing', {}).get('transcribe_audio', False)

            # ---- 🚀 独立提前音频转文字并支持复用 ----
            if transcribe_enabled:
                if os.path.exists(transcript_cache_path):
                    logger.warning(f"\nℹ️  检测到已存在该视频的文字起こし缓存，直接复用...")
                    with open(transcript_cache_path, 'r', encoding='utf-8') as f:
                        transcript_result = f.read()
                else:
                    logger.info(f"\n🎙️  音频文字起こし开始...")
                    audio_path_for_transcribe = extract_audio(original_path, speedup=1.0)
                    is_audio_temp = (audio_path_for_transcribe is not None and audio_path_for_transcribe != original_path)
                    
                    if audio_path_for_transcribe:
                        transcript_result = self.model_manager.transcribe_from_audio(audio_path_for_transcribe)
                        if is_audio_temp:
                            try: os.unlink(audio_path_for_transcribe)
                            except: pass
                        if transcript_result:
                            with open(transcript_cache_path, 'w', encoding='utf-8') as f:
                                f.write(transcript_result)
                            logger.info(f"✅ 文字起こし成功并已保存缓存")

            # ---- 🎬 视频直送处理 ----
            is_temp = False
            processed_path = video_path
            
            if strategy['audio_only']:
                logger.info(f"\n🎵 第5档: 提取总结用音频")
                processed_path = extract_audio(video_path, speedup=1.0)
                is_temp = (processed_path != original_path)

            # 第一轮：不做任何本地检验或转码，挺起胸膛直接原样投递原始视频文件
            logger.info(f"\n📹 投递 AI 分析{'音频' if strategy['audio_only'] else '视频'}: {os.path.basename(processed_path)}")
            full_response, model_name, duration = self.model_manager.summarize_from_video(
                processed_path,
                fps=strategy['fps']
            )
            
            # ---- 🚨 闪电保底：如果原视频投递被 Gemini 云端无情拒绝，秒切纯音频 🚨 ----
            if not full_response and not strategy['audio_only']:
                logger.warning(f"⚠️  原始视频在 Gemini 云端处理失败。立刻触发【纯音频闪电保底方案】...")
                
                if is_temp and processed_path != original_path:
                    try: os.unlink(processed_path)
                    except: pass
                
                # 秒抽一条纯音频（不重压画面，仅拷贝/转换音频轨，通常只需1-2秒）
                logger.info(f"🎵 正在提取标准音频轨道进行二次投递...")
                processed_path = extract_audio(original_path, speedup=1.0)
                is_temp = (processed_path != original_path)
                
                # 重新用纯音频投递给 Gemini（纯音频不带 fps 参数）
                full_response, model_name, duration = self.model_manager.summarize_from_video(
                    processed_path,
                    fps=None
                )
            
            # ⚠️ 分析完毕，彻底删除本地生成的临时音频文件（原视频保持不动）
            if is_temp and processed_path != original_path:
                try:
                    os.unlink(processed_path)
                    logger.warning(f"   🗑️  分析完毕：已成功删除本地临时媒体文件")
                except:
                    pass
                
            if not full_response:
                logger.error(f"\n❌ 该视频通过【视频原件】和【纯音频】双重投递均告失败，跳过本视频")
                return False
            
            # ---- 3. 分割、验证和结果保存逻辑 ----
            detailed_version, youtube_version = Summarizer.parse_dual_summary(full_response)
            invalid_raw_content = None
            
            if not detailed_version or not youtube_version:
                logger.warning(f"⚠️  分割失败，使用备用方案")
                detailed_version = full_response
                youtube_version = generate_youtube_simple(detailed_version)
                invalid_raw_content = full_response
            elif not Summarizer.validate_youtube_format(youtube_version):
                logger.warning(f"⚠️  YouTube 版格式验证失败，使用代码生成")
                invalid_raw_content = youtube_version
                youtube_version = generate_youtube_simple(detailed_version)
            
            transcript = transcript_result if transcript_result else f"[{'音声のみ' if strategy['audio_only'] else '動画直接分析'}モード - 文字起こしなし]"
            timeline = []

            save_raw_enabled = self.config.get('processing', {}).get('save_raw_on_fail', True)
            groq_model = self.config.get('groq', {}).get('model', '')
            transcript_model = f"Groq {groq_model}" if groq_model and transcript_result else "Gemini"

            detailed_txt, youtube_txt, json_file = save_results(
                original_path, transcript, detailed_version, timeline,
                youtube_version, model_name, output_dir,
                raw_content=invalid_raw_content if save_raw_enabled else None,
                transcript_model=transcript_model
            )
            logger.info(f"💾 最终结果保存成功！")
            
            # 全部跑通，销毁缓存
            if os.path.exists(transcript_cache_path):
                try: os.unlink(transcript_cache_path)
                except: pass

            return True
            
        except Exception as e:
            logger.error(f"\n❌ 处理失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _process_whisper(self, video_path: str) -> bool:
        """Whisper 转录模式"""
        try:
            # 步骤1：转录
            transcript, segments = self.transcriber.transcribe(video_path)
            
            if not transcript:
                logger.error(f"❌ 转录失败")
                return False
            
            # 步骤2：AI 总结
            logger.info(f"\n📝 步骤 2: AI总结")
            logger.info(f"{'='*70}")
            
            duration = segments[-1]['end'] if segments else 0
            summary, model_name = self.model_manager.summarize_from_text(transcript, duration)
            
            if not summary:
                logger.error(f"\n❌ 所有模型都失败了")
                
                # 只保存转录
                output_dir = self.config['output_dir']
                os.makedirs(output_dir, exist_ok=True)
                
                transcript_file = os.path.join(
                    output_dir,
                    f"transcript_only_{Path(video_path).stem}.txt"
                )
                with open(transcript_file, 'w', encoding='utf-8') as f:
                    f.write(transcript)
                
                logger.info(f"💾 转录已保存: {transcript_file}")
                return False
            
            # 显示总结
            logger.info(f"\n{'='*70}")
            logger.info(f"📋 总结结果:")
            logger.info(f"{'='*70}")
            logger.info(summary[:500] + "..." if len(summary) > 500 else summary)
            logger.info(f"{'='*70}\n")
            
            # 步骤3：生成输出
            logger.info(f"\n📝 步骤 3: 生成输出")
            logger.info(f"{'='*70}")
            
            num_points = self.config['timeline']['num_points']
            timeline = create_timeline(segments, num_points)
            youtube_comment = generate_youtube_simple(summary)
            
            logger.info(f"✅ 时间轴已生成 ({len(timeline)} 个时间点)")
            logger.info(f"✅ YouTube评论已生成")
            
            # 步骤4：保存结果
            logger.info(f"\n💾 保存结果...")
            
            output_dir = self.config['output_dir']
            detailed_txt, youtube_txt, json_file = save_results(
                video_path, transcript, summary, timeline,
                youtube_comment, model_name, output_dir
            )
            
            logger.info(f"✅ 结果已保存:")
            logger.info(f"   📄 详细版: {os.path.basename(detailed_txt)}")
            logger.info(f"   📺 YouTube版: {os.path.basename(youtube_txt)}")
            logger.info(f"   📊 JSON: {os.path.basename(json_file)}")
            
            return True
            
        except Exception as e:
            logger.error(f"\n❌ 处理失败: {e}")
            import traceback
            traceback.print_exc()
            return False
