#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ArXiv智能科研助理 v7.0 (Personalized Profile Edition)
新增功能：
1. 深度源码扫描：使用正确的ArXiv源码地址 (https://arxiv.org/src/...)
2. 同时检测会议模板和GitHub链接（从LaTeX源码中挖掘）
3. 区分摘要中的GitHub链接和源码中发现的隐藏链接
4. 宏观趋势统计：统计当天整个领域（如CS）的论文分布
5. 类别映射：将 cs.CV 等代码映射为可读名称
6. 图表可视化
7. 智能综述生成
8. [User Profile]: 从 user_profile.json 加载用户画像（发表记录、兴趣）
9. [Search Expansion]: 基于用户画像自动生成衍生搜索关键词
10. [Contextual Analysis]: LLM分析时会比对新论文与用户代表作的关联性
11. [Source Tagging]: 邮件中标记论文来源是"手动搜索"还是"AI推荐"
"""

import arxiv
import smtplib
import asyncio
import json
import html
import os
import re
import io
import tarfile
import aiohttp
import matplotlib
matplotlib.use('Agg')  # 非交互式后端
import matplotlib.pyplot as plt
from collections import Counter
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from datetime import datetime, timedelta
from typing import List, Dict, Any
from dotenv import load_dotenv
from openai import AsyncOpenAI

# 加载环境变量
load_dotenv()

# ================= 模板指纹库 =================
# 正则表达式 : 对应的会议/期刊名称
# 注意：顺序很重要，更具体的模式应该放在前面
TEMPLATE_SIGNATURES = {
    # 计算机视觉会议
    r'\\usepackage.*\{cvpr\}': 'CVPR',
    r'\\usepackage.*\{iccv\}': 'ICCV',
    r'\\usepackage.*\{eccv\}': 'ECCV',
    # 机器学习会议
    r'\\usepackage.*\{neurips.*\}': 'NeurIPS',
    r'\\usepackage.*\{nips.*\}': 'NeurIPS',  # 旧名称
    r'\\usepackage.*\{iclr\d+.*\}': 'ICLR',
    r'\\usepackage.*\{iclr.*\}': 'ICLR',
    # AI会议
    r'\\usepackage.*\{aaai.*\}': 'AAAI',
    # NLP会议
    r'\\usepackage.*\{acl.*\}': 'ACL',
    r'\\usepackage.*\{naacl.*\}': 'NAACL',
    r'\\usepackage.*\{emnlp.*\}': 'EMNLP',
    # 期刊
    r'\\documentclass.*\{acmart\}': 'ACM',
    r'\\documentclass.*\{IEEEtran\}': 'IEEE',
    r'\\documentclass.*\{nature\}': 'Nature',
    r'\\documentclass.*\{llncs\}': 'Springer (LNCS)',
    # 其他模式
    r'\\usepackage.*\{jmlr\}': 'JMLR',
    r'\\usepackage.*\{icml.*\}': 'ICML',
    # 文本模式（放在最后，作为兜底）
    r'Submitted to.*CVPR': 'CVPR',
    r'Submitted to.*ICCV': 'ICCV',
    r'Submitted to.*ECCV': 'ECCV',
    r'Submitted to.*NeurIPS': 'NeurIPS',
    r'Submitted to.*ICLR': 'ICLR',
}
# ===============================================

# ================= 领域代码映射表 =================
# 用于将 arxiv category 转换为可读名称
CATEGORY_MAP = {
    'cs.AI': 'Artificial Intelligence',
    'cs.CL': 'Computation & Language (NLP)',
    'cs.CV': 'Computer Vision',
    'cs.LG': 'Machine Learning',
    'cs.RO': 'Robotics',
    'cs.SE': 'Software Engineering',
    'cs.CR': 'Cryptography & Security',
    'cs.DS': 'Data Structures',
    'cs.NE': 'Neural & Evol. Computing',
    'cs.MA': 'Multiagent Systems',
    'cs.SI': 'Social & Info Networks',
    'q-bio.BM': 'Biomolecules',
    'q-bio.GN': 'Genomics',
    'stat.ML': 'Machine Learning (Stat)'
}
# ===============================================

# ================= 新增类：用户画像管理 =================

class UserProfileManager:
    """[新增] 用户画像管理器"""
    
    def __init__(self, profile_path: str = "user_profile.json"):
        self.profile_path = profile_path
        self.data = self._load_profile()
        
    def _load_profile(self) -> Dict:
        """加载JSON画像"""
        if not os.path.exists(self.profile_path):
            print(f"[!] ⚠️ 未找到用户画像文件: {self.profile_path}，将仅使用基础搜索功能。")
            return {"research_interests": [], "publications": []}
        try:
            with open(self.profile_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                print(f"[*] ✅ 成功加载用户画像")
                return data
        except Exception as e:
            print(f"[!] ❌ 读取用户画像失败: {e}")
            return {"research_interests": [], "publications": []}

    def get_interests_str(self) -> str:
        """格式化兴趣描述"""
        return "\n".join([f"- {i}" for i in self.data.get("research_interests", [])])

    def get_publications_context(self) -> str:
        """获取论文上下文供LLM使用"""
        pubs = self.data.get("publications", [])
        if not pubs: 
            return "用户暂无已发表论文记录。"
        return "\n".join([f"- Title: {p['title']}\n  Abstract: {p['abstract'][:200]}..." for p in pubs])

    async def generate_derived_keywords(self, client: AsyncOpenAI, model: str) -> List[str]:
        """基于画像生成 3 个衍生搜索词"""
        if not self.data.get("publications") and not self.data.get("research_interests"):
            return []
            
        print("[*] 🧠 [画像] 正在根据您的发表记录联想搜索词...")
        
        prompt = f"""
用户画像：
兴趣: {self.get_interests_str()}
代表作:
{self.get_publications_context()}

请生成 3 个 ArXiv 英文搜索关键词 (Search Queries)。
目标：找到可能引用用户工作，或在方法论上高度相关的最新论文。
不要只是重复兴趣词，要尝试组合（如 "GNN AND Protein"）。

输出仅返回JSON列表: ["query1", "query2", "query3"]
"""
        
        try:
            resp = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            res_json = json.loads(resp.choices[0].message.content)
            keywords = []
            # 兼容不同的JSON key
            for k, v in res_json.items():
                if isinstance(v, list): 
                    keywords = v
                    break
            
            print(f"    -> 🧠 AI联想词: {keywords}")
            return keywords
        except Exception as e:
            print(f"[!] 衍生词生成失败: {e}")
            return []

# ===============================================

class ArXivPaperFetcher:
    """ArXiv论文爬取类"""
    
    def __init__(self, max_results: int = 10):
        self.max_results = max_results
        self.client = arxiv.Client()
    
    def fetch_personal_papers(self, query: str, days: int = 7) -> List[Dict]:
        """精读轨道：获取用户感兴趣的特定论文"""
        queries = [q.strip() for q in query.replace(';', ',').split(',') if q.strip()]
        all_papers = []
        seen_ids = set()
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days) if days > 0 else None
        
        for q in queries:
            print(f"[*] 🔍 [精读] 正在搜索个性化内容: {q} ...")
            try:
                full_query = q
                if start_date:
                    date_query = f"submittedDate:[{start_date.strftime('%Y%m%d')}000000 TO {end_date.strftime('%Y%m%d')}235959]"
                    full_query = f"({q}) AND {date_query}"

                search = arxiv.Search(
                    query=full_query,
                    max_results=self.max_results,
                    sort_by=arxiv.SortCriterion.SubmittedDate,
                    sort_order=arxiv.SortOrder.Descending
                )
                
                for result in self.client.results(search):
                    arxiv_id = result.entry_id.split('/')[-1]
                    if arxiv_id not in seen_ids:
                        seen_ids.add(arxiv_id)
                        all_papers.append({
                            'title': result.title,
                            'authors': [a.name for a in result.authors],
                            'published': result.published.strftime('%Y-%m-%d'),
                            'summary': result.summary,
                            'arxiv_id': arxiv_id,
                            'pdf_url': result.pdf_url,
                            'query': q,
                            # 默认分类，稍后由LLM细化
                            'topic': result.primary_category, 
                            'github_info': None,
                            # 预留分析字段
                            'title_cn': '',
                            'summary_cn': '',
                            'tldr': '',
                            'score': 0,
                            'reasoning': ''
                        })
            except Exception as e:
                print(f"[!] 搜索失败: {e}")
        return all_papers

    def fetch_papers_mixed(self, manual_queries: List[str], derived_queries: List[str], days: int = 7) -> List[Dict]:
        """混合搜索：合并手动查询和衍生查询，并去重"""
        all_papers = {}  # {arxiv_id: paper_dict}
        
        # 1. 整理所有查询，并标记来源
        search_tasks = []  # [(query, source_type)]
        for q in manual_queries: 
            search_tasks.append((q, "Manual"))
        for q in derived_queries: 
            search_tasks.append((q, "AI Derived"))
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days) if days > 0 else None
        
        for query_text, source_type in search_tasks:
            if not query_text.strip(): 
                continue
            print(f"[*] 🔍 [{source_type}] 搜索: {query_text} ...")
            
            try:
                # 构造时间查询
                full_query = query_text
                if start_date:
                    date_q = f"submittedDate:[{start_date.strftime('%Y%m%d')}000000 TO {end_date.strftime('%Y%m%d')}235959]"
                    full_query = f"({query_text}) AND {date_q}"
                
                search = arxiv.Search(
                    query=full_query,
                    max_results=self.max_results,
                    sort_by=arxiv.SortCriterion.SubmittedDate,
                    sort_order=arxiv.SortOrder.Descending
                )
                
                count = 0
                for r in self.client.results(search):
                    pid = r.entry_id.split('/')[-1]
                    count += 1
                    # 去重逻辑：如果已存在，且当前是Manual来源，覆盖旧的（Manual优先级高）
                    if pid not in all_papers:
                        all_papers[pid] = {
                            'title': r.title, 
                            'authors': [a.name for a in r.authors],
                            'published': r.published.strftime('%Y-%m-%d'), 
                            'summary': r.summary,
                            'arxiv_id': pid, 
                            'pdf_url': r.pdf_url,
                            'topic': r.primary_category,
                            'source_query': query_text,
                            'source_type': source_type,  # 关键：标记来源
                            'venue_guess': None, 
                            'github_info': None
                        }
                    elif source_type == "Manual":
                        all_papers[pid]['source_type'] = "Manual"  # 升级为手动
                        
            except Exception as e:
                print(f"[!] 搜索 '{query_text}' 失败: {e}")
                
        return list(all_papers.values())

    def fetch_global_stats(self, category_prefix: str = "cs", days: int = 1) -> Dict[str, int]:
        """宏观轨道：统计整个领域（如cs.*）今天的论文分布"""
        print(f"[*] 📈 [宏观] 正在扫描全站 {category_prefix} 领域论文...")
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        # 搜索该大类下所有论文，限制数量防止超时 (例如取最近300篇作为样本)
        query = f"cat:{category_prefix}.* AND submittedDate:[{start_date.strftime('%Y%m%d')}000000 TO {end_date.strftime('%Y%m%d')}235959]"
        
        search = arxiv.Search(
            query=query,
            max_results=300, # 采样300篇足以代表今日趋势
            sort_by=arxiv.SortCriterion.SubmittedDate,
            sort_order=arxiv.SortOrder.Descending
        )
        
        categories = []
        try:
            for result in self.client.results(search):
                # 只统计主分类
                categories.append(result.primary_category)
        except Exception as e:
            print(f"[!] 宏观统计失败: {e}")
            
        print(f"[*] 宏观扫描完成，样本数: {len(categories)}")
        return Counter(categories)


class SourceInspector:
    """源码深度侦探类：负责下载 LaTeX 并分析会议/期刊模板和GitHub链接"""
    
    # 模板特征指纹 (正则: 标识)
    TEMPLATE_SIGNATURES = {
        r'\\usepackage.*\{iclr\d*\}': 'ICLR',
        r'\\usepackage.*\{cvpr\}': 'CVPR',
        r'\\usepackage.*\{iccv\}': 'ICCV',
        r'\\usepackage.*\{neurips\d*\}': 'NeurIPS',
        r'\\usepackage.*\{nips\d*\}': 'NeurIPS',  # 旧名称
        r'\\usepackage.*\{aaai\d*\}': 'AAAI',
        r'\\usepackage.*\{acl\d*\}': 'ACL',
        r'\\usepackage.*\{naacl\d*\}': 'NAACL',
        r'\\usepackage.*\{emnlp\d*\}': 'EMNLP',
        r'\\documentclass.*\{acmart\}': 'ACM',
        r'\\documentclass.*\{IEEEtran\}': 'IEEE',
        r'\\documentclass.*\{nature\}': 'Nature',
        r'\\documentclass.*\{llncs\}': 'Springer (LNCS)',
        r'\\usepackage.*\{spconf\}': 'ICASSP',
        r'\\usepackage.*\{jmlr\}': 'JMLR',
        r'\\usepackage.*\{icml.*\}': 'ICML',
    }
    
    # 文件名模式检测（用于检测.sty等样式文件）
    FILENAME_PATTERNS = {
        r'nips[_\-]?style\.sty': 'NeurIPS',
        r'neurips[_\-]?style\.sty': 'NeurIPS',
        r'iclr\d*\.sty': 'ICLR',
        r'cvpr\.sty': 'CVPR',
        r'iccv\.sty': 'ICCV',
        r'aaai\d*\.sty': 'AAAI',
        r'acl\.sty': 'ACL',
        r'naacl\.sty': 'NAACL',
        r'emnlp\.sty': 'EMNLP',
        r'icml\d*\.sty': 'ICML',
    }
    
    @staticmethod
    async def inspect_source(arxiv_id: str, semaphore: asyncio.Semaphore) -> tuple:
        """
        下载并分析源码（深度扫描）
        新增参数: semaphore (用于控制并发)
        Return: (venue_name, found_github_url)
        """
        # 使用信号量，限制同时下载的数量
        async with semaphore:
            clean_id = arxiv_id.split('v')[0] if 'v' in arxiv_id else arxiv_id
            url = f"https://arxiv.org/src/{clean_id}"
            
            print(f"    🕵️ [Deep Scan] 正在请求: {arxiv_id} (排队中...)")
            
            detected_venue = None
            detected_github = None
            
            # 伪装 Header，防止被 ArXiv 拦截
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            
            # 增加重试机制
            for attempt in range(2):  # 尝试2次
                try:
                    # 将超时延长到 60 秒
                    timeout = aiohttp.ClientTimeout(total=60, connect=10)
                    async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
                        async with session.get(url) as resp:
                            if resp.status != 200:
                                print(f"    [!] {arxiv_id} 下载失败: HTTP {resp.status}")
                                return None, None
                            
                            content_type = resp.headers.get('Content-Type', '').lower()
                            if 'pdf' in content_type:
                                print(f"    [!] {arxiv_id} 返回的是PDF文件，跳过")
                                return None, None
                            
                            print(f"    [*] {arxiv_id} 下载成功，Content-Type: {content_type}")
                            
                            # 读取二进制流
                            content = await resp.read()
                            
                            if len(content) == 0:
                                print(f"    [!] {arxiv_id} 内容为空")
                                return None, None
                            
                            print(f"    [*] {arxiv_id} 文件大小: {len(content)} bytes")
                            
                            file_obj = io.BytesIO(content)
                            
                            # 尝试作为 tar.gz 打开
                            try:
                                with tarfile.open(fileobj=file_obj, mode="r:gz") as tar:
                                    print(f"    [*] {arxiv_id} 成功解压tar.gz，开始扫描...")
                                    
                                    # 第一步：先检查文件名模式（如 nips_style.sty）
                                    if not detected_venue:
                                        for member in tar.getmembers():
                                            if member.isfile():
                                                filename = member.name.lower()
                                                for pattern, venue in SourceInspector.FILENAME_PATTERNS.items():
                                                    if re.search(pattern, filename, re.IGNORECASE):
                                                        detected_venue = venue
                                                        print(f"    ✅ [Venue] 通过文件名检测到模板: {venue} (文件: {member.name})")
                                                        break
                                                if detected_venue:
                                                    break
                                    
                                    # 第二步：扫描 .tex 文件内容
                                    tex_files_found = 0
                                    for member in tar.getmembers():
                                        if member.name.endswith('.tex') and member.isfile():
                                            tex_files_found += 1
                                            try:
                                                f = tar.extractfile(member)
                                                if f:
                                                    # 读取文本 (忽略编码错误)
                                                    tex_text = f.read().decode('utf-8', errors='ignore')
                                                    
                                                    # 1. 匹配会议模板（如果文件名没检测到）
                                                    if not detected_venue:
                                                        for pattern, venue in SourceInspector.TEMPLATE_SIGNATURES.items():
                                                            if re.search(pattern, tex_text, re.IGNORECASE):
                                                                detected_venue = venue
                                                                print(f"    ✅ [Venue] 通过内容检测到模板: {venue} (文件: {member.name})")
                                                                break
                                                    
                                                    # 2. 匹配 GitHub 链接
                                                    if not detected_github:
                                                        gh_match = re.search(r'https?://github\.com/[\w-]+/[\w.-]+', tex_text)
                                                        if gh_match:
                                                            detected_github = gh_match.group(0)
                                                            print(f"    ✅ [GitHub] 在源码中发现: {detected_github}")
                                                            
                                                    # 如果两个都找到了，提前结束循环
                                                    if detected_venue and detected_github:
                                                        break
                                            except Exception as e:
                                                continue
                                    
                                    if tex_files_found == 0:
                                        print(f"    [!] {arxiv_id} 未找到.tex文件")
                                    else:
                                        print(f"    [*] {arxiv_id} 扫描了 {tex_files_found} 个.tex文件")
                                            
                            except (tarfile.ReadError, tarfile.CompressionError, tarfile.TarError) as e:
                                print(f"    [!] {arxiv_id} tar.gz解压失败: {e}，尝试作为纯文本处理...")
                                # 可能是单个 .gz 文件（不是 tar），或者就是纯文本
                                try:
                                    text_content = content[:10000].decode('utf-8', errors='ignore')
                                    # 检查是否看起来像LaTeX文件
                                    if '\\documentclass' in text_content or '\\usepackage' in text_content:
                                        print(f"    [*] {arxiv_id} 检测到LaTeX内容，匹配模板...")
                                        # 匹配模板
                                        if not detected_venue:
                                            for pattern, venue in SourceInspector.TEMPLATE_SIGNATURES.items():
                                                if re.search(pattern, text_content, re.IGNORECASE):
                                                    detected_venue = venue
                                                    print(f"    ✅ [Venue] 检测到模板: {venue}")
                                                    break
                                        # 匹配GitHub链接
                                        if not detected_github:
                                            gh_match = re.search(r'https?://github\.com/[\w-]+/[\w.-]+', text_content)
                                            if gh_match:
                                                detected_github = gh_match.group(0)
                                                print(f"    ✅ [GitHub] 在源码中发现: {detected_github}")
                                except Exception as e2:
                                    print(f"    [!] {arxiv_id} 文本解码失败: {e2}")
                            
                            # 输出最终结果
                            if detected_venue:
                                print(f"    ✅ [Deep Scan] 完成: {arxiv_id} -> Venue: {detected_venue}")
                            else:
                                print(f"    ✅ [Deep Scan] 完成: {arxiv_id} -> 未检测到模板")
                            
                            if detected_github:
                                print(f"    ✅ [Deep Scan] GitHub: {detected_github}")
                            
                            return detected_venue, detected_github
                            
                except asyncio.TimeoutError:
                    print(f"    [!] {arxiv_id} 下载超时 (尝试 {attempt+1}/2)")
                    if attempt == 1:  # 最后一次尝试也失败
                        return None, None
                except aiohttp.ClientError as e:
                    print(f"    [!] {arxiv_id} 网络错误 (尝试 {attempt+1}/2): {e}")
                    if attempt == 1:  # 最后一次尝试也失败
                        return None, None
                except Exception as e:
                    print(f"    [!] {arxiv_id} 源码分析异常 (尝试 {attempt+1}/2): {e}")
                    if attempt == 1:  # 最后一次尝试也失败
                        return None, None
            
            return None, None
    
    @staticmethod
    async def detect_venue(arxiv_id: str, semaphore: asyncio.Semaphore = None) -> str:
        """兼容旧接口：仅返回venue"""
        # 如果没有提供信号量，创建一个临时的（限制为1，避免并发）
        if semaphore is None:
            semaphore = asyncio.Semaphore(1)
        venue, _ = await SourceInspector.inspect_source(arxiv_id, semaphore)
        return venue if venue else None


class PaperProcessor:
    """论文智能分析器：负责并发翻译、打分和总结"""
    
    def __init__(self, profile_manager=None, model="gpt-3.5-turbo", user_interest=""):
        api_key = os.getenv('OPENAI_API_KEY')
        base_url = os.getenv('OPENAI_BASE_URL')
        if api_key:
            kwargs = {'api_key': api_key}
            if base_url:
                kwargs['base_url'] = base_url
            self.client = AsyncOpenAI(**kwargs)
        else:
            self.client = None
        self.model = model
        self.user_interest = user_interest
        self.profile = profile_manager  # 用户画像管理器
        # 创建一个全局的信号量，限制最大并发数为 3
        self.download_semaphore = asyncio.Semaphore(3)

    async def _audit_github(self, text):
        """审计GitHub链接并获取仓库信息"""
        url_match = re.search(r'https?://github\.com/([\w-]+/[\w.-]+)', text)
        if not url_match:
            return None
        
        full_url = url_match.group(0)
        repo_path = url_match.group(1)
        api_url = f"https://api.github.com/repos/{repo_path}"
        info = {"url": full_url, "stars": "N/A", "last_update": "N/A", "desc": "Found Link"}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        info["stars"] = data.get('stargazers_count', 0)
                        info["last_update"] = data.get('pushed_at', '').split('T')[0]
                        info["desc"] = "✅ Repo Found"
                    elif resp.status == 404:
                        info["desc"] = "⚠️ 404 Not Found"
        except:
            pass
        return info

    async def analyze_paper_async(self, paper: Dict) -> Dict:
        """异步处理单篇论文：一次调用完成翻译、打分、总结和模板检测"""
        if not self.client or not self.client.api_key:
            # 无Key直接返回原数据
            paper['title_cn'] = paper['title']
            paper['summary_cn'] = paper['summary']
            paper['tldr'] = 'AI分析不可用'
            paper['score'] = 5
            paper['reasoning'] = '未配置API密钥'
            paper['topic'] = paper.get('topic', 'Unknown')
            paper['github_info'] = None
            # 即使没有API，也尝试检测模板（使用临时的信号量）
            temp_semaphore = asyncio.Semaphore(1)
            paper['venue_guess'] = await SourceInspector.detect_venue(paper['arxiv_id'], temp_semaphore)
            return paper

        # 并行执行任务：LLM分析、源码深度扫描（包含venue和GitHub检测）
        # 源码扫描会同时检测venue和GitHub链接
        # 传递信号量给 SourceInspector，限制并发下载数量
        source_task = SourceInspector.inspect_source(paper['arxiv_id'], self.download_semaphore)
        
        # 构造提示词（包含用户画像）
        profile_context = ""
        if self.profile:
            profile_context = f"""
【当前用户画像】
研究兴趣: {self.profile.get_interests_str()}
用户代表作:
{self.profile.get_publications_context()}

特别要求：
1. 关联性分析 (Contextual Analysis): 必须将新论文与【用户代表作】进行比对。如果新论文引用了类似方法、解决了用户论文中的遗留问题，或属于同一技术路线（如Mamba/GNN/MLLM），请在 reasoning 中明确指出（例如："此文扩展了您关于Mamba的研究..."）。
2. 打分 (Score): 基于与用户画像的契合度打分 (0-10)。

"""
        
        system_prompt = f"""
        你是一个专业的科研助理。
        
        {profile_context}
        
        用户的研究兴趣是：

        ---

        {self.user_interest}

        ---

        请阅读给定的论文标题和摘要，完成以下任务：

        1. Translate: 将标题和摘要翻译成中文（专业学术风格）。

        2. Score: 根据用户兴趣和画像对论文相关性进行打分（0-10分）。

        3. TLDR: 用中文写一句话的"太长不看"总结，直接指出论文的核心贡献。

        4. Topic: 提取论文的核心主题（简短短语，如"图神经网络"、"多模态学习"）。

        5. Reasoning: 简短说明打分理由，如果与用户代表作相关，请明确指出。

        请严格以JSON格式输出，包含以下字段:

        - title_cn (string)
        - summary_cn (string)
        - score (integer)
        - tldr (string)
        - topic (string)
        - reasoning (string)
        """

        user_content = f"Title: {paper['title']}\nAbstract: {paper['summary']}"

        try:
            # 创建LLM任务（这是一个协程）
            llm_task = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                response_format={"type": "json_object"},
                temperature=0.3
            )
            
            # 等待两个任务完成（LLM分析、源码深度扫描）
            # 使用return_exceptions=True确保即使某个任务失败，其他任务也能完成
            results = await asyncio.gather(llm_task, source_task, return_exceptions=True)
            res, source_result = results
            
            # 检查是否有异常
            if isinstance(res, Exception):
                raise res
            if isinstance(source_result, Exception):
                source_result = (None, None)
            
            # 解析源码扫描结果
            venue, deep_github = source_result if source_result else (None, None)
            print(f"    [DEBUG] 源码扫描结果: venue={venue}, github={deep_github}")
            
            # 解析LLM响应
            if hasattr(res, 'choices') and len(res.choices) > 0:
                data = json.loads(res.choices[0].message.content)
            else:
                raise ValueError("LLM响应格式错误")
            
            # 合并GitHub链接：优先使用摘要里的，如果没有，使用源码里挖出来的
            final_github = None
            is_hidden_github = False
            
            # 先看摘要里有没有
            summary_gh_match = re.search(r'https?://github\.com/[\w-]+/[\w.-]+', paper['summary'])
            if summary_gh_match:
                final_github = summary_gh_match.group(0)
            elif deep_github:
                final_github = deep_github  # 使用源码里挖出来的
                is_hidden_github = True
                print(f"    🎉 [惊喜] 在正文中发现了隐藏的 GitHub: {final_github}")
            
            # 获取GitHub详细信息（如果有链接）
            github_info = None
            if final_github:
                # 异步获取GitHub仓库信息
                github_info = await self._audit_github(final_github)
                if github_info:
                    github_info['is_hidden'] = is_hidden_github
                else:
                    github_info = {
                        "url": final_github,
                        "desc": "Link Found",
                        "stars": "N/A",
                        "last_update": "N/A",
                        "is_hidden": is_hidden_github
                    }
            
            # 更新paper字典
            paper['title_cn'] = data.get('title_cn', paper['title'])
            paper['summary_cn'] = data.get('summary_cn', paper['summary'])
            paper['score'] = data.get('score', 0)
            paper['tldr'] = data.get('tldr', '暂无总结')
            paper['topic'] = data.get('topic', paper.get('topic', 'Unknown'))
            paper['reasoning'] = data.get('reasoning', '')
            paper['github_info'] = github_info
            paper['venue_guess'] = venue  # 保存侦探结果
            print(f"    [DEBUG] 保存到paper: venue_guess={venue}, github_info={github_info is not None}")
            
            return paper

        except Exception as e:
            print(f"[!] 分析论文 {paper['arxiv_id']} 失败: {e}")
            # 失败回退：至少保留原文
            paper['title_cn'] = paper['title']
            paper['summary_cn'] = "AI分析失败，显示原文。\n" + paper['summary']
            paper['tldr'] = '分析失败'
            paper['score'] = 0
            paper['reasoning'] = f'分析错误: {str(e)}'
            paper['topic'] = paper.get('topic', 'Unknown')
            
            # 确保之前创建的任务被await（如果还没有完成）
            # 即使LLM失败，也尝试获取源码扫描结果
            try:
                # 如果之前的任务还没有完成，等待它
                if 'source_task' in locals():
                    source_result = await asyncio.gather(source_task, return_exceptions=True)[0]
                    if not isinstance(source_result, Exception):
                        venue, deep_github = source_result if source_result else (None, None)
                        paper['venue_guess'] = venue
                        # 尝试获取GitHub信息
                        if deep_github:
                            github_info = await self._audit_github(deep_github)
                            if github_info:
                                github_info['is_hidden'] = True
                            else:
                                github_info = {"url": deep_github, "desc": "Link Found", "is_hidden": True}
                            paper['github_info'] = github_info
                        else:
                            # 尝试从摘要中提取
                            summary_gh_match = re.search(r'https?://github\.com/[\w-]+/[\w.-]+', paper['summary'])
                            if summary_gh_match:
                                github_info = await self._audit_github(summary_gh_match.group(0))
                                if github_info:
                                    github_info['is_hidden'] = False
                                paper['github_info'] = github_info
                else:
                    # 如果任务还没有创建，创建新任务
                    source_task = SourceInspector.inspect_source(paper['arxiv_id'], self.download_semaphore)
                    source_result = await asyncio.gather(source_task, return_exceptions=True)[0]
                    if not isinstance(source_result, Exception):
                        venue, deep_github = source_result if source_result else (None, None)
                        paper['venue_guess'] = venue
                        if deep_github:
                            github_info = await self._audit_github(deep_github)
                            if github_info:
                                github_info['is_hidden'] = True
                            paper['github_info'] = github_info
            except Exception as e2:
                print(f"[!] 获取源码信息失败: {e2}")
                paper['github_info'] = None
                paper['venue_guess'] = None
            return paper

    async def generate_briefing(self, papers: List[Dict], global_stats_desc: str) -> str:
        """结合了个人论文和宏观趋势的综述"""
        context = "\n".join([f"- {p.get('title_cn', p['title'])} (Topic: {p.get('topic', 'Unknown')})" for p in papers[:5]])
        
        prompt = f"""
        你是科研情报专家。

        【宏观数据】
        今天ArXiv全站计算机领域的热门方向分布：{global_stats_desc}

        【用户个性化精选】
        {context}

        请写一段"ArXiv早报"。
        1. 先用一句话概括今天的宏观大盘（哪个子领域最火）。
        2. 再介绍用户关注的领域有什么新突破。
        3. 风格简练专业。
        """
        
        if not self.client or not self.client.api_key:
            return "AI综述生成不可用（未配置API密钥）"
        
        try:
            resp = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7
            )
            return resp.choices[0].message.content
        except Exception as e:
            print(f"[!] 综述生成失败: {e}")
            return "综述生成失败"

    async def process_batch(self, papers: List[Dict]) -> List[Dict]:
        """批量并发处理"""
        print(f"[*] 开始并行分析 {len(papers)} 篇论文 (使用模型: {self.model})...")
        tasks = [self.analyze_paper_async(paper) for paper in papers]
        # 并发执行所有任务
        processed_papers = await asyncio.gather(*tasks)
        print("[*] 分析完成！")
        
        # 按照相关性分数降序排序，分数高的排前面
        processed_papers.sort(key=lambda x: x.get('score', 0), reverse=True)
        return processed_papers


class Visualizer:
    """图表可视化类"""
    
    @staticmethod
    def draw_global_trend(category_counts: Dict[str, int]) -> bytes:
        """绘制宏观趋势图"""
        if not category_counts:
            return None
        
        # 1. 映射名称 (cs.CV -> Computer Vision)
        mapped_counts = {}
        for code, count in category_counts.items():
            # 取前两个分段，例如 cs.CV
            name = CATEGORY_MAP.get(code, code) 
            mapped_counts[name] = mapped_counts.get(name, 0) + count
            
        # 2. 排序并取 Top 10
        sorted_stats = sorted(mapped_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        if not sorted_stats:
            return None
        
        labels, sizes = zip(*sorted_stats)
        
        # 3. 绘图 (水平柱状图，适合长标签)
        fig, ax = plt.subplots(figsize=(10, 6))
        y_pos = range(len(labels))
        
        # 配色：构建渐变色
        import numpy as np
        color_range = plt.cm.GnBu(np.linspace(0.4, 0.9, len(labels)))
        
        bars = ax.barh(y_pos, sizes, align='center', color=color_range)
        ax.set_yticks(y_pos)
        ax.set_yticklabels(labels)
        ax.invert_yaxis()  # 最大的在最上面
        
        # 数据标签
        for i, v in enumerate(sizes):
            ax.text(v + 0.5, i, str(v), color='#333', va='center', fontweight='bold')
            
        ax.set_title(f"ArXiv Global Trend: Top Areas Today (Sampled)", fontsize=14, pad=20)
        ax.spines['right'].set_visible(False)
        ax.spines['top'].set_visible(False)
        plt.tight_layout()
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=100)
        plt.close(fig)
        buf.seek(0)
        return buf.getvalue()


class EmailSender:
    """邮件发送类 (优化HTML模板)"""
    
    def __init__(self, smtp_server, smtp_port, sender_email, sender_password):
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.sender_email = sender_email
        self.sender_password = sender_password
        
    def _generate_html(self, papers: List[Dict], query: str, briefing: str, derived_queries: List[str] = None, has_chart: bool = False) -> str:
        """生成美化的HTML内容"""
        if derived_queries is None:
            derived_queries = []
        
        # HTML 头部样式
        chart_section = ""
        if has_chart:
            chart_section = """
                <div style="text-align:center; margin:20px 0;">
                    <h3>📊 Global Category Trends (Today)</h3>
                    <img src="cid:trend_chart" style="max-width:100%; border:1px solid #eee; border-radius:8px;">
                    <p style="font-size:12px; color:#999;">Statistics based on broad field sampling</p>
                </div>
            """
        
        html_content = f"""
        <html>
        <head>
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 800px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #f8f9fa; padding: 20px; border-bottom: 3px solid #0056b3; margin-bottom: 20px; }}
                .paper-card {{ border: 1px solid #e0e0e0; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }}
                .high-score {{ border-left: 5px solid #28a745; background-color: #fcffff; }}
                .med-score {{ border-left: 5px solid #ffc107; }}
                .low-score {{ border-left: 5px solid #dc3545; opacity: 0.9; }}
                .title {{ color: #0056b3; text-decoration: none; font-size: 18px; font-weight: bold; }}
                .meta {{ font-size: 12px; color: #666; margin-bottom: 10px; }}
                .score-badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px; color: white; font-weight: bold; font-size: 12px; margin-right: 10px; }}
                .tldr {{ background-color: #eef2f7; padding: 10px; border-radius: 4px; font-style: italic; margin: 10px 0; border-left: 3px solid #0056b3; }}
                .abstract {{ font-size: 14px; text-align: justify; }}
                .footer {{ text-align: center; font-size: 12px; color: #999; margin-top: 30px; }}
                .briefing {{ background-color: #f9f9f9; padding: 15px; border-radius: 8px; margin-bottom: 20px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>🕵️ ArXiv Agent v7.0 Report</h2>
                    <p>Search Query: <strong>{html.escape(query)}</strong> | Found: {len(papers)} papers</p>
                    <p style="font-size:12px; color:#666;">Papers sorted by AI Relevance Score | Venue Detection Enabled | Personalized Profile Edition</p>
                </div>
                
                <div class="briefing">
                    <h3>🤖 Agent's Briefing</h3>
                    <p>{html.escape(briefing).replace(chr(10), '<br>')}</p>
                    {f'<div style="margin-top:10px; font-size:12px; color:#586069; border-top:1px solid #e1e4e8; padding-top:10px;"><b>Auto-Expanded Search:</b> {", ".join([f"<code>{html.escape(q)}</code>" for q in derived_queries]) if derived_queries else "None"}</div>' if derived_queries else ''}
                </div>
                
                {chart_section}
        """
        
        for p in papers:
            # 1. 颜色编码分数
            score = p.get('score', 0)
            score_class = "high-score" if score >= 8 else ("med-score" if score >= 5 else "low-score")
            score_color = "#28a745" if score >= 8 else ("#ffc107" if score >= 5 else "#dc3545")
            
            # 2. HTML 转义
            title_display = html.escape(p.get('title_cn', p['title']))
            summary_display = html.escape(p.get('summary_cn', p.get('summary', ''))).replace('\n', '<br>')
            tldr_display = html.escape(p.get('tldr', ''))
            authors_display = html.escape(", ".join(p['authors'][:5])) + ("..." if len(p['authors'])>5 else "")
            reasoning = html.escape(p.get('reasoning', ''))
            
            # [UI增强] 来源 Badge
            src_badge = ""
            src_type = p.get('source_type', 'Manual')
            if src_type == "Manual":
                src_text = "🎯 Manual"
                src_style = "background:#e1ecf4; color:#39739d;"
            else:
                src_text = "🧠 AI Derived"
                src_style = "background:#f0f4c3; color:#827717;"
            
            src_badge = f"<span style='{src_style} padding:2px 6px; border-radius:4px; font-size:11px; margin-right:5px; border:1px solid rgba(0,0,0,0.1);'>{src_text}</span>"
            
            # GitHub信息
            github_badge = ""
            if p.get('github_info'):
                info = p['github_info']
                # 区分摘要中的链接和源码中发现的链接
                if info.get('is_hidden'):
                    badge_text = "🕵️ Code (Found in Source)"
                    badge_color = "#2ea44f"  # GitHub绿
                else:
                    badge_text = "📦 Code (In Abstract)"
                    badge_color = "#0366d6"  # 蓝色
                
                github_badge = f"""
                <span style="background:{badge_color}; color:white; padding:2px 6px; border-radius:4px; font-size:11px; margin-right:5px;" title="{info.get('url', '')}">
                    {badge_text} | ⭐ {info.get('stars', 'N/A')}
                </span>
                """
            
            # Venue Badge (会议/期刊模板检测)
            venue_badge = ""
            venue_name = p.get('venue_guess')
            # 调试：打印venue_name的值
            # print(f"[DEBUG] Paper {p['arxiv_id']}: venue_guess = {venue_name}")
            
            # 修复：venue_name可能是None，需要检查
            if venue_name and venue_name not in [None, "Unknown", "Error", "No Source", "PDF Only", "Unknown Template", ""]:
                # 不同的会议用不同的颜色
                bg_color = "#6f42c1"  # 紫色默认
                if "CVPR" in venue_name:
                    bg_color = "#0366d6"  # 蓝
                elif "NeurIPS" in venue_name:
                    bg_color = "#b60205"  # 红
                elif "ICLR" in venue_name:
                    bg_color = "#d9534f"  # 浅红
                elif "ICCV" in venue_name:
                    bg_color = "#28a745"  # 绿
                elif "ECCV" in venue_name:
                    bg_color = "#17a2b8"  # 青
                elif "AAAI" in venue_name:
                    bg_color = "#ffc107"  # 黄
                elif "ACL" in venue_name or "NAACL" in venue_name or "EMNLP" in venue_name:
                    bg_color = "#dc3545"  # 红
                elif "ACM" in venue_name:
                    bg_color = "#007bff"  # 蓝
                elif "IEEE" in venue_name:
                    bg_color = "#00629b"  # 深蓝
                elif "ICML" in venue_name:
                    bg_color = "#e83e8c"  # 粉红
                elif "JMLR" in venue_name:
                    bg_color = "#20c997"  # 青绿
                
                venue_badge = f"""
                <span style="background:{bg_color}; color:white; padding:2px 6px; border-radius:4px; font-size:11px; font-weight:bold; margin-right:5px;" title="Detected via LaTeX Source">
                    🏛️ {venue_name}
                </span>
                """
            # 显示扫描状态（即使没有检测到模板）
            elif venue_name is None:
                # 显示"已扫描但未检测到"
                venue_badge = f"""
                <span style="background:#f0f0f0; color:#666; padding:2px 6px; border-radius:4px; font-size:11px;" title="Source scanned but no template detected">
                    🔍 Scanned
                </span>
                """
            
            html_content += f"""
                <div class="paper-card {score_class}">
                    <div style="margin-bottom: 8px;">
                        <span class="score-badge" style="background-color: {score_color};">Score: {score}/10</span>
                        {src_badge}
                        {venue_badge}
                        {github_badge}
                        <span style="color:#666; font-size:12px; float:right;">{p['published']}</span>
                    </div>
                    <a href="{p['pdf_url']}" class="title">{title_display}</a>
                    <div class="meta">
                        <strong>ID:</strong> {p['arxiv_id']} | <strong>Topic:</strong> {html.escape(p.get('topic', 'Unknown'))}<br>
                        <strong>Authors:</strong> {authors_display}
                    </div>
                    <div class="tldr">
                        <strong>💡 TL;DR:</strong> {tldr_display}
                    </div>
                    <div class="abstract">
                        <details>
                            <summary style="cursor: pointer; color: #0056b3;">Read Abstract (点击展开摘要)</summary>
                            <p>{summary_display}</p>
                            <hr>
                            <p style="font-size:12px; color:#999;">Original Title: {html.escape(p['title'])}</p>
                        </details>
                    </div>
                </div>
            """
            
        html_content += """
                <div class="footer">
                    Generated by ArXiv Agent v7.0 (Powered by GPT) | Personalized Profile Edition
                </div>
            </div>
        </body>
        </html>
        """
        return html_content

    def send_email(self, recipient_email: str, subject: str, papers: List[Dict], query: str, briefing: str, derived_queries: List[str] = None, chart_img: bytes = None):
        """发送邮件，支持嵌入图表"""
        if derived_queries is None:
            derived_queries = []
        try:
            # 创建related类型的multipart，用于嵌入图片
            msg = MIMEMultipart('related')
            msg['From'] = self.sender_email
            msg['To'] = recipient_email
            msg['Subject'] = subject
            
            # 创建alternative部分用于HTML内容
            alt = MIMEMultipart('alternative')
            msg.attach(alt)
            
            # 生成HTML，如果有图表则包含图表占位符
            html_body = self._generate_html(papers, query, briefing, derived_queries=derived_queries, has_chart=(chart_img is not None))
            alt.attach(MIMEText(html_body, 'html', 'utf-8'))
            
            # 如果有图表，嵌入图片
            if chart_img:
                img = MIMEImage(chart_img)
                img.add_header('Content-ID', '<trend_chart>')
                msg.attach(img)
            
            # 建立连接
            print(f"[*] 正在连接SMTP服务器...")
            if self.smtp_port in [465, 995]:
                print(f"[*] 使用SSL连接（端口 {self.smtp_port}）")
                server = smtplib.SMTP_SSL(self.smtp_server, self.smtp_port)
            else:
                print(f"[*] 使用TLS连接（端口 {self.smtp_port}）")
                server = smtplib.SMTP(self.smtp_server, self.smtp_port)
                server.starttls()
            
            print("[*] 正在登录...")
            server.login(self.sender_email, self.sender_password)
            print("[*] 正在发送邮件...")
            server.send_message(msg)
            server.quit()
            print(f"[*] 邮件已发送至")
            
        except Exception as e:
            print(f"[!] 发送邮件失败: {e}")
            raise


class ArXivAgent:
    """Agent 主控制器"""
    
    def __init__(self, query: str, recipient: str, broad_category: str = "cs", max_results: int = 10, days: int = 3):
        self.query = query
        self.recipient = recipient
        self.broad_category = broad_category
        self.days = days
        
        # 1. 加载用户画像
        # 优先使用环境变量，否则尝试多个可能的路径
        profile_path = os.getenv('USER_PROFILE_PATH')
        if not profile_path:
            # 尝试相对于代码文件的路径（code/main.py -> ../user_profile.json）
            code_dir = os.path.dirname(os.path.abspath(__file__))
            parent_dir = os.path.dirname(code_dir)
            profile_path = os.path.join(parent_dir, 'user_profile.json')
            # 如果不存在，尝试当前工作目录
            if not os.path.exists(profile_path):
                profile_path = 'user_profile.json'
        self.profile_mgr = UserProfileManager(profile_path)
        
        # 初始化组件
        self.fetcher = ArXivPaperFetcher(max_results=max_results)
        # 传递用户兴趣和画像管理器用于打分
        user_interest = os.getenv('USER_INTEREST', 'AI for Science')
        self.processor = PaperProcessor(
            profile_manager=self.profile_mgr,
            model=os.getenv('OPENAI_MODEL', 'gpt-3.5-turbo'),
            user_interest=user_interest
        )
        
        # 从环境变量读取邮件配置
        smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        smtp_port_str = os.getenv('SMTP_PORT', '587')
        smtp_port = int(smtp_port_str) if smtp_port_str else 587
        sender_email = os.getenv('SENDER_EMAIL')
        sender_password = os.getenv('SENDER_PASSWORD')
        
        if not sender_email or not sender_password:
            raise ValueError("请设置发送者邮箱和密码（通过环境变量SENDER_EMAIL和SENDER_PASSWORD）")
        
        self.email_sender = EmailSender(
            smtp_server,
            smtp_port,
            sender_email,
            sender_password
        )

    async def run(self):
        """运行主流程"""
        print("--- ArXiv Agent v7.0 Started (Personalized Profile Edition) ---")
        
        # 1. 画像增强：生成衍生关键词
        derived_queries = []
        if self.processor.client and self.processor.client.api_key:
            derived_queries = await self.profile_mgr.generate_derived_keywords(
                self.processor.client, 
                self.processor.model
            )
        
        manual_queries = [q.strip() for q in self.query.replace(';', ',').split(',') if q.strip()]
        
        # 2. 并行任务：混合爬取(手动+AI) + 宏观统计
        task_papers = asyncio.to_thread(
            self.fetcher.fetch_papers_mixed, 
            manual_queries, 
            derived_queries, 
            self.days
        )
        task_stats = asyncio.to_thread(
            self.fetcher.fetch_global_stats, 
            self.broad_category, 
            1
        )
        
        papers, stats_global = await asyncio.gather(task_papers, task_stats)
        
        if not papers:
            print("[-] 未找到论文，结束任务。")
            return

        print(f"[*] 成功获取 {len(papers)} 篇论文（手动: {len([p for p in papers if p.get('source_type') == 'Manual'])}, AI推荐: {len([p for p in papers if p.get('source_type') == 'AI Derived'])}），准备进行AI分析...")

        # 3. 智能分析
        processed_papers = await self.processor.process_batch(papers)
        processed_papers.sort(key=lambda x: x.get('score', 0), reverse=True)
        
        # 4. 生成图表和综述
        chart_img = Visualizer.draw_global_trend(stats_global)
        top_3_trends = ", ".join([f"{k}({v})" for k, v in stats_global.most_common(3)])
        briefing = await self.processor.generate_briefing(processed_papers, top_3_trends)
        
        # 5. 发送
        high_score_count = sum(1 for p in processed_papers if p.get('score', 0) >= 8)
        subject = f"ArXiv Report: {len(processed_papers)} Papers (Personalized)"
        
        self.email_sender.send_email(
            self.recipient,
            subject,
            processed_papers,
            self.query,
            briefing,
            derived_queries=derived_queries,
            chart_img=chart_img
        )
        print("--- Mission Complete ---")


async def main():
    """主函数"""
    # 配置
    query = os.getenv('ARXIV_QUERY', 'machine learning, llm agent')
    recipient = os.getenv('RECIPIENT_EMAIL', 'your_email@example.com')
    max_results = int(os.getenv('MAX_RESULTS', '10'))
    days = int(os.getenv('ARXIV_DAYS', '3'))  # 默认查看最近3天
    # 宏观分类：cs (计算机), q-bio (生物), stat (统计), physics (物理)
    broad_category = os.getenv('BROAD_CATEGORY', 'cs')
    
    agent = ArXivAgent(
        query=query,
        recipient=recipient,
        broad_category=broad_category,
        max_results=max_results,
        days=days
    )
    await agent.run()


if __name__ == "__main__":
    # 使用 asyncio 运行主程序
    asyncio.run(main())
