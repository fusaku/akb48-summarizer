#!/usr/bin/env python3
"""
更新总结文件到 Git 仓库
将处理好的 _detailed.txt 文件推送到 GitHub Pages
"""

import sys
import subprocess
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
    """解析路径(支持相对路径和绝对路径)"""
    path = Path(path_str).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path

VIDEOS_DIR = resolve_path(config['input']['video_folder'])
OUTPUTS_DIR = resolve_path(config['output_dir'])
GIT_REPO_PATH = Path(git_config.get('git_repo_path', '/home/ubuntu/fusaku.github.io'))
SUMMARIES_DIR = GIT_REPO_PATH / git_config.get('summaries_dir', 'summaries')


def run_git_command(command: list, cwd: Path) -> tuple[bool, str]:
    """
    执行 git 命令
    
    Args:
        command: git 命令列表
        cwd: 工作目录
    
    Returns:
        (是否成功, 输出信息)
    """
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.returncode == 0, result.stdout + result.stderr
    except Exception as e:
        return False, str(e)


def validate_git_repo() -> bool:
    """验证 git 仓库是否有效"""
    if not GIT_REPO_PATH.exists():
        print(f"   ❌ Git 仓库不存在: {GIT_REPO_PATH}")
        return False
    
    success, output = run_git_command(['git', 'status'], GIT_REPO_PATH)
    if not success:
        print(f"   ❌ 不是有效的 git 仓库")
        return False
    
    return True


def git_pull() -> bool:
    """执行 git pull 避免冲突"""
    print(f"   📥 执行 git pull...")
    
    success, output = run_git_command(['git', 'pull'], GIT_REPO_PATH)
    
    if success:
        if 'Already up to date' in output or 'Already up-to-date' in output:
            print(f"   ✅ 已是最新")
        else:
            print(f"   ✅ Pull 成功")
        return True
    else:
        print(f"   ❌ Pull 失败: {output}")
        return False


def find_detailed_txt(uploaded_file: Path) -> Path:
    """
    根据 .uploaded 文件名找到对应的 _detailed.txt 文件
    如果有多个，选择最新的
    """
    base_name = uploaded_file.name.replace('.mp4.uploaded', '')
    pattern = f"{base_name}_*_detailed.txt"
    matches = list(OUTPUTS_DIR.glob(pattern))
    
    if not matches:
        raise FileNotFoundError(f"未找到匹配的 detailed.txt 文件: {pattern}")
    
    # 如果有多个，按修改时间排序，选最新的
    if len(matches) > 1:
        matches.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        print(f"   ℹ️  找到 {len(matches)} 个文件，使用最新的: {matches[0].name}")
    
    return matches[0]


def extract_video_title(uploaded_file: Path) -> str:
    """
    从文件名提取视频标题
    例如: 260117 Showroom - AKB48 Team 8 Hashimoto Haruna 091623.mp4.uploaded
    返回: 260117 Showroom - AKB48 Team 8 Hashimoto Haruna 091623
    """
    return uploaded_file.name.replace('.mp4.uploaded', '')


def update_single_video(uploaded_file: Path) -> bool:
    """更新单个视频的总结到 Git"""
    
    print(f"\n{'='*70}")
    print(f"📝 处理: {uploaded_file.name}")
    print(f"{'='*70}")
    
    # 1. 读取视频 ID
    video_id = uploaded_file.read_text().strip()
    
    # 验证视频 ID 格式（YouTube ID 通常是 11 位）
    if len(video_id) != 11:
        print(f"   ⚠️  视频 ID 格式可能不正确: {video_id} (长度: {len(video_id)})")
    
    print(f"   视频ID: {video_id}")
    
    # 2. 检查是否已经更新过
    marker_suffix = git_config.get('marker_suffix', '.git_updated')
    marker_file = uploaded_file.parent / f"{uploaded_file.name}{marker_suffix}"
    
    if marker_file.exists():
        print(f"   ⏭️  已推送到 Git，跳过")
        return True
    
    # 3. 找到对应的 _detailed.txt
    try:
        detailed_file = find_detailed_txt(uploaded_file)
        print(f"   找到文件: {detailed_file.name}")
    except FileNotFoundError as e:
        print(f"   ❌ {e}")
        return False
    
    # 4. 读取内容
    try:
        content = detailed_file.read_text(encoding='utf-8')
        print(f"   内容长度: {len(content)} 字符")
    except Exception as e:
        print(f"   ❌ 读取文件失败: {e}")
        return False
    
    # 5. 确保 summaries 目录存在
    SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)
    
    # 6. 写入目标文件
    file_extension = git_config.get('file_extension', '.txt')
    target_file = SUMMARIES_DIR / f"{video_id}{file_extension}"
    
    try:
        target_file.write_text(content, encoding='utf-8')
        
        if target_file.exists():
            action = "覆盖" if target_file.stat().st_size > 0 else "创建"
            print(f"   ✅ 文件已{action}: {target_file.name}")
        else:
            print(f"   ✅ 文件已创建: {target_file.name}")
    except Exception as e:
        print(f"   ❌ 写入文件失败: {e}")
        return False
    
    # 7. Git add
    print(f"   📦 添加到 Git...")
    relative_path = target_file.relative_to(GIT_REPO_PATH)
    success, output = run_git_command(
        ['git', 'add', str(relative_path)],
        GIT_REPO_PATH
    )
    
    if not success:
        print(f"   ❌ git add 失败: {output}")
        return False
    
    # 8. Git commit
    video_title = extract_video_title(uploaded_file)
    commit_template = git_config.get('commit_message_template', 'Add summary for video {video_id}')
    commit_message = commit_template.format(
        video_id=video_id,
        video_title=video_title
    )
    
    print(f"   💬 提交信息: {commit_message}")
    success, output = run_git_command(
        ['git', 'commit', '-m', commit_message],
        GIT_REPO_PATH
    )
    
    if not success:
        # 检查是否是"没有变化"的情况
        if 'nothing to commit' in output or 'no changes added' in output:
            print(f"   ℹ️  没有变化需要提交")
            # 虽然没有新的 commit，但文件已存在，算成功
            marker_file.write_text(f"No changes at: {datetime.now()}")
            return True
        else:
            print(f"   ❌ git commit 失败: {output}")
            return False
    
    # 9. Git push
    print(f"   📤 推送到远程...")
    success, output = run_git_command(
        ['git', 'push'],
        GIT_REPO_PATH
    )
    
    if not success:
        print(f"   ❌ git push 失败: {output}")
        print(f"   ℹ️  文件已添加到本地仓库，但推送失败")
        print(f"   ℹ️  请手动执行: cd {GIT_REPO_PATH} && git push")
        return False
    
    print(f"   ✅ 推送成功")
    
    # 10. 创建标记文件
    marker_file.write_text(f"Pushed to Git at: {datetime.now()}")
    
    return True


def update_all_to_git() -> int:
    """批量更新所有视频总结到 Git"""
    
    # 检查是否启用
    if not git_config.get('enabled', False):
        print(f"ℹ️  Git 更新功能未启用")
        print(f"ℹ️  请在 config.yaml 中设置 git_update.enabled: true")
        return 0
    
    print(f"\n{'='*70}")
    print(f"📦 批量更新总结到 Git 仓库")
    print(f"{'='*70}\n")
    
    print(f"📂 Git 仓库: {GIT_REPO_PATH}")
    print(f"📂 目标目录: {SUMMARIES_DIR}")
    
    # 验证 Git 仓库
    print(f"\n🔍 验证 Git 仓库...")
    if not validate_git_repo():
        return 0
    print(f"   ✅ Git 仓库有效")
    
    # Git pull
    if not git_pull():
        print(f"\n⚠️  Pull 失败，但继续处理...")
    
    # 获取所有 .uploaded 文件
    uploaded_files = list(VIDEOS_DIR.glob("*.mp4.uploaded"))
    
    if not uploaded_files:
        print(f"\nℹ️  没有找到 .uploaded 文件")
        return 0
    
    print(f"\n📋 找到 {len(uploaded_files)} 个已上传的视频\n")
    
    # 统计
    success_count = 0
    fail_count = 0
    skip_count = 0
    
    # 逐个处理
    for uploaded_file in uploaded_files:
        # 检查是否已经更新过
        marker_suffix = git_config.get('marker_suffix', '.git_updated')
        marker_file = uploaded_file.parent / f"{uploaded_file.name}{marker_suffix}"
        
        if marker_file.exists():
            skip_count += 1
            continue
        
        result = update_single_video(uploaded_file)
        
        if result:
            success_count += 1
        else:
            fail_count += 1
    
    # 最终统计
    print(f"\n{'='*70}")
    print(f"✅ 批量更新完成")
    print(f"{'='*70}")
    print(f"   成功: {success_count} 个")
    print(f"   失败: {fail_count} 个")
    print(f"   跳过: {skip_count} 个")
    print(f"   总计: {len(uploaded_files)} 个")
    print(f"{'='*70}\n")
    
    return success_count


def main():
    """主函数"""
    try:
        update_all_to_git()
    except KeyboardInterrupt:
        print(f"\n\n⚠️  用户中断")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()