#!/usr/bin/env python3
"""
更新总结文件到 Git 仓库
将处理好的 _detailed.txt 文件推送到 GitHub Pages
优化版：批量 Commit，统一 Push
"""

import sys
import subprocess
import time
import os
from pathlib import Path
from datetime import datetime

# 添加父目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils import load_config

# 加载配置
config = load_config()
git_config = config.get('git_update', {})

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent

# 配置路径处理
def resolve_path(path_str: str) -> Path:
    path = Path(path_str).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path

VIDEOS_DIR = resolve_path(config['input']['video_folder'])
OUTPUTS_DIR = resolve_path(config['output_dir'])
GIT_REPO_PATH = Path(git_config.get('git_repo_path', '/home/ubuntu/fusaku.github.io'))
SUMMARIES_DIR = GIT_REPO_PATH / git_config.get('summaries_dir', 'summaries')


def run_git_command(command: list, cwd: Path) -> tuple[bool, str]:
    """执行 git 命令"""
    try:
        # 简单的锁检查
        lock_file = cwd / ".git" / "index.lock"
        if lock_file.exists():
            # 如果存在锁，简单等待一下
            print("   ⏳ 等待 Git 锁释放...")
            time.sleep(2)
            
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=60 # 增加一点超时时间，防止网络波动
        )
        return result.returncode == 0, result.stdout + result.stderr
    except Exception as e:
        return False, str(e)


def validate_git_repo() -> bool:
    if not GIT_REPO_PATH.exists():
        print(f"   ❌ Git 仓库不存在: {GIT_REPO_PATH}")
        return False
    success, _ = run_git_command(['git', 'status'], GIT_REPO_PATH)
    return success


def git_pull() -> bool:
    print(f"   📥 执行 git pull...")
    success, output = run_git_command(['git', 'pull'], GIT_REPO_PATH)
    if success:
        print(f"   ✅ Pull 成功")
        return True
    else:
        print(f"   ❌ Pull 失败: {output}")
        return False


def git_push() -> bool:
    """单独的 Push 函数"""
    print(f"   📤 执行 git push (批量推送)...")
    success, output = run_git_command(['git', 'push'], GIT_REPO_PATH)
    if success:
        print(f"   ✅ Push 成功")
        return True
    else:
        print(f"   ❌ Push 失败: {output}")
        print(f"   ℹ️  更改已保存在本地，下次运行时将再次尝试推送")
        return False


def find_detailed_txt(uploaded_file: Path) -> Path:
    base_name = uploaded_file.name.replace('.mp4.uploaded', '')
    pattern = f"{base_name}_*_detailed.txt"
    matches = list(OUTPUTS_DIR.glob(pattern))
    
    if not matches:
        raise FileNotFoundError(f"未找到匹配的 detailed.txt 文件: {pattern}")
    
    if len(matches) > 1:
        matches.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    return matches[0]


def extract_video_title(uploaded_file: Path) -> str:
    return uploaded_file.name.replace('.mp4.uploaded', '')


def update_single_video(uploaded_file: Path) -> bool:
    """
    更新单个视频的总结到本地 Git 仓库 (不推送)
    """
    print(f"\n--- 处理: {uploaded_file.name} ---")
    
    # 1. 读取 ID
    try:
        video_id = uploaded_file.read_text().strip()
        if len(video_id) != 11:
            print(f"   ⚠️  ID 长度异常: {video_id}")
    except Exception as e:
        print(f"   ❌ 读取 .uploaded 失败: {e}")
        return False

    # 2. 检查标记
    marker_suffix = git_config.get('marker_suffix', '.git_updated')
    marker_file = uploaded_file.parent / f"{uploaded_file.name}{marker_suffix}"
    
    if marker_file.exists():
        # 稍微检查一下是否已经在 Git 里了，防止重复处理
        return True

    # 3. 找源文件
    try:
        detailed_file = find_detailed_txt(uploaded_file)
    except FileNotFoundError:
        print(f"   ⏳ 总结文件尚未生成，跳过")
        return False
    
    # 4. 写入 Git 目录
    SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)
    file_extension = git_config.get('file_extension', '.txt')
    target_file = SUMMARIES_DIR / f"{video_id}{file_extension}"
    
    try:
        content = detailed_file.read_text(encoding='utf-8')
        target_file.write_text(content, encoding='utf-8')
    except Exception as e:
        print(f"   ❌ 文件读写失败: {e}")
        return False

    # 5. Git Add & Commit
    relative_path = target_file.relative_to(GIT_REPO_PATH)
    
    # Add
    run_git_command(['git', 'add', str(relative_path)], GIT_REPO_PATH)
    
    # Commit
    video_title = extract_video_title(uploaded_file)
    commit_msg = git_config.get('commit_message_template', 'Summary: {video_id}').format(
        video_id=video_id, video_title=video_title
    )
    
    success, output = run_git_command(['git', 'commit', '-m', commit_msg], GIT_REPO_PATH)
    
    if success:
        print(f"   ✅ 已提交 (Commit)")
        marker_file.write_text(f"Committed at: {datetime.now()}")
        return True
    elif 'nothing to commit' in output or 'no changes' in output.lower():
        print(f"   ℹ️  内容无变化")
        marker_file.write_text(f"No changes: {datetime.now()}")
        return True
    else:
        print(f"   ❌ Commit 失败: {output}")
        return False


def update_all_to_git() -> int:
    """主流程"""
    if not git_config.get('enabled', False):
        return 0

    print(f"\n{'='*60}")
    print(f"📦 开始同步总结到 Git")
    print(f"{'='*60}")

    if not validate_git_repo():
        return 0

    # 1. 统一先 Pull
    git_pull()

    uploaded_files = list(VIDEOS_DIR.glob("*.mp4.uploaded"))
    changes_made = False
    success_count = 0

    # 2. 循环处理 (只 Commit，不 Push)
    for uploaded_file in uploaded_files:
        if update_single_video(uploaded_file):
            success_count += 1
            # 只有当 marker 文件刚刚被创建，且确实有提交动作时，这里很难判断
            # 但只要 success_count > 0，我们最后都尝试 push 一下是安全的
            changes_made = True

    # 3. 统一最后 Push
    # 只要有处理成功的文件，或者为了保险起见（防止之前有未推送的提交），都执行一次 Push
    print(f"\n{'-'*60}")
    if changes_made:
        git_push()
    else:
        # 即使这次没有新文件，也可以检查一下有没有本地积压的提交
        success, output = run_git_command(['git', 'cherry', '-v'], GIT_REPO_PATH)
        if success and output.strip():
            print(f"   ℹ️  检测到本地有未推送的提交，执行推送...")
            git_push()
        else:
            print(f"   ✅ 没有需要推送的更新")

    return success_count


if __name__ == "__main__":
    try:
        update_all_to_git()
    except KeyboardInterrupt:
        sys.exit(0)