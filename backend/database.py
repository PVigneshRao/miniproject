import os
import uuid
import bcrypt
from typing import Optional, Dict, Any

import mysql.connector
from mysql.connector import Error

# ------------------------------------------------
# MYSQL DATABASE CONFIGURATION
# Reads database credentials from environment variables
# ------------------------------------------------
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", "root"),
    "database": os.getenv("DB_NAME", "wildlife_ai"),
    "port": int(os.getenv("DB_PORT", "3306")),
}


def get_connection():
    """
    Creates and returns a new connection to the MySQL database.
    """
    return mysql.connector.connect(**DB_CONFIG)

# ------------------------------------------------
# PASSWORD UTILITIES
# ------------------------------------------------
def hash_password(password: str) -> str:
    """
    Encrypts the plain-text password using bcrypt hashing.
    This ensures passwords are never stored in plain text.
    """
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    """
    Verifies user-entered password with stored hashed password.
    Used during login.
    """
    return bcrypt.checkpw(password.encode(), hashed.encode())

# ------------------------------------------------
# USER DATABASE FUNCTIONS
# ------------------------------------------------
def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    """
    Fetches a user record using username (email).
    Used during login and registration validation.
    """
    try:
        conn = get_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM users WHERE username=%s", (username,))
        return cur.fetchone()
    except Error as e:
        print("DB error get_user_by_username:", e)
        return None
    finally:
        cur.close()
        conn.close()


def create_user(username: str, password: str, name: str, email: str, phone: str) -> Dict[str, Any]:
    """
    Creates a new user in the database.
    Password is securely hashed before storage.
    """
    password_hash = hash_password(password)

    try:
        conn = get_connection()
        cur = conn.cursor(dictionary=True)

        cur.execute(
            """
            INSERT INTO users (username, password_hash, name, email, phone)
            VALUES (%s,%s,%s,%s,%s)
            """,
            (username, password_hash, name, email, phone),
        )
        conn.commit()

        # Fetch and return the created user
        cur.execute("SELECT * FROM users WHERE username=%s", (username,))
        return cur.fetchone()

    except Error as e:
        print("DB error create_user:", e)
        raise
    finally:
        cur.close()
        conn.close()


def update_user_token(user_id: int) -> str:
    """
    Generates a unique session token for the user.
    Used for token-based authentication.
    """
    token = str(uuid.uuid4())
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("UPDATE users SET token=%s WHERE id=%s", (token, user_id))
        conn.commit()
        return token
    except Error as e:
        print("DB error update_user_token:", e)
        return ""
    finally:
        cur.close()
        conn.close()


def ensure_admin_exists():
    """
    Ensures a default admin user exists in the system.
    Automatically created when backend starts for first time.
    """
    if not get_user_by_username("admin"):
        print("[INIT] Creating default admin user")
        create_user(
            username="admin",
            password="admin123",
            name="Administrator",
            email="admin@wildlife.ai",
            phone="+919999999999",
        )

# ------------------------------------------------
# DETECTION / ALERT / LOG FUNCTIONS
# ------------------------------------------------
def insert_detection(timestamp, label, confidence, x, y, w, h, alert_sent=0):
    """
    Stores each detected animal with bounding box and confidence.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO detections
           (timestamp,label,confidence,x,y,w,h,alert_sent)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
        (timestamp, label, confidence, x, y, w, h, alert_sent),
    )
    conn.commit()
    cur.close()
    conn.close()


def insert_alert(animal, confidence, image_path, is_read=0):
    """
    Stores alert record when dangerous animal is detected.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO alerts (animal,confidence,image_path,is_read) VALUES (%s,%s,%s,%s)",
        (animal, confidence, image_path, is_read),
    )
    conn.commit()
    cur.close()
    conn.close()


def insert_log(user_id, animal, confidence, image_path, message):
    """
    Stores application activity logs for tracking & auditing.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO logs (user_id,animal,confidence,image_path,message) VALUES (%s,%s,%s,%s,%s)",
        (user_id, animal, confidence, image_path, message),
    )
    conn.commit()
    cur.close()
    conn.close()


def fetch_alerts(limit=50):
    """
    Fetches recent alerts for display in dashboard.
    """
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM alerts ORDER BY timestamp DESC LIMIT %s", (limit,))
    data = cur.fetchall()
    cur.close()
    conn.close()
    return data


def fetch_logs(limit=200):
    """
    Fetches recent system logs.
    """
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM logs ORDER BY timestamp DESC LIMIT %s", (limit,))
    data = cur.fetchall()
    cur.close()
    conn.close()
    return data


def fetch_detections(limit=500):
    """
    Fetches recent detection history.
    """
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM detections ORDER BY timestamp DESC LIMIT %s", (limit,))
    data = cur.fetchall()
    cur.close()
    conn.close()
    return data


def mark_all_alerts_read():
    """
    Marks all alerts as read (used after viewing alerts).
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE alerts SET is_read=1 WHERE is_read=0")
    conn.commit()
    cur.close()
    conn.close()


def get_user_by_token(token: str):
    """
    Fetches user details using authentication token.
    Used for securing detection endpoint.
    """
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT id, name, email, phone FROM users WHERE token=%s",
        (token,)
    )
    user = cur.fetchone()
    cur.close()
    conn.close()
    return user
