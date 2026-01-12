# AKB48 视频自动总结系统

日语视频高精度转录与智能总结工具，专为 AKB48 Team 8 橋本陽菜配信内容优化。

## ✨ 功能特性

- 🎤 **高精度转录**：使用 Whisper Large-v3 + 自定义词汇表
- 🤖 **智能总结**：支持 Gemini 3/2.5 Flash 多模型自动降级
- 🎬 **视频直传**：直接上传视频到 Gemini 分析（快速模式）
- ⚡ **视频加速**：支持 2x 加速处理
- 📁 **批量处理**：自动扫描目录，跳过已处理文件
- 🔄 **实时监控**：守护进程模式，自动处理新上传视频

## 📦 项目结构

```
akb48-summarizer/
├── config/              # 配置文件
│   ├── config.yaml     # 主配置
│   └── vocabulary.txt  # 自定义词汇表
├── core/               # 核心业务逻辑
│   ├── transcriber.py  # Whisper 转录
│   ├── summarizer.py   # AI 总结
│   └── processor.py    # 视频处理协调
├── services/           # 外部服务
│   └── gemini.py      # Gemini API 客户端
├── models/            # 模型管理
│   └── manager.py     # 模型管理器
├── utils/             # 工具函数
│   ├── file.py        # 文件操作
│   ├── video.py       # 视频工具
│   └── format.py      # 格式化输出
├── scripts/           # 可执行脚本
│   ├── main.py        # 主程序
│   └── watch.py       # 监控守护进程
└── outputs/           # 输出目录
```

## 🚀 快速开始

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

## 📖 文档

- [使用指南](USAGE.md) - 详细的使用说明
- [迁移指南](MIGRATION.md) - 从旧版本迁移
- [重构总结](REFACTOR_SUMMARY.md) - 项目重构详情

## 🎯 两种处理模式

### 模式 1：视频直传（推荐）

- ⚡ 速度快 3-4 倍
- 🎬 直接上传到 Gemini 分析
- 📝 输出：详细总结 + YouTube 简洁版

### 模式 2：Whisper 转录

- 📄 完整转录文本
- 🎯 支持自定义词汇表
- 📊 输出：转录 + 总结 + 时间轴

## 🛠️ 技术栈

- **转录**：faster-whisper (Whisper Large-v3)
- **AI 总结**：Google Gemini API
- **视频处理**：ffmpeg
- **配置**：YAML

## 📊 输出格式

每个视频生成两个文件：

**1. 文本文件 (`.txt`)**
- AI 总结（详细版）
- YouTube 评论（简洁版）
- 时间轴
- 完整转录（Whisper 模式）

**2. JSON 文件 (`.json`)**
- 结构化数据
- 便于后续处理

## ❓ 常见问题

**Q: 视频太长怎么办？**  
A: 当前版本暂不支持超长视频自动分段，建议手动分割。

**Q: 如何提高准确率？**  
A: 在 `config/vocabulary.txt` 中添加专有名词。

**Q: API 调用失败怎么办？**  
A: 系统自动降级到备用模型（Gemini 3→2.5→Lite→Ollama）。

## 📝 许可证

MIT License

## 🙏 致谢

专为 AKB48 粉丝社区开发。
