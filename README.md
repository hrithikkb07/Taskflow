# ⚡ TaskFlow — Team Task Manager

A full-stack team task management application with role-based access control, built with Flask + SQLite + vanilla JS.

![TaskFlow](https://img.shields.io/badge/TaskFlow-v1.0-6366f1?style=flat-square)
![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python)
![Flask](https://img.shields.io/badge/Flask-3.1-000000?style=flat-square&logo=flask)
![SQLite](https://img.shields.io/badge/SQLite-3-003B57?style=flat-square&logo=sqlite)

---

## 🌐 Live Demo

**Live URL:** `https://your-app.railway.app`

**Demo Credentials:**
| Role | Email | Password |
|------|-------|----------|
| Admin | admin@demo.com | admin123 |
| Member | bob@demo.com | member123 |
| Member | carol@demo.com | member123 |

---

## 🚀 Features

### Authentication
- JWT-based signup/login/logout
- 7-day token expiry
- Secure password hashing (PBKDF2-SHA256 with salt)
- Auto-seeded demo data on first boot

### Role-Based Access Control (RBAC)
| Feature | Admin | Member |
|---------|-------|--------|
| View all projects | ✅ | ❌ (own projects only) |
| Create projects | ✅ | ✅ |
| Delete any project | ✅ | ❌ (owner only) |
| Manage all users | ✅ | ❌ |
| Promote/demote users | ✅ | ❌ |
| Add project members | ✅ | Project admin only |
| Create/edit tasks | ✅ | ✅ |
| Delete tasks | ✅ | Creator/project admin |

### Project Management
- Create, update, archive, delete projects
- Project status: Active / Completed / Archived
- Due dates with overdue detection
- Progress tracking (% tasks done)
- Member management with per-project roles

### Task Management
- **Kanban Board** (4 columns: To Do, In Progress, Review, Done)
- **List View** toggle
- Task fields: title, description, status, priority, assignee, due date
- Priority levels: Low, Medium, High, Urgent
- Overdue task detection and highlighting
- Task comments/activity
- Real-time status updates via dropdown (no page reload)
- Filters by status, priority, assignee, search

### Dashboard
- Stats: total projects, tasks, my tasks, overdue count
- Task distribution by status (visual bar chart)
- Priority breakdown visualization
- Recent activity table
- Admin sees global stats; Members see their scope

---

## 🏗️ Architecture

```
taskflow/
├── backend/
│   └── server.py          # Flask REST API (all routes)
├── frontend/
│   └── index.html         # Single-page app (HTML + CSS + JS)
├── requirements.txt        # Python dependencies
├── Procfile                # Railway/Heroku start command
├── railway.json            # Railway deployment config
├── nixpacks.toml           # Build config
└── README.md
```

### Tech Stack
- **Backend:** Python 3.10+, Flask 3.1, SQLite 3
- **Auth:** PyJWT (HS256), PBKDF2-SHA256 password hashing
- **Frontend:** Vanilla JS (no framework), CSS custom properties
- **Database:** SQLite with foreign keys, proper relationships
- **Deployment:** Railway (Nixpacks), Gunicorn WSGI

### Database Schema

```sql
users           -- id, name, email, password_hash, role, created_at
projects        -- id, name, description, owner_id, status, due_date, created_at
project_members -- project_id, user_id, role (admin/member), joined_at
tasks           -- id, title, description, project_id, assignee_id, creator_id,
                --    status, priority, due_date, created_at, updated_at
task_comments   -- id, task_id, user_id, content, created_at
```

---

## 🔌 REST API Reference

### Auth
```
POST /api/auth/signup     Create account
POST /api/auth/login      Login → JWT token
GET  /api/auth/me         Current user info
```

### Users
```
GET  /api/users           List all users
GET  /api/users/:id       Get user
PUT  /api/users/:id       Update user (admin: role change)
```

### Projects
```
GET    /api/projects                    List accessible projects
POST   /api/projects                    Create project
GET    /api/projects/:id                Get project details
PUT    /api/projects/:id                Update project
DELETE /api/projects/:id                Delete project
GET    /api/projects/:id/members        List members
POST   /api/projects/:id/members        Add member
DELETE /api/projects/:id/members/:uid   Remove member
```

### Tasks
```
GET    /api/projects/:id/tasks          List tasks (filterable)
POST   /api/projects/:id/tasks          Create task
GET    /api/projects/:id/tasks/:tid     Get task + comments
PUT    /api/projects/:id/tasks/:tid     Update task
DELETE /api/projects/:id/tasks/:tid     Delete task
POST   /api/projects/:id/tasks/:tid/comments  Add comment
```

### Other
```
GET  /api/dashboard    Dashboard stats
GET  /api/tasks/my     My assigned tasks
GET  /api/health       Health check
POST /api/seed         Seed demo data (first boot only)
```

**Authentication:** All protected routes require `Authorization: Bearer <token>` header.

---

## 🖥️ Local Development

### Prerequisites
- Python 3.10+
- pip

### Setup
```bash
# Clone the repository
git clone https://github.com/your-username/taskflow.git
cd taskflow

# Install dependencies
pip install -r requirements.txt

# Run the server
python backend/server.py
```

App runs at `http://localhost:5000`

The database is auto-created and demo data seeded on first boot.

### Environment Variables
| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | 5000 | Server port |
| `SECRET_KEY` | dev secret | JWT signing key |
| `DATABASE_PATH` | backend/taskflow.db | SQLite database path |
| `DEBUG` | false | Flask debug mode |

---

## 🚂 Deploy to Railway

1. **Fork/clone this repo** and push to GitHub

2. **Create a new Railway project:**
   - Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub
   - Select your repository

3. **Set environment variables** in Railway dashboard:
   ```
   SECRET_KEY=your-super-secret-production-key-here
   DATABASE_PATH=/data/taskflow.db
   ```

4. **(Optional) Add a volume** for persistent SQLite storage:
   - Railway Dashboard → Your Service → Volumes → Add Volume
   - Mount path: `/data`

5. **Deploy** — Railway auto-detects Python and uses `nixpacks.toml` / `Procfile`

6. **First visit** auto-seeds demo data via `POST /api/seed`

---

## 📸 Screenshots

### Dashboard
- Stats cards with project/task/overdue counts
- Task status distribution bars
- Priority breakdown chart
- Recent activity table

### Project Board
- Kanban columns (To Do → In Progress → Review → Done)
- Task cards with priority badges, assignee avatars, due dates
- Overdue task highlighting in red
- Quick status/assignee update from task modal

### Task Detail Modal
- Full task description and metadata
- Inline status/priority/assignee editing
- Comment thread
- Edit and delete actions

---

## 🔒 Security Notes

- Passwords hashed with PBKDF2-SHA256 + 32-byte random salt (100,000 iterations)
- JWT tokens expire after 7 days
- RBAC enforced at every API endpoint
- SQL parameterized queries (no SQL injection risk)
- CORS headers configured

---

## 📝 License

MIT License — free to use and modify.
