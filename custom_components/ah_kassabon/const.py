"""Constants for AH Kassabon."""

DOMAIN = "ah_kassabon"
STORAGE_KEY = DOMAIN
STORAGE_VERSION = 1

EVENT_IMPORTED = f"{DOMAIN}_imported"
SIGNAL_UPDATED = f"{DOMAIN}_updated"

UPLOAD_URL = f"/api/{DOMAIN}/upload"
CARD_URL = f"/{DOMAIN}/ah-kassabon-card.js"
