#!/usr/bin/env python3
"""
模型管理器 - 统一管理所有 AI 模型
"""

import os
import time
import requests
import json
import logging
from typing import Optional, Tuple, Dict, Any
from pathlib import Path
from services import GeminiClient
logger = logging.getLogger(__name__)

class ModelManager:
    """AI 模型管理器"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        
        # 加载 Gemini API 密钥
        self.gemini_client = None
        try:
            key_file = config['gemini_api_key_file']
            with open(key_file, 'r') as f:
                api_key = f.read().strip()
            self.gemini_client = GeminiClient(api_key)
        except Exception as e:
            logger.error(f"⚠️  无法加载Gemini API密钥: {e}")
        
        # 获取启用的模型列表
        self.models = [
            m for m in config['summarization_models'] 
            if m.get('enabled', True)
        ]
        
        logger.info(f"✅ 模型管理器初始化完成")
        logger.info(f"   已启用 {len(self.models)} 个模型")
        for i, m in enumerate(self.models, 1):
            logger.info(f"   {i}. {m['name']} ({m['type']})")
    
    # ------------------------------------------------------------------
    # 文本摘要
    # ------------------------------------------------------------------

    def summarize_from_text(
        self,
        text: str,
        duration: float
    ) -> Tuple[Optional[str], Optional[str]]:
        logger.info(f"\n🤖 开始AI总结...")
        logger.info(f"   文本长度: {len(text):,} 字符")
        logger.info(f"   视频时长: {duration/60:.1f} 分钟\n")
        
        prompt = self._create_text_prompt(text, duration)
        
        for i, model_config in enumerate(self.models, 1):
            model_name = model_config['name']
            model_type = model_config['type']
            
            logger.info(f"{'='*70}")
            logger.info(f"尝试模型 {i}/{len(self.models)}: {model_name}")
            logger.info(f"类型: {model_type}")
            logger.info(f"说明: {model_config.get('notes', 'N/A')}")
            logger.info(f"{'='*70}\n")
            
            try:
                if model_type == 'gemini':
                    summary = self._call_gemini_text(prompt, model_config)
                elif model_type == 'ollama':
                    summary = self._call_ollama(prompt, model_config)
                else:
                    logger.error(f"❌ 未知模型类型: {model_type}")
                    continue
                
                if summary:
                    logger.info(f"\n✅ 成功！使用模型: {model_name}\n")
                    return summary, model_name
                    
            except Exception as e:
                logger.error(f"❌ {model_name} 失败: {e}\n")
                continue
        
        logger.error(f"❌ 所有模型都失败了")
        return None, None
    
    # ------------------------------------------------------------------
    # 视频直送分析
    # ------------------------------------------------------------------

    def summarize_from_video(
        self,
        video_path: str,
        fps: float = None
    ) -> Tuple[Optional[str], Optional[str], Optional[float]]:
        logger.info(f"\n🎬 直接视频分析模式")
        logger.info(f"{'='*70}")
        
        if not os.path.exists(video_path):
            logger.error(f"❌ 视频文件不存在: {video_path}")
            return None, None, None
        
        file_size = os.path.getsize(video_path) / (1024 * 1024)
        logger.info(f"📹 视频文件: {os.path.basename(video_path)}")
        logger.info(f"📊 文件大小: {file_size:.1f} MB")
        
        gemini_models = [m for m in self.models if m['type'] == 'gemini']
        
        if not gemini_models:
            logger.error(f"❌ 没有可用的 Gemini 模型")
            return None, None, None
        
        logger.info(f"🔍 将尝试 {len(gemini_models)} 个 Gemini 模型\n")
        
        prompt = self._create_video_prompt()
        media_res = self.config.get('processing', {}).get('media_resolution', 'MEDIUM')
        
        for i, model_config in enumerate(gemini_models, 1):
            model_name = model_config['name']
            
            logger.info(f"{'='*70}")
            logger.info(f"尝试模型 {i}/{len(gemini_models)}: {model_name}")
            logger.info(f"说明: {model_config.get('notes', 'N/A')}")
            logger.info(f"{'='*70}\n")
            
            try:
                summary, duration = self.gemini_client.generate_from_video(
                    video_path,
                    prompt,
                    model_config['model_id'],
                    model_config['config'],
                    media_res,
                    fps
                )
                
                if summary:
                    logger.info(f"\n✅ 成功！使用模型: {model_name}\n")
                    return summary, model_name, duration
                    
            except Exception as e:
                logger.info(f"❌ {model_name} 失败: {e}\n")
                import traceback
                traceback.print_exc()
                continue
        
        logger.info(f"❌ 所有 Gemini 模型都失败了")
        return None, None, None
    
    # ------------------------------------------------------------------
    # 音声転写 + Gemini 後処理（メイン変更箇所）
    # ------------------------------------------------------------------

    def transcribe_from_audio(self, audio_path: str) -> Optional[str]:
        """
        音声ファイルから転写テキストを生成する。

        処理フロー:
          1. Groq Whisper で転写（silence-aware チャンク分割）
          2. Gemini で句読点追加・可読性向上（タイムスタンプは保持）
          3. 結果を返す

        Returns:
            転写テキスト or None
        """
        logger.info(f"\n{'='*70}")
        logger.info(f"🎙️  音声転写パイプライン開始")
        logger.info(f"{'='*70}")

        # Step 1: Groq 転写
        raw_transcript = self._transcribe_with_groq(audio_path)

        if not raw_transcript:
            logger.error(f"\n❌ Groq転写に失敗しました")
            return None

        logger.info(f"\n   📄 Groq転写テキスト:")
        logger.info(f"   文字数: {len(raw_transcript):,} 文字")
        preview = raw_transcript[:300].replace('\n', ' ')
        logger.info(f"   先頭300字: {preview}...")

        # Step 2: Gemini 後処理
        polished = self._polish_with_gemini(raw_transcript, audio_path)

        if polished:
            improvement = len(polished) - len(raw_transcript)
            logger.info(f"\n   ✅ Gemini後処理完了")
            logger.info(f"   文字数変化: {len(raw_transcript):,} → {len(polished):,}"
                  f" ({improvement:+d} 文字)")
            return polished
        else:
            logger.warning(f"\n   ⚠️  Gemini後処理失敗 → Groq生テキストをそのまま使用")
            return raw_transcript

    def _transcribe_with_groq(self, audio_path: str) -> Optional[str]:
        """Groq Whisper で転写を実行する内部メソッド"""
        groq_config = self.config.get('groq', {})
        groq_key_file = groq_config.get('api_keys_file', '')

        if not groq_key_file:
            logger.warning(f"   ⚠️  Groq設定なし → スキップ")
            return None

        try:
            from services import GroqTranscriber
            groq = GroqTranscriber(self.config)
            return groq.transcribe(audio_path, self.config)
        except Exception as e:
            logger.error(f"   ❌ Groq転写で例外発生: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _polish_with_gemini(self, raw_text: str, audio_path: str) -> Optional[str]:
        """
        Gemini で転写テキストの句読点追加・可読性向上を行う。

        ルール:
          - [hh:mm:ss] 形式のタイムスタンプは絶対に移動・削除しない
          - 内容（事実・固有名詞）は変更しない
          - 句読点の追加・誤字修正・読みやすい区切りへの調整のみ行う
        """
        if not self.gemini_client:
            logger.warning(f"   ⚠️  Geminiクライアント未初期化 → スキップ")
            return None

        gemini_models = [m for m in self.models if m['type'] == 'gemini']
        if not gemini_models:
            logger.warning(f"   ⚠️  利用可能なGeminiモデルなし → スキップ")
            return None

        logger.info(f"\n{'='*70}")
        logger.info(f"   ✨ Gemini後処理: 句読点追加・可読性向上")
        logger.info(f"{'='*70}")
        logger.info(f"   入力文字数: {len(raw_text):,} 文字")
        logger.info(f"   ※ タイムスタンプ [hh:mm:ss] は保持します")

        prompt = self._create_polish_prompt(raw_text)

        for i, model_config in enumerate(gemini_models, 1):
            model_name = model_config['name']
            logger.info(f"\n   [{i}/{len(gemini_models)}] {model_name} で試行中...")

            try:
                result, _ = self.gemini_client.generate_from_video(
                    audio_path,
                    prompt,
                    model_config['model_id'],
                    model_config['config'],
                    fps=None
                )

                if result:
                    # タイムスタンプが失われていないか検証
                    original_ts_count = raw_text.count('[')
                    result_ts_count = result.count('[')

                    logger.info(f"   タイムスタンプ数: 元 {original_ts_count} → 後処理後 {result_ts_count}")

                    if result_ts_count < original_ts_count * 0.8:
                        # 20%以上消えていたら後処理結果を棄却
                        logger.warning(f"   ⚠️  タイムスタンプが大幅に失われました → このモデルの結果を棄却")
                        continue

                    logger.info(f"   ✅ {model_name} 後処理成功")
                    return result

            except Exception as e:
                logger.error(f"   ❌ {model_name} 例外: {e}")
                continue

        logger.error(f"   ❌ 全Geminiモデルで後処理失敗")
        return None

    def _create_polish_prompt(self, raw_text: str) -> str:
        """Gemini後処理用プロンプトを生成する"""
        return f"""# Role
                あなたは日本語テキストの校正専門家です。
                添付の音声と、Whisper音声認識システムが生成した転写テキストを照合し、
                誤認識を修正しながら読みやすく整えることが仕事です。

                # 最重要ルール（絶対に守ること）

                ## タイムスタンプについて
                - `[00:00:00]` `[00:05:00]` のような `[hh:mm:ss]` 形式のタイムスタンプは **絶対に削除・移動・変更しないこと**
                - タイムスタンプの前後の改行も保持すること
                - タイムスタンプは動画の時刻を示す重要なマーカーです

                ## 内容について
                - **音声に存在しない内容**（Whisperの幻覚）は削除すること。音声を聞いて実際に発話されていない文は除去する
                - テキストに書かれている **事実・固有名詞・発言内容は一切変更しないこと**
                - 話者が言っていない言葉を追加しないこと
                - 要約・省略・言い換えは禁止

                # 許可されている操作（これだけ行うこと）

                1. **句読点の追加**: 読点「、」句点「。」を適切な位置に追加する
                2. **誤字修正**: 音声と照合し、明らかな音声認識ミス（同音異義語など）を修正する
                   - 例: 「よろしくおねがいします」→「よろしくお願いします」
                   - 例: 「きょうはいい天気ですね」→「今日はいい天気ですね」
                3. **改行整理**: 不自然な改行を整え、段落を読みやすくする
                   - ただしタイムスタンプ前後の改行は変えないこと
                4. **歌唱部分の処理**: 音声を聞いて歌っている区間を判断し、以下のルールで処理する
                   - 歌詞はすべて省略し、代わりに `[🎵 曲名]` の形式で表記する
                   - 曲名が不明な場合は `[🎵 歌唱]` と表記する
                   - 歌唱中に話し声（トーク）が入った場合は、その発言を歌唱表記の後に続けて記載する
                   - 例:
                    [🎵 フライングゲット]
                    （ここで急に）あ、間違えた！（笑）
                    [🎵 歌唱]
                5. **幻覚テキストの除去**: 音声と照合し、実際に発話されていない内容は削除すること
                   - 同じ文章が連続して繰り返されている場合（例：「私はあなたを愛しています」が複数回）は削除する
                   - 音声に存在しない唐突な宣言文・無関係なURL・アプリ名は削除する
                   - 削除した箇所には何も補完しないこと

                # 出力形式
                - 整形後のテキストのみを出力すること
                - 「以下が整形後のテキストです」などの前置きは不要
                - コードブロック（```）で囲まない

                # 添付音声と照合しながら、以下の転写テキストを校正してください。

                # 処理対象テキスト

                {raw_text}"""

    # ------------------------------------------------------------------
    # Gemini テキスト呼び出し
    # ------------------------------------------------------------------

    def _call_gemini_text(self, prompt: str, model_config: Dict[str, Any]) -> Optional[str]:
        if not self.gemini_client:
            raise Exception("Gemini API客户端未初始化")
        return self.gemini_client.generate_from_text(
            prompt,
            model_config['model_id'],
            model_config['config']
        )

    # ------------------------------------------------------------------
    # Ollama
    # ------------------------------------------------------------------

    def _call_ollama(self, prompt: str, model_config: Dict[str, Any]) -> Optional[str]:
        api_url = model_config.get('api_url', 'http://localhost:11434/api/generate')
        model_id = model_config['model_id']
        config = model_config['config']
        
        logger.info(f"⏳ 调用本地 {model_id}...")
        logger.info(f"   (这可能需要10-15分钟，请耐心等待)\n")
        
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
        
        logger.info(f"{'='*70}")
        
        try:
            response = requests.post(api_url, json=payload, stream=True, timeout=30)
            
            summary = ""
            last_activity = time.time()
            
            for line in response.iter_lines():
                if time.time() - last_activity > 120:
                    logger.warning(f"\n⚠️ 流式响应超时（2分钟无数据）")
                    return None
                
                if line:
                    last_activity = time.time()
                    try:
                        data = json.loads(line)
                        token = data.get('response', '')
                        summary += token
                        logger.info(token, end='', flush=True)
                        
                        if data.get('done', False):
                            break
                    except:
                        continue
            
            logger.info(f"\n{'='*70}\n")
            return summary.strip() if summary else None
            
        except requests.exceptions.Timeout:
            logger.error(f"⚠️ Ollama 连接超时")
            return None
        except Exception as e:
            logger.error(f"❌ Ollama 错误: {e}")
            return None

    # ------------------------------------------------------------------
    # プロンプト生成
    # ------------------------------------------------------------------

    def _create_text_prompt(self, text: str, duration: float) -> str:
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
        return """# Role
                あなたはAKB48、特に橋本陽菜（はるpyon）に精通した専門家ですが、今回はその知識を一切封印し、**「動画内で発生した事実のみを正確に書き起こす、極めて客観的な記録員」**として振る舞ってください。
                
                # Task
                提供された動画を視聴し、以下の2つのセクション（詳細版・YouTube版）を作成してください。
                
                # Constraints（厳守事項）
                1. **ビデオ内情報限定**: 動画内で直接言及された言葉、表示されたテロップ、映った映像のみを情報源にしてください。
                2. **背景知識の排除**: あなたが知っている「生年月日」「所属チーム名」「過去の経歴」「メンバー間の関係性」などを補完してはいけません。
                   - 例：動画で「誕生日」と言っていたら「誕生日」とだけ書く。「3月5日の誕生日」と書くのは禁止です。
                3. **推測表現の禁止**: 「〜と思われる」「〜のような雰囲気」といった主観的・推測的な表現は一切排除し、断定的な事実のみを記述してください。
                4. **固有名詞の表記**: 括弧書きでの読み仮名や愛称の追加（例:橋本陽菜（はるpyon））は禁止です。動画内の呼称をそのまま使用してください。
                
                # Output Format
                必ず以下の形式で、前置きなしで出力してください。
                
                === 詳細版 ===
                ## 概要
                （動画の内容を、客観的な事実のみを用いて1〜2文で紹介）
                
                ## 主なトピック
                1. **[トピック見出し]**
                   - 動画内で語られた具体的なエピソードや発言の詳細。
                
                2. **[トピック見出し]**
                   - 動画内で語られた具体的なエピソードや発言の詳細。
                
                （内容の密度に応じて項目を増減してください）
                
                ## 重要なポイント・結論
                （具体的な数字、特定の発言、決定事項など、動画内の確定情報）
                
                === YouTube版 ===
                【[配信の核心を突くタイトル]】
                
                [配信の雰囲気を伝える紹介文。ここでのみ、視聴者の興味を引くためのポジティブな表現を許可します]
                
                💡 この配信の見どころ：
                - [見どころ1]
                - [見どころ2]
                - [見どころ3]
                
                ぜひ動画を最後までチェックしてください！
                
                ※ この要約は自動生成されました
                
                # Final Verification
                出力前に必ず以下を自検してください：
                - [ ] 「=== 詳細版 ===」から書き始めているか？
                - [ ] 動画で言及されていない日付、年齢、チーム名が含まれていないか？
                - [ ] 「おそらく」「〜と思われる」という言葉を使っていないか？
                - [ ] 固有名詞に余計な読み仮名や愛称を付与していないか？"""