#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试源码扫描功能
"""

import asyncio
import sys
import os
import aiohttp
import tarfile
import io

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main import SourceInspector

async def list_source_files(arxiv_id: str):
    """列出源码包中的所有文件"""
    clean_id = arxiv_id.split('v')[0] if 'v' in arxiv_id else arxiv_id
    url = f"https://arxiv.org/src/{clean_id}"
    
    print(f"\n{'='*60}")
    print(f"📦 列出 ArXiv ID: {arxiv_id} 的源码文件")
    print(f"下载地址: {url}")
    print(f"{'='*60}\n")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    print(f"❌ 下载失败: HTTP {resp.status}")
                    return
                
                content_type = resp.headers.get('Content-Type', '').lower()
                print(f"📄 Content-Type: {content_type}")
                
                if 'pdf' in content_type:
                    print("⚠️  返回的是PDF文件，无法列出文件列表")
                    return
                
                content = await resp.read()
                print(f"📊 文件大小: {len(content):,} bytes ({len(content)/1024:.2f} KB)\n")
                
                if len(content) == 0:
                    print("❌ 内容为空")
                    return
                
                file_obj = io.BytesIO(content)
                
                # 尝试作为 tar.gz 打开
                try:
                    with tarfile.open(fileobj=file_obj, mode="r:gz") as tar:
                        members = tar.getmembers()
                        print(f"📁 找到 {len(members)} 个文件/目录:\n")
                        
                        # 按文件类型分类
                        tex_files = []
                        image_files = []
                        other_files = []
                        directories = []
                        
                        for member in members:
                            name = member.name
                            if member.isdir():
                                directories.append(name)
                            elif name.endswith('.tex'):
                                tex_files.append((name, member.size))
                            elif any(name.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.pdf', '.eps', '.svg']):
                                image_files.append((name, member.size))
                            else:
                                other_files.append((name, member.size))
                        
                        # 显示目录
                        if directories:
                            print("📂 目录:")
                            for d in sorted(directories):
                                print(f"   {d}/")
                            print()
                        
                        # 显示 .tex 文件
                        if tex_files:
                            print(f"📝 LaTeX 文件 ({len(tex_files)} 个):")
                            for name, size in sorted(tex_files):
                                size_str = f"{size:,} bytes" if size > 0 else "0 bytes"
                                print(f"   {name} ({size_str})")
                            print()
                        
                        # 显示图片文件
                        if image_files:
                            print(f"🖼️  图片文件 ({len(image_files)} 个):")
                            for name, size in sorted(image_files):
                                size_str = f"{size:,} bytes" if size > 0 else "0 bytes"
                                print(f"   {name} ({size_str})")
                            print()
                        
                        # 显示其他文件
                        if other_files:
                            print(f"📄 其他文件 ({len(other_files)} 个):")
                            for name, size in sorted(other_files):
                                size_str = f"{size:,} bytes" if size > 0 else "0 bytes"
                                print(f"   {name} ({size_str})")
                            print()
                        
                        # 统计信息
                        total_size = sum(m.size for m in members if m.isfile())
                        print(f"📊 统计:")
                        print(f"   总文件数: {len([m for m in members if m.isfile()])}")
                        print(f"   总目录数: {len(directories)}")
                        print(f"   总大小: {total_size:,} bytes ({total_size/1024:.2f} KB)")
                        
                except (tarfile.ReadError, tarfile.CompressionError, tarfile.TarError) as e:
                    print(f"⚠️  不是有效的 tar.gz 文件: {e}")
                    print("尝试作为纯文本显示前1000个字符...")
                    try:
                        text_content = content[:1000].decode('utf-8', errors='ignore')
                        print(f"\n前1000字符预览:\n{text_content}")
                    except Exception as inner_e:
                        print(f"❌ 无法解码为文本: {inner_e}")
                        
    except asyncio.TimeoutError:
        print("❌ 下载超时")
    except aiohttp.ClientError as e:
        print(f"❌ 网络错误: {e}")
    except Exception as e:
        print(f"❌ 发生错误: {e}")

async def test_scan():
    """测试源码扫描功能"""
    # 测试几个真实的ArXiv ID
    test_ids = [
        "2512.14693",  # 一个真实的ID
        "2312.12345",  # 另一个ID
    ]
    
    print("=" * 60)
    print("测试源码扫描功能")
    print("=" * 60)
    
    for arxiv_id in test_ids:
        print(f"\n测试 ArXiv ID: {arxiv_id}")
        print("-" * 60)
        
        # 先列出文件
        await list_source_files(arxiv_id)
        
        # 再执行扫描
        print(f"\n{'='*60}")
        print("执行扫描检测...")
        print(f"{'='*60}")
        venue, github = await SourceInspector.inspect_source(arxiv_id)
        
        print(f"\n✅ 检测结果:")
        print(f"  Venue: {venue if venue else 'None'}")
        print(f"  GitHub: {github if github else 'None'}")
        print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_scan())

