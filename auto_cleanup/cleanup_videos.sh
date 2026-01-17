#!/bin/bash

# 配置
VIDEO_DIR="/home/ubuntu/akb48-summarizer/videos"
MAX_SIZE_GB=10  # 最大限制
TARGET_PERCENT=80  # 删除到限制的80%
MAX_SIZE_BYTES=$((MAX_SIZE_GB * 1024 * 1024 * 1024))
TARGET_SIZE_BYTES=$((MAX_SIZE_BYTES * TARGET_PERCENT / 100))

# 检查目录是否存在
if [ ! -d "$VIDEO_DIR" ]; then
    echo "错误: 目录不存在 $VIDEO_DIR"
    exit 1
fi

# 计算当前目录大小(字节)
current_size=$(du -sb "$VIDEO_DIR" | cut -f1)
current_size_gb=$(echo "scale=2; $current_size / 1024 / 1024 / 1024" | bc)
target_size_gb=$(echo "scale=2; $TARGET_SIZE_BYTES / 1024 / 1024 / 1024" | bc)

echo "当前大小: ${current_size_gb}GB / ${MAX_SIZE_GB}GB"
echo "目标大小: ${target_size_gb}GB (${TARGET_PERCENT}%)"

# 如果未超过限制,退出
if [ $current_size -le $MAX_SIZE_BYTES ]; then
    echo "✓ 大小在限制内,无需清理"
    exit 0
fi

echo "⚠ 超过限制,开始清理到 ${TARGET_PERCENT}%..."

# 进入视频目录
cd "$VIDEO_DIR" || exit 1

# 获取所有.mp4文件,按修改时间排序(最旧的在前)
while [ $current_size -gt $TARGET_SIZE_BYTES ]; do
    # 找到最旧的mp4文件
    oldest_file=$(ls -1t *.mp4 2>/dev/null | tail -1)
    
    if [ -z "$oldest_file" ]; then
        echo "没有更多文件可删除"
        break
    fi
    
    # 获取基础文件名(去掉.mp4)
    base_name="${oldest_file%.mp4}"
    
    echo ""
    echo "删除视频组: $base_name"
    
    # 删除这个视频的所有相关文件
    deleted_size=0
    for file in "${base_name}".*; do
        if [ -f "$file" ]; then
            file_size=$(stat -c%s "$file" 2>/dev/null)
            echo "  删除: $file ($(numfmt --to=iec-i --suffix=B $file_size 2>/dev/null || echo "${file_size}B"))"
            rm -f "$file"
            deleted_size=$((deleted_size + file_size))
        fi
    done
    
    # 更新当前大小
    current_size=$((current_size - deleted_size))
    current_size_gb=$(echo "scale=2; $current_size / 1024 / 1024 / 1024" | bc)
    echo "  剩余大小: ${current_size_gb}GB / 目标: ${target_size_gb}GB"
done

echo ""
echo "✓ 清理完成"
echo "最终大小: ${current_size_gb}GB"