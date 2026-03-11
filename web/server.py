"""
GeoClaw Web Chat Server
=======================
轻量 Flask API，将 GeoAgent 对话能力暴露为 HTTP 接口。

用法:
    cd GeoClaw_Claude
    python web/server.py                    # 默认 http://localhost:7860
    python web/server.py --port 8080        # 自定义端口
    python web/server.py --rule             # 强制规则模式（无需 API Key）
"""

import sys
import os
import argparse
import json
import time
from pathlib import Path

# 将项目根目录加入路径
_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS  # type: ignore

app = Flask(__name__, static_folder="static")
CORS(app)

# ── 全局 Agent（单实例，多轮对话共享）──────────────────────────
_agent = None
_agent_mode = None  # "ai" / "rule" / None

def get_agent(mode=None):
    global _agent, _agent_mode
    if _agent is None or mode != _agent_mode:
        from geoclaw_claude.nl import GeoAgent
        use_ai = True if mode == "ai" else (False if mode == "rule" else None)
        _agent = GeoAgent(use_ai=use_ai, verbose=False)
        _agent_mode = mode
    return _agent


# ── 路由 ────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(Path(__file__).parent, "index.html")


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(force=True)
    message = (data.get("message") or "").strip()
    mode    = data.get("mode")   # "ai" / "rule" / null

    if not message:
        return jsonify({"error": "message is required"}), 400

    t0 = time.time()
    try:
        agent  = get_agent(mode)
        reply  = agent.chat(message)
        elapsed = round(time.time() - t0, 2)

        # 获取 AI 模式状态
        is_ai = getattr(agent._proc, "_use_ai", False)
        provider = ""
        if is_ai and agent._proc._llm:
            provider = agent._proc._llm.provider_name

        return jsonify({
            "reply":    reply,
            "elapsed":  elapsed,
            "is_ai":    is_ai,
            "provider": provider,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/status", methods=["GET"])
def status():
    try:
        agent = get_agent()
        s = agent.status()
        is_ai = getattr(agent._proc, "_use_ai", False)
        provider = ""
        if is_ai and agent._proc._llm:
            provider = agent._proc._llm.provider_name
        return jsonify({
            **s,
            "is_ai":    is_ai,
            "provider": provider,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/reset", methods=["POST"])
def reset():
    global _agent, _agent_mode
    try:
        if _agent:
            try:
                _agent.end(title="Web 会话重置")
            except Exception:
                pass
        _agent = None
        _agent_mode = None
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/layers", methods=["GET"])
def layers():
    try:
        agent = get_agent()
        layer_list = agent._exec.list_layers()
        return jsonify({"layers": layer_list})
    except Exception as e:
        return jsonify({"layers": [], "error": str(e)})


# ── 启动 ────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GeoClaw Web Chat Server")
    parser.add_argument("--port",  type=int, default=7860, help="监听端口（默认 7860）")
    parser.add_argument("--host",  default="127.0.0.1",    help="监听地址（默认 127.0.0.1）")
    parser.add_argument("--rule",  action="store_true",    help="强制规则模式")
    parser.add_argument("--ai",    action="store_true",    help="强制 AI 模式")
    args = parser.parse_args()

    mode = "rule" if args.rule else ("ai" if args.ai else None)

    # 预热 Agent
    print(f"\n  GeoClaw Web Chat  →  http://{args.host}:{args.port}")
    try:
        agent = get_agent(mode)
        is_ai = getattr(agent._proc, "_use_ai", False)
        provider = agent._proc._llm.provider_name if is_ai and agent._proc._llm else "规则"
        print(f"  模式: {'AI (' + provider + ')' if is_ai else '离线规则'}\n")
    except Exception as e:
        print(f"  ⚠ Agent 初始化警告: {e}\n")

    try:
        from flask_cors import CORS  # noqa
    except ImportError:
        print("  提示: pip install flask-cors 可启用跨域支持\n")

    app.run(host=args.host, port=args.port, debug=False)
