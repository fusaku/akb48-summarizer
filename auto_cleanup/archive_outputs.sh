#!/bin/bash

# 配置
OUTPUTS_DIR="/home/ubuntu/akb48-summarizer/outputs"
ARCHIVE_DIR="/home/ubuntu/akb48-summarizer/archives"

# 检查目录是否存在
if [ ! -d "$OUTPUTS_DIR" ]; then
    echo "错误: 目录不存在 $OUTPUTS_DIR"
    exit 1
fi

# 创建存档目录
mkdir -p "$ARCHIVE_DIR"

# 获取上个月的年月 (格式: YYYYMM, 例如 202501)
last_month=$(date -d "last month" +%Y%m 2>/dev/null || date -v-1m +%Y%m 2>/dev/null)
last_year=$(date -d "last month" +%Y 2>/dev/null || date -v-1m +%Y 2>/dev/null)
last_month_num=$(date -d "last month" +%m 2>/dev/null || date -v-1m +%m 2>/dev/null)

echo "开始打包 ${last_year}年${last_month_num}月 的文件..."
echo "目标目录: $OUTPUTS_DIR"

cd "$OUTPUTS_DIR" || exit 1

# 查找上个月的文件
# 文件名格式: YYMMDD 开头 (例如 260115)
# 提取年月部分,匹配上个月
file_pattern="${last_year:2:2}${last_month_num}*"

# 统计匹配的文件
file_count=$(ls -1 $file_pattern 2>/dev/null | wc -l)

if [ "$file_count" -eq 0 ]; then
    echo "没有找到 ${last_year}年${last_month_num}月 的文件"
    exit 0
fi

echo "找到 $file_count 个文件"

# 压缩包文件名
archive_name="outputs_${last_year}_${last_month_num}.tar.gz"
archive_path="$ARCHIVE_DIR/$archive_name"

# 检查压缩包是否已存在
if [ -f "$archive_path" ]; then
    echo "警告: 压缩包已存在 $archive_path"
    echo "将覆盖现有压缩包..."
    rm -f "$archive_path"
fi

# 打包压缩
echo "正在压缩到: $archive_path"
tar -czf "$archive_path" $file_pattern

if [ $? -eq 0 ]; then
    # 计算压缩包大小
    archive_size=$(du -h "$archive_path" | cut -f1)
    echo "✓ 压缩完成: $archive_name ($archive_size)"
    
    # 删除已打包的原文件
    echo "删除原文件..."
    rm -f $file_pattern
    echo "✓ 已删除 $file_count 个原文件"
    
    # 显示当前存档列表
    echo ""
    echo "当前存档列表:"
    ls -lh "$ARCHIVE_DIR"/*.tar.gz 2>/dev/null | awk '{print "  " $9 " (" $5 ")"}'
else
    echo "✗ 压缩失败"
    exit 1
fi