# GeoClaw Web Chat

GeoClaw 的 Web 对话前端，提供地图科技感的深色主题界面。

## 启动

```bash
# 在项目根目录运行
python web/server.py                   # 默认 http://localhost:7860
python web/server.py --port 8080       # 自定义端口
python web/server.py --rule            # 离线规则模式（无需 API Key）
python web/server.py --ai              # 强制 AI 模式
```

打开浏览器访问 `http://localhost:7860` 即可使用。

## 文件结构

```
web/
├── server.py     Flask API 服务器
├── index.html    前端界面（单文件，无需构建）
└── README.md
```

## API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 前端页面 |
| `/api/chat` | POST | 发送消息，返回回复 |
| `/api/status` | GET | 获取会话状态 |
| `/api/reset` | POST | 重置会话 |
| `/api/layers` | GET | 获取当前图层列表 |
