# app.py (COMPLETO COM TODAS AS ROTAS)
import platform
import json
import sqlite3
import threading
import time
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_socketio import SocketIO, emit
import bcrypt
import os

# --- GPIO ---
if platform.system() == "Windows":
    from gpio_mock import GPIO, DHT22
else:
    import RPi.GPIO as GPIO
    import adafruit_dht

# --- CONFIG ---
app = Flask(__name__)
app.secret_key = 'super_secret_key_change_me'
socketio = SocketIO(app, cors_allowed_origins="*")

CONFIG_DIR = 'config'
DATA_DIR = 'data'
os.makedirs(CONFIG_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

DEVICES_PATH = f'{CONFIG_DIR}/devices.json'
AUTOMATIONS_PATH = f'{CONFIG_DIR}/automations.json'
USERS_DB = f'{CONFIG_DIR}/users.db'

# --- INIT DB ---
def init_db():
    conn = sqlite3.connect(USERS_DB)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        username TEXT UNIQUE,
        password TEXT,
        is_admin INTEGER
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY,
        timestamp TEXT,
        device TEXT,
        event TEXT,
        value TEXT
    )''')
    hashed = bcrypt.hashpw('admin123'.encode(), bcrypt.gensalt())
    c.execute("INSERT OR IGNORE INTO users (username, password, is_admin) VALUES (?, ?, ?)",
              ('admin', hashed, 1))
    conn.commit()
    conn.close()

def log_event(device, event, value=""):
    conn = sqlite3.connect(USERS_DB)
    c = conn.cursor()
    c.execute("INSERT INTO logs (timestamp, device, event, value) VALUES (?, ?, ?, ?)",
              (datetime.now().isoformat(), device, event, str(value)))
    conn.commit()
    conn.close()

# --- CARREGA CONFIGS ---
def load_json(path, default):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(default, f, indent=4)
        return default

devices = load_json(DEVICES_PATH, [
    {"id": "led_sala", "name": "Lâmpada Sala", "type": "led", "pin": 18, "state": False},
    {"id": "relay_quarto", "name": "Tomada Quarto", "type": "relay", "pin": 23, "state": False},
    {"id": "pir_corredor", "name": "Sensor Movimento", "type": "pir", "pin": 17, "enabled": True},
    {"id": "dht_sala", "name": "Temp/Umidade Sala", "type": "dht22", "pin": 4}
])
automations = load_json(AUTOMATIONS_PATH, [])

# --- GPIO SETUP ---
GPIO.setmode(GPIO.BCM)
dht_device = None

for dev in devices:
    if dev['type'] in ['led', 'relay']:
        GPIO.setup(dev['pin'], GPIO.OUT)
        GPIO.output(dev['pin'], GPIO.HIGH if dev['state'] else GPIO.LOW)
    elif dev['type'] == 'pir':
        GPIO.setup(dev['pin'], GPIO.IN)
    elif dev['type'] == 'dht22' and platform.system() != "Windows":
        dht_device = adafruit_dht.DHT22(dev['pin'])

# --- FUNÇÕES ---
def set_device_state(dev_id, state):
    dev = next((d for d in devices if d['id'] == dev_id), None)
    if not dev or dev['type'] not in ['led', 'relay']:
        return
    dev['state'] = state
    GPIO.output(dev['pin'], GPIO.HIGH if state else GPIO.LOW)
    with open(DEVICES_PATH, 'w') as f:
        json.dump(devices, f, indent=4)
    log_event(dev['name'], 'state_change', 'ON' if state else 'OFF')
    broadcast_status()

def get_all_status():
    status = {}
    for dev in devices:
        if dev['type'] in ['led', 'relay']:
            status[dev['id']] = dev['state']
        elif dev['type'] == 'dht22':
            if platform.system() == "Windows":
                temp, hum = 24.5, 55.0
            else:
                try:
                    temp = dht_device.temperature
                    hum = dht_device.humidity
                except:
                    temp, hum = None, None
            status[dev['id']] = {'temp': temp, 'hum': hum}
    return status

def broadcast_status():
    socketio.emit('status', get_all_status())

# --- THREADS ---
def sensor_thread():
    while True:
        for dev in devices:
            if dev['type'] == 'pir' and dev.get('enabled', False):
                if GPIO.input(dev['pin']):
                    set_device_state('led_sala', True)
                    time.sleep(5)
                    set_device_state('led_sala', False)
            elif dev['type'] == 'dht22':
                time.sleep(2)
                temp = 24.5 + (time.time() % 5) if platform.system() == "Windows" else (dht_device.temperature or 0)
                hum = 55.0 + (time.time() % 10) if platform.system() == "Windows" else (dht_device.humidity or 0)
                socketio.emit('sensor_update', {
                    'id': dev['id'],
                    'temp': round(temp, 1),
                    'hum': round(hum, 1)
                })
        time.sleep(0.1)

threading.Thread(target=sensor_thread, daemon=True).start()

# --- ROTAS ---
@app.route('/')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('dashboard.html', devices=devices)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = sqlite3.connect(USERS_DB)
        c = conn.cursor()
        c.execute("SELECT id, password, is_admin FROM users WHERE username=?", (username,))
        user = c.fetchone()
        conn.close()
        if user and bcrypt.checkpw(password.encode(), user[1].encode()):
            session['user_id'] = user[0]
            session['username'] = username
            session['is_admin'] = bool(user[2])
            return redirect(url_for('dashboard'))
        return render_template('login.html', error="Credenciais inválidas")
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
        conn = sqlite3.connect(USERS_DB)
        c = conn.cursor()
        try:
            c.execute("INSERT INTO users (username, password, is_admin) VALUES (?, ?, ?)",
                      (username, hashed.decode(), 0))
            conn.commit()
            return redirect(url_for('login'))
        except:
            return render_template('register.html', error="Usuário já existe")
        finally:
            conn.close()
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/toggle/<dev_id>')
def toggle(dev_id):
    dev = next((d for d in devices if d['id'] == dev_id), None)
    if dev:
        set_device_state(dev_id, not dev['state'])
    return redirect(url_for('dashboard'))

@app.route('/devices')
def devices_page():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('devices.html', devices=devices)

@app.route('/add_device', methods=['POST'])
def add_device():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    name = request.form['name'].strip()
    dev_type = request.form['type']
    pin = int(request.form['pin'])

    if any(d['pin'] == pin for d in devices):
        return render_template('devices.html', devices=devices, error="Pino GPIO já em uso!")
    if any(d['name'].lower() == name.lower() for d in devices):
        return render_template('devices.html', devices=devices, error="Nome já existe!")

    new_id = name.lower().replace(' ', '_').replace('-', '_')
    new_dev = {
        "id": new_id,
        "name": name,
        "type": dev_type,
        "pin": pin,
        "state": False
    }

    if dev_type in ['led', 'relay']:
        GPIO.setup(pin, GPIO.OUT)
        GPIO.output(pin, GPIO.LOW)
    elif dev_type == 'pir':
        GPIO.setup(pin, GPIO.IN)

    devices.append(new_dev)
    with open(DEVICES_PATH, 'w', encoding='utf-8') as f:
        json.dump(devices, f, indent=4)

    log_event(name, 'device_added', f"Tipo: {dev_type}, Pino: {pin}")
    return redirect(url_for('devices_page'))

@app.route('/delete_device/<dev_id>')
def delete_device(dev_id):
    if 'user_id' not in session or not session.get('is_admin'):
        return redirect(url_for('login'))

    global devices
    dev = next((d for d in devices if d['id'] == dev_id), None)
    if dev:
        if dev['type'] in ['led', 'relay', 'pir']:
            try:
                GPIO.cleanup(dev['pin'])
            except:
                pass
        devices = [d for d in devices if d['id'] != dev_id]
        with open(DEVICES_PATH, 'w') as f:
            json.dump(devices, f, indent=4)
        log_event(dev['name'], 'device_removed')
    return redirect(url_for('devices_page'))

@app.route('/automations')
def automations_page():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('automations.html', devices=devices, automations=automations)

@app.route('/add_automation', methods=['POST'])
def add_automation():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    name = request.form['name'].strip()
    trigger_device = request.form['trigger_device']
    condition = request.form['condition']
    value = float(request.form['value'])
    action_device = request.form['action_device']
    action_state = request.form['action_state'] == 'true'

    new_auto = {
        "id": f"auto_{len(automations)+1}",
        "name": name,
        "trigger": {
            "device": trigger_device,
            "condition": condition,
            "value": value
        },
        "action": {
            "device": action_device,
            "state": action_state
        },
        "enabled": True
    }

    automations.append(new_auto)
    with open(AUTOMATIONS_PATH, 'w', encoding='utf-8') as f:
        json.dump(automations, f, indent=4)

    log_event("Automação", 'automation_added', name)
    return redirect(url_for('automations_page'))

@app.route('/delete_automation/<int:auto_id>')
def delete_automation(auto_id):
    if 'user_id' not in session or not session.get('is_admin'):
        return redirect(url_for('login'))

    global automations
    auto = next((a for a in automations if a['id'] == f"auto_{auto_id}"), None)
    if auto:
        automations = [a for a in automations if a['id'] != f"auto_{auto_id}"]
        with open(AUTOMATIONS_PATH, 'w') as f:
            json.dump(automations, f, indent=4)
        log_event("Automação", 'automation_removed', auto['name'])
    return redirect(url_for('automations_page'))

@app.route('/logs')
def logs_page():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = sqlite3.connect(USERS_DB)
    c = conn.cursor()
    c.execute("SELECT * FROM logs ORDER BY id DESC LIMIT 50")
    logs = [dict(zip(['id','timestamp','device','event','value'], row)) for row in c.fetchall()]
    conn.close()
    return render_template('logs.html', logs=logs)

# --- SOCKETIO ---
@socketio.on('connect')
def handle_connect():
    emit('status', get_all_status())

# --- INIT ---
init_db()

if __name__ == '__main__':
    print(f"[INFO] Rodando em {'MOCK (Windows)' if platform.system() == 'Windows' else 'Raspberry Pi'}")
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)