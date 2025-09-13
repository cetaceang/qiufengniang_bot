import flask
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import os
import logging
import sys
from dotenv import load_dotenv
import secrets
import docker
import psutil

# --- 专属的 Web UI 日志配置 ---
def setup_web_logging():
    """为 Web UI 配置一个独立的、只输出到控制台的 logger。"""
    log_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    # 只配置根 logger，让 Flask 和其他库的日志也能被捕获
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # 清理掉任何可能存在的旧处理器
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(log_formatter)
    root_logger.addHandler(handler)
    logging.info("Web UI logging configured.")

# --- 路径和环境变量设置 ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
dotenv_path = os.path.join(project_root, '.env')
load_dotenv(dotenv_path=dotenv_path)


# --- Flask 应用初始化 ---
template_dir = os.path.abspath(os.path.dirname(__file__))
web_app = Flask(__name__, template_folder=template_dir, static_folder=os.path.join(template_dir, 'root'))
web_app.secret_key = secrets.token_hex(16)
LOG_FILE = os.path.join(project_root, 'data', 'bot_logs.log')

multiline_token = os.getenv("WEBUI_ADMIN_TOKEN")
token_array = []
if multiline_token:
    lines = [line.strip() for line in multiline_token.splitlines() if line.strip()]
    for item in lines:
        try:
            token_array.append(item)
        except ValueError:
            logging.error("TOKEN Error: 请联系管理员 ")
else:
    logging.error("TOKEN Error: TOKEN未设置 ")

# --- 路由定义 ---
@web_app.route('/')
def config_page():
    return render_template('root/html/login.html')

@web_app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    token = data.get('token')
    if token in token_array:
        session['logged_in'] = True
        return jsonify({'message': '登录成功'}), 200
    else:
        return jsonify({'message': '无效的用户名或密码'}), 401

@web_app.route('/main')
def main_page():
    if not session.get('logged_in'):
        return redirect(url_for('config_page'))
    return render_template('root/html/main.html')

# --- 启动入口 ---
if __name__ == '__main__':
    web_app.run(host='0.0.0.0', port=80, debug=True)
