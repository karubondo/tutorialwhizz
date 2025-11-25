from flask import Flask, request, redirect, send_from_directory, session, jsonify
import sqlite3
import os
from functools import wraps
import json
from datetime import datetime

app = Flask(__name__)
app.secret_key = "SUPER_SECRET_KEY"

DB_PATH = os.path.join('sql', 'stone.db')


# ------------------------------
# Helper: DB connection
# ------------------------------
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ------------------------------
# Login Required Decorator
# ------------------------------
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_email" not in session:
            return redirect("/login.html")
        return f(*args, **kwargs)
    return wrapper


# ------------------------------
# Static File Routes
# ------------------------------
@app.route('/<page>')
def serve_page(page):
    if page.endswith(".html"):
        return send_from_directory('.', page)
    return "Not Found", 404

@app.route('/images/<path:filename>')
def serve_images(filename):
    return send_from_directory('images', filename)


# ------------------------------
# Session Check API
# ------------------------------
@app.route('/session-check')
def session_check():
    if "user_email" in session:
        conn = get_db()
        row = conn.execute(
            "SELECT username FROM users WHERE email=?",
            (session["user_email"],)
        ).fetchone()
        conn.close()
        return {"logged_in": True, "email": session["user_email"], "username": row["username"]}
    return {"logged_in": False}


# ------------------------------
# Sign Up
# ------------------------------
@app.route('/signup', methods=['POST'])
def signup_submit():
    email = request.form.get("email")
    password = request.form.get("password")

    if not email or not password:
        return "Missing fields", 400

    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO users (email, password, username, bio, achievements) VALUES (?, ?, ?, ?, ?)",
            (email, password, email.split("@")[0], "", json.dumps({}))
        )
        conn.commit()
        return redirect("/login.html")
    except sqlite3.IntegrityError:
        return "Email already exists", 400
    finally:
        conn.close()


# ------------------------------
# Login
# ------------------------------
@app.route('/login', methods=['POST'])
def login_submit():
    email = request.form.get("email")
    password = request.form.get("password")

    conn = get_db()
    row = conn.execute(
        "SELECT password FROM users WHERE email=?", (email,)
    ).fetchone()
    conn.close()

    if row and row["password"] == password:
        session["user_email"] = email
        return redirect("/home.html")
    return "Invalid login", 401


# ------------------------------
# Logout
# ------------------------------
@app.route('/logout')
def logout():
    session.pop("user_email", None)
    return redirect("/login.html")


# ------------------------------
# Profile APIs
# ------------------------------
@app.route('/api/profile')
@login_required
def api_get_profile():
    conn = get_db()
    user = conn.execute(
        "SELECT username, bio, achievements FROM users WHERE email=?",
        (session["user_email"],)
    ).fetchone()
    conn.close()

    return jsonify({
        "username": user["username"],
        "bio": user["bio"],
        "achievements": json.loads(user["achievements"])
    })

@app.route('/api/profile/update', methods=['POST'])
@login_required
def api_update_profile():
    username = request.json.get("username")
    bio = request.json.get("bio")

    conn = get_db()
    conn.execute(
        "UPDATE users SET username=?, bio=? WHERE email=?",
        (username, bio, session["user_email"])
    )
    conn.commit()
    conn.close()

    return {"status": "success"}

@app.route('/api/profile/change-password', methods=['POST'])
@login_required
def api_change_password():
    old = request.json.get("oldPassword")
    new = request.json.get("newPassword")

    conn = get_db()
    row = conn.execute(
        "SELECT password FROM users WHERE email=?", (session["user_email"],)
    ).fetchone()

    if row["password"] != old:
        return {"error": "Incorrect current password"}, 400

    conn.execute(
        "UPDATE users SET password=? WHERE email=?",
        (new, session["user_email"])
    )
    conn.commit()
    conn.close()

    return {"status": "success"}

@app.route('/api/achievement', methods=['POST'])
@login_required
def api_add_achievement():
    achievement = request.json.get("achievement")

    conn = get_db()
    row = conn.execute(
        "SELECT achievements FROM users WHERE email=?",
        (session["user_email"],)
    ).fetchone()

    achievements = json.loads(row["achievements"])
    achievements[achievement] = True

    conn.execute(
        "UPDATE users SET achievements=? WHERE email=?",
        (json.dumps(achievements), session["user_email"])
    )
    conn.commit()
    conn.close()

    return {"status": "success"}

# Serve Progress Tracker page
@app.route('/progress.html')
@login_required
def progress_page():
    return send_from_directory('.', 'progress.html')

# ------------------------------
# COMMUNITY POSTS APIs
# ------------------------------
@app.route('/api/posts', methods=['GET'])
def get_posts():
    conn = get_db()
    rows = conn.execute(
        "SELECT user_email, text, created_at FROM community_posts ORDER BY created_at DESC"
    ).fetchall()
    posts = []

    for row in rows:
        user = conn.execute(
            "SELECT username FROM users WHERE email=?",
            (row["user_email"],)
        ).fetchone()

        posts.append({
            "user": user["username"] if user else "Guest",
            "text": row["text"],
            "date": row["created_at"]
        })

    conn.close()
    return jsonify(posts)


@app.route('/api/posts', methods=['POST'])
@login_required
def create_post():
    data = request.json
    text = data.get("text")
    if not text:
        return {"error": "Post text cannot be empty"}, 400

    conn = get_db()
    conn.execute(
        "INSERT INTO community_posts (user_email, text) VALUES (?, ?)",
        (session["user_email"], text)
    )
    conn.commit()
    conn.close()

    return {"status": "success"}


# ------------------------------
# FEEDBACK APIs
# ------------------------------

ADMIN_EMAIL = "jrmanipor1@gmail.com"


# Submit feedback
@app.route('/api/feedback', methods=['POST'])
def submit_feedback():
    data = request.json
    message = data.get("message")

    if not message:
        return {"error": "Feedback cannot be empty"}, 400

    user_email = session.get("user_email", None)

    conn = get_db()
    conn.execute(
        "INSERT INTO feedback (user_email, message) VALUES (?, ?)",
        (user_email, message)
    )
    conn.commit()
    conn.close()

    return {"status": "success"}


# Get feedback (admin only)
@app.route('/api/feedback', methods=['GET'])
def view_feedback():
    if session.get("user_email") != ADMIN_EMAIL:
        return {"error": "Unauthorized"}, 403

    conn = get_db()
    rows = conn.execute(
        "SELECT user_email, message, created_at FROM feedback ORDER BY created_at DESC"
    ).fetchall()
    conn.close()

    result = []
    for row in rows:
        result.append({
            "user_email": row["user_email"] if row["user_email"] else "Guest",
            "message": row["message"],
            "date": row["created_at"]
        })

    return jsonify(result)

@app.route('/api/save-kda', methods=['POST'])
@login_required
def save_kda():
    data = request.json
    game = data.get("game")
    if not game:
        return {"error": "Game is required"}, 400

    # Collect kills/deaths/assists
    fields = {}
    for i in range(1, 6):
        fields[f'kills{i}'] = data.get(f'kills{i}', 0)
        fields[f'deaths{i}'] = data.get(f'deaths{i}', 1)
        fields[f'assists{i}'] = data.get(f'assists{i}', 0)

    conn = get_db()
    # Check if row exists
    existing = conn.execute(
        "SELECT id FROM kda_progress WHERE user_email=? AND game=?",
        (session["user_email"], game)
    ).fetchone()

    if existing:
        # Update existing
        conn.execute(
            f"""UPDATE kda_progress SET
                kills1=?, deaths1=?, assists1=?,
                kills2=?, deaths2=?, assists2=?,
                kills3=?, deaths3=?, assists3=?,
                kills4=?, deaths4=?, assists4=?,
                kills5=?, deaths5=?, assists5=?,
                updated_at=CURRENT_TIMESTAMP
                WHERE user_email=? AND game=?""",
            (*fields.values(), session["user_email"], game)
        )
    else:
        # Insert new
        conn.execute(
            f"""INSERT INTO kda_progress 
                (user_email, game, kills1, deaths1, assists1,
                 kills2, deaths2, assists2,
                 kills3, deaths3, assists3,
                 kills4, deaths4, assists4,
                 kills5, deaths5, assists5)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (session["user_email"], game, *fields.values())
        )

    conn.commit()
    conn.close()
    return {"status": "success"}

@app.route('/api/get-kda')
@login_required
def get_kda():
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM kda_progress WHERE user_email=?",
        (session["user_email"],)
    ).fetchall()
    conn.close()

    result = {}
    for row in rows:
        game = row["game"]
        result[game] = {key: row[key] for key in row.keys() if key.startswith(("kills", "deaths", "assists"))}
    return jsonify(result)

# ------------------------------
# Start Flask
# ------------------------------
if __name__ == "__main__":
    app.run(debug=True)
