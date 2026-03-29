import os
import sqlite3
import requests
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__, static_folder='static')
DATABASE = 'database.db'

# --- Инициализация базы данных ---
def init_db():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            persona TEXT DEFAULT 'Ты — дружелюбный собеседник. Отвечай кратко, тепло, по-русски.'
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            role TEXT,
            content TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            note TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

# --- Вспомогательные функции ---
def get_or_create_user(username):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE username = ?', (username,))
    user = c.fetchone()
    if not user:
        c.execute('INSERT INTO users (username) VALUES (?)', (username,))
        conn.commit()
        user_id = c.lastrowid
        conn.close()
        return {'id': user_id, 'username': username, 'persona': 'Ты — дружелюбный собеседник. Отвечай кратко, тепло, по-русски.'}
    conn.close()
    return {'id': user[0], 'username': user[1], 'persona': user[2]}

def get_history(user_id, limit=50):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('''
        SELECT role, content FROM messages 
        WHERE user_id = ? 
        ORDER BY timestamp DESC LIMIT ?
    ''', (user_id, limit))
    rows = c.fetchall()
    conn.close()
    return [{'role': r[0], 'content': r[1]} for r in reversed(rows)]

def save_message(user_id, role, content):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('''
        INSERT INTO messages (user_id, role, content) 
        VALUES (?, ?, ?)
    ''', (user_id, role, content))
    conn.commit()
    conn.close()

def get_notes(user_id, limit=5):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('''
        SELECT note FROM notes 
        WHERE user_id = ? 
        ORDER BY created_at DESC LIMIT ?
    ''', (user_id, limit))
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows]

# --- API ---
@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.json
    username = data.get('username', 'anonymous')
    user_message = data.get('message', '')

    if not user_message:
        return jsonify({'error': 'Пустое сообщение'}), 400

    user = get_or_create_user(username)
    user_id = user['id']

    save_message(user_id, 'user', user_message)

    history = get_history(user_id)
    notes = get_notes(user_id)

    system_prompt = user['persona']
    if notes:
        system_prompt += "\n\nТвои заметки о собеседнике:\n- " + "\n- ".join(notes)

    messages = [{"role": "system", "content": system_prompt}]
    for msg in history:
        messages.append({"role": msg['role'], "content": msg['content']})
    messages.append({"role": "user", "content": user_message})

    api_key = os.environ.get('DEEPSEEK_API_KEY')
    if not api_key:
        return jsonify({'error': 'API key not configured'}), 500

    try:
        response = requests.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "deepseek-chat",
                "messages": messages,
                "max_tokens": 500,
                "temperature": 0.7
            }
        )
        if response.status_code != 200:
            return jsonify({'error': 'DeepSeek API error', 'details': response.text}), 500

        data = response.json()
        assistant_response = data['choices'][0]['message']['content']
        save_message(user_id, 'assistant', assistant_response)

        return jsonify({'response': assistant_response})

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

# --- Запуск ---
if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000)
