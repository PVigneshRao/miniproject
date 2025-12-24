import os
import io
import time
import smtplib
from datetime import datetime
from email.message import EmailMessage

from fastapi import FastAPI, File, UploadFile, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from PIL import Image
from dotenv import load_dotenv
from twilio.rest import Client

# 🔗 Import database helper functions
from database import (
    get_user_by_username,
    get_user_by_token,
    create_user,
    verify_password,
    update_user_token,
    ensure_admin_exists,
    insert_detection,
    insert_alert,
    insert_log,
    fetch_alerts,
    fetch_logs,
    fetch_detections,
    mark_all_alerts_read,
)

# --------------------------------------------------
# ENVIRONMENT VARIABLES & CONSTANTS
# --------------------------------------------------
load_dotenv()                  # Load .env file values
ensure_admin_exists()          # Create admin user if not present

MODEL_PATH = os.getenv("MODEL_PATH", "best.pt")
ALERT_COOLDOWN_SECONDS = int(os.getenv("ALERT_COOLDOWN_SECONDS", "15"))

# Animals considered dangerous
DANGER_CLASSES = {"lion", "tiger", "elephant"}

# ✅ DEMO SMS NUMBER (used only for demonstration)
DEMO_SMS_NUMBER = os.getenv("DEMO_SMS_NUMBER")

# --------------------------------------------------
# TWILIO SMS SETUP
# --------------------------------------------------
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_SMS_FROM = os.getenv("TWILIO_SMS_FROM")

twilio_client = None
if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_SMS_FROM:
    twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    print("[TWILIO] SMS client ready")
else:
    print("[TWILIO] SMS disabled")

# --------------------------------------------------
# FASTAPI APP SETUP
# --------------------------------------------------
app = FastAPI(title="Wildlife AI Backend")

# Enable frontend-backend communication (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------
# YOLO MODEL LOADING
# --------------------------------------------------
try:
    from ultralytics import YOLO
    model = YOLO(MODEL_PATH)
    print("[YOLO] Model loaded:", MODEL_PATH)
except Exception as e:
    print("[YOLO ERROR]", e)
    model = None

# Used to avoid sending too many alerts continuously
_last_alert_time = 0.0

# --------------------------------------------------
# AUTH REQUEST MODELS
# --------------------------------------------------
class RegisterRequest(BaseModel):
    name: str
    email: str
    phone: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str

# --------------------------------------------------
# AUTHENTICATION APIs
# --------------------------------------------------
@app.post("/auth/register")
def register(req: RegisterRequest):
    """
    Registers a new user into the system.
    """
    username = req.email.lower()

    if get_user_by_username(username):
        raise HTTPException(status_code=400, detail="User already exists")

    create_user(username, req.password, req.name, req.email, req.phone)
    user = get_user_by_username(username)
    token = update_user_token(user["id"])

    return {"token": token, "user": user}


@app.post("/auth/login")
def login(req: LoginRequest):
    """
    Validates user login credentials and generates a session token.
    """
    user = get_user_by_username(req.email.lower())

    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = update_user_token(user["id"])
    return {"token": token, "user": user}

# --------------------------------------------------
# YOLO IMAGE INFERENCE
# --------------------------------------------------
def run_inference(img: Image.Image):
    """
    Runs YOLO object detection on a frame.
    Returns detected objects with bounding boxes.
    """
    if not model:
        return []

    import numpy as np
    results = model(np.array(img), imgsz=512)

    detections = []
    for r in results:
        if r.boxes:
            for b in r.boxes:
                detections.append({
                    "label": model.names[int(b.cls[0])],
                    "confidence": float(b.conf[0]),
                    "bbox": b.xyxy[0].tolist(),
                })
    return detections

# --------------------------------------------------
# SMS ALERT FUNCTION (DEMO SAFE ✅)
# --------------------------------------------------
def send_sms_alert(animal: str, confidence: float, ts: str):
    """
    Sends SMS alert to a fixed demo number (Twilio trial safe).
    """
    if not twilio_client or not DEMO_SMS_NUMBER:
        print("[SMS] Skipped")
        return

    body = (
        "🚨 Wildlife Detection Alert\n\n"
        f"Animal Detected : {animal.upper()}\n"
        f"Confidence      : {confidence:.2f}\n"
        f"Time            : {ts}\n\n"
        "Please take immediate action."
    )

    try:
        twilio_client.messages.create(
            from_=TWILIO_SMS_FROM,
            to=DEMO_SMS_NUMBER,
            body=body
        )
        print(f"[SMS] Sent to demo number {DEMO_SMS_NUMBER}")
    except Exception as e:
        print("[SMS ERROR]", e)

# --------------------------------------------------
# EMAIL ALERT FUNCTION
# --------------------------------------------------
def send_email_alert(to_email: str, animal: str, confidence: float, ts: str):
    """
    Sends email alert to the logged-in user.
    """
    email_from = os.getenv("EMAIL_FROM")
    email_pass = os.getenv("EMAIL_PASSWORD")

    if not email_from or not email_pass:
        print("[EMAIL] Disabled")
        return

    msg = EmailMessage()
    msg["Subject"] = f"🚨 Wildlife Alert: {animal.upper()}"
    msg["From"] = email_from
    msg["To"] = to_email

    msg.set_content(
        f"""
Wildlife Detection Alert

Animal Detected : {animal}
Confidence      : {confidence:.2f}
Time            : {ts}

Please take immediate action.
"""
    )

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(email_from, email_pass)
            server.send_message(msg)
        print("[EMAIL] Sent")
    except Exception as e:
        print("[EMAIL ERROR]", e)

# --------------------------------------------------
# MAIN DETECTION API
# --------------------------------------------------
@app.post("/detect")
async def detect(
    file: UploadFile = File(...),
    token: str = Header(None)
):
    """
    Receives video frame, runs detection,
    stores data, and triggers alerts if needed.
    """
    global _last_alert_time

    # Authenticate user using token
    user = get_user_by_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Read image from request
    img = Image.open(io.BytesIO(await file.read())).convert("RGB")
    detections = run_inference(img)

    # Timestamps
    ts_db = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    ts_msg = datetime.now().strftime("%d/%m/%Y %I:%M %p")

    # Store detection data
    for d in detections:
        x1, y1, x2, y2 = d["bbox"]
        insert_detection(
            ts_db,
            d["label"],
            d["confidence"],
            x1,
            y1,
            x2 - x1,
            y2 - y1,
            user["id"]
        )
        insert_log(user["id"], d["label"], d["confidence"], "", "frame detection")

    # Filter dangerous animals
    danger = [d for d in detections if d["label"].lower() in DANGER_CLASSES]
    now = time.time()

    # Send alerts only after cooldown
    if danger and now - _last_alert_time >= ALERT_COOLDOWN_SECONDS:
        top = max(danger, key=lambda x: x["confidence"])
        insert_alert(top["label"], top["confidence"], user["id"])

        send_sms_alert(top["label"], top["confidence"], ts_msg)

        if user.get("email"):
            send_email_alert(user["email"], top["label"], top["confidence"], ts_msg)

        _last_alert_time = now

    return {"detections": detections}

# --------------------------------------------------
# DATA FETCH APIs
# --------------------------------------------------
@app.get("/alerts")
def get_alerts(limit: int = 50):
    return {"alerts": fetch_alerts(limit)}

@app.post("/alerts/mark-read")
def mark_read():
    mark_all_alerts_read()
    return {"status": "ok"}

@app.get("/logs")
def get_logs(limit: int = 200):
    return {"logs": fetch_logs(limit)}

@app.get("/detections")
def get_detections(limit: int = 500):
    return {"detections": fetch_detections(limit)}
