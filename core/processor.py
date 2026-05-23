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
        """视频直传模式"""
        try:
            # 🆕 获取优化策略
            strategy = self.optimizer.get_strategy(video_path)
            
            if strategy is None:
                logger.error(f"\n❌ 视频过长，无法处理")
                return False
            
            # 🆕 根据策略处理视频
            original_path = video_path
            is_temp = False
            processed_path = video_path
            
            # 处理：加速或提取音频
            # 并行处理：同时提取视频和音频
            transcribe_enabled = self.config.get('processing', {}).get('transcribe_audio', False)
            audio_path_for_transcribe = [None]  # 用list传引用
            transcript_result_ref = [None]      # 转文字结果
            
            def prepare_audio_and_transcribe():
                if transcribe_enabled:
                    logger.info(f"   🎵 [并行] 提取文字起こし用音频...")
                    audio_path = extract_audio(original_path, speedup=1.0)
                    audio_path_for_transcribe[0] = audio_path
                    if audio_path:
                        logger.info(f"   🎙️ [并行] 开始音频转文字...")
                        transcript_result_ref[0] = self.model_manager.transcribe_from_audio(audio_path)
                        logger.info(f"   ✅ [并行] 音频转文字完成")

            # 启动音频提取线程
            audio_thread = threading.Thread(target=prepare_audio_and_transcribe)
            audio_thread.start()

            # 主线程处理视频（总结用）
            if strategy['audio_only']:
                logger.info(f"\n🎵 第5档: 提取总结用音频")
                processed_path = extract_audio(video_path, strategy['speedup'])
                is_temp = (processed_path != original_path)
            elif strategy['speedup'] != 1.0:
                logger.info(f"\n⚡ 视频加速: {strategy['speedup']}x")
                processed_path = speed_up_video(video_path, strategy['speedup'])
                is_temp = (processed_path != original_path)
            
            # 🆕 调用 API 生成（传递 fps 参数）
            logger.info(f"\n📹 分析{'音频' if strategy['audio_only'] else '视频'}: {os.path.basename(original_path)}")
            full_response, model_name, duration = self.model_manager.summarize_from_video(
                processed_path,
                fps=strategy['fps']  # 🆕 传递 fps
            )
            # 等待音频转文字完成（与视频总结并行执行）
            logger.info(f"   ⏳ 等待音频转文字完成...")
            audio_thread.join()
            logger.info(f"   ✅ 两个任务均完成")
            
            # 清理临时文件
            if is_temp:
                try:
                    os.unlink(processed_path)
                    logger.info(f"   🗑️  已清理临时文件")
                except:
                    pass
                
            if not full_response:
                logger.error(f"\n❌ {'音频' if strategy['audio_only'] else '视频'}分析失败")
                return False
            
            # 分割两个版本
            detailed_version, youtube_version = Summarizer.parse_dual_summary(full_response)
            # 🆕 备份原始版本用于保存
            invalid_raw_content = None
            
            # 2. 验证逻辑
            if not detailed_version or not youtube_version:
                logger.warning(f"⚠️  分割失败，使用备用方案")
                detailed_version = full_response
                youtube_version = generate_youtube_simple(detailed_version)
                invalid_raw_content = full_response # 保存整个 AI 回复
            elif not Summarizer.validate_youtube_format(youtube_version):
                logger.warning(f"⚠️  YouTube 版格式验证失败，使用代码生成")
                invalid_raw_content = youtube_version # 只保存那个格式不对的版本
                youtube_version = generate_youtube_simple(detailed_version)
            
            # 显示结果
            logger.info(f"\n{'='*70}")
            logger.info(f"📋 详细版:")
            logger.info(f"{'='*70}")
            logger.info(detailed_version[:400] + "..." if len(detailed_version) > 400 else detailed_version)
            logger.info(f"{'='*70}\n")
            
            logger.info(f"\n{'='*70}")
            logger.info(f"📺 YouTube 版:")
            logger.info(f"{'='*70}")
            logger.info(youtube_version)
            logger.info(f"{'='*70}\n")
            
            # 保存结果
            # 文字起こし
            transcript = f"[{'音声のみ' if strategy['audio_only'] else '動画直接分析'}モード - 文字起こしなし]"
            timeline = []

            transcript_result = None
            if transcribe_enabled:
                audio_path = audio_path_for_transcribe[0]
                transcript_result = transcript_result_ref[0]

                # 两个都结束后再清理音频临时文件
                if audio_path and audio_path != original_path:
                    try:
                        os.unlink(audio_path)
                        logger.info(f"   🗑️  已清理音频临时文件")
                    except:
                        pass
                    
                if transcript_result:
                    transcript = transcript_result
                    logger.info(f"✅ 文字起こし完了 ({len(transcript_result):,} 文字)")
                else:
                    logger.warning(f"⚠️ 文字起こし失敗、スキップ")
            
            output_dir = self.config['output_dir']
            # 从 config 获取开关（默认为 True）

            save_raw_enabled = self.config.get('processing', {}).get('save_raw_on_fail', True)
            groq_model = self.config.get('groq', {}).get('model', '')
            transcript_model = f"Groq {groq_model}" if groq_model and transcript_result else "Gemini"

            detailed_txt, youtube_txt, json_file = save_results(
                original_path, transcript, detailed_version, timeline,
                youtube_version, model_name, output_dir,
                raw_content=invalid_raw_content if save_raw_enabled else None,
                transcript_model=transcript_model
            )
            
            logger.info(f"💾 结果已保存:")
            logger.info(f"   📄 详细版: {os.path.basename(detailed_txt)}")
            logger.info(f"   📺 YouTube版: {os.path.basename(youtube_txt)}")
            
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
