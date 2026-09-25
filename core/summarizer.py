#!/usr/bin/env python3
"""
总结模块 - 负责解析和分割 AI 生成的总结
"""

from typing import Tuple


class Summarizer:
    """总结处理器"""
    
    @staticmethod
    def parse_dual_summary(full_response: str) -> Tuple[str, str]:
        """
        解析包含详细版和 YouTube 版的响应
        
        Args:
            full_response: 完整的 AI 响应
            
        Returns:
            (详细版, YouTube版)
        """
        detailed_version = ""
        youtube_version = ""
        
        detail_marker = "=== 詳細版 ==="
        youtube_marker = "=== YouTube版 ==="
        
        if detail_marker in full_response and youtube_marker in full_response:
            detail_start = full_response.find(detail_marker)
            youtube_start = full_response.find(youtube_marker)
            
            if detail_start >= 0 and youtube_start > detail_start:
                # 提取详细版
                detailed_version = full_response[
                    detail_start + len(detail_marker):youtube_start
                ].strip()
                
                # 提取 YouTube 版
                youtube_version = full_response[
                    youtube_start + len(youtube_marker):
                ].strip()
        
        return detailed_version, youtube_version
    
    @staticmethod
    def validate_youtube_format(text: str) -> bool:
        """
        验证 YouTube 版本格式（兼容 AI 提示词输出格式与代码生成备用格式）
        
        Args:
            text: YouTube 版本文本
            
        Returns:
            是否符合格式
        """
        if not text or not isinstance(text, str):
            return False

        text_clean = text.strip()

        # 核心必须标记：见どころ部分与自动生成声明
        has_highlights = ('💡 この配信の見どころ：' in text_clean or 'この配信の見どころ' in text_clean)
        has_disclaimer = ('※ この要約は自動生成されました' in text_clean or '※この要約は自動生成されました' in text_clean)

        # 必须包含列表项标记（支持 •、- 或 *）
        has_bullet = any(b in text_clean for b in ['•', '- ', '-\t', '* '])

        # 头部应该有合法标题或标记（支持 【...】、📝 或 Markdown 标题 #）
        has_valid_header = text_clean.startswith('📝') or text_clean.startswith('【') or text_clean.startswith('#')

        return has_highlights and has_disclaimer and has_bullet and has_valid_header
