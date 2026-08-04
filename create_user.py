import os
import sqlite3
from werkzeug.security import generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.environ.get('DATABASE_PATH', os.path.join(BASE_DIR, 'database.db'))

conn = sqlite3.connect(DATABASE)
c = conn.cursor()

c.execute('''
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL DEFAULT '',
    plan TEXT NOT NULL DEFAULT 'free',
    avatar TEXT,
    created TEXT NOT NULL,
    skills TEXT NOT NULL DEFAULT '[]',
    target_role TEXT NOT NULL DEFAULT ''
)
''')

email = "vindhiya@gmail.com"
name = "Vindhiya"
password = "123456"
avatar = f"https://api.dicebear.com/7.x/initials/svg?seed={name}"

c.execute('SELECT 1 FROM users WHERE email = ?', (email,))
if c.fetchone():
    print("User already exists")
else:
    c.execute('''
        INSERT INTO users
        (id, name, email, password, plan, avatar, created, skills, target_role)
        VALUES (?, ?, ?, ?, ?, ?, datetime('now'), ?, ?)
    ''', (
        'vindhiya-demo-user',
        name,
        email,
        generate_password_hash(password),
        'free',
        avatar,
        '[]',
        ''
    ))
    conn.commit()
    print("User created: vindhiya@gmail.com / 123456")

conn.close()
