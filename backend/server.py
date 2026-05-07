"""TaskFlow - Full-stack: Flask REST API + SQLite + serves frontend"""
import sqlite3, hashlib, os, json
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import Flask, request, jsonify, g, send_from_directory, Response
import jwt

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'frontend')
if not os.path.exists(FRONTEND_DIR):
    FRONTEND_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path='')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'taskflow-dev-secret-2024')
DATABASE = os.environ.get('DATABASE_PATH', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'taskflow.db'))

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None: db.close()

def init_db():
    with app.app_context():
        db = get_db()
        db.executescript("""
            CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'member' CHECK(role IN ('admin','member')), created_at TEXT NOT NULL DEFAULT (datetime('now')));
            CREATE TABLE IF NOT EXISTS projects (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, description TEXT, owner_id INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','archived','completed')), created_at TEXT NOT NULL DEFAULT (datetime('now')), due_date TEXT, FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE);
            CREATE TABLE IF NOT EXISTS project_members (id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL, user_id INTEGER NOT NULL, role TEXT NOT NULL DEFAULT 'member' CHECK(role IN ('admin','member')), joined_at TEXT NOT NULL DEFAULT (datetime('now')), FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE, FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE, UNIQUE(project_id, user_id));
            CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, description TEXT, project_id INTEGER NOT NULL, assignee_id INTEGER, creator_id INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'todo' CHECK(status IN ('todo','in_progress','review','done')), priority TEXT NOT NULL DEFAULT 'medium' CHECK(priority IN ('low','medium','high','urgent')), due_date TEXT, created_at TEXT NOT NULL DEFAULT (datetime('now')), updated_at TEXT NOT NULL DEFAULT (datetime('now')), FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE, FOREIGN KEY (assignee_id) REFERENCES users(id) ON DELETE SET NULL, FOREIGN KEY (creator_id) REFERENCES users(id) ON DELETE CASCADE);
            CREATE TABLE IF NOT EXISTS task_comments (id INTEGER PRIMARY KEY AUTOINCREMENT, task_id INTEGER NOT NULL, user_id INTEGER NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT (datetime('now')), FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE, FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE);
        """)
        db.commit()

def hash_password(password):
    salt = os.urandom(32)
    key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    return salt.hex() + ':' + key.hex()

def verify_password(stored, provided):
    try:
        salt_hex, key_hex = stored.split(':')
        salt = bytes.fromhex(salt_hex); key = bytes.fromhex(key_hex)
        new_key = hashlib.pbkdf2_hmac('sha256', provided.encode('utf-8'), salt, 100000)
        result = 0
        for x, y in zip(key, new_key): result |= x ^ y
        return result == 0 and len(key) == len(new_key)
    except: return False

def generate_token(user_id, role):
    payload = {'user_id': user_id, 'role': role, 'exp': datetime.now(timezone.utc) + timedelta(days=7), 'iat': datetime.now(timezone.utc)}
    return jwt.encode(payload, app.config['SECRET_KEY'], algorithm='HS256')

def row_to_dict(row): return dict(row) if row else None
def rows_to_list(rows): return [dict(r) for r in rows]
AVATAR_COLORS = ['#6366f1','#ec4899','#f59e0b','#10b981','#3b82f6','#8b5cf6','#ef4444','#14b8a6']
def get_avatar_color(uid): return AVATAR_COLORS[uid % len(AVATAR_COLORS)]

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '): return jsonify({'error': 'Missing or invalid token'}), 401
        token = auth_header[7:]
        try:
            payload = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            user = get_db().execute('SELECT * FROM users WHERE id = ?', (payload['user_id'],)).fetchone()
            if not user: return jsonify({'error': 'User not found'}), 401
            g.current_user = row_to_dict(user)
        except jwt.ExpiredSignatureError: return jsonify({'error': 'Token expired'}), 401
        except jwt.InvalidTokenError: return jsonify({'error': 'Invalid token'}), 401
        return f(*args, **kwargs)
    return decorated

def require_project_access(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        project_id = kwargs.get('project_id')
        if not project_id: return f(*args, **kwargs)
        db = get_db(); user_id = g.current_user['id']
        if g.current_user['role'] == 'admin':
            project = db.execute('SELECT * FROM projects WHERE id = ?', (project_id,)).fetchone()
        else:
            project = db.execute('SELECT p.* FROM projects p JOIN project_members pm ON p.id = pm.project_id WHERE p.id = ? AND pm.user_id = ?', (project_id, user_id)).fetchone()
        if not project: return jsonify({'error': 'Project not found or access denied'}), 404
        g.project = row_to_dict(project)
        return f(*args, **kwargs)
    return decorated

@app.after_request
def add_cors(response):
    response.headers.update({'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'Content-Type, Authorization','Access-Control-Allow-Methods':'GET, POST, PUT, PATCH, DELETE, OPTIONS'})
    return response

@app.before_request
def handle_preflight():
    if request.method == 'OPTIONS': return Response(status=200)

@app.route("/")
def serve_index(): return send_from_directory(FRONTEND_DIR, 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    if path.startswith('api/'): return jsonify({'error': 'Not found'}), 404
    try: return send_from_directory(FRONTEND_DIR, path)
    except: return send_from_directory(FRONTEND_DIR, 'index.html')

@app.route('/api/auth/signup', methods=['POST'])
def signup():
    data = request.get_json() or {}
    name = (data.get('name') or '').strip(); email = (data.get('email') or '').strip().lower(); password = data.get('password') or ''; role = data.get('role', 'member')
    if not name or not email or not password: return jsonify({'error': 'Name, email and password are required'}), 400
    if len(password) < 6: return jsonify({'error': 'Password must be at least 6 characters'}), 400
    if '@' not in email: return jsonify({'error': 'Invalid email'}), 400
    if role not in ('admin','member'): role = 'member'
    db = get_db()
    if db.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone(): return jsonify({'error': 'Email already registered'}), 409
    cursor = db.execute('INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)', (name, email, hash_password(password), role))
    db.commit(); uid = cursor.lastrowid; token = generate_token(uid, role)
    return jsonify({'token': token, 'user': {'id': uid, 'name': name, 'email': email, 'role': role, 'avatar_color': get_avatar_color(uid)}}), 201

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json() or {}; email = (data.get('email') or '').strip().lower(); password = data.get('password') or ''
    if not email or not password: return jsonify({'error': 'Email and password are required'}), 400
    db = get_db(); user = db.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
    if not user or not verify_password(user['password_hash'], password): return jsonify({'error': 'Invalid email or password'}), 401
    token = generate_token(user['id'], user['role'])
    return jsonify({'token': token, 'user': {'id': user['id'], 'name': user['name'], 'email': user['email'], 'role': user['role'], 'avatar_color': get_avatar_color(user['id'])}})

@app.route('/api/auth/me', methods=['GET'])
@require_auth
def get_me():
    u = g.current_user
    return jsonify({'id': u['id'], 'name': u['name'], 'email': u['email'], 'role': u['role'], 'avatar_color': get_avatar_color(u['id']), 'created_at': u['created_at']})

@app.route('/api/users', methods=['GET'])
@require_auth
def list_users():
    users = get_db().execute('SELECT id, name, email, role, created_at FROM users ORDER BY name').fetchall()
    return jsonify([{**dict(u), 'avatar_color': get_avatar_color(u['id'])} for u in users])

@app.route('/api/users/<int:user_id>', methods=['GET'])
@require_auth
def get_user(user_id):
    user = get_db().execute('SELECT id, name, email, role, created_at FROM users WHERE id = ?', (user_id,)).fetchone()
    if not user: return jsonify({'error': 'User not found'}), 404
    return jsonify({**dict(user), 'avatar_color': get_avatar_color(user['id'])})

@app.route('/api/users/<int:user_id>', methods=['PUT'])
@require_auth
def update_user(user_id):
    if g.current_user['id'] != user_id and g.current_user['role'] != 'admin': return jsonify({'error': 'Forbidden'}), 403
    data = request.get_json() or {}; db = get_db(); updates = []; params = []
    if 'name' in data and data['name'].strip(): updates.append('name = ?'); params.append(data['name'].strip())
    if 'role' in data and g.current_user['role'] == 'admin' and data['role'] in ('admin','member'): updates.append('role = ?'); params.append(data['role'])
    if not updates: return jsonify({'error': 'Nothing to update'}), 400
    params.append(user_id)
    db.execute(f'UPDATE users SET {", ".join(updates)} WHERE id = ?', params); db.commit()
    user = db.execute('SELECT id, name, email, role, created_at FROM users WHERE id = ?', (user_id,)).fetchone()
    return jsonify({**dict(user), 'avatar_color': get_avatar_color(user['id'])})

@app.route('/api/projects', methods=['GET'])
@require_auth
def list_projects():
    db = get_db(); uid = g.current_user['id']
    if g.current_user['role'] == 'admin':
        projects = db.execute("SELECT p.*, u.name as owner_name, COUNT(DISTINCT pm.user_id) as member_count, COUNT(DISTINCT t.id) as task_count, COUNT(DISTINCT CASE WHEN t.status='done' THEN t.id END) as done_count FROM projects p JOIN users u ON p.owner_id=u.id LEFT JOIN project_members pm ON p.id=pm.project_id LEFT JOIN tasks t ON p.id=t.project_id GROUP BY p.id ORDER BY p.created_at DESC").fetchall()
    else:
        projects = db.execute("SELECT p.*, u.name as owner_name, COUNT(DISTINCT pm2.user_id) as member_count, COUNT(DISTINCT t.id) as task_count, COUNT(DISTINCT CASE WHEN t.status='done' THEN t.id END) as done_count FROM projects p JOIN users u ON p.owner_id=u.id JOIN project_members pm ON p.id=pm.project_id AND pm.user_id=? LEFT JOIN project_members pm2 ON p.id=pm2.project_id LEFT JOIN tasks t ON p.id=t.project_id GROUP BY p.id ORDER BY p.created_at DESC", (uid,)).fetchall()
    return jsonify(rows_to_list(projects))

@app.route('/api/projects', methods=['POST'])
@require_auth
def create_project():
    data = request.get_json() or {}; name = (data.get('name') or '').strip()
    if not name: return jsonify({'error': 'Project name is required'}), 400
    db = get_db(); owner_id = g.current_user['id']
    cursor = db.execute('INSERT INTO projects (name, description, owner_id, due_date) VALUES (?, ?, ?, ?)', (name, data.get('description',''), owner_id, data.get('due_date')))
    pid = cursor.lastrowid; db.execute('INSERT INTO project_members (project_id, user_id, role) VALUES (?, ?, ?)', (pid, owner_id, 'admin')); db.commit()
    return jsonify(row_to_dict(db.execute('SELECT * FROM projects WHERE id = ?', (pid,)).fetchone())), 201

@app.route('/api/projects/<int:project_id>', methods=['GET'])
@require_auth
@require_project_access
def get_project(project_id):
    project = get_db().execute("SELECT p.*, u.name as owner_name, COUNT(DISTINCT pm.user_id) as member_count, COUNT(DISTINCT t.id) as task_count FROM projects p JOIN users u ON p.owner_id=u.id LEFT JOIN project_members pm ON p.id=pm.project_id LEFT JOIN tasks t ON p.id=t.project_id WHERE p.id=? GROUP BY p.id", (project_id,)).fetchone()
    return jsonify(row_to_dict(project))

@app.route('/api/projects/<int:project_id>', methods=['PUT'])
@require_auth
@require_project_access
def update_project(project_id):
    db = get_db(); uid = g.current_user['id']
    if g.current_user['role'] != 'admin':
        m = db.execute('SELECT role FROM project_members WHERE project_id=? AND user_id=?', (project_id, uid)).fetchone()
        if not m or m['role'] != 'admin': return jsonify({'error': 'Only project admins can update'}), 403
    data = request.get_json() or {}; updates = []; params = []
    for f in ['name','description','status','due_date']:
        if f in data: updates.append(f'{f} = ?'); params.append(data[f])
    if not updates: return jsonify({'error': 'Nothing to update'}), 400
    params.append(project_id); db.execute(f'UPDATE projects SET {", ".join(updates)} WHERE id = ?', params); db.commit()
    return jsonify(row_to_dict(db.execute('SELECT * FROM projects WHERE id = ?', (project_id,)).fetchone()))

@app.route('/api/projects/<int:project_id>', methods=['DELETE'])
@require_auth
@require_project_access
def delete_project(project_id):
    db = get_db(); uid = g.current_user['id']
    if g.current_user['role'] != 'admin' and g.project['owner_id'] != uid: return jsonify({'error': 'Only owner or admin can delete'}), 403
    db.execute('DELETE FROM projects WHERE id = ?', (project_id,)); db.commit()
    return jsonify({'message': 'Project deleted'})

@app.route('/api/projects/<int:project_id>/members', methods=['GET'])
@require_auth
@require_project_access
def list_project_members(project_id):
    members = get_db().execute("SELECT u.id, u.name, u.email, u.role as global_role, pm.role as project_role, pm.joined_at FROM project_members pm JOIN users u ON pm.user_id=u.id WHERE pm.project_id=? ORDER BY u.name", (project_id,)).fetchall()
    return jsonify([{**dict(m), 'avatar_color': get_avatar_color(m['id'])} for m in members])

@app.route('/api/projects/<int:project_id>/members', methods=['POST'])
@require_auth
@require_project_access
def add_project_member(project_id):
    db = get_db(); uid = g.current_user['id']
    if g.current_user['role'] != 'admin':
        m = db.execute('SELECT role FROM project_members WHERE project_id=? AND user_id=?', (project_id, uid)).fetchone()
        if not m or m['role'] != 'admin': return jsonify({'error': 'Only project admins can add members'}), 403
    data = request.get_json() or {}; target_uid = data.get('user_id'); role = data.get('role', 'member')
    if not target_uid: return jsonify({'error': 'user_id is required'}), 400
    if not db.execute('SELECT id FROM users WHERE id=?', (target_uid,)).fetchone(): return jsonify({'error': 'User not found'}), 404
    try:
        db.execute('INSERT INTO project_members (project_id, user_id, role) VALUES (?, ?, ?)', (project_id, target_uid, role)); db.commit()
        return jsonify({'message': 'Member added'}), 201
    except sqlite3.IntegrityError: return jsonify({'error': 'User already a member'}), 409

@app.route('/api/projects/<int:project_id>/members/<int:member_user_id>', methods=['DELETE'])
@require_auth
@require_project_access
def remove_project_member(project_id, member_user_id):
    db = get_db(); uid = g.current_user['id']
    if g.current_user['role'] != 'admin' and uid != member_user_id:
        m = db.execute('SELECT role FROM project_members WHERE project_id=? AND user_id=?', (project_id, uid)).fetchone()
        if not m or m['role'] != 'admin': return jsonify({'error': 'Forbidden'}), 403
    db.execute('DELETE FROM project_members WHERE project_id=? AND user_id=?', (project_id, member_user_id)); db.commit()
    return jsonify({'message': 'Member removed'})

@app.route('/api/projects/<int:project_id>/tasks', methods=['GET'])
@require_auth
@require_project_access
def list_project_tasks(project_id):
    db = get_db(); now = datetime.now().isoformat()
    query = "SELECT t.*, u1.name as assignee_name, u1.email as assignee_email, u2.name as creator_name FROM tasks t LEFT JOIN users u1 ON t.assignee_id=u1.id JOIN users u2 ON t.creator_id=u2.id WHERE t.project_id=?"
    params = [project_id]
    for f, key in [('status','status'),('priority','priority'),('assignee_id','assignee_id')]:
        v = request.args.get(f); 
        if v: query += f' AND t.{key}=?'; params.append(v)
    query += ' ORDER BY t.created_at DESC'
    tasks = db.execute(query, params).fetchall()
    result = []
    for t in tasks:
        d = dict(t)
        if d.get('assignee_id'): d['assignee_avatar_color'] = get_avatar_color(d['assignee_id'])
        d['is_overdue'] = bool(d['due_date'] and d['due_date'] < now and d['status'] != 'done')
        result.append(d)
    return jsonify(result)

@app.route('/api/projects/<int:project_id>/tasks', methods=['POST'])
@require_auth
@require_project_access
def create_task(project_id):
    data = request.get_json() or {}; title = (data.get('title') or '').strip()
    if not title: return jsonify({'error': 'Task title is required'}), 400
    db = get_db()
    cursor = db.execute('INSERT INTO tasks (title, description, project_id, assignee_id, creator_id, status, priority, due_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
        (title, data.get('description',''), project_id, data.get('assignee_id'), g.current_user['id'], data.get('status','todo'), data.get('priority','medium'), data.get('due_date')))
    db.commit(); tid = cursor.lastrowid
    task = db.execute("SELECT t.*, u1.name as assignee_name, u2.name as creator_name FROM tasks t LEFT JOIN users u1 ON t.assignee_id=u1.id JOIN users u2 ON t.creator_id=u2.id WHERE t.id=?", (tid,)).fetchone()
    return jsonify(row_to_dict(task)), 201

@app.route('/api/projects/<int:project_id>/tasks/<int:task_id>', methods=['GET'])
@require_auth
@require_project_access
def get_task(project_id, task_id):
    db = get_db()
    task = db.execute("SELECT t.*, u1.name as assignee_name, u1.email as assignee_email, u2.name as creator_name FROM tasks t LEFT JOIN users u1 ON t.assignee_id=u1.id JOIN users u2 ON t.creator_id=u2.id WHERE t.id=? AND t.project_id=?", (task_id, project_id)).fetchone()
    if not task: return jsonify({'error': 'Task not found'}), 404
    d = dict(task); now = datetime.now().isoformat()
    d['is_overdue'] = bool(d['due_date'] and d['due_date'] < now and d['status'] != 'done')
    if d.get('assignee_id'): d['assignee_avatar_color'] = get_avatar_color(d['assignee_id'])
    comments = db.execute("SELECT tc.*, u.name as user_name FROM task_comments tc JOIN users u ON tc.user_id=u.id WHERE tc.task_id=? ORDER BY tc.created_at ASC", (task_id,)).fetchall()
    d['comments'] = rows_to_list(comments)
    return jsonify(d)

@app.route('/api/projects/<int:project_id>/tasks/<int:task_id>', methods=['PUT'])
@require_auth
@require_project_access
def update_task(project_id, task_id):
    db = get_db()
    if not db.execute('SELECT id FROM tasks WHERE id=? AND project_id=?', (task_id, project_id)).fetchone(): return jsonify({'error': 'Task not found'}), 404
    data = request.get_json() or {}; updates = []; params = []
    for f in ['title','description','assignee_id','status','priority','due_date']:
        if f in data: updates.append(f'{f} = ?'); params.append(data[f])
    updates.append("updated_at = datetime('now')")
    params.extend([task_id, project_id]); db.execute(f'UPDATE tasks SET {", ".join(updates)} WHERE id=? AND project_id=?', params); db.commit()
    updated = db.execute("SELECT t.*, u1.name as assignee_name, u2.name as creator_name FROM tasks t LEFT JOIN users u1 ON t.assignee_id=u1.id JOIN users u2 ON t.creator_id=u2.id WHERE t.id=?", (task_id,)).fetchone()
    return jsonify(row_to_dict(updated))

@app.route('/api/projects/<int:project_id>/tasks/<int:task_id>', methods=['DELETE'])
@require_auth
@require_project_access
def delete_task(project_id, task_id):
    db = get_db()
    task = db.execute('SELECT * FROM tasks WHERE id=? AND project_id=?', (task_id, project_id)).fetchone()
    if not task: return jsonify({'error': 'Task not found'}), 404
    uid = g.current_user['id']
    if g.current_user['role'] != 'admin' and task['creator_id'] != uid:
        m = db.execute('SELECT role FROM project_members WHERE project_id=? AND user_id=?', (project_id, uid)).fetchone()
        if not m or m['role'] != 'admin': return jsonify({'error': 'Forbidden'}), 403
    db.execute('DELETE FROM tasks WHERE id=?', (task_id,)); db.commit()
    return jsonify({'message': 'Task deleted'})

@app.route('/api/projects/<int:project_id>/tasks/<int:task_id>/comments', methods=['POST'])
@require_auth
@require_project_access
def add_comment(project_id, task_id):
    db = get_db()
    if not db.execute('SELECT id FROM tasks WHERE id=? AND project_id=?', (task_id, project_id)).fetchone(): return jsonify({'error': 'Task not found'}), 404
    data = request.get_json() or {}; content = (data.get('content') or '').strip()
    if not content: return jsonify({'error': 'Comment content required'}), 400
    cursor = db.execute('INSERT INTO task_comments (task_id, user_id, content) VALUES (?, ?, ?)', (task_id, g.current_user['id'], content)); db.commit()
    comment = db.execute("SELECT tc.*, u.name as user_name FROM task_comments tc JOIN users u ON tc.user_id=u.id WHERE tc.id=?", (cursor.lastrowid,)).fetchone()
    return jsonify(row_to_dict(comment)), 201

@app.route('/api/dashboard', methods=['GET'])
@require_auth
def dashboard():
    db = get_db(); uid = g.current_user['id']; is_admin = g.current_user['role'] == 'admin'; now = datetime.now().isoformat()
    if is_admin:
        total_projects = db.execute('SELECT COUNT(*) as c FROM projects').fetchone()['c']
        total_tasks = db.execute('SELECT COUNT(*) as c FROM tasks').fetchone()['c']
        total_users = db.execute('SELECT COUNT(*) as c FROM users').fetchone()['c']
        my_tasks = db.execute('SELECT COUNT(*) as c FROM tasks WHERE assignee_id=?', (uid,)).fetchone()['c']
        overdue = db.execute("SELECT COUNT(*) as c FROM tasks WHERE due_date<? AND status!='done'", (now,)).fetchone()['c']
        status_counts = db.execute('SELECT status, COUNT(*) as count FROM tasks GROUP BY status').fetchall()
        priority_counts = db.execute('SELECT priority, COUNT(*) as count FROM tasks GROUP BY priority').fetchall()
        recent = db.execute("SELECT t.*, p.name as project_name, u.name as assignee_name, CASE WHEN t.due_date<? AND t.status!='done' THEN 1 ELSE 0 END as is_overdue FROM tasks t JOIN projects p ON t.project_id=p.id LEFT JOIN users u ON t.assignee_id=u.id ORDER BY t.updated_at DESC LIMIT 10", (now,)).fetchall()
    else:
        total_projects = db.execute('SELECT COUNT(*) as c FROM project_members WHERE user_id=?', (uid,)).fetchone()['c']
        total_tasks = db.execute('SELECT COUNT(*) as c FROM tasks t JOIN project_members pm ON t.project_id=pm.project_id WHERE pm.user_id=?', (uid,)).fetchone()['c']
        total_users = db.execute('SELECT COUNT(*) as c FROM users').fetchone()['c']
        my_tasks = db.execute('SELECT COUNT(*) as c FROM tasks WHERE assignee_id=?', (uid,)).fetchone()['c']
        overdue = db.execute("SELECT COUNT(*) as c FROM tasks WHERE assignee_id=? AND due_date<? AND status!='done'", (uid, now)).fetchone()['c']
        status_counts = db.execute("SELECT t.status, COUNT(*) as count FROM tasks t JOIN project_members pm ON t.project_id=pm.project_id WHERE pm.user_id=? GROUP BY t.status", (uid,)).fetchall()
        priority_counts = db.execute('SELECT priority, COUNT(*) as count FROM tasks WHERE assignee_id=? GROUP BY priority', (uid,)).fetchall()
        recent = db.execute("SELECT t.*, p.name as project_name, u.name as assignee_name, CASE WHEN t.due_date<? AND t.status!='done' THEN 1 ELSE 0 END as is_overdue FROM tasks t JOIN projects p ON t.project_id=p.id JOIN project_members pm ON t.project_id=pm.project_id LEFT JOIN users u ON t.assignee_id=u.id WHERE pm.user_id=? ORDER BY t.updated_at DESC LIMIT 10", (now, uid)).fetchall()
    return jsonify({'stats': {'total_projects': total_projects, 'total_tasks': total_tasks, 'total_users': total_users, 'my_tasks': my_tasks, 'overdue_tasks': overdue}, 'task_by_status': {r['status']: r['count'] for r in status_counts}, 'task_by_priority': {r['priority']: r['count'] for r in priority_counts}, 'recent_tasks': rows_to_list(recent)})

@app.route('/api/tasks/my', methods=['GET'])
@require_auth
def my_tasks():
    db = get_db(); uid = g.current_user['id']; now = datetime.now().isoformat()
    tasks = db.execute("SELECT t.*, p.name as project_name, u.name as assignee_name, CASE WHEN t.due_date<? AND t.status!='done' THEN 1 ELSE 0 END as is_overdue FROM tasks t JOIN projects p ON t.project_id=p.id LEFT JOIN users u ON t.assignee_id=u.id WHERE t.assignee_id=? ORDER BY t.due_date ASC, t.priority DESC", (now, uid)).fetchall()
    return jsonify(rows_to_list(tasks))

@app.route('/api/seed', methods=['POST'])
def seed():
    db = get_db()
    if db.execute('SELECT COUNT(*) as c FROM users').fetchone()['c'] > 0: return jsonify({'message': 'Already seeded'}), 200
    apw = hash_password('admin123'); mpw = hash_password('member123')
    db.execute("INSERT INTO users (name,email,password_hash,role) VALUES ('Alice Admin','admin@demo.com',?,'admin')", (apw,))
    db.execute("INSERT INTO users (name,email,password_hash,role) VALUES ('Bob Builder','bob@demo.com',?,'member')", (mpw,))
    db.execute("INSERT INTO users (name,email,password_hash,role) VALUES ('Carol Coder','carol@demo.com',?,'member')", (mpw,))
    db.execute("INSERT INTO users (name,email,password_hash,role) VALUES ('Dave Designer','dave@demo.com',?,'member')", (mpw,))
    db.commit()
    db.execute("INSERT INTO projects (name,description,owner_id,status,due_date) VALUES ('Website Redesign','Complete overhaul of company website with modern UI',1,'active','2026-06-30')")
    db.execute("INSERT INTO projects (name,description,owner_id,status,due_date) VALUES ('Mobile App v2','New features and improvements for mobile application',1,'active','2026-07-15')")
    db.execute("INSERT INTO projects (name,description,owner_id,status,due_date) VALUES ('API Integration','Third-party API integrations and webhooks',1,'active','2026-05-31')")
    db.commit()
    for uid in [1,2,3,4]: db.execute("INSERT OR IGNORE INTO project_members (project_id,user_id,role) VALUES (1,?,?)", (uid,'admin' if uid==1 else 'member'))
    for uid in [1,2,4]: db.execute("INSERT OR IGNORE INTO project_members (project_id,user_id,role) VALUES (2,?,?)", (uid,'admin' if uid==1 else 'member'))
    for uid in [1,3]: db.execute("INSERT OR IGNORE INTO project_members (project_id,user_id,role) VALUES (3,?,?)", (uid,'admin' if uid==1 else 'member'))
    db.commit()
    for t in [
        ('Design new homepage mockups','Create high-fidelity mockups for the new homepage',1,4,1,'in_progress','high','2026-05-20'),
        ('Implement responsive navigation','Build mobile-first navigation component',1,2,1,'todo','medium','2026-05-25'),
        ('Write component unit tests','Achieve 80% test coverage for all components',1,3,1,'todo','medium','2026-06-01'),
        ('SEO metadata optimization','Add proper meta tags and structured data',1,2,1,'done','low','2026-05-10'),
        ('Fix authentication session bug','Users getting logged out after 10 minutes',1,3,1,'in_progress','urgent','2026-05-08'),
        ('Design v2 app icons','New icon set following brand guidelines',2,4,1,'done','medium','2026-05-15'),
        ('Push notification system','Implement FCM push notifications',2,2,1,'in_progress','high','2026-06-10'),
        ('Performance profiling audit','Identify and fix rendering bottlenecks',2,2,1,'todo','high','2026-06-20'),
        ('Stripe payment integration','Complete payment processing with Stripe v3',3,3,1,'in_progress','urgent','2026-05-15'),
        ('Sendgrid transactional emails','Email notifications for key user actions',3,3,1,'todo','medium','2026-06-05'),
    ]:
        db.execute('INSERT INTO tasks (title,description,project_id,assignee_id,creator_id,status,priority,due_date) VALUES (?,?,?,?,?,?,?,?)', t)
    db.commit()
    return jsonify({'message':'Demo data seeded!','credentials':{'admin':{'email':'admin@demo.com','password':'admin123'},'member':{'email':'bob@demo.com','password':'member123'}}}), 201

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now().isoformat(),
        'app': 'TaskFlow'
    })

with app.app_context():
    init_db()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"🚀 TaskFlow running on http://0.0.0.0:{port}")
    app.run(host='0.0.0.0', port=port, debug=os.environ.get('DEBUG','false').lower()=='true')