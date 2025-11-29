# database.py
import os
from typing import List, Dict, Any, Optional

import mysql.connector
from mysql.connector import Error

# --- MySQL CONFIG ---------------------------------------------------------

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", "root"),  # you said password = root
    "database": os.getenv("DB_NAME", "wildlife_ai"),
    "port": int(os.getenv("DB_PORT", "3306")),
}


def get_connection():
    """Create a new MySQL connection."""
    return mysql.connector.connect(**DB_CONFIG)


# --- INSERT HELPERS -------------------------------------------------------


def insert_detection(
    timestamp: str,
    label: str,
    confidence: float,
    x: float,
    y: float,
    w: float,
    h: float,
    alert_sent: int = 0,
) -> None:
    """
    Insert one row into detections table.

    detections(
        id INT PK AUTO_INCREMENT,
        timestamp DATETIME NOT NULL,
        label VARCHAR(128) NOT NULL,
        confidence FLOAT NOT NULL,
        x FLOAT, y FLOAT, w FLOAT, h FLOAT,
        alert_sent TINYINT(1) DEFAULT 0
    )
    """
    try:
        conn = get_connection()
        cur = conn.cursor()
        sql = """
        INSERT INTO detections
        (timestamp, label, confidence, x, y, w, h, alert_sent)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        cur.execute(
            sql,
            (timestamp, label, float(confidence), float(x), float(y), float(w), float(h), int(alert_sent)),
        )
        conn.commit()
    except Error as e:
        print("DB error insert_detection:", e)
    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass


def insert_alert(
    animal: str,
    confidence: float,
    image_path: str,
    is_read: int = 0,
) -> None:
    """
    Insert one row into alerts table.

    alerts(
        id INT PK AUTO_INCREMENT,
        animal VARCHAR(100),
        confidence FLOAT,
        image_path TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        is_read TINYINT(1) DEFAULT 0
    )
    """
    try:
        conn = get_connection()
        cur = conn.cursor()
        sql = """
        INSERT INTO alerts (animal, confidence, image_path, is_read)
        VALUES (%s, %s, %s, %s)
        """
        cur.execute(sql, (animal, float(confidence), image_path, int(is_read)))
        conn.commit()
    except Error as e:
        print("DB error insert_alert:", e)
    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass


def insert_log(
    user_id: Optional[int],
    animal: str,
    confidence: float,
    image_path: str,
    message: str,
) -> None:
    """
    Insert one row into logs table.

    logs(
        id INT PK AUTO_INCREMENT,
        user_id INT,
        animal VARCHAR(100),
        confidence FLOAT,
        image_path TEXT,
        message TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """
    try:
        conn = get_connection()
        cur = conn.cursor()
        sql = """
        INSERT INTO logs (user_id, animal, confidence, image_path, message)
        VALUES (%s, %s, %s, %s, %s)
        """
        cur.execute(
            sql,
            (user_id, animal, float(confidence), image_path, message),
        )
        conn.commit()
    except Error as e:
        print("DB error insert_log:", e)
    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass


# --- FETCH HELPERS --------------------------------------------------------


def fetch_alerts(limit: int = 50) -> List[Dict[str, Any]]:
    """
    Return latest alerts as a list of dicts.
    """
    rows: List[Dict[str, Any]] = []
    try:
        conn = get_connection()
        cur = conn.cursor(dictionary=True)
        sql = """
        SELECT id, animal, confidence, image_path, timestamp, is_read
        FROM alerts
        ORDER BY timestamp DESC
        LIMIT %s
        """
        cur.execute(sql, (limit,))
        rows = cur.fetchall()
    except Error as e:
        print("DB error fetch_alerts:", e)
    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass
    return rows


def mark_all_alerts_read() -> None:
    """
    Set is_read = 1 for all alerts.
    """
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("UPDATE alerts SET is_read = 1 WHERE is_read = 0")
        conn.commit()
    except Error as e:
        print("DB error mark_all_alerts_read:", e)
    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass


def fetch_logs(limit: int = 200) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    try:
        conn = get_connection()
        cur = conn.cursor(dictionary=True)
        sql = """
        SELECT id, user_id, animal, confidence, image_path, message, timestamp
        FROM logs
        ORDER BY timestamp DESC
        LIMIT %s
        """
        cur.execute(sql, (limit,))
        rows = cur.fetchall()
    except Error as e:
        print("DB error fetch_logs:", e)
    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass
    return rows


def fetch_detections(limit: int = 500) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    try:
        conn = get_connection()
        cur = conn.cursor(dictionary=True)
        sql = """
        SELECT id, timestamp, label, confidence, x, y, w, h, alert_sent
        FROM detections
        ORDER BY timestamp DESC
        LIMIT %s
        """
        cur.execute(sql, (limit,))
        rows = cur.fetchall()
    except Error as e:
        print("DB error fetch_detections:", e)
    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass
    return rows
