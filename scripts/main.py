#!/usr/bin/env python3
"""
主程序 - 批量处理视频
"""

import os
import sys
import oci
import logging
from datetime import datetime
from pathlib import Path

# 添加父目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils import (
    load_config,
    get_video_files,
    load_processed_log,
    save_processed_log
)
from core import VideoProcessor

# 配置全局日志格式
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger(__name__)

# 测试输出
logger.info("日志系统已启动")

def main():
    """主流程"""
    start_time = datetime.now()
    
    logger.info("="*70)
    logger.info("🎯 日语视频高精度总结工具")
    logger.info("="*70)
    
    # 加载配置
    try:
        config = load_config()
    except Exception as e:
        logger.error(f"❌ 配置文件加载失败: {e}")
        sys.exit(1)
    
    # 获取视频文件列表
    video_files = get_video_files(config)
    
    if not video_files:
        logger.error(f"\n❌ 没有找到视频文件")
        logger.error(f"请检查配置:")
        if config['input']['mode'] == 'single':
            logger.info(f"  - 单文件模式: {config['input'].get('video_file')}")
        else:
            logger.info(f"  - 文件夹模式: {config['input']['video_folder']}")
        sys.exit(1)
    
    # 显示找到的视频
    logger.info(f"\n📹 找到 {len(video_files)} 个视频文件:")
    for i, vf in enumerate(video_files, 1):
        size_mb = os.path.getsize(vf) / (1024 * 1024)
        logger.info(f"   {i}. {os.path.basename(vf)} ({size_mb:.1f} MB)")
    
    # 加载已处理记录
    processing_config = config.get('processing', {})
    skip_processed = processing_config.get('skip_processed', True)
    continue_on_error = processing_config.get('continue_on_error', True)
    
    processed_log = load_processed_log(config)
    
    # 过滤已处理的视频
    if skip_processed:
        unprocessed = [
            vf for vf in video_files
            if os.path.abspath(vf) not in processed_log['videos']
        ]
        
        if len(unprocessed) < len(video_files):
            skipped = len(video_files) - len(unprocessed)
            logger.warning(f"\n⏭️  跳过 {skipped} 个已处理的视频")
            video_files = unprocessed
    
    if not video_files:
        logger.info(f"\n✅ 所有视频都已处理！")
        sys.exit(0)
    
    logger.info(f"\n📊 待处理: {len(video_files)} 个视频")
    
    # 初始化处理器
    try:
        logger.info(f"\n🔧 初始化模块...")
        processor = VideoProcessor(config)
    except Exception as e:
        logger.error(f"❌ 初始化失败: {e}")
        sys.exit(1)
    
    logger.info(f"\n{'='*70}")
    logger.info(f"🚀 开始批量处理")
    logger.info(f"{'='*70}\n")
    
    # 统计
    stats = {
        'total': len(video_files),
        'success': 0,
        'failed': 0
    }
    
    # 逐个处理
    for i, video_path in enumerate(video_files, 1):
        logger.info(f"\n\n{'#'*70}")
        logger.info(f"# 进度: {i}/{len(video_files)}")
        logger.info(f"{'#'*70}")
        
        abs_video_path = os.path.abspath(video_path)
        success = processor.process(video_path)
        
        if success:
            stats['success'] += 1
            processed_log['videos'][abs_video_path] = {
                'processed_at': datetime.now().isoformat(),
                'success': True
            }
            save_processed_log(processed_log, config)
        else:
            stats['failed'] += 1
            # 🆕 优化点 2：如果分析/处理失败，绝不写入已处理日志，并在日志中清除它（如果之前存在过）
            if abs_video_path in processed_log['videos']:
                processed_log['videos'].pop(abs_video_path)
                save_processed_log(processed_log, config)
            
            logger.warning(f"⚠️  视频 {os.path.basename(video_path)} 处理失败，已从 processed.json 移除（下次运行将自动重试）")
            
            if not continue_on_error:
                logger.error(f"\n⚠️  出错停止，剩余 {len(video_files) - i} 个视频未处理")
                break
    
    # 最终统计
    elapsed = (datetime.now() - start_time).total_seconds()
    
    logger.info(f"\n\n{'='*70}")
    logger.info(f"✅ 批量处理完成！")
    logger.info(f"{'='*70}")
    logger.info(f"\n📊 最终统计:")
    logger.info(f"   - 总计: {stats['total']} 个视频")
    logger.info(f"   - 成功: {stats['success']} 个")
    logger.info(f"   - 失败: {stats['failed']} 个")
    logger.info(f"   - 总耗时: {elapsed/60:.1f} 分钟")
    if stats['success'] > 0:
        logger.info(f"   - 平均耗时: {elapsed/stats['success']/60:.1f} 分钟/视频")
    logger.info(f"\n📁 输出目录: {config['output_dir']}")
    logger.info(f"{'='*70}")

    # 清理存储桶
    if 'oracle_download' in config:
        logger.info(f"\n{'='*70}")
        logger.info(f"🗑️  清理存储桶")
        logger.info(f"{'='*70}\n")
        
        deleted = cleanup_bucket_after_processing(config)
        
        if deleted > 0:
            logger.warning(f"\n✅ 已删除 {deleted} 个已处理的视频")

    if 'youtube_description_update' in config:
        logger.info(f"\n{'='*70}")
        logger.info(f"📝 更新 YouTube 视频简介")
        logger.info(f"{'='*70}\n")
        
        try:
            # 动态导入避免循环依赖
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "update_description", 
                Path(__file__).parent / "update_description.py"
            )
            update_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(update_module)
            
            update_module.update_all_descriptions()
        except Exception as e:
            logger.error(f"⚠️  简介更新出错: {e}")
            import traceback
            traceback.print_exc()

    # 新增：Git 仓库更新
    if 'git_update' in config:
        logger.info(f"\n{'='*70}")
        logger.info(f"📦 更新 Git 仓库")
        logger.info(f"{'='*70}\n")
        
        try:
            # 动态导入避免循环依赖
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "update_git",
                Path(__file__).parent / "update_git.py"
            )
            git_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(git_module)
            
            git_module.update_all_to_git()
        except Exception as e:
            logger.error(f"⚠️  Git 更新出错: {e}")
            import traceback
            traceback.print_exc()
def cleanup_bucket_after_processing(config):
    """处理完成后清理存储桶"""
    try:
        # 读取 Oracle 配置
        oracle_config = config.get('oracle_download', {})

        # 【新增】检查是否启用自动清理
        if not oracle_config.get('auto_cleanup', False):
            logger.warning(f"   ⏭️  跳过清理（未启用 auto_cleanup）")
            return 0
        
        # 读取 key 文件
        key_file = Path(__file__).parent.parent / "config" / "bucket_credentials.key"
        if not key_file.exists():
            logger.warning(f"   ⏭️  跳过清理（未找到配置文件）")
            return 0
        
        with open(key_file, 'r') as f:
            lines = [line.strip() for line in f.readlines()]
            namespace = lines[0]
            bucket_name = lines[1]
        
        video_prefix = oracle_config.get('video_prefix', 'showroom/videos/')
        video_exts = oracle_config.get('video_extensions', ['.mp4'])
        download_folder = Path(oracle_config.get('download_folder', './videos')).expanduser()
        
        # 连接 Oracle
        oci_config = oci.config.from_file()
        client = oci.object_storage.ObjectStorageClient(oci_config)
        
        # 列出视频
        response = client.list_objects(
            namespace_name=namespace,
            bucket_name=bucket_name,
            prefix=video_prefix
        )
        
        videos = [
            obj.name for obj in response.data.objects
            if any(obj.name.lower().endswith(ext) for ext in video_exts)
        ]
        
        if not videos:
            logger.warning(f"   ℹ️  存储桶中没有视频")
            return 0
        
        logger.info(f"   📋 检查 {len(videos)} 个视频")
        
        output_dir = config['output_dir']
        deleted_count = 0
        
        for video_name in videos:
            filename = video_name.split('/')[-1]
            video_stem = Path(filename).stem
            
            # 检查是否已处理
            has_output = any(Path(output_dir).glob(f"{video_stem}_*.txt"))
            
            if has_output:
                logger.info(f"   🗑️  删除: {filename}")
                try:
                    # 删除视频文件
                    client.delete_object(
                        namespace_name=namespace,
                        bucket_name=bucket_name,
                        object_name=video_name
                    )
                    deleted_count += 1

                    # 删除对应的 .uploaded 标记文件
                    marker_name = video_name + '.uploaded'
                    try:
                        client.delete_object(
                            namespace_name=namespace,
                            bucket_name=bucket_name,
                            object_name=marker_name
                        )
                        logger.info(f"      ✅ 已删除标记文件")
                    except oci.exceptions.ServiceError as e:
                        if e.status == 404:
                            pass  # 标记文件不存在,忽略
                        else:
                            logger.error(f"      ⚠️ 标记文件删除失败: {e}")

                except Exception as e:
                    logger.info(f"      ⚠️ 删除失败: {e}")
        
        return deleted_count
        
    except Exception as e:
        logger.error(f"   ⚠️ 清理出错: {e}")
        return 0

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.error(f"\n\n⚠️  用户中断")
        sys.exit(0)
