#!/usr/bin/env python3
"""
Oracle对象存储下载模块
"""

import oci
import sys
import yaml 
import logging
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
        except Exception as e:
            logger.error(f"❌ 初始化失败: {e}")
            raise
    
    def list_videos(self):
        try:
            logger.info(f"\n📋 列出视频:")
            logger.info(f"   Namespace: {NAMESPACE}")
            logger.info(f"   Bucket: {BUCKET_NAME}")
            logger.info(f"   前缀: {VIDEO_PREFIX}")
            
            response = self.client.list_objects(
                namespace_name=NAMESPACE,
                bucket_name=BUCKET_NAME,
                prefix=VIDEO_PREFIX
            )
            
            videos = [
                obj.name for obj in response.data.objects
                if any(obj.name.lower().endswith(ext) for ext in VIDEO_EXTENSIONS)
            ]
            
            logger.info(f"   找到 {len(videos)} 个视频\n")
            return videos
        except Exception as e:
            logger.error(f"❌ 列出视频失败: {e}")
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
        logger.info(f"\n{'='*70}")
        logger.info(f"📥 Oracle 对象存储视频下载")
        logger.info(f"{'='*70}\n")
        
        videos = self.list_videos()
        
        if not videos:
            logger.error("❌ 没有找到视频文件")
            return
        
        logger.info(f"📹 找到 {len(videos)} 个视频:\n")
        for i, video in enumerate(videos, 1):
            logger.info(f"   {i}. {video.split('/')[-1]}")
        
        success_count = 0
        
        for i, video_name in enumerate(videos, 1):
            logger.info(f"\n{'='*70}")
            logger.info(f"[{i}/{len(videos)}] {video_name.split('/')[-1]}")
            logger.info(f"{'='*70}")
            
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
                    # 检查标记文件是否存在
                    self.client.head_object(
                        namespace_name=NAMESPACE,
                        bucket_name=BUCKET_NAME,
                        object_name=marker_name
                    )
                    
                    # 如果存在就下载
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

        logger.info(f"\n{'='*70}")
        logger.info(f"✅ 下载完成: {success_count}/{len(videos)} 个文件")
        logger.info(f"📁 保存在: {DOWNLOAD_FOLDER.absolute()}")
        logger.info(f"{'='*70}")


def main():
    try:
        downloader = OracleBucketDownloader()
        downloader.download_all_videos()
    except KeyboardInterrupt:
        logger.warning(f"\n\n⚠️  用户中断")
        sys.exit(0)
    except Exception as e:
        logger.error(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()