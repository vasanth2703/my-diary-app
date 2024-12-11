import os
import io
import uuid
import logging
import datetime
from typing import Optional, List

import soundfile as sf
import speech_recognition as sr
from fastapi import FastAPI, File, UploadFile, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

app = FastAPI(title="Personalized Diary Backend")

# OAuth2 configuration
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],  
    allow_headers=["*"],  
)

# Google OAuth Configuration
GOOGLE_CLIENT_ID = "852882200826-n5ai58l4sg8gpikheeja2md5ibp9dg5u.apps.googleusercontent.com"
UPLOAD_DIRECTORY = "uploads"

# Ensure upload directory exists
os.makedirs(UPLOAD_DIRECTORY, exist_ok=True)

# Temporary in-memory storage for entries (replace with a database in production)
DIARY_ENTRIES: List[dict] = []

def speech_to_text(audio_bytes: bytes) -> str:
    """Convert audio to text using speech recognition"""
    recognizer = sr.Recognizer()
    
    try:
        with BytesIO(audio_bytes) as audio_file:
            with sf.SoundFile(audio_file) as sound_file:
                audio_data = recognizer.record(
                    sr.AudioFile(sf.SoundFile(audio_file))
                )
                text = recognizer.recognize_google(audio_data)
                return text
    except Exception as e:
        logger.error(f"Speech recognition error: {e}")
        return ""

def save_file(content: bytes, filename: str) -> str:
    """Save file to upload directory and return file path"""
    try:
        file_path = os.path.join(UPLOAD_DIRECTORY, filename)
        with open(file_path, "wb") as f:
            f.write(content)
        return file_path
    except Exception as e:
        logger.error(f"File save error: {e}")
        raise

@app.post("/login")
async def login(token: str):
    """Authenticate user via Google OAuth token"""
    try:
        # Verify Google token
        idinfo = id_token.verify_oauth2_token(
            token, 
            google_requests.Request(), 
            GOOGLE_CLIENT_ID
        )
        
        return {
            "status": "success", 
            "user": {
                "sub": idinfo['sub'],
                "name": idinfo.get('name', ''),
                "email": idinfo['email'],
                "picture": idinfo.get('picture', '')
            }
        }
    except ValueError as e:
        logger.error(f"Token verification failed: {e}")
        raise HTTPException(status_code=403, detail="Invalid authentication token")

@app.post("/entries")
async def add_diary_entry(
    text: Optional[str] = None, 
    image: Optional[UploadFile] = File(None), 
    audio: Optional[UploadFile] = File(None)
):
    """Add a new diary entry with optional text, image, and audio"""
    try:
        # Validate at least one content type is present
        if not any([text, image, audio]):
            raise HTTPException(
                status_code=400, 
                detail="At least one content type must be provided"
            )

        # Generate unique entry ID
        entry_id = str(uuid.uuid4())
        timestamp = datetime.datetime.now()

        # Prepare entry data
        entry = {
            "id": entry_id,
            "text": text or "",
            "files": [],
            "created_at": timestamp.isoformat()
        }

        # Handle image upload
        if image:
            image_content = await image.read()
            image_filename = f"{entry_id}_{image.filename}"
            image_path = save_file(image_content, image_filename)
            entry['files'].append({
                "type": "image",
                "file_id": image_path
            })

        # Handle audio upload
        if audio:
            audio_content = await audio.read()
            audio_filename = f"{entry_id}_{audio.filename}"
            audio_path = save_file(audio_content, audio_filename)
            
            # Optional: Transcribe audio
            transcription = speech_to_text(audio_content)
            if transcription and not text:
                entry['text'] += transcription

            entry['files'].append({
                "type": "audio",
                "file_id": audio_path
            })

        # Store entry
        DIARY_ENTRIES.append(entry)
        logger.info(f"Diary entry created: {entry_id}")

        return entry

    except Exception as e:
        logger.error(f"Entry creation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/entries")
async def get_diary_entries():
    """Retrieve all diary entries"""
    return DIARY_ENTRIES

@app.get("/entries/search")
async def search_diary_entries(query: str):
    """Search diary entries by keywords"""
    return [
        entry for entry in DIARY_ENTRIES 
        if query.lower() in entry['text'].lower()
    ]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
