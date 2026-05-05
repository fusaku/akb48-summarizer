#!/usr/bin/env python3
"""
Groq Whisper API 転写クライアント
複数アカウント対応・自動フォールバック
"""

import os
import math
import tempfile
import subprocess
import time
from typing import Optional

import requests


class GroqTranscriber:
    """Groq Whisper APIを使った転写クライアント"""

    def __init__(self, config: dict):
        groq_config = config.get('groq', {})
        self.model = groq_config.get('model', 'whisper-large-v3')
        self.chunk_duration = groq_config.get('chunk_duration_seconds', 1800)
        self.current_key_index = 0
        self.api_keys = self._load_api_keys(groq_config)

    def _load_api_keys(self, groq_config: dict) -> list[str]:
        """キーファイルからAPIキーを読み込む"""
        from pathlib import Path
        key_file = groq_config.get('api_keys_file', '')
        if not key_file:
            return []

        # 絶対パスに変換
        key_path = Path(__file__).parent.parent / key_file
        if not key_path.exists():
            print(f"   ❌ Groqキーファイルが見つかりません: {key_path}")
            return []

        keys = []
        for line in key_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#'):  # コメント行も対応
                keys.append(line)

        print(f"   ✅ Groqキー読み込み: {len(keys)}アカウント")
        return keys

    def _get_audio_info(self, audio_path: str) -> dict:
        """音声ファイルの時間と容量を取得"""
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries',
             'format=duration,size', '-of', 'default=noprint_wrappers=1',
             audio_path],
            capture_output=True, text=True, timeout=10
        )
        info = {}
        for line in result.stdout.strip().splitlines():
            key, _, val = line.partition('=')
            info[key.strip()] = val.strip()

        duration = float(info.get('duration', 0))
        size_bytes = int(info.get('size', 0))
        size_mb = size_bytes / (1024 * 1024)

        print(f"   🎵 音声情報: {duration/60:.1f}分 / {size_mb:.1f}MB")
        return {'duration': duration, 'size_mb': size_mb}

    def _split_audio(self, audio_path: str, duration: float) -> list[str]:
        """音声を20MB以下になるよう分割"""

        # まず再エンコードして小さくする
        tmp_reenc = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False)
        tmp_reenc.close()

        subprocess.run([
            'ffmpeg', '-y', '-i', audio_path,
            '-acodec', 'libmp3lame',
            '-ar', '16000',
            '-ac', '1',
            '-q:a', '6',
            tmp_reenc.name
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        size_mb = os.path.getsize(tmp_reenc.name) / (1024 * 1024)
        print(f"   🎵 再エンコード後: {size_mb:.1f}MB")

        # 20MB以下なら分割不要
        TARGET_MB = 20
        if size_mb <= TARGET_MB:
            print(f"   ✅ 分割不要")
            return [tmp_reenc.name]

        # 分割数を計算
        num_chunks = math.ceil(size_mb / TARGET_MB)
        chunk_duration = duration / num_chunks
        print(f"   ✂️  {num_chunks}分割します（約{chunk_duration/60:.1f}分ずつ）")

        chunks = []
        for i in range(num_chunks):
            start = i * chunk_duration
            tmp = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False)
            tmp.close()
            cmd = [
                'ffmpeg', '-y',
                '-ss', str(start),
            '-i', tmp_reenc.name,
            '-t', str(chunk_duration),
            '-acodec', 'copy',  # 再エンコード済みなのでcopyでOK
                tmp.name
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
            chunk_size = os.path.getsize(tmp.name) / (1024 * 1024)
            print(f"   チャンク{i+1}/{num_chunks}: {chunk_size:.1f}MB")
            chunks.append(tmp.name)

        # 再エンコードした中間ファイルを削除
        try:
            os.unlink(tmp_reenc.name)
        except:
            pass
        
        return chunks

    def _transcribe_chunk(self, chunk_path: str, time_offset: float = 0.0) -> Optional[str]:
        """1チャンクをGroq APIに送信、失敗時は次のキーへ"""
        for attempt in range(len(self.api_keys)):
            key_index = (self.current_key_index + attempt) % len(self.api_keys)
            api_key = self.api_keys[key_index]

            try:
                with open(chunk_path, 'rb') as f:
                    response = requests.post(
                        'https://api.groq.com/openai/v1/audio/transcriptions',
                        headers={'Authorization': f'Bearer {api_key}'},
                        files={'file': ('audio.mp3', f, 'audio/mpeg')},
                        data={
                            'model': self.model,
                            'language': 'ja',
                            'response_format': 'verbose_json',
                            'prompt': 'これはShowroomのライブ配信の書き起こしです。'
                                        "「柱の会」「チーム8」「RESET公演」「ドボン」などの用語を正しく認識してください。",
                        },
                        timeout=120
                    )

                if response.status_code == 200:
                    self.current_key_index = key_index
                    segments = response.json().get('segments', [])

                    INTERVAL = 300  # 5分ごと
                    result = []
                    last_timestamp = -INTERVAL

                    for seg in segments:
                        start = seg['start'] + time_offset
                        text = seg['text'].strip()

                        if start - last_timestamp >= INTERVAL:
                            h = int(start // 3600)
                            m = int((start % 3600) // 60)
                            s = int(start % 60)
                            result.append(f"\n[{h:02d}:{m:02d}:{s:02d}]\n")
                            last_timestamp = start

                        result.append(text)

                    return ''.join(result)

                elif response.status_code == 429:
                    print(f"   ⚠️  キー{key_index+1} レート制限、次のキーへ")
                    # 次のキーに切り替え
                    self.current_key_index = (key_index + 1) % len(self.api_keys)
                    time.sleep(1)
                    continue

                else:
                    print(f"   ❌ キー{key_index+1} エラー: {response.status_code}")
                    print(f"   詳細: {response.text}")
                    continue

            except Exception as e:
                print(f"   ❌ キー{key_index+1} 例外: {e}")
                continue

        return None

    def transcribe(self, audio_path: str, config: dict) -> Optional[str]:
        """
        メインの転写メソッド
        Returns: 転写テキスト or None
        """
        if not self.api_keys:
            print("   ❌ Groq APIキーが設定されていません")
            return None

        print(f"\n🎙️ Groq Whisper 転写開始")

        # 音声情報を取得・記録
        info = self._get_audio_info(audio_path)

        # 必要なら分割
        chunks = self._split_audio(audio_path, info['duration'])
        is_split = len(chunks) > 1

        results = []
        chunk_offset = info['duration'] / len(chunks) if len(chunks) > 1 else 0
        for i, chunk in enumerate(chunks):
            offset = i * chunk_offset
            print(f"   📤 チャンク{i+1}/{len(chunks)} 送信中...")
            text = self._transcribe_chunk(chunk, offset)
            if text:
                results.append(text)
                print(f"   ✅ チャンク{i+1} 完了 ({len(text)}文字)")
            else:
                print(f"   ❌ チャンク{i+1} 失敗")
                results.append(f"[チャンク{i+1}転写失敗]")

            # 分割ファイルは後始末
            try:
                os.unlink(chunk)
            except:
                pass

        if not results:
            return None

        full_text = '\n'.join(results)
        print(f"✅ 転写完了: 合計{len(full_text)}文字")
        return full_text