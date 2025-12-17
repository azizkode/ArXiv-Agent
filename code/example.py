#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ArXiv Agent使用示例
"""

from main import ArXivAgent
import os

# 示例1：搜索机器学习相关论文
def example1():
    """基本使用示例"""
    agent = ArXivAgent(
        query="machine learning",
        recipient_email="your_email@example.com",
        max_results=5,
        days=7
    )
    agent.run()


# 示例2：搜索深度学习相关论文
def example2():
    """搜索深度学习论文"""
    agent = ArXivAgent(
        query="deep learning",
        recipient_email="your_email@example.com",
        max_results=10,
        days=3
    )
    agent.run()


# 示例3：搜索量子计算相关论文
def example3():
    """搜索量子计算论文"""
    agent = ArXivAgent(
        query="quantum computing",
        recipient_email="your_email@example.com",
        max_results=8,
        days=14
    )
    agent.run()


# 示例4：使用自定义邮件服务器
def example4():
    """使用自定义SMTP服务器"""
    agent = ArXivAgent(
        query="natural language processing",
        recipient_email="your_email@example.com",
        smtp_server="smtp.qq.com",  # QQ邮箱
        smtp_port=587,
        sender_email="your_qq_email@qq.com",
        sender_password="your_password",
        max_results=10,
        days=7
    )
    agent.run()


if __name__ == "__main__":
    # 运行示例（记得修改邮箱地址）
    print("请先修改示例中的邮箱地址，然后取消注释下面的代码来运行")
    # example1()

