# 自建 Nitter 指南

## 前提
- Docker + Docker Compose
- 一个真实 Twitter/X 账号

## 部署
```bash
mkdir -p ~/nitter && cd ~/nitter
# 创建 docker-compose.yml 和 nitter.conf（确保 enableRSS=true）
# 获取 session token（浏览器 F12 → Cookies → auth_token + ct0）
docker compose up -d
```

## 测试
访问 `http://localhost:8585/karpathy/rss`，能看到 XML 就成功了。

## 配置
在 `intel_config.py` 中改为:
```python
NITTER_INSTANCES = ["http://localhost:8585"]
```

详细步骤参考: https://github.com/zedeus/nitter/wiki
