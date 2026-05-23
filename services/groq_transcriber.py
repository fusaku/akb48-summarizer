#!/usr/bin/env python3
"""
Groq Whisper API 転写クライアント
silence-aware 切片 + 精确时间偏移 + 复数账号自动切换
"""

import os
import math
import tempfile
import subprocess
import time
import json
import logging
import requests
from typing import Optional
from pathlib import Path
logger = logging.getLogger(__name__)


class GroqTranscriber:
    """Groq Whisper APIを使った転写クライアント"""

    def __init__(self, config: dict):
        groq_config = config.get('groq', {})
        self.model = groq_config.get('model', 'whisper-large-v3')
        self.chunk_duration = groq_config.get('chunk_duration_seconds', 60)
        self.silence_duration = groq_config.get('silence_duration_ms', 500)   # 静音判定最短时长(ms)
        self.silence_threshold = groq_config.get('silence_threshold_db', -35) # 静音判定阈值(dB)
        self.current_key_index = 0
        self.api_keys = self._load_api_keys(groq_config)

    # ------------------------------------------------------------------
    # 初期化
    # ------------------------------------------------------------------

    def _load_api_keys(self, groq_config: dict) -> list[str]:
        """キーファイルからAPIキーを読み込む"""
        key_file = groq_config.get('api_keys_file', '')
        if not key_file:
            return []

        key_path = Path(__file__).parent.parent / key_file
        if not key_path.exists():
            logger.error(f"   ❌ Groqキーファイルが見つかりません: {key_path}")
            return []

        keys = []
        for line in key_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#'):
                keys.append(line)

        logger.info(f"   ✅ Groqキー読み込み完了: {len(keys)} アカウント")
        return keys

    # ------------------------------------------------------------------
    # 音声情報取得
    # ------------------------------------------------------------------

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

        logger.info(f"   📊 音声情報:")
        logger.info(f"      時間: {duration/60:.1f} 分 ({duration:.1f} 秒)")
        logger.info(f"      サイズ: {size_mb:.1f} MB")
        return {'duration': duration, 'size_mb': size_mb}

    # ------------------------------------------------------------------
    # Silence-aware 切片
    # ------------------------------------------------------------------

    def _detect_silence_points(self, audio_path: str, duration: float) -> list[float]:
        """
        ffmpeg silencedetect で静音区間を検出し、
        切り目の候補（静音の中点）リストを返す。

        Args:
            audio_path: 音声ファイルパス
            duration: 総時間(秒)

        Returns:
            切り目候補の秒数リスト（昇順）
        """
        logger.info(f"\n   🔍 静音区間を検出中...")
        logger.info(f"      閾値: {self.silence_threshold} dB  /  最短静音: {self.silence_duration} ms")

        cmd = [
            'ffmpeg', '-i', audio_path,
            '-af', f'silencedetect=noise={self.silence_threshold}dB:d={self.silence_duration/1000}',
            '-f', 'null', '-'
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

        # stderr に silence_start / silence_end が出力される
        silence_starts = []
        silence_ends = []
        for line in result.stderr.splitlines():
            if 'silence_start' in line:
                try:
                    val = float(line.split('silence_start:')[1].strip().split()[0])
                    silence_starts.append(val)
                except:
                    pass
            if 'silence_end' in line:
                try:
                    val = float(line.split('silence_end:')[1].strip().split('|')[0].strip())
                    silence_ends.append(val)
                except:
                    pass

        # 静音の中点を切り目候補とする
        cut_points = []
        for s, e in zip(silence_starts, silence_ends):
            midpoint = (s + e) / 2.0
            cut_points.append(midpoint)

        logger.info(f"      検出した静音区間: {len(cut_points)} 箇所")
        if cut_points:
            logger.info(f"      例: {[f'{p:.1f}s' for p in cut_points[:5]]}" +
                  (" ..." if len(cut_points) > 5 else ""))

        return sorted(cut_points)

    def _build_cut_plan(
        self,
        cut_points: list[float],
        duration: float,
        target_chunk_sec: int
    ) -> list[tuple[float, float]]:
        """
        切り目候補から「約 target_chunk_sec 秒ごと」の切り計画を作成。

        静音点が見つからない区間は強制的に target_chunk_sec で切る。

        Returns:
            [(start_sec, end_sec), ...] のリスト
        """
        segments = []
        current_start = 0.0

        while current_start < duration - 1.0:
            ideal_end = current_start + target_chunk_sec

            if ideal_end >= duration:
                # 最終チャンク
                segments.append((current_start, duration))
                break

            # ideal_end の前後 30 秒以内で最も近い静音点を探す
            search_min = ideal_end - 30
            search_max = ideal_end + 30

            candidates = [p for p in cut_points
                          if search_min <= p <= search_max and p > current_start]

            if candidates:
                # ideal_end に最も近い静音点
                best = min(candidates, key=lambda p: abs(p - ideal_end))
                segments.append((current_start, best))
                current_start = best
            else:
                # 近くに静音がない → 強制カット
                segments.append((current_start, ideal_end))
                current_start = ideal_end

        return segments

    def _extract_chunk(
        self,
        audio_path: str,
        start_sec: float,
        end_sec: float,
        index: int
    ) -> Optional[str]:
        """
        ffmpeg で指定区間を切り出し、一時ファイルに保存。

        Returns:
            一時ファイルパス、失敗時は None
        """
        tmp = tempfile.NamedTemporaryFile(
            suffix=f'_chunk{index:03d}.mp3', delete=False
        )
        tmp.close()

        duration_sec = end_sec - start_sec
        cmd = [
            'ffmpeg', '-y',
            '-ss', str(start_sec),
            '-i', audio_path,
            '-t', str(duration_sec),
            '-acodec', 'libmp3lame',
            '-ar', '16000',
            '-ac', '1',
            '-q:a', '4',
            tmp.name
        ]
        result = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=120
        )

        if result.returncode != 0 or not os.path.exists(tmp.name):
            logger.error(f"      ❌ チャンク {index+1} 切り出し失敗")
            return None

        size_mb = os.path.getsize(tmp.name) / (1024 * 1024)
        logger.info(f"      チャンク {index+1:03d}: {start_sec/60:.1f}〜{end_sec/60:.1f} 分  "
              f"({duration_sec:.0f}秒 / {size_mb:.1f}MB)  →  {os.path.basename(tmp.name)}")
        return tmp.name

    def _split_audio_by_silence(
        self,
        audio_path: str,
        duration: float
    ) -> list[tuple[str, float]]:
        """
        silence-aware でチャンク分割。

        Returns:
            [(chunk_path, start_sec), ...] のリスト
        """
        target_sec = self.chunk_duration  # 設定値（デフォルト60秒）

        # 静音点を検出
        cut_points = self._detect_silence_points(audio_path, duration)

        # カット計画を作成
        plan = self._build_cut_plan(cut_points, duration, target_sec)

        logger.info(f"\n   ✂️  カット計画: {len(plan)} チャンク")
        logger.info(f"      目標チャンク長: {target_sec} 秒")

        chunks = []
        for i, (start, end) in enumerate(plan):
            chunk_path = self._extract_chunk(audio_path, start, end, i)
            if chunk_path:
                chunks.append((chunk_path, start))
            else:
                logger.warning(f"      ⚠️  チャンク {i+1} をスキップ")

        logger.info(f"\n   ✅ 分割完了: {len(chunks)}/{len(plan)} チャンク生成")
        return chunks

    # ------------------------------------------------------------------
    # Groq API 転写
    # ------------------------------------------------------------------

    def _transcribe_chunk(
        self,
        chunk_path: str,
        time_offset: float,
        chunk_index: int,
        total_chunks: int
    ) -> Optional[str]:
        """
        1チャンクをGroq APIに送信。失敗時は次のキーへフォールバック。

        タイムスタンプは time_offset を加算した絶対時間で挿入する。
        """
        TIMESTAMP_INTERVAL = 300  # 5分ごとにタイムスタンプ

        for attempt in range(len(self.api_keys)):
            key_index = (self.current_key_index + attempt) % len(self.api_keys)
            api_key = self.api_keys[key_index]

            logger.info(f"      📤 送信中 [キー {key_index+1}/{len(self.api_keys)}] ...")

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
                            'prompt': (
                                'これはShowroomのライブ配信の書き起こしです。'
                                '「チーム8」「RESET公演」「ドボン」「橋本陽菜」「はるpyon」'
                                'などのAKB48用語を正しく認識してください。'
                            ),
                        },
                        timeout=120
                    )

                if response.status_code == 200:
                    self.current_key_index = key_index
                    data = response.json()
                    segments = data.get('segments', [])
                    chunk_text = data.get('text', '')

                    logger.info(f"      ✅ 成功: {len(segments)} セグメント / {len(chunk_text)} 文字")

                    # タイムスタンプ付きテキストを構築
                    result = []
                    last_timestamp_abs = time_offset - TIMESTAMP_INTERVAL  # 最初のセグメントで必ず挿入

                    for seg in segments:
                        abs_start = seg['start'] + time_offset
                        text = seg['text'].strip()

                        if not text:
                            continue

                        # 5分ごとにタイムスタンプ挿入
                        if abs_start - last_timestamp_abs >= TIMESTAMP_INTERVAL:
                            h = int(abs_start // 3600)
                            m = int((abs_start % 3600) // 60)
                            s = int(abs_start % 60)
                            result.append(f"\n[{h:02d}:{m:02d}:{s:02d}]\n")
                            last_timestamp_abs = abs_start

                        result.append(text)

                    return ''.join(result)

                elif response.status_code == 429:
                    logger.warning(f"      ⚠️  キー {key_index+1} レート制限 → 次のキーへ切り替え")
                    self.current_key_index = (key_index + 1) % len(self.api_keys)
                    time.sleep(2)
                    continue

                elif response.status_code == 413:
                    logger.error(f"      ❌ キー {key_index+1}: ファイルサイズ超過 (413)")
                    return None

                else:
                    logger.error(f"      ❌ キー {key_index+1}: HTTPエラー {response.status_code}")
                    logger.error(f"         詳細: {response.text[:200]}")
                    continue

            except requests.exceptions.Timeout:
                logger.warning(f"      ⚠️  キー {key_index+1}: タイムアウト")
                continue
            except Exception as e:
                logger.error(f"      ❌ キー {key_index+1}: 例外発生 - {e}")
                continue

        logger.error(f"      ❌ 全キーで失敗")
        return None

    # ------------------------------------------------------------------
    # メインエントリ
    # ------------------------------------------------------------------

    def transcribe(self, audio_path: str, config: dict) -> Optional[str]:
        """
        メインの転写メソッド。

        1. 音声情報取得
        2. silence-aware チャンク分割
        3. 各チャンクをGroqへ送信（キーフォールバック付き）
        4. テキストを結合して返す（Gemini後処理はmanager側で行う）

        Returns:
            転写テキスト（タイムスタンプ付き） or None
        """
        if not self.api_keys:
            logger.error("   ❌ Groq APIキーが設定されていません")
            return None

        logger.info(f"\n{'='*60}")
        logger.info(f"🎙️  Groq Whisper 転写開始")
        logger.info(f"{'='*60}")
        logger.info(f"   モデル: {self.model}")
        logger.info(f"   目標チャンク長: {self.chunk_duration} 秒")

        # Step 1: 音声情報取得
        info = self._get_audio_info(audio_path)
        if info['duration'] == 0:
            logger.error("   ❌ 音声時間を取得できませんでした")
            return None

        # Step 2: silence-aware 分割
        logger.info(f"\n   📂 チャンク分割を開始します...")
        chunks = self._split_audio_by_silence(audio_path, info['duration'])

        if not chunks:
            logger.error("   ❌ チャンク生成に失敗しました")
            return None

        # Step 3: 各チャンクを転写
        logger.info(f"\n{'='*60}")
        logger.info(f"   🚀 転写開始: 計 {len(chunks)} チャンク")
        logger.info(f"{'='*60}")

        results = []
        failed_chunks = []
        total_chars = 0

        for i, (chunk_path, start_sec) in enumerate(chunks):
            logger.info(f"\n   ── チャンク {i+1}/{len(chunks)} "
                  f"[開始: {start_sec/60:.1f}分] ──")

            text = self._transcribe_chunk(
                chunk_path,
                time_offset=start_sec,
                chunk_index=i,
                total_chunks=len(chunks)
            )

            # 一時ファイルを削除
            try:
                os.unlink(chunk_path)
            except:
                pass

            if text:
                results.append(text)
                total_chars += len(text)
                logger.info(f"      📝 累計文字数: {total_chars:,} 文字")
            else:
                placeholder = f"\n[チャンク {i+1} 転写失敗 ({start_sec/60:.1f}分〜)]\n"
                results.append(placeholder)
                failed_chunks.append(i + 1)
                logger.warning(f"      ⚠️  プレースホルダーを挿入しました")

            # レート制限対策: チャンク間に少し待機
            if i < len(chunks) - 1:
                time.sleep(0.5)

        # Step 4: 結合
        logger.info(f"\n{'='*60}")
        logger.info(f"   📋 転写結果まとめ")
        logger.info(f"{'='*60}")
        logger.info(f"   総チャンク数: {len(chunks)}")
        logger.info(f"   成功: {len(chunks) - len(failed_chunks)} チャンク")
        if failed_chunks:
            logger.error(f"   失敗: {len(failed_chunks)} チャンク (番号: {failed_chunks})")
        logger.info(f"   総文字数: {total_chars:,} 文字")

        if not results:
            return None

        full_text = '\n'.join(results)
        logger.info(f"\n   ✅ Groq転写完了 → Gemini後処理へ渡します")
        return full_text