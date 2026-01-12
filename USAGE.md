# 使用指南

## 快速开始

### 1. 安装依赖

```bash
pip3 install --break-system-packages -r requirements.txt
```

### 2. 配置

编辑 `config/config.yaml`：

```yaml
# 设置 Gemini API 密钥路径
gemini_api_key_file: "/path/to/your/.gemini_api_key"

# 选择处理模式
processing:
  use_video_direct_analysis: true  # true=视频直传，false=Whisper转录
  video_speedup: 2.0               # 视频加速倍数
  media_resolution: "LOW"          # 视频分辨率
```

### 3. 运行

**单次处理模式：**
```bash
cd scripts
python3 main.py
```

**监控模式（自动处理新视频）：**
```bash
cd scripts
python3 watch.py
```

## 两种处理模式

### 模式 1：视频直传（推荐）

**优点：**
- 速度快 3-4 倍
- 无需本地转录
- 适合只需要总结的场景

**配置：**
```yaml
processing:
  use_video_direct_analysis: true
  video_speedup: 2.0  # 可加速处理
```

**输出：**
- 详细总结
- YouTube 简洁版
- ⚠️ 无完整转录文本

### 模式 2：Whisper 转录

**优点：**
- 完整转录文本
- 支持自定义词汇表
- 更高准确率

**配置：**
```yaml
processing:
  use_video_direct_analysis: false

whisper:
  custom_vocabulary:
    enabled: true
    file: "vocabulary.txt"
```

**输出：**
- 完整转录
- AI 总结
- 时间轴
- YouTube 评论

## 自定义词汇表

编辑 `config/vocabulary.txt`：

```
# AKB48 成员
橋本陽菜
はるぴょん
チーム8
水島美結
みずみん

# 活动
SHOWROOM
握手会
劇場公演
```

## 批量处理

1. 将视频放入 `videos/` 目录
2. 运行 `python3 scripts/main.py`
3. 系统自动：
   - 扫描所有视频
   - 跳过已处理
   - 逐个处理
   - 保存结果到 `outputs/`

## 监控模式

```bash
cd scripts
python3 watch.py
```

功能：
- 实时监控 `videos/` 目录
- 检测新上传的视频
- 自动触发处理
- 后台持续运行

停止：按 `Ctrl+C`

## 输出文件

每个视频生成两个文件：

**1. 文本文件 (`.txt`)**
```
动画: video_name.mp4
生成時間: 2026-01-11 13:30:00
使用モデル: gemini-3-flash-preview

【AI要約（詳細版）】
...

【YouTube コメント用（簡潔版）】
...

【タイムライン】
...

【完全な文字起こし】
...
```

**2. JSON 文件 (`.json`)**
```json
{
  "video": "video_name.mp4",
  "summary": "...",
  "timeline": [...],
  "transcript": "...",
  "youtube_comment": "...",
  "model": "gemini-3-flash-preview",
  "stats": {...}
}
```

## 常见问题

### Q: 视频太长怎么办？

A: 当前版本暂不支持超长视频自动分段。建议：
- 手动分割视频
- 或等待后续更新

### Q: 如何跳过已处理的视频？

A: 在配置中设置：
```yaml
processing:
  skip_processed: true
```

系统会记录已处理的视频在 `outputs/processed.json`

### Q: 转录不准确怎么办？

A: 
1. 使用 Whisper 模式（不是视频直传）
2. 在 `config/vocabulary.txt` 中添加专有名词
3. 重新处理

### Q: API 调用失败怎么办？

A: 系统会自动降级到备用模型：
1. Gemini 3 Flash Preview
2. Gemini 2.5 Flash
3. Gemini 2.5 Flash Lite
4. Ollama Qwen 14B（本地）

## 性能优化

### 提高速度

1. 使用视频直传模式
2. 启用视频加速：
   ```yaml
   video_speedup: 2.0
   ```
3. 降低分辨率：
   ```yaml
   media_resolution: "LOW"
   ```

### 提高质量

1. 使用 Whisper 转录模式
2. 添加自定义词汇表
3. 使用更好的模型（Gemini 3）

## 项目结构

```
akb48-summarizer/
├── config/              # 配置文件
│   ├── config.yaml     # 主配置
│   └── vocabulary.txt  # 词汇表
├── core/               # 核心逻辑
│   ├── transcriber.py  # 转录器
│   ├── summarizer.py   # 总结器
│   └── processor.py    # 处理器
├── services/           # 外部服务
│   └── gemini.py      # Gemini 客户端
├── models/            # 模型管理
│   └── manager.py     # 模型管理器
├── utils/             # 工具函数
│   ├── file.py        # 文件操作
│   ├── video.py       # 视频工具
│   └── format.py      # 格式化
├── scripts/           # 可执行脚本
│   ├── main.py        # 主程序
│   └── watch.py       # 监控服务
├── videos/            # 输入目录
└── outputs/           # 输出目录
```

## 技术支持

遇到问题请：
1. 检查配置文件
2. 查看错误日志
3. 提交 Issue

## 许可证

MIT License
