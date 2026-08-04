from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_cors import CORS
import os
import json
import re
import sqlite3
from datetime import datetime
import hashlib
import secrets
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-only-change-this-secret-key')
CORS(app, supports_credentials=True)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.environ.get('DATABASE_PATH', os.path.join(BASE_DIR, 'database.db'))

CHAT_HISTORY = {}
RESUMES = {}

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute('''
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
    conn.commit()
    conn.close()

def get_user(email):
    conn = get_db()
    row = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
    conn.close()
    return dict(row) if row else None

def public_user(user):
    return {
        'email': user['email'],
        'name': user['name'],
        'plan': user['plan'],
        'avatar': user['avatar']
    }

init_db()

# ─── Routes ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect('/')
    return render_template('dashboard.html', user=session['user'])

@app.route('/api/auth/signup', methods=['POST'])
def signup():
    data = request.get_json(silent=True) or {}
    email = data.get('email', '').lower().strip()
    name = data.get('name', '').strip()
    password = data.get('password', '')

    if not email or not password or not name:
        return jsonify({'error': 'All fields required'}), 400

    if get_user(email):
        return jsonify({'error': 'Email already registered'}), 400

    user = {
        'id': secrets.token_hex(8),
        'name': name,
        'email': email,
        'password': generate_password_hash(password),
        'plan': 'free',
        'avatar': f"https://api.dicebear.com/7.x/initials/svg?seed={name}",
        'created': datetime.now().isoformat(),
        'skills': '[]',
        'target_role': ''
    }

    conn = get_db()
    conn.execute('''
        INSERT INTO users (id, name, email, password, plan, avatar, created, skills, target_role)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        user['id'], user['name'], user['email'], user['password'],
        user['plan'], user['avatar'], user['created'],
        user['skills'], user['target_role']
    ))
    conn.commit()
    conn.close()

    session['user'] = public_user(user)
    return jsonify({'success': True, 'user': session['user']})

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}
    email = data.get('email', '').lower().strip()
    password = data.get('password', '')

    user = get_user(email)

    if not user or not user['password']:
        return jsonify({'error': 'Invalid credentials'}), 401

    stored_password = user['password']
    valid = False

    # New users use Werkzeug password hashes.
    if stored_password.startswith(('scrypt:', 'pbkdf2:')):
        valid = check_password_hash(stored_password, password)
    # Backward compatibility for the old CareerLens SHA-256 passwords.
    elif len(stored_password) == 64 and all(c in '0123456789abcdef' for c in stored_password.lower()):
        valid = secrets.compare_digest(stored_password, hashlib.sha256(password.encode()).hexdigest())
        if valid:
            new_hash = generate_password_hash(password)
            conn = get_db()
            conn.execute('UPDATE users SET password = ? WHERE email = ?', (new_hash, email))
            conn.commit()
            conn.close()
    else:
        # Temporary compatibility for an old plain-text local database.
        valid = secrets.compare_digest(stored_password, password)
        if valid:
            new_hash = generate_password_hash(password)
            conn = get_db()
            conn.execute('UPDATE users SET password = ? WHERE email = ?', (new_hash, email))
            conn.commit()
            conn.close()

    if not valid:
        return jsonify({'error': 'Invalid credentials'}), 401

    session['user'] = public_user(user)
    return jsonify({'success': True, 'user': session['user']})

@app.route('/api/auth/google', methods=['POST'])
def google_auth():
    data = request.get_json(silent=True) or {}
    email = data.get('email', 'demo@gmail.com').lower().strip()
    name = data.get('name', 'Demo User').strip()
    avatar = data.get('avatar') or f"https://api.dicebear.com/7.x/initials/svg?seed={name}"

    user = get_user(email)

    if not user:
        user = {
            'id': secrets.token_hex(8),
            'name': name,
            'email': email,
            'password': '',
            'plan': 'free',
            'avatar': avatar,
            'created': datetime.now().isoformat(),
            'skills': '[]',
            'target_role': ''
        }
        conn = get_db()
        conn.execute('''
            INSERT INTO users (id, name, email, password, plan, avatar, created, skills, target_role)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user['id'], user['name'], user['email'], user['password'],
            user['plan'], user['avatar'], user['created'],
            user['skills'], user['target_role']
        ))
        conn.commit()
        conn.close()
    else:
        user['name'] = name
        user['avatar'] = avatar

    session['user'] = public_user(user)
    return jsonify({'success': True, 'user': session['user']})

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'success': True})

@app.route('/api/auth/status')
def auth_status():
    if 'user' in session:
        return jsonify({'logged_in': True, 'user': session['user']})
    return jsonify({'logged_in': False})

@app.route('/api/analyze-skills', methods=['POST'])
def analyze_skills():
    data = request.json
    skills = data.get('skills', [])
    target_role = data.get('target_role', 'Software Engineer')
    
    role_requirements = {
        'Software Engineer': {
            'required': ['Python', 'JavaScript', 'Data Structures', 'Algorithms', 'Git', 'SQL', 'REST APIs', 'Docker', 'Testing', 'OOP'],
            'salary_range': '₹6L - ₹25L',
            'avg_salary': '₹12.5L',
            'growth': '+22%',
            'demand': 'Very High'
        },
        'Data Scientist': {
            'required': ['Python', 'Machine Learning', 'Statistics', 'SQL', 'TensorFlow', 'Data Visualization', 'Pandas', 'NumPy', 'Deep Learning', 'Feature Engineering'],
            'salary_range': '₹8L - ₹35L',
            'avg_salary': '₹18L',
            'growth': '+35%',
            'demand': 'Extremely High'
        },
        'UI/UX Designer': {
            'required': ['Figma', 'Adobe XD', 'User Research', 'Wireframing', 'Prototyping', 'CSS', 'HTML', 'Design Systems', 'Accessibility', 'Typography'],
            'salary_range': '₹5L - ₹20L',
            'avg_salary': '₹10L',
            'growth': '+18%',
            'demand': 'High'
        },
        'DevOps Engineer': {
            'required': ['Docker', 'Kubernetes', 'CI/CD', 'AWS', 'Linux', 'Terraform', 'Ansible', 'Monitoring', 'Git', 'Python'],
            'salary_range': '₹8L - ₹30L',
            'avg_salary': '₹16L',
            'growth': '+28%',
            'demand': 'Very High'
        },
        'Product Manager': {
            'required': ['Product Strategy', 'Agile', 'Data Analysis', 'User Research', 'Roadmapping', 'Stakeholder Management', 'A/B Testing', 'SQL', 'Communication', 'Market Research'],
            'salary_range': '₹10L - ₹40L',
            'avg_salary': '₹22L',
            'growth': '+20%',
            'demand': 'High'
        },
        'Full Stack Developer': {
            'required': ['React', 'Node.js', 'Python', 'SQL', 'MongoDB', 'REST APIs', 'Docker', 'Git', 'TypeScript', 'CSS'],
            'salary_range': '₹7L - ₹28L',
            'avg_salary': '₹14L',
            'growth': '+25%',
            'demand': 'Very High'
        },
        'Cybersecurity Analyst': {
            'required': ['Network Security', 'Penetration Testing', 'SIEM', 'Python', 'Linux', 'Cryptography', 'Incident Response', 'Risk Assessment', 'Compliance', 'Forensics'],
            'salary_range': '₹7L - ₹30L',
            'avg_salary': '₹15L',
            'growth': '+32%',
            'demand': 'Very High'
        },
        'Machine Learning Engineer': {
            'required': ['Python', 'TensorFlow', 'PyTorch', 'MLOps', 'Statistics', 'Docker', 'Kubernetes', 'Feature Engineering', 'Model Deployment', 'Cloud Platforms'],
            'salary_range': '₹10L - ₹45L',
            'avg_salary': '₹22L',
            'growth': '+40%',
            'demand': 'Extremely High'
        }
    }
    
    req = role_requirements.get(target_role, role_requirements['Software Engineer'])
    required = req['required']
    skills_upper = [s.strip() for s in skills]
    
    matched = [r for r in required if any(r.lower() in s.lower() or s.lower() in r.lower() for s in skills_upper)]
    missing = [r for r in required if r not in matched]
    
    match_pct = round(len(matched) / len(required) * 100) if required else 0
    
    roadmap = []
    for i, skill in enumerate(missing[:6]):
        roadmap.append({
            'skill': skill,
            'duration': f"{(i%3)+1} week{'s' if (i%3)+1>1 else ''}",
            'resources': [
                {'name': f'Coursera: {skill} Fundamentals', 'url': f'https://coursera.org/search?query={skill.replace(" ","+")}', 'type': 'course'},
                {'name': f'YouTube: {skill} Tutorial', 'url': f'https://youtube.com/results?search_query={skill.replace(" ","+")}+tutorial', 'type': 'video'},
                {'name': f'Udemy: {skill} Complete Guide', 'url': f'https://udemy.com/courses/search/?q={skill.replace(" ","+")}', 'type': 'course'},
            ],
            'priority': 'High' if i < 2 else 'Medium' if i < 4 else 'Low'
        })
    
    nearby_courses = [
        {'name': f'IIT Madras Online - {target_role} Program', 'location': 'Chennai, TN', 'type': 'University', 'rating': 4.8, 'fee': '₹45,000'},
        {'name': f'NIIT Chennai - {target_role} Course', 'location': 'T. Nagar, Chennai', 'type': 'Institute', 'rating': 4.5, 'fee': '₹35,000'},
        {'name': f'Simplilearn - {target_role} Bootcamp', 'location': 'Online + Chennai', 'type': 'Bootcamp', 'rating': 4.6, 'fee': '₹55,000'},
        {'name': f'Jigsaw Academy - {target_role}', 'location': 'Chennai, TN', 'type': 'Academy', 'rating': 4.4, 'fee': '₹40,000'},
    ]
    
    return jsonify({
        'match_percentage': match_pct,
        'matched_skills': matched,
        'missing_skills': missing,
        'roadmap': roadmap,
        'salary': req,
        'nearby_courses': nearby_courses,
        'target_role': target_role
    })

@app.route('/api/analyze-resume', methods=['POST'])
def analyze_resume():
    text = request.json.get('text', '')
    
    skill_keywords = ['Python', 'JavaScript', 'React', 'Node.js', 'SQL', 'MongoDB', 'Docker', 'Git',
                      'Machine Learning', 'TensorFlow', 'CSS', 'HTML', 'Java', 'C++', 'AWS', 'Azure',
                      'Kubernetes', 'REST API', 'TypeScript', 'Vue', 'Angular', 'Flask', 'Django',
                      'PostgreSQL', 'Redis', 'GraphQL', 'Figma', 'Agile', 'Scrum', 'Linux']
    
    found_skills = [s for s in skill_keywords if s.lower() in text.lower()]
    
    ats_score = min(95, 40 + len(found_skills) * 4)
    
    issues = []
    suggestions = []
    
    if len(text) < 300:
        issues.append({'type': 'warning', 'msg': 'Resume seems too short. Add more details.'})
    if 'objective' not in text.lower() and 'summary' not in text.lower():
        suggestions.append('Add a professional summary/objective section')
    if '@' not in text:
        issues.append({'type': 'error', 'msg': 'No email address found'})
    if len(found_skills) < 5:
        suggestions.append('Add more technical skills to improve ATS score')
    
    suggestions.append('Use action verbs: "Developed", "Implemented", "Optimized"')
    suggestions.append('Quantify achievements: "Improved performance by 40%"')
    suggestions.append('Include LinkedIn profile URL')
    
    return jsonify({
        'ats_score': ats_score,
        'found_skills': found_skills,
        'issues': issues,
        'suggestions': suggestions,
        'word_count': len(text.split()),
        'skill_count': len(found_skills)
    })

@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.json
    message = data.get('message', '').lower()
    user_email = session.get('user', {}).get('email', 'guest')
    
    if user_email not in CHAT_HISTORY:
        CHAT_HISTORY[user_email] = []
    
    CHAT_HISTORY[user_email].append({'role': 'user', 'msg': message, 'time': datetime.now().strftime('%H:%M')})
    
    # Smart rule-based AI responses
    if any(w in message for w in ['salary', 'package', 'ctc', 'pay']):
        reply = "💰 **Salary Insights for India (2025):**\n\n• **Software Engineer**: ₹6L–₹25L (Avg: ₹12.5L)\n• **Data Scientist**: ₹8L–₹35L (Avg: ₹18L)\n• **ML Engineer**: ₹10L–₹45L (Avg: ₹22L)\n• **DevOps Engineer**: ₹8L–₹30L (Avg: ₹16L)\n• **Product Manager**: ₹10L–₹40L (Avg: ₹22L)\n\n🏙️ **Top paying cities**: Bangalore > Hyderabad > Pune > Chennai > Mumbai\n\nWant salary details for a specific role?"
    elif any(w in message for w in ['roadmap', 'path', 'learn', 'how to become']):
        reply = "🗺️ **Career Roadmap Builder**\n\nTo get your personalized roadmap:\n1. Go to **Skill Analyzer** tab\n2. Enter your current skills\n3. Select your target role\n4. Get a week-by-week learning plan!\n\nPopular paths right now:\n• 🤖 ML Engineer (fastest growing)\n• ☁️ Cloud/DevOps (highest demand)\n• 🎨 UI/UX Design (creative field)\n\nWhich role interests you most?"
    elif any(w in message for w in ['resume', 'cv', 'ats']):
        reply = "📄 **Resume & ATS Tips:**\n\n✅ **Must-Have Sections**: Contact, Summary, Skills, Experience, Education, Projects\n\n🎯 **ATS Optimization**:\n• Use keywords from job descriptions\n• Avoid tables/images in ATS version\n• Use standard section headings\n• Save as PDF + DOCX both\n\n⚡ **Power Words**: Developed, Engineered, Optimized, Led, Architected, Scaled\n\nUse our **ATS Resume Analyzer** for a detailed score!"
    elif any(w in message for w in ['python', 'javascript', 'react', 'coding', 'programming']):
        reply = "💻 **Learning Path for Programming:**\n\n**Beginner → Job-Ready in 6 months:**\n\n📅 **Month 1-2**: Python basics, OOP, Git\n📅 **Month 3-4**: Web Dev (HTML/CSS/JS/React)\n📅 **Month 5**: Backend (Node.js or Django)\n📅 **Month 6**: Projects + DSA + Interview Prep\n\n🔗 **Free Resources**:\n• freeCodeCamp.org\n• The Odin Project\n• CS50 (Harvard, free)\n• LeetCode for DSA\n\nWhat specific tech do you want to master?"
    elif any(w in message for w in ['interview', 'prepare', 'crack']):
        reply = "🎯 **Interview Preparation Guide:**\n\n**Technical Rounds:**\n• DSA: Arrays, Trees, DP, Graphs\n• System Design (for 3+ yrs exp)\n• Language-specific concepts\n• LeetCode: 150 most asked questions\n\n**HR Rounds:**\n• STAR method for behavioral questions\n• Research company culture\n• Prepare 5 strong projects to talk about\n\n**Top Interview Platforms:**\n• LeetCode, HackerRank, CodeSignal\n• Pramp for mock interviews\n• Glassdoor for company-specific questions\n\nWant a 30-day interview prep plan?"
    elif any(w in message for w in ['job', 'placement', 'hire', 'fresher']):
        reply = "🚀 **Job Search Strategy for Freshers:**\n\n**Best Platforms (India):**\n• LinkedIn (most important!)\n• Naukri.com\n• Internshala (internships → PPO)\n• AngelList (startups)\n• Instahyre (product companies)\n\n**Application Tips:**\n• Apply to 20-30 roles per week\n• Customize resume per JD\n• Cold connect on LinkedIn (works!)\n• Build 2-3 strong projects on GitHub\n\n**Fresher-Friendly Companies:**\nTCS, Infosys, Wipro (mass hiring)\nFlipkart, Swiggy, CRED (product companies)\nStartups via AngelList\n\nNeed help with LinkedIn optimization?"
    elif any(w in message for w in ['hi', 'hello', 'hey', 'hii']):
        reply = "👋 **Hello! I'm CareerBot, your AI career advisor!**\n\nI can help you with:\n• 🗺️ Career roadmaps & skill paths\n• 💰 Salary insights & negotiation\n• 📄 Resume & ATS optimization\n• 🎯 Interview preparation\n• 🔍 Job search strategies\n• 📍 Courses near you\n\nWhat's your career goal? Let's make it happen! 🚀"
    elif any(w in message for w in ['course', 'certification', 'certificate']):
        reply = "📚 **Top Certifications for 2025:**\n\n**Cloud & DevOps:**\n• AWS Solutions Architect (₹15K, highest ROI)\n• Google Cloud Professional (₹12K)\n• Kubernetes (CKA) (₹18K)\n\n**Data & AI:**\n• Google Data Analytics (Free on Coursera)\n• TensorFlow Developer Certificate (₹15K)\n• IBM Data Science Professional (₹8K)\n\n**Development:**\n• Meta React Developer (Free on Coursera)\n• MongoDB Developer (Free)\n\n🎯 **Best value**: Google Career Certificates on Coursera (₹3K/month, job guaranteed!)\n\nWant course recommendations for a specific role?"
    else:
        reply = f"🤔 Great question about **\"{data.get('message', '')}\"**!\n\nAs your AI Career Advisor, I can help with:\n\n• 🎯 **Skill Analysis** — What skills to learn next\n• 🗺️ **Career Roadmaps** — Step-by-step learning paths  \n• 💰 **Salary Benchmarks** — Know your market value\n• 📄 **Resume Tips** — ATS-optimized resumes\n• 🔍 **Job Search** — Where and how to apply\n• 🎓 **Course Recommendations** — Best learning resources\n\nTry asking: *\"What skills do I need for Data Science?\"* or *\"How much does a React developer earn?\"*"
    
    CHAT_HISTORY[user_email].append({'role': 'bot', 'msg': reply, 'time': datetime.now().strftime('%H:%M')})
    
    return jsonify({'reply': reply, 'time': datetime.now().strftime('%H:%M')})

@app.route('/api/chat/history')
def chat_history():
    user_email = session.get('user', {}).get('email', 'guest')
    return jsonify({'history': CHAT_HISTORY.get(user_email, [])})

@app.route('/api/subscribe', methods=['POST'])
def subscribe():
    data = request.get_json(silent=True) or {}
    plan = data.get('plan')
    user = session.get('user')

    if not user or not plan:
        return jsonify({'error': 'Login required'}), 401

    conn = get_db()
    conn.execute('UPDATE users SET plan = ? WHERE email = ?', (plan, user['email']))
    conn.commit()
    updated = conn.execute('SELECT * FROM users WHERE email = ?', (user['email'],)).fetchone()
    conn.close()

    if updated:
        session['user'] = public_user(dict(updated))

    return jsonify({
        'success': True,
        'plan': plan,
        'message': f'Successfully upgraded to {plan} plan!'
    })

@app.route('/api/jobs')
def get_jobs():
    role = request.args.get('role', 'Software Engineer')
    jobs = [
        {'title': f'Senior {role}', 'company': 'TCS', 'location': 'Chennai', 'salary': '₹12-18L', 'type': 'Full-time', 'posted': '2 days ago', 'match': 92},
        {'title': role, 'company': 'Infosys', 'location': 'Hyderabad', 'salary': '₹8-15L', 'type': 'Full-time', 'posted': '1 day ago', 'match': 87},
        {'title': f'Junior {role}', 'company': 'Wipro', 'location': 'Bangalore', 'salary': '₹5-9L', 'type': 'Full-time', 'posted': '3 days ago', 'match': 95},
        {'title': f'{role} Intern', 'company': 'Zoho', 'location': 'Chennai', 'salary': '₹25-40K/mo', 'type': 'Internship', 'posted': 'Today', 'match': 88},
        {'title': f'Lead {role}', 'company': 'Freshworks', 'location': 'Chennai', 'salary': '₹20-35L', 'type': 'Full-time', 'posted': '5 days ago', 'match': 79},
        {'title': f'Contract {role}', 'company': 'Cognizant', 'location': 'Remote', 'salary': '₹10-16L', 'type': 'Contract', 'posted': 'Today', 'match': 83},
    ]
    return jsonify({'jobs': jobs})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)