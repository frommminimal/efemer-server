import os
import sqlite3
import requests
import traceback
import time
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__, static_folder='static')
DATABASE = 'database.db'

def init_db():
    print("📀 Инициализация базы данных...")
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
    print("✅ База данных готова")

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

@app.route('/api/chat', methods=['POST'])
def chat():
    # ... (код получения сообщения и истории)

    # Указываем бесплатную модель, которую будем использовать
    # Для Эфемера я рекомендую начать с Qwen3.5-4B
    MODEL_NAME = "Qwen/Qwen3.5-4B"

    try:
        response = requests.post(
            "https://api.siliconflow.cn/v1/chat/completions", # адрес для текстовых моделей
            headers={
                "Authorization": f"Bearer {os.environ.get('SILICONFLOW_API_KEY')}",
                "Content-Type": "application/json"
            },
            json={
                "model": MODEL_NAME,          # <-- вот здесь указываем модель
                "messages": messages,
                "max_tokens": 500,
                "temperature": 0.7
            },
            timeout=30
        )
        # ... (обработка ответа)

        if response.status_code != 200:
            return jsonify({'error': 'SiliconFlow API error', 'details': response.text}), 500

        data = response.json()
        assistant_response = data['choices'][0]['message']['content']
        save_message(user_id, 'assistant', assistant_response)

        return jsonify({'response': assistant_response})

    except Exception as e:
        print(f"Ошибка: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000)
