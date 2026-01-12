#!/usr/bin/env python3
"""
Gemini API 客户端
"""

import os
import time
from typing import Optional, Tuple
from google import genai
from google.genai import types


class GeminiClient:
    """Gemini API 客户端封装"""
    
    def __init__(self, api_key: str):
        """
        初始化客户端
        
        Args:
            api_key: Gemini API 密钥
        """
        self.api_key = api_key
        self.client = genai.Client(api_key=api_key)
    
    def generate_from_text(
        self,
        prompt: str,
        model_id: str,
        config: dict
    ) -> Optional[str]:
        """
        从文本生成内容
        
        Args:
            prompt: 提示文本
            model_id: 模型 ID
            config: 模型配置
            
        Returns:
            生成的文本，失败返回 None
        """
        print(f"⏳ 调用 {model_id}...")
        
        try:
            response = self.client.models.generate_content(
                model=model_id,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=config.get('temperature', 0.3),
                    top_p=config.get('top_p', 0.85),
                    top_k=config.get('top_k', 40),
                    max_output_tokens=config.get('max_output_tokens', 16384),
                )
            )
            
            # 验证响应
            if not response or not response.text:
                print(f"⚠️ API返回空内容")
                return None

            # 检查安全过滤
            if hasattr(response, 'prompt_feedback') and response.prompt_feedback:
                if hasattr(response.prompt_feedback, 'block_reason') and response.prompt_feedback.block_reason:
                    print(f"⚠️ 内容被过滤: {response.prompt_feedback.block_reason}")
                    return None

            return response.text.strip()
            
        except Exception as e:
            print(f"❌ API调用失败: {e}")
            return None
    
    def generate_from_video(
        self,
        video_path: str,
        prompt: str,
        model_id: str,
        config: dict,
        media_resolution: str = "MEDIUM"
    ) -> Tuple[Optional[str], Optional[float]]:
        """
        从视频生成内容
        
        Args:
            video_path: 视频文件路径
            prompt: 提示文本
            model_id: 模型 ID
            config: 模型配置
            media_resolution: 视频分辨率（LOW/MEDIUM/HIGH）
            
        Returns:
            (生成的文本, 视频时长)，失败返回 (None, None)
        """
        print(f"⏳ 上传视频到 {model_id}...")
        
        try:
            # 确定 MIME 类型
            ext = os.path.splitext(video_path)[1].lower()
            mime_types = {
                '.mp4': 'video/mp4',
                '.mkv': 'video/x-matroska',
                '.avi': 'video/x-msvideo',
                '.mov': 'video/quicktime',
                '.flv': 'video/x-flv',
                '.wmv': 'video/x-ms-wmv',
                '.webm': 'video/webm',
                '.m4v': 'video/mp4'
            }
            mime_type = mime_types.get(ext, 'video/mp4')
            
            # 上传视频
            print(f"   正在上传...")
            video_file = self.client.files.upload(
                file=video_path,
                config={'mime_type': mime_type}
            )
            
            print(f"   ✅ 上传完成: {video_file.name}")
            
            # 等待处理
            print(f"   ⏳ 等待 Gemini 处理视频...")
            while video_file.state == "PROCESSING":
                time.sleep(2)
                video_file = self.client.files.get(name=video_file.name)
            
            if video_file.state == "FAILED":
                print(f"   ❌ 视频处理失败")
                return None, None
            
            print(f"   ✅ 视频处理完成")
            
            # 获取视频时长
            duration = None
            try:
                if hasattr(video_file, 'video_metadata') and video_file.video_metadata:
                    if isinstance(video_file.video_metadata, dict):
                        duration = video_file.video_metadata.get('duration_seconds')
                    else:
                        duration = getattr(video_file.video_metadata, 'duration_seconds', None)
                
                if duration:
                    print(f"   📹 视频时长: {duration:.1f}秒 ({duration/60:.1f}分钟)")
            except:
                pass
            
            # 生成内容
            print(f"   ⏳ 正在分析视频并生成总结...")
            
            response = self.client.models.generate_content(
                model=model_id,
                contents=[video_file, prompt],
                config=types.GenerateContentConfig(
                    temperature=config.get('temperature', 0.3),
                    top_p=config.get('top_p', 0.85),
                    top_k=config.get('top_k', 40),
                    max_output_tokens=config.get('max_output_tokens', 16384),
                    media_resolution=f'MEDIA_RESOLUTION_{media_resolution}'
                )
            )
            
            # 验证响应
            if not response or not response.text:
                print(f"⚠️ API返回空内容")
                self._cleanup_file(video_file.name)
                return None, None
            
            # 检查安全过滤
            if hasattr(response, 'prompt_feedback') and response.prompt_feedback:
                if hasattr(response.prompt_feedback, 'block_reason') and response.prompt_feedback.block_reason:
                    print(f"⚠️ 内容被过滤: {response.prompt_feedback.block_reason}")
                    self._cleanup_file(video_file.name)
                    return None, None
            
            # 清理上传的文件
            self._cleanup_file(video_file.name)
            
            return response.text.strip(), duration
            
        except Exception as e:
            print(f"❌ API调用失败: {e}")
            import traceback
            traceback.print_exc()
            return None, None
    
    def _cleanup_file(self, file_name: str):
        """
        清理上传的文件
        
        Args:
            file_name: 文件名
        """
        try:
            self.client.files.delete(name=file_name)
            print(f"   🗑️  已清理上传文件")
        except:
            pass
