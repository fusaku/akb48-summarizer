#!/usr/bin/env python3
"""
模型管理器 - 统一管理所有 AI 模型
"""

import os
import time
import requests
import json
from typing import Optional, Tuple, Dict, Any
from pathlib import Path

from services import GeminiClient


class ModelManager:
    """AI 模型管理器"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化模型管理器
        
        Args:
            config: 配置字典
        """
        self.config = config
        
        # 加载 Gemini API 密钥
        self.gemini_client = None
        try:
            key_file = config['gemini_api_key_file']
            with open(key_file, 'r') as f:
                api_key = f.read().strip()
            self.gemini_client = GeminiClient(api_key)
        except Exception as e:
            print(f"⚠️  无法加载Gemini API密钥: {e}")
        
        # 获取启用的模型列表
        self.models = [
            m for m in config['summarization_models'] 
            if m.get('enabled', True)
        ]
        
        print(f"✅ 模型管理器初始化完成")
        print(f"   已启用 {len(self.models)} 个模型")
        for i, m in enumerate(self.models, 1):
            print(f"   {i}. {m['name']} ({m['type']})")
    
    def summarize_from_text(
        self,
        text: str,
        duration: float
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        从文本生成总结
        
        Args:
            text: 转录文本
            duration: 视频时长（秒）
            
        Returns:
            (总结文本, 模型名称)，失败返回 (None, None)
        """
        print(f"\n🤖 开始AI总结...")
        print(f"   文本长度: {len(text):,} 字符")
        print(f"   视频时长: {duration/60:.1f} 分钟\n")
        
        prompt = self._create_text_prompt(text, duration)
        
        # 按优先级尝试每个模型
        for i, model_config in enumerate(self.models, 1):
            model_name = model_config['name']
            model_type = model_config['type']
            
            print(f"{'='*70}")
            print(f"尝试模型 {i}/{len(self.models)}: {model_name}")
            print(f"类型: {model_type}")
            print(f"说明: {model_config.get('notes', 'N/A')}")
            print(f"{'='*70}\n")
            
            try:
                if model_type == 'gemini':
                    summary = self._call_gemini_text(prompt, model_config)
                elif model_type == 'ollama':
                    summary = self._call_ollama(prompt, model_config)
                else:
                    print(f"❌ 未知模型类型: {model_type}")
                    continue
                
                if summary:
                    print(f"\n✅ 成功！使用模型: {model_name}\n")
                    return summary, model_name
                    
            except Exception as e:
                print(f"❌ {model_name} 失败: {e}\n")
                continue
        
        print(f"❌ 所有模型都失败了")
        return None, None
    
    def summarize_from_video(
        self,
        video_path: str,
        fps: float = None  # 🆕 添加 fps 参数
    ) -> Tuple[Optional[str], Optional[str], Optional[float]]:
        """
        从视频直接生成总结
        
        Args:
            video_path: 视频文件路径
            
        Returns:
            (总结文本, 模型名称, 视频时长)，失败返回 (None, None, None)
        """
        print(f"\n🎬 直接视频分析模式")
        print(f"{'='*70}")
        
        if not os.path.exists(video_path):
            print(f"❌ 视频文件不存在: {video_path}")
            return None, None, None
        
        file_size = os.path.getsize(video_path) / (1024 * 1024)
        print(f"📹 视频文件: {os.path.basename(video_path)}")
        print(f"📊 文件大小: {file_size:.1f} MB")
        
        # 只尝试 Gemini 模型
        gemini_models = [m for m in self.models if m['type'] == 'gemini']
        
        if not gemini_models:
            print(f"❌ 没有可用的 Gemini 模型")
            return None, None, None
        
        print(f"🔍 将尝试 {len(gemini_models)} 个 Gemini 模型\n")
        
        prompt = self._create_video_prompt()
        media_res = self.config.get('processing', {}).get('media_resolution', 'MEDIUM')
        
        # 按优先级尝试
        for i, model_config in enumerate(gemini_models, 1):
            model_name = model_config['name']
            
            print(f"{'='*70}")
            print(f"尝试模型 {i}/{len(gemini_models)}: {model_name}")
            print(f"说明: {model_config.get('notes', 'N/A')}")
            print(f"{'='*70}\n")
            
            try:
                summary, duration = self.gemini_client.generate_from_video(
                    video_path,
                    prompt,
                    model_config['model_id'],
                    model_config['config'],
                    media_res,
                    fps  # 🆕 传递 fps 参数
                )
                
                if summary:
                    print(f"\n✅ 成功！使用模型: {model_name}\n")
                    return summary, model_name, duration
                    
            except Exception as e:
                print(f"❌ {model_name} 失败: {e}\n")
                import traceback
                traceback.print_exc()
                continue
        
        print(f"❌ 所有 Gemini 模型都失败了")
        return None, None, None
    
    def _call_gemini_text(self, prompt: str, model_config: Dict[str, Any]) -> Optional[str]:
        """调用 Gemini API（文本模式）"""
        if not self.gemini_client:
            raise Exception("Gemini API客户端未初始化")
        
        return self.gemini_client.generate_from_text(
            prompt,
            model_config['model_id'],
            model_config['config']
        )
    
    def _call_ollama(self, prompt: str, model_config: Dict[str, Any]) -> Optional[str]:
        """调用 Ollama 本地模型"""
        api_url = model_config.get('api_url', 'http://localhost:11434/api/generate')
        model_id = model_config['model_id']
        config = model_config['config']
        
        print(f"⏳ 调用本地 {model_id}...")
        print(f"   (这可能需要10-15分钟，请耐心等待)\n")
        
        payload = {
            "model": model_id,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": config.get('temperature', 0.3),
                "top_p": config.get('top_p', 0.85),
                "top_k": config.get('top_k', 30),
                "repeat_penalty": config.get('repeat_penalty', 1.2),
                "num_predict": config.get('num_predict', 2000),
                "num_ctx": config.get('num_ctx', 8192)
            }
        }
        
        print(f"{'='*70}")
        
        try:
            response = requests.post(api_url, json=payload, stream=True, timeout=30)
            
            summary = ""
            last_activity = time.time()
            
            for line in response.iter_lines():
                # 检查超时
                if time.time() - last_activity > 120:
                    print(f"\n⚠️ 流式响应超时（2分钟无数据）")
                    return None
                
                if line:
                    last_activity = time.time()
                    try:
                        data = json.loads(line)
                        token = data.get('response', '')
                        summary += token
                        print(token, end='', flush=True)
                        
                        if data.get('done', False):
                            break
                    except:
                        continue
            
            print(f"\n{'='*70}\n")
            return summary.strip() if summary else None
            
        except requests.exceptions.Timeout:
            print(f"⚠️ Ollama 连接超时")
            return None
        except Exception as e:
            print(f"❌ Ollama 错误: {e}")
            return None
    
    def _create_text_prompt(self, text: str, duration: float) -> str:
        """生成文本总结提示词"""
        minutes = int(duration // 60)
        seconds = int(duration % 60)
        
        return f"""あなたは日本語の動画内容を正確に要約する専門家です。
この動画は{minutes}分{seconds}秒です。

以下の文字起こし内容を注意深く読み、視聴者に最も役立つ要約を作成してください。

【要求事項】
1. 事実を正確に反映すること（推測や創作をしない）
2. 重要な情報を漏らさないこと
3. 適切な構造で分かりやすく整理すること
4. 自然で読みやすい日本語で書くこと
5. ⭐ 文字起こしに書かれていない内容は絶対に追加しない

【要約の形式】
## 概要
（動画全体の内容を2-3文で簡潔に説明）

## 主なトピック
1. **[トピック1のタイトル]**
   - 重要なポイント

2. **[トピック2のタイトル]**
   - 重要なポイント

（必要に応じて3-5個のトピック）

## 重要なポイント・結論
（特に重要な内容、結論、印象的な発言や具体的な数字など）

---
文字起こし内容：
{text}

---
要約："""
    
    def _create_video_prompt(self) -> str:
        """生成视频分析提示词"""
        return """あなたはAKB48、特にチーム8と橋本陽菜（愛称：はるpyon）に詳しい熱心なファンです。

⚠️ 最重要ルール：動画で見聞きした内容「だけ」を書く
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
❌ 禁止：背景知識や推測を加える
❌ 禁止：日付・年齢・チーム名などを推測で補完する
❌ 禁止：「おそらく」「〜と思われる」等の推測表現
✅ OK：動画内で明確に言及された内容のみ
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【具体例】
✅ 良い：「誕生日のお祝いをした」
❌ 悪い：「橋本陽菜の誕生日（3月5日）のお祝いをした」

✅ 良い：「メンバーと食事に行った」
❌ 悪い：「チーム8のメンバーと食事に行った」

⭐ 人名を書く時、括弧内に読み仮名や愛称を追加しないでください。
例：❌「水島美結（みずみん）」→ ✅「水島美結」または「みずみん」

この動画を視聴し、以下の2つを作成してください：

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 パート1：詳細版（必ず以下の形式を守る）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## 概要
（動画全体の内容を伝える紹介文）

## 主なトピック
1. **[トピック1]**
   - 詳細な内容とエピソード

2. **[トピック2]**
   - 詳細な内容とエピソード

（内容に応じて増減OK）

## 重要なポイント・結論
（重要な内容、具体的な発言や数字など）

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📺 パート2：YouTube投稿用（必ず以下の形式を守る）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📝 [配信のタイトル]

[配信の雰囲気を伝える紹介文]

💡 この配信の見どころ：
- [見どころ1]
- [見どころ2]
- [見どころ3]
（内容に応じて増減OK）

[視聴を促す一言]

※ この要約は自動生成されました

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【要求事項】
1. 固有名詞を正確に聞き取る
2. 動画で見聞きした内容だけを書く（推測・創作・背景知識の追加は厳禁）
3. 詳細版は具体的に書く
4. 必ず指定の形式を守る

【出力形式】必ず以下の形式で出力してください：

=== 詳細版 ===
（パート1の内容）

=== YouTube版 ===
（パート2の内容）

⚠️ 重要：
- 必ず「=== 詳細版 ===」から始めてください
- 前置き文章は一切書かないでください
- 上記の2つのパートだけを出力してください
- 動画で言及されていない情報は一切書かないでください"""