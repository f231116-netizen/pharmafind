"""Run once while building the website (see Dockerfile):
builds the photo index for visual matching, so the site is ready immediately.
Also useful locally:  python prepare.py
"""
from app import recognizer, AI_ERROR

if recognizer is None:
    raise SystemExit(f"AI scanner not available: {AI_ERROR}")
recognizer.load_now()
print("OCR:", recognizer.status["ocr"])
print("Visual:", recognizer.status["visual"])
