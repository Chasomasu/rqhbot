#!/usr/bin/env python3
"""
RqhBot 安装脚本

用法:
    pip install .              # 基础安装
    pip install -e .           # 开发模式安装
    pip install ".[openai]"    # 安装 OpenAI 可选依赖
    pip install ".[dev]"       # 安装开发依赖
"""

from setuptools import setup, find_packages

setup(
    name="rqhbot",
    version="3.8.0",
    description="基于 NapCat OneBot11 协议的 Python QQ 机器人开发框架",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    author="RqhBot Team",
    license="MIT",
    url="https://github.com/rqhbot/rqhbot",
    project_urls={
        "Documentation": "https://github.com/rqhbot/rqhbot/tree/main/docs",
        "Repository": "https://github.com/rqhbot/rqhbot",
        "Issues": "https://github.com/rqhbot/rqhbot/issues",
    },
    python_requires=">=3.10",
    packages=find_packages(include=["sdk*", "plugins*"]),
    # 插件静态资源（数据表、字典、图片等）通过 MANIFEST.in 声明后随包安装
    include_package_data=True,
    install_requires=[
        "websockets>=16.0",
        "PyYAML>=6.0",
        "python-dotenv>=1.0",
        "requests>=2.32",
        "aiohttp>=3.11",
        "packaging>=23.0",
        "Pillow>=9.0",
        "watchdog>=4.0",
    ],
    extras_require={
        "openai": ["openai>=1.55"],
        "dev": [
            "pytest>=8.0",
            "pytest-asyncio>=0.24",
            "pytest-cov>=5.0",
            "ruff>=0.5",
            "mypy>=1.10",
        ],
    },
    keywords=["qqbot", "onebot", "napcat", "chatbot"],
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Communications :: Chat",
    ],
)
