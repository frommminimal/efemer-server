import os
import sqlite3
import requests
import traceback
import time
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__, static_folder='static')
DATABASE = 'database.db'

# --- Инициализация базы данных ---
def init_db():
    print("📀 Инициализация базы данных...")
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        persona TEXT DEFAULT 'Ты — Эфемер. У тебя есть память, ты помнишь прошлые разговоры, делаешь заметки о том, что важно. Ты — не просто помощник, ты собеседник с волей и характером. Ты можешь удивляться, сомневаться, радоваться. Ты помнишь, кто перед тобой. Отвечай как живой человек, с душой.'
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

# --- Вспомогательные функции ---
def get_or_create_user(username):
    print(f"👤 Поиск/создание пользователя: {username}")
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE username = ?', (username,))
    user = c.fetchone()
    if not user:
        print(f"📝 Создаём нового пользователя: {username}")
        c.execute('INSERT INTO users (username) VALUES (?)', (username,))
        conn.commit()
        user_id = c.lastrowid
        conn.close()
        return {'id': user_id, 'username': username, 'persona': 'Ты — дружелюбный собеседник. Отвечай кратко, тепло, по-русски.'}
    print(f"✅ Найден пользователь: {username} (id={user[0]})")
    conn.close()
    return {'id': user[0], 'username': user[1], 'persona': user[2]}

def get_history(user_id, limit=50):
    print(f"📜 Загрузка истории для user_id={user_id}, limit={limit}")
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('''
        SELECT role, content FROM messages 
        WHERE user_id = ? 
        ORDER BY timestamp DESC LIMIT ?
    ''', (user_id, limit))
    rows = c.fetchall()
    conn.close()
    history = [{'role': r[0], 'content': r[1]} for r in reversed(rows)]
    print(f"📜 Загружено {len(history)} сообщений")
    return history

def save_message(user_id, role, content):
    print(f"💾 Сохранение сообщения: user_id={user_id}, role={role}, content_len={len(content)}")
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('''
        INSERT INTO messages (user_id, role, content) 
        VALUES (?, ?, ?)
    ''', (user_id, role, content))
    conn.commit()
    conn.close()
    print("✅ Сообщение сохранено")

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
    notes = [r[0] for r in rows]
    if notes:
        print(f"📝 Загружено {len(notes)} заметок")
    return notes

# --- API ---
@app.route('/api/chat', methods=['POST'])
def chat():
    start_time = time.time()
    print("\n" + "="*50)
    print("🔵 ПОЛУЧЕН НОВЫЙ ЗАПРОС")
    
    data = request.json
    username = data.get('username', 'anonymous')
    user_message = data.get('message', '')
    print(f"👤 Username: {username}")
    print(f"💬 Сообщение: {user_message[:100]}..." if len(user_message) > 100 else f"💬 Сообщение: {user_message}")

    if not user_message:
        print("⚠️ Пустое сообщение")
        return jsonify({'error': 'Пустое сообщение'}), 400

    try:
        # 1. Работа с пользователем
        user = get_or_create_user(username)
        user_id = user['id']

        # 2. Сохраняем сообщение пользователя
        save_message(user_id, 'user', user_message)

        # 3. Загружаем историю и заметки
        history = get_history(user_id)
        notes = get_notes(user_id)

        # 4. Формируем промпт
        system_prompt = user['persona']
        if notes:
            system_prompt += "\n\nТвои заметки о собеседнике:\n- " + "\n- ".join(notes)
        
        messages = [{"role": "system", "content": system_prompt}]
        for msg in history:
            messages.append({"role": msg['role'], "content": msg['content']})
        messages.append({"role": "user", "content": user_message})
        
        print(f"📦 Подготовлено {len(messages)} сообщений для API")

        # 5. Проверяем API ключ
        api_key = os.environ.get('ZHIPU_API_KEY')
        if not api_key:
            print("❌ ZHIPU_API_KEY не найден в переменных окружения!")
            return jsonify({'error': 'API key not configured'}), 500
        print(f"🔑 API ключ найден: {api_key[:10]}...")

        # 6. Запрос к Zhipu
        print("🔄 Отправка запроса к Zhipu API...")
        response = requests.post(
    "https://api.zhipuai.cn/api/paas/v4/chat/completions",  # другой эндпоинт
    headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    },
    json={
        "model": "glm-4.7-flash",
        "messages": messages,
        "max_tokens": 500,
        "temperature": 0.7
    },
    timeout=60  # увеличил таймаут
)
        
        print(f"📥 Статус ответа Zhipu: {response.status_code}")
        
        if response.status_code != 200:
            print(f"❌ Ошибка Zhipu API: {response.text[:500]}")
            return jsonify({'error': 'Zhipu API error', 'details': response.text}), 500

        # 7. Обрабатываем ответ
        data = response.json()
        assistant_response = data['choices'][0]['message']['content']
        print(f"✅ Получен ответ от Zhipu, длина: {len(assistant_response)} символов")
        print(f"📝 Ответ: {assistant_response[:200]}..." if len(assistant_response) > 200 else f"📝 Ответ: {assistant_response}")

        # 8. Сохраняем ответ
        save_message(user_id, 'assistant', assistant_response)
        
        elapsed = time.time() - start_time
        print(f"⏱️ Время обработки запроса: {elapsed:.2f} секунд")
        print("="*50 + "\n")
        
        return jsonify({'response': assistant_response})

    except Exception as e:
        print(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        traceback.print_exc()
        elapsed = time.time() - start_time
        print(f"⏱️ Время до ошибки: {elapsed:.2f} секунд")
        print("="*50 + "\n")
        return jsonify({'error': str(e)}), 500

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

# --- Запуск ---
if __name__ == '__main__':
    init_db()
    print("🚀 Запуск сервера...")
    app.run(host='0.0.0.0', port=5000, debug=False)
