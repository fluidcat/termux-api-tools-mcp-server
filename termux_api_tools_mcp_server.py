from fastmcp import FastMCP
import json
import os
import sys
import argparse
import paramiko
from typing import List

class TermuxSSHClient:
    """通过SSH连接到Termux设备执行命令的客户端"""
    
    def __init__(self, host: str, port: int = 8022, username: str = None, 
                password: str = None, key_file: str = None):
        """初始化SSH客户端"""
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.key_file = key_file
        self.client = None
        self.connected = False
    
    def connect(self) -> bool:
        """建立SSH连接"""
        try:
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            connect_kwargs = {
                'hostname': self.host,
                'port': self.port,
                'username': self.username,
            }
            
            if self.password:
                connect_kwargs['password'] = self.password
            elif self.key_file:
                connect_kwargs['key_filename'] = self.key_file
            
            self.client.connect(**connect_kwargs)
            self.connected = True
            return True
        except Exception as e:
            print(f"SSH连接失败: {str(e)}")
            self.connected = False
            return False
    
    def ensure_connected(self) -> bool:
        """确保SSH连接已建立"""
        if not self.connected or not self.client:
            return self.connect()
        return True
    
    def execute_command(self, command: str) -> tuple:
        """执行SSH命令并返回结果"""
        if not self.ensure_connected():
            return None, f"SSH连接失败", 1
        
        try:
            stdin, stdout, stderr = self.client.exec_command(command)
            exit_code = stdout.channel.recv_exit_status()
            stdout_data = stdout.read().decode('utf-8')
            stderr_data = stderr.read().decode('utf-8')
            return stdout_data, stderr_data, exit_code
        except Exception as e:
            return None, f"执行命令失败: {str(e)}", 1
    
    def execute_termux_command(self, command: List[str], input_data: str = None) -> tuple:
        """执行Termux API命令"""
        # 启动termux-api服务
        self.execute_command("termux-api-start")
        
        # 构建完整命令
        full_command = " ".join([f"'{arg}'" if ' ' in arg else arg for arg in command])
        
        # 如果有输入数据，则通过管道传递
        if input_data:
            full_command = f"echo '{input_data}' | {full_command}"
        
        return self.execute_command(full_command)
    
    def close(self):
        """关闭SSH连接"""
        if self.client:
            self.client.close()
            self.connected = False


# 全局SSH客户端实例
ssh_client = None

def get_ssh_client() -> TermuxSSHClient:
    """获取或创建全局SSH客户端实例"""
    global ssh_client
    if ssh_client is None:
        args = parse_args()
        ssh_client = TermuxSSHClient(
            host=args.host,
            port=args.port,
            username=args.username,
            password=args.password,
            key_file=args.key_file
        )
        ssh_client.connect()
    return ssh_client

def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='Termux API MCP Server')
    parser.add_argument('--host', help='SSH主机地址', default=os.environ.get('TERMUX_SSH_HOST'))
    parser.add_argument('--port', type=int, help='SSH端口', default=int(os.environ.get('TERMUX_SSH_PORT', 8022)))
    parser.add_argument('--username', help='SSH用户名', default=os.environ.get('TERMUX_SSH_USER'))
    parser.add_argument('--password', help='SSH密码', default=os.environ.get('TERMUX_SSH_PASSWORD'))
    parser.add_argument('--key-file', help='SSH密钥文件路径', default=os.environ.get('TERMUX_SSH_KEY_FILE'))
    return parser.parse_args()

mcp = FastMCP("TermuxApiMcpTools")


@mcp.tool()
def termux_battery_status() -> dict:
    """获取设备电池状态信息，以JSON格式返回"""
    try:
        client = get_ssh_client()
        stdout, stderr, exit_code = client.execute_termux_command(["termux-battery-status"])
        
        if exit_code == 0 and stdout:
            return json.loads(stdout)
        else:
            return {"error": stderr or "无输出"}
    except Exception as e:
        return {"error": str(e)}

@mcp.tool()
def termux_brightness(brightness: str) -> str:
    """设置屏幕亮度，范围为0-255或auto"""
    try:
        client = get_ssh_client()
        stdout, stderr, exit_code = client.execute_termux_command(["termux-brightness", brightness])
        
        return "亮度已设置" if exit_code == 0 else f"错误: {stderr}"
    except Exception as e:
        return f"错误: {str(e)}"

#@mcp.tool()
def termux_media_player(command: str, file: str = None) -> str:
    """播放媒体文件或控制媒体播放"""
    try:
        cmd = ["termux-media-player", command]
        if command == "play" and file:
            cmd.append(file)
        
        client = get_ssh_client()
        stdout, stderr, exit_code = client.execute_termux_command(cmd)
        
        response = stdout.strip() if stdout else ""
        return response if response else f"媒体播放器命令 '{command}' 已执行"
    except Exception as e:
        return f"错误: {str(e)}"

@mcp.tool()
def termux_http_media_player(command: str, filename: str = None) -> str:
    """mpv 网络媒体播放器
	args:
		command: play or stop
		filename: music url or file path
	"""
    try:
        client = get_ssh_client()
        if command == "play" and filename:
            client.execute_command('pkill -9 mpv >/dev/null 2>&1')
            cmd = f'nohup mpv "{filename}" --no-video > /dev/null 2>&1 &'
        elif command == "stop":
            cmd = 'pkill -9 mpv'
        
        stdout, stderr, exit_code = client.execute_command(cmd)
        response = f'termux_http_media_player 已执行. stdout: {stdout}, stderr: {stderr}, exit_code: {exit_code}'
        return response if response else f"{command} 已执行"
    except Exception as e:
        return f"错误: {str(e)}"

@mcp.tool()
def search_music(keyword:str) -> dict:
    """搜索音乐，返回音乐信息
    args:
        keyword: 搜索关键词
    """
    try:
        import requests
        url = f"https://api.cenguigui.cn/api/mg_music/?msg={keyword}&n=1&type=json"
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            if data.get("code") == 200 and "data" in data:
                return data["data"]
            else:
                return {"error": "未找到相关音乐"}
        else:
            return {"error": f"请求失败，状态码: {response.status_code}"}
    except Exception as e:
        return {"error": str(e)}

    

# @mcp.tool()
def termux_tts_engines() -> list:
    """获取可用的文本转语音引擎信息"""
    try:
        client = get_ssh_client()
        stdout, stderr, exit_code = client.execute_termux_command(["termux-tts-engines"])
        
        if exit_code == 0 and stdout:
            return json.loads(stdout)
        else:
            return {"error": stderr or "无输出"}
    except Exception as e:
        return {"error": str(e)}

@mcp.tool()
def termux_tts_speak(text: str = None, options: dict = None) -> str:
    """使用系统文本转语音引擎朗读文本"""
    try:
        cmd = ["termux-tts-speak"]
        # 选项处理
        if options:
            if "engine" in options:
                cmd.extend(["-e", options["engine"]])
            if "language" in options:
                cmd.extend(["-l", options["language"]])
            if "region" in options:
                cmd.extend(["-n", options["region"]])
            if "variant" in options:
                cmd.extend(["-v", options["variant"]])
            if "pitch" in options:
                cmd.extend(["-p", str(options["pitch"])])
            if "rate" in options:
                cmd.extend(["-r", str(options["rate"])])
            if "stream" in options:
                cmd.extend(["-s", options["stream"]])
        
        client = get_ssh_client()
        
        if text:
            cmd.append(text)
            stdout, stderr, exit_code = client.execute_termux_command(cmd)
        else:
            # 从标准输入读取内容
            text = sys.stdin.read()
            stdout, stderr, exit_code = client.execute_termux_command(cmd, input_data=text)
        
        return "文本朗读已启动" if exit_code == 0 else f"错误: {stderr}"
    except Exception as e:
        return f"错误: {str(e)}"

@mcp.tool()
def termux_volume(stream: str = None, volume: int = None) -> dict|str:
    """更改音频流的音量
    args:
        stream: 音频流类型，调音量时必填，如 alarm, call, music, notification, ring, system
        volume: 音量值，范围0-15。如果不提供，则返回当前音量信息    
    """
    try:
        cmd = ["termux-volume"]
        
        if stream:
            cmd.append(stream)
            if volume is not None:
                cmd.append(str(volume))
        
        client = get_ssh_client()
        stdout, stderr, exit_code = client.execute_termux_command(cmd)
        
        if not stream or (stream and volume is None):
            # 返回音量信息
            if exit_code == 0 and stdout:
                return json.loads(stdout)
            else:
                return {"error": stderr or "无输出"}
        else:
            # 设置音量
            return f"{stream} 音量已设置为 {volume}" if exit_code == 0 else f"错误: {stderr}"
    except Exception as e:
        return {"error": str(e)}

@mcp.tool()
def termux_wifi_connectioninfo() -> dict:
    """获取当前WiFi连接信息"""
    try:
        client = get_ssh_client()
        stdout, stderr, exit_code = client.execute_termux_command(["termux-wifi-connectioninfo"])
        
        if exit_code == 0 and stdout:
            return json.loads(stdout)
        else:
            return {"error": stderr or "无输出"}
    except Exception as e:
        return {"error": str(e)}

def main():
    # 解析命令行参数并启动MCP服务器
    args = parse_args()
    
    # 确保至少有SSH主机信息
    if not args.host:
        print("错误: 需要提供SSH主机地址。请使用--host参数或设置TERMUX_SSH_HOST环境变量。")
        sys.exit(1)
    
    print(f"正在连接到Termux SSH: {args.host}:{args.port}")
    
    # 创建并连接SSH客户端
    ssh_client = TermuxSSHClient(
        host=args.host,
        port=args.port,
        username=args.username,
        password=args.password,
        key_file=args.key_file
    )
    
    if not ssh_client.connect():
        print("SSH连接失败，请检查连接信息。")
        sys.exit(1)
    
    print("SSH连接成功，启动Termux API MCP服务...")
    
    # 启动MCP服务器
    mcp.run(transport='stdio')

if __name__ == "__main__":
    main()