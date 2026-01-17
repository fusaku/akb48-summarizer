#!/usr/bin/env python3
"""
更新 YouTube 视频简介
"""

import sys
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
import pickle

# 添加父目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils import load_config

# 加载配置
config = load_config()
yt_config = config.get('youtube_description_update', {})

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
OUTPUTS_DIR = resolve_path(yt_config.get('source_dir', './outputs'))
CREDENTIALS_DIR = resolve_path(yt_config.get('credentials_dir'))
SCOPES = ['https://www.googleapis.com/auth/youtube.force-ssl']

def get_youtube_client():
    """获取 YouTube API 客户端"""
    creds = None
    token_file = CREDENTIALS_DIR / yt_config.get('token_file', 'youtube_token.pickle')
    
    if token_file.exists():
        with open(token_file, 'rb') as token:
            creds = pickle.load(token)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            client_secret = CREDENTIALS_DIR / yt_config.get('client_secret_file', 'client_secret.json')
            flow = InstalledAppFlow.from_client_secrets_file(str(client_secret), SCOPES)  # 加 str()
            creds = flow.run_local_server(port=0)
        
        with open(token_file, 'wb') as token:
            pickle.dump(creds, token)
    
    return build('youtube', 'v3', credentials=creds)

def find_txt_file(uploaded_file: Path) -> Path:
    """
    根据 .uploaded 文件名找到对应的 _youtube.txt 文件
    """
    base_name = uploaded_file.name.replace('.mp4.uploaded', '')
    pattern = f"{base_name}_*_youtube.txt"
    matches = list(OUTPUTS_DIR.glob(pattern))
    
    if not matches:
        raise FileNotFoundError(f"未找到匹配的 txt 文件: {pattern}")
    
    if len(matches) > 1:
        print(f"   ⚠️  找到多个匹配文件,使用第一个: {matches[0].name}")
    
    return matches[0]

def update_video_description(uploaded_file: Path, youtube):
    """更新单个视频的简介"""
    
    print(f"\n{'='*70}")
    print(f"📝 处理: {uploaded_file.name}")
    print(f"{'='*70}")
    
    # 1. 读取视频ID
    video_id = uploaded_file.read_text().strip()
    print(f"   视频ID: {video_id}")
    
    # 2. 找到对应的 txt 文件
    try:
        txt_file = find_txt_file(uploaded_file)
        print(f"   找到文件: {txt_file.name}")
    except FileNotFoundError as e:
        print(f"   ❌ {e}")
        return False
    
    # 3. 检查是否已经更新过
    marker_suffix = yt_config.get('marker_suffix', '.description_updated')
    marker_file = uploaded_file.parent / f"{uploaded_file.name}{marker_suffix}"
    if marker_file.exists():
        print(f"   ⏭️  已更新过,跳过")
        return True
    
    # 4. 读取要添加的内容
    additional_content = txt_file.read_text(encoding='utf-8')
    print(f"   内容长度: {len(additional_content)} 字符")
    
    # 5. 获取当前视频信息
    try:
        response = youtube.videos().list(
            part="snippet",
            id=video_id
        ).execute()
        
        if not response['items']:
            print(f"   ❌ 视频不存在或无权限")
            return False
        
        current_snippet = response['items'][0]['snippet']
        current_description = current_snippet.get('description', '')
        
        print(f"   当前简介长度: {len(current_description)} 字符")
        
    except Exception as e:
        print(f"   ❌ 获取视频信息失败: {e}")
        return False
    
    # 6. 组合新简介
    separator = yt_config.get('separator', '\n\n' + '='*50 + '\n\n')
    new_description = additional_content + separator + current_description
    
    max_length = yt_config.get('max_length', 5000)
    if len(new_description) > max_length:
        print(f"   ⚠️  新简介过长 ({len(new_description)} 字符),截断到 {max_length}")
        new_description = new_description[:max_length]
    
    print(f"   新简介长度: {len(new_description)} 字符")
    
    # 7. 更新视频
    try:
        youtube.videos().update(
            part="snippet",
            body={
                "id": video_id,
                "snippet": {
                    "title": current_snippet['title'],
                    "description": new_description,
                    "categoryId": current_snippet['categoryId']
                }
            }
        ).execute()
        
        print(f"   ✅ 简介更新成功")
        
        # 创建标记文件
        from datetime import datetime
        marker_file.write_text(f"Updated at: {datetime.now()}")
        
        return True
        
    except Exception as e:
        print(f"   ❌ 更新失败: {e}")
        return False

def update_all_descriptions():
    """批量更新所有视频的简介"""
    
    # 检查是否启用
    if not yt_config.get('enabled', False):
        print(f"ℹ️  YouTube 简介更新功能未启用")
        return 0
    
    print(f"\n{'='*70}")
    print(f"📝 YouTube 视频简介批量更新")
    print(f"{'='*70}\n")
    
    # 获取所有 .uploaded 文件
    uploaded_files = list(VIDEOS_DIR.glob("*.mp4.uploaded"))
    
    if not uploaded_files:
        print(f"ℹ️  没有找到 .uploaded 文件")
        return 0
    
    print(f"📋 找到 {len(uploaded_files)} 个已上传的视频\n")
    
    # 初始化 YouTube 客户端
    try:
        youtube = get_youtube_client()
    except Exception as e:
        print(f"❌ YouTube 客户端初始化失败: {e}")
        return 0
    
    # 统计
    success_count = 0
    fail_count = 0
    
    # 逐个处理
    for uploaded_file in uploaded_files:
        result = update_video_description(uploaded_file, youtube)
        
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
    print(f"   总计: {len(uploaded_files)} 个")
    print(f"{'='*70}\n")
    
    return success_count

def main():
    """主函数"""
    update_all_descriptions()

if __name__ == "__main__":
    main()