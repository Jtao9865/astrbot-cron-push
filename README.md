# AstrBot Plugin: cron_push
# 定时消息推送插件

## 功能说明
- 支持通过 Cron 表达式配置定时任务
- 向已知会话推送自定义消息

## 安装方式
将本文件夹复制到 AstrBot 的 stars 目录下即可自动加载。

## 配置说明
在 main.py 中的 TASKS 列表里添加/修改任务：
- enabled: 是否启用
- cron: Cron 表达式（如 * * * * * 表示每分钟）
- message: 推送的消息内容

## 依赖
- astrbot >= 3.0.0
- APScheduler
