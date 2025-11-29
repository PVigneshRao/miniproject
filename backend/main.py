# main.py
import os
import io
import time
from datetime import datetime
from typing import List, Dict, Any

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, ImageDraw, ImageFont
from dotenv import load_dotenv

from database import (
    insert_detection,
    insert_alert,
    insert_log,
    fetch_alerts,
    fetch_logs,
    fetch_detections,
    mark_all_alerts_read,
)

# ------------------------------------------------------------------------
load_dotenv()

# ✅ Danger classes (UPDATED)
DANGER_CLASSES = {"lion", "tiger", "elephant", "human"}

MODEL_PATH = os.getenv("MODEL_PATH", "best.pt")
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
ALERT_COOLDOWN_SECONDS = int(os.getenv("ALERT_COOLDOWN_SECONDS", "15"))

os.makedirs(UPLOAD_DIR, exist_ok=True)

# ------------------------------------------------------------------------
# FASTAPI
# ------------------------------------------------------------------------
app = FastAPI(title="Wildlife AI Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080", "http://127.0.0.1:8080"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------------------
# LOAD YOLO
# ------------------------------------------------------------------------
try:
    from ultralytics import YOLO
    model = YOLO(MODEL_PATH)
    print(f"[YOLO] Loaded model: {MODEL_PATH}")
except Exception as e:
    print("[YOLO ERROR]", e)
    model = None

_last_alert_time = 0.0

# ------------------------------------------------------------------------
# HELPERS
# ------------------------------------------------------------------------
def run_inference(img: Image.Image, conf_thres: float = 0.35):
    if model is None:
        return []

    import numpy as np

    results = model(np.array(img), imgsz=512, conf=conf_thres)
    detections = []

    for r in results:
        if r.boxes is None:
            continue

        for box in r.boxes:
            cls_id = int(box.cls[0])
            label = model.names.get(cls_id, str(cls_id))  # ✅ label
            conf = float(box.conf[0])
            x1, y1, x2, y2 = box.xyxy[0].tolist()

            detections.append({
                "label": label,
                "confidence": conf,
                "bbox": [x1, y1, x2, y2]
            })

    return detections


def draw_boxes(img: Image.Image, detections):
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("arial.ttf", 16)
    except:
        font = ImageFont.load_default()

    for d in detections:
        x1, y1, x2, y2 = d["bbox"]
        label = f'{d["label"]} {int(d["confidence"] * 100)}%'

        draw.rectangle([x1, y1, x2, y2], outline=(52, 199, 89), width=3)

        tb = draw.textbbox((x1, y1), label, font=font)
        tw, th = tb[2]-tb[0], tb[3]-tb[1]
        draw.rectangle([x1, y1-th-6, x1+tw+6, y1], fill=(52,199,89))
        draw.text((x1+3, y1-th-3), label, fill=(0,0,0), font=font)

    return img


# ------------------------------------------------------------------------
# ROUTES
# ------------------------------------------------------------------------
@app.post("/detect")
async def detect(file: UploadFile = File(...)):
    global _last_alert_time

    try:
        img = Image.open(io.BytesIO(await file.read())).convert("RGB")
    except:
        raise HTTPException(status_code=400, detail="Invalid image")

    detections = run_inference(img)

    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    # ✅ Store detections
    for d in detections:
        x1, y1, x2, y2 = d["bbox"]

        insert_detection(
            timestamp=ts,
            label=d["label"],
            confidence=d["confidence"],
            x=x1, y=y1,
            w=x2-x1, h=y2-y1,
            alert_sent=0
        )

        insert_log(
            user_id=None,
            animal=d["label"],
            confidence=d["confidence"],
            image_path="",
            message="frame detection"
        )

    # ✅ ALERT LOGIC
    now = time.time()
    danger = [d for d in detections if d["label"].lower() in DANGER_CLASSES]

    if danger and (now - _last_alert_time) >= ALERT_COOLDOWN_SECONDS:
        boxed = draw_boxes(img.copy(), detections)
        filename = f"alert_{int(now)}.jpg"
        path = os.path.join(UPLOAD_DIR, filename)
        boxed.save(path)

        top = max(danger, key=lambda x: x["confidence"])

        insert_alert(
            animal=top["label"],
            confidence=top["confidence"],
            image_path=path,
            is_read=0
        )

        insert_log(
            user_id=None,
            animal=top["label"],
            confidence=top["confidence"],
            image_path=path,
            message="DANGER ALERT"
        )

        _last_alert_time = now

    # ✅ RESPONSE FIX (THIS FIXES UNDEFINED)
    return {
        "detections": [
            {
                "label": d["label"],
                "confidence": float(d["confidence"]),
                "bbox": [float(v) for v in d["bbox"]]
            }
            for d in detections
        ]
    }


# ------------------------------------------------------------------------
# ALERTS / LOGS APIs
# ------------------------------------------------------------------------
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
