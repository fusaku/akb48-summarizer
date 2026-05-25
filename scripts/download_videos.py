#!/usr/bin/env python3
"""
Oracle对象存储下载模块
"""

import oci
import sys
import yaml 
import logging
import time
from pathlib import Path
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    force=True  # 强制应用配置，防止被其他库拦截
)
logger = logging.getLogger(__name__)

# 加载配置
def load_key_config():
    """从 .key 文件加载敏感信息"""
    script_dir = Path(__file__).parent
    key_paths = [
        script_dir / "config" / "bucket_credentials.key",
        script_dir.parent / "config" / "bucket_credentials.key",
    ]
    
    for key_path in key_paths:
        if key_path.exists():
            with open(key_path, 'r', encoding='utf-8') as f:
                lines = [line.strip() for line in f.readlines()]
                return lines[0], lines[1], lines[2] if len(lines) > 2 else 'ap-tokyo-1'
    
    logger.error("❌ 找不到 config/bucket_credentials.key")
    sys.exit(1)

def load_yaml_config():
    """从 config.yaml 加载其他配置"""
    script_dir = Path(__file__).parent
    yaml_paths = [
        script_dir / "config" / "config.yaml",
        script_dir.parent / "config" / "config.yaml",
    ]
    
    for yaml_path in yaml_paths:
        if yaml_path.exists():
            with open(yaml_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                return config.get('oracle_download', {})
    
    logger.error("❌ 找不到 config/config.yaml")
    sys.exit(1)

# 加载配置
NAMESPACE, BUCKET_NAME, REGION = load_key_config()
oracle_config = load_yaml_config()

DOWNLOAD_FOLDER = Path(oracle_config.get('download_folder', './videos')).expanduser()
VIDEO_PREFIX = oracle_config.get('video_prefix', 'showroom/videos/')
VIDEO_EXTENSIONS = oracle_config.get('video_extensions', ['.mp4'])

class OracleBucketDownloader:
    def __init__(self):
        try:
            config = oci.config.from_file()
            self.client = oci.object_storage.ObjectStorageClient(config)
            logger.info("✅ 使用配置文件认证 (~/.oci/config)")
            # 新增：在内存中保存已经扫描处理过的标记文件名（生命周期仅随类实例存在）
            self.scanned_markers = set()
        except Exception as e:
            logger.error(f"❌ 初始化失败: {e}")
            raise
    
    def list_videos(self):
        try:
            local_scan_folder = DOWNLOAD_FOLDER
            logger.info(f"\n🔍 检查本地标记文件夹: {local_scan_folder}")
            
            if not local_scan_folder.exists():
                logger.error(f"❌ 本地路径不存在: {local_scan_folder}")
                return []

            # 1. 找出本地所有的 .uploaded 标记文件
            local_markers = list(local_scan_folder.glob("*.uploaded"))
            if not local_markers:
                logger.info("ℹ️  本地未找到任何 .uploaded 标记文件，不扫描存储桶。")
                return None  # ← 改变返回值：本地啥都没有，返回 None

            # 2. 检查这些本地标记是否都已经存在于内存变量中了
            local_marker_names = {m.name for m in local_markers}
            if local_marker_names.issubset(self.scanned_markers):
                # 这里保留你要求的输出，直接结束
                logger.info("ℹ️  当前本地所有标记在内存中均已扫描过，跳过存储桶扫描。")
                return None  # ← 改变返回值：全都是老面孔，返回 None

            # 3. 触发“仅此一次”的存储桶扫描（因为有新文件或第一次运行）
            logger.info(f"   发现未记录的本地标记，触发存储桶全量扫描 (Bucket: {BUCKET_NAME})...")
            
            response = self.client.list_objects(
                namespace_name=NAMESPACE,
                bucket_name=BUCKET_NAME,
                prefix=VIDEO_PREFIX
            )
            
            # 拿到存储桶里所有的视频
            bucket_videos = [
                obj.name for obj in response.data.objects
                if any(obj.name.lower().endswith(ext) for ext in VIDEO_EXTENSIONS)
            ]

            # 4. 将本地当前的标记全部吃进内存变量里，下次再进来就不会触发扫描了
            self.scanned_markers.update(local_marker_names)

            # 5. 精准匹配：只留下【本地有标记】且【云端也有文件】的视频路径
            matched_videos = []
            for video_path in bucket_videos:
                filename = video_path.split('/')[-1]
                corresponding_marker = f"{filename}.uploaded"
                
                if corresponding_marker in local_marker_names:
                    matched_videos.append(video_path)
            
            return matched_videos  # ← 如果没匹配到，这里自然会返回空列表 []

        except Exception as e:
            logger.error(f"❌ 扫描比对失败: {e}")
            return []
    
    def download_video(self, object_name: str, local_path: Path) -> bool:
        try:
            head_response = self.client.head_object(
                namespace_name=NAMESPACE,
                bucket_name=BUCKET_NAME,
                object_name=object_name
            )
            
            file_size = int(head_response.headers.get('Content-Length', 0))
            file_size_mb = file_size / (1024 * 1024)
            logger.info(f"   大小: {file_size_mb:.1f} MB")
            
            local_path.parent.mkdir(parents=True, exist_ok=True)
            
            response = self.client.get_object(
                namespace_name=NAMESPACE,
                bucket_name=BUCKET_NAME,
                object_name=object_name
            )
            
            with open(local_path, 'wb') as f:
                downloaded = 0
                for chunk in response.data.raw.stream(1024 * 1024, decode_content=False):
                    f.write(chunk)
                    downloaded += len(chunk)
                    
                    if file_size > 0:
                        percent = (downloaded / file_size) * 100
                        logger.info(f"   进度: {percent:.1f}% ({downloaded/(1024*1024):.1f}/{file_size_mb:.1f} MB)")
            
            logger.info(f"✅ 下载完成: {local_path.name}")
            return True
        except Exception as e:
            logger.error(f"❌ 下载失败: {e}")
            return False
    
    def download_all_videos(self):
        # 把原本一进函数就打印的横幅日志删掉，或者往后移。
        # 否则每次 10 秒检测什么都没发生时，日志里都会刷屏一堆大横幅，很不清爽。
        
        videos = self.list_videos()
        
        # 情况 A：因为本地没新增，提前被内存拦截返回了 None
        if videos is None:
            # list_videos 内部已经打印了具体原因，这里直接静默退出即可
            return
            
        # 情况 B：触发了云端扫描，但是对齐之后没有发现任何可下载文件
        if len(videos) == 0:
            logger.info("ℹ️  存储桶里没有与本地标记匹配的新视频文件。")
            return

        # 情况 C：真的有文件需要下载，此时再打印正式的下载横幅
        logger.info(f"📥 Oracle 对象存储视频下载 - 开始处理")
        
        logger.info(f"📹 找到 {len(videos)} 个视频:\n")
        for i, video in enumerate(videos, 1):
            logger.info(f"   {i}. {video.split('/')[-1]}")
        
        success_count = 0
        
        for i, video_name in enumerate(videos, 1):
            logger.info(f"[{i}/{len(videos)}] {video_name.split('/')[-1]}")
            
            filename = video_name.split('/')[-1]
            local_path = DOWNLOAD_FOLDER / filename
            
            if local_path.exists():
                size_mb = local_path.stat().st_size / (1024 * 1024)
                logger.warning(f"⏭️  已存在 ({size_mb:.1f} MB)，跳过")
                success_count += 1
                continue
            
            if self.download_video(video_name, local_path):
                success_count += 1
        
                # 下载对应的 .uploaded 标记文件
                marker_name = video_name + '.uploaded'
                marker_local_path = local_path.with_suffix('.mp4.uploaded')
                
                try:
                    self.client.head_object(
                        namespace_name=NAMESPACE,
                        bucket_name=BUCKET_NAME,
                        object_name=marker_name
                    )
                    response = self.client.get_object(
                        namespace_name=NAMESPACE,
                        bucket_name=BUCKET_NAME,
                        object_name=marker_name
                    )
                    with open(marker_local_path, 'wb') as f:
                        for chunk in response.data.raw.stream(1024 * 1024, decode_content=False):
                            f.write(chunk)
                    logger.info(f"✅ 已下载标记文件: {marker_local_path.name}")
                except oci.exceptions.ServiceError as e:
                    if e.status == 404:
                        logger.error(f"ℹ️  未找到标记文件 (可能是旧视频)")
                    else:
                        logger.error(f"⚠️  标记文件下载失败: {e}")
                except Exception as e:
                    logger.error(f"⚠️  标记文件下载失败: {e}")

        logger.info(f"✅ 下载完成: {success_count}/{len(videos)} 个文件")
        logger.info(f"📁 保存在: {DOWNLOAD_FOLDER.absolute()}")
        logger.info(f"{'='*70}")


def main():
    try:
        downloader = OracleBucketDownloader()
        logger.info("🚀 下载服务已启动，进入后台轮询模式...")
        
        while True:
            try:
                downloader.download_all_videos()
            except Exception as e:
                logger.error(f"❌ 本轮下载发生错误: {e}")
            
            # 每隔 10 秒检查一次本地有没有新增的 .uploaded 文件
            # 或者是 30 秒、60 秒，你觉得舒服就行
            time.sleep(10)
            
    except KeyboardInterrupt:
        logger.warning(f"\n\n⚠️  用户中断，服务退出")
        sys.exit(0)
    except Exception as e:
        logger.error(f"\n❌ 服务崩溃: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()