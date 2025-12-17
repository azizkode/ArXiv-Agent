#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
邮件发送测试脚本
用于测试SMTP配置是否正确，能否正常发送邮件
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()


def test_email_send():
    """测试邮件发送功能"""
    
    # 从环境变量读取配置
    smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
    smtp_port = int(os.getenv('SMTP_PORT', '587'))
    sender_email = os.getenv('SENDER_EMAIL', 'your_email@example.com')
    sender_password = os.getenv('SENDER_PASSWORD', '')
    recipient_email = os.getenv('RECIPIENT_EMAIL', sender_email)
    
    # 检查配置
    print("=" * 50)
    print("邮件配置信息：")
    print(f"SMTP服务器: {smtp_server}")
    print(f"SMTP端口: {smtp_port}")
    print(f"发送者邮箱: {sender_email}")
    print(f"接收者邮箱: {recipient_email}")
    print("=" * 50)
    
    if not sender_password:
        print("\n❌ 错误：未设置 SENDER_PASSWORD")
        print("请在 .env 文件中设置 SENDER_PASSWORD")
        return False
    
    # 创建测试邮件
    msg = MIMEMultipart('alternative')
    msg['From'] = sender_email
    msg['To'] = recipient_email
    msg['Subject'] = 'ArXiv Agent 邮件发送测试'
    
    # 邮件正文（中英文）
    html_content = """
    <html>
      <head></head>
      <body>
        <h2>邮件发送测试</h2>
        <p>这是一封测试邮件，用于验证ArXiv Agent的邮件发送功能是否正常。</p>
        <hr>
        <h3>Email Send Test</h3>
        <p>This is a test email to verify that the ArXiv Agent email sending function is working correctly.</p>
        <hr>
        <p>如果你收到这封邮件，说明邮件配置正确！</p>
        <p>If you receive this email, it means the email configuration is correct!</p>
        <p><small>发送时间 / Sent at: {}</small></p>
      </body>
    </html>
    """.format(os.popen('date').read().strip())
    
    text_content = """
邮件发送测试
============

这是一封测试邮件，用于验证ArXiv Agent的邮件发送功能是否正常。

Email Send Test
===============

This is a test email to verify that the ArXiv Agent email sending function is working correctly.

如果你收到这封邮件，说明邮件配置正确！
If you receive this email, it means the email configuration is correct!
"""
    
    # 添加文本和HTML版本
    part1 = MIMEText(text_content, 'plain', 'utf-8')
    part2 = MIMEText(html_content, 'html', 'utf-8')
    
    msg.attach(part1)
    msg.attach(part2)
    
    # 尝试发送邮件
    try:
        print(f"\n正在连接SMTP服务器 {smtp_server}:{smtp_port}...")
        
        # 根据端口判断使用SSL还是TLS
        if smtp_port == 465 or smtp_port == 995:
            # 使用SSL连接
            print("使用SSL连接...")
            with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
                print("✓ SSL连接成功")
                print("正在登录...")
                server.login(sender_email, sender_password)
                print("✓ 登录成功")
                print("正在发送邮件...")
                server.send_message(msg)
                print("✓ 邮件发送成功！")
        else:
            # 使用TLS连接
            print("使用TLS连接...")
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                print("✓ SMTP连接成功")
                print("正在启动TLS...")
                server.starttls()
                print("✓ TLS启动成功")
                print("正在登录...")
                server.login(sender_email, sender_password)
                print("✓ 登录成功")
                print("正在发送邮件...")
                server.send_message(msg)
                print("✓ 邮件发送成功！")
        
        print("\n" + "=" * 50)
        print("✅ 测试成功！邮件已发送到:", recipient_email)
        print("=" * 50)
        return True
        
    except smtplib.SMTPAuthenticationError as e:
        print("\n" + "=" * 50)
        print("❌ 认证失败！")
        print("可能的原因：")
        print("1. 邮箱密码错误")
        print("2. 邮箱未启用SMTP服务")
        print("3. 需要使用应用专用密码（Gmail等）")
        print(f"\n错误详情: {e}")
        print("=" * 50)
        return False
        
    except smtplib.SMTPConnectError as e:
        print("\n" + "=" * 50)
        print("❌ SMTP连接失败！")
        print("可能的原因：")
        print("1. SMTP服务器地址错误")
        print("2. SMTP端口错误")
        print("3. 网络连接问题")
        print(f"\n错误详情: {e}")
        print("=" * 50)
        return False
        
    except Exception as e:
        print("\n" + "=" * 50)
        print("❌ 发送邮件时出错！")
        print(f"错误类型: {type(e).__name__}")
        print(f"错误详情: {e}")
        print("=" * 50)
        return False


def test_smtp_connection():
    """测试SMTP连接（不发送邮件）"""
    
    smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
    smtp_port = int(os.getenv('SMTP_PORT', '587'))
    
    print("=" * 50)
    print("测试SMTP连接...")
    print(f"服务器: {smtp_server}")
    print(f"端口: {smtp_port}")
    print("=" * 50)
    
    try:
        if smtp_port == 465 or smtp_port == 995:
            print("尝试SSL连接...")
            server = smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=10)
            print("✓ SSL连接成功！")
            server.quit()
        else:
            print("尝试TLS连接...")
            server = smtplib.SMTP(smtp_server, smtp_port, timeout=10)
            print("✓ SMTP连接成功！")
            server.starttls()
            print("✓ TLS启动成功！")
            server.quit()
        
        print("\n✅ SMTP连接测试通过！")
        return True
        
    except Exception as e:
        print(f"\n❌ SMTP连接失败: {e}")
        return False


if __name__ == "__main__":
    print("\n" + "=" * 50)
    print("ArXiv Agent 邮件发送测试")
    print("=" * 50 + "\n")
    
    # 先测试连接
    print("步骤1: 测试SMTP连接...")
    if test_smtp_connection():
        print("\n步骤2: 测试邮件发送...")
        test_email_send()
    else:
        print("\n⚠️  SMTP连接失败，请检查配置后再试")
        print("\n提示：")
        print("- 检查 .env 文件中的 SMTP_SERVER 和 SMTP_PORT")
        print("- 确认网络连接正常")
        print("- 如果使用防火墙，确认端口未被阻止")

