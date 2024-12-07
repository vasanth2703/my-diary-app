# main.py
import os
import datetime
from fastapi import FastAPI, File, UploadFile, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import soundfile as sf
from io import BytesIO
import speech_recognition as sr

app = FastAPI(title="Personalized Diary Backend")

# OAuth2 configuration
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Google OAuth Configuration
GOOGLE_CLIENT_ID = "852882200826-n5ai58l4sg8gpikheeja2md5ibp9dg5u.apps.googleusercontent.com"
GOOGLE_CLIENT_SECRET = "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"
SCOPES = ['https://www.googleapis.com/auth/drive.file']

def get_google_flow():
    """Create Google OAuth flow"""
    return Flow.from_client_config(
        client_config={
            "web": {
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost:8000/callback"]
            }
        },
        scopes=SCOPES
    )

def get_drive_service(credentials):
    """Get Google Drive service"""
    return build('drive', 'v3', credentials=credentials)

def upload_to_drive(service, file_name, file_content, mime_type):
    """Upload file to Google Drive"""
    file_metadata = {'name': file_name}
    media = MediaIoBaseUpload(
        io.BytesIO(file_content), 
        mimetype=mime_type, 
        resumable=True
    )
    file = service.files().create(
        body=file_metadata, 
        media_body=media, 
        fields='id'
    ).execute()
    return file.get('id')

def speech_to_text(audio_bytes):
    """Convert audio to text using alternative method"""
    recognizer = sr.Recognizer()
    
    # Save audio bytes to temporary file
    with BytesIO(audio_bytes) as audio_file:
        try:
            with sf.SoundFile(audio_file) as sound_file:
                audio_data = recognizer.record(
                    sr.AudioFile(sf.SoundFile(audio_file))
                )
                text = recognizer.recognize_google(audio_data)
                return text
        except Exception as e:
            return f"Speech recognition error: {str(e)}"
            
@app.post("/login")
async def login(token: str):
    try:
        # Verify Google token
        idinfo = id_token.verify_oauth2_token(
            token, 
            requests.Request(), 
            GOOGLE_CLIENT_ID
        )
        
        # Create session or generate your app's token
        return {"status": "success", "user": idinfo}
    except ValueError:
        raise HTTPException(status_code=403, detail="Invalid token")
    
@app.post("/add-entry")
async def add_diary_entry(
    text: str = None, 
    image: UploadFile = File(None), 
    audio: UploadFile = File(None)
):
    """Add a new diary entry with authentication"""
    try:
        # Validate at least one content type is present
        if not any([text, image, audio]):
            raise HTTPException(
                status_code=400, 
                detail="At least one content type must be provided"
            )

        # Simulated authentication (replace with actual OAuth flow)
        flow = get_google_flow()
        credentials = flow.credentials

        drive_service = get_drive_service(credentials)
        
        entry_files = []
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

        # Handle text entry
        if text:
            text_file_id = upload_to_drive(
                drive_service, 
                f"diary_entry_{timestamp}.txt", 
                text.encode(), 
                "text/plain"
            )
            entry_files.append({"type": "text", "file_id": text_file_id})

        # Handle image entry
        if image:
            image_content = await image.read()
            image_file_id = upload_to_drive(
                drive_service, 
                f"diary_image_{timestamp}{image.filename}", 
                image_content, 
                image.content_type
            )
            entry_files.append({"type": "image", "file_id": image_file_id})

        # Handle audio entry
        if audio:
            audio_content = await audio.read()
            audio_file_id = upload_to_drive(
                drive_service, 
                f"diary_audio_{timestamp}{audio.filename}", 
                audio_content, 
                audio.content_type
            )
            
            # Transcribe audio
            temp_audio_path = f"temp_audio_{timestamp}.wav"
            with open(temp_audio_path, "wb") as f:
                f.write(audio_content)
            
            transcription = speech_to_text(temp_audio_path)
            os.remove(temp_audio_path)  # Clean up temporary file
            
            if transcription:
                transcription_file_id = upload_to_drive(
                    drive_service, 
                    f"audio_transcription_{timestamp}.txt", 
                    transcription.encode(), 
                    "text/plain"
                )
                entry_files.append({
                    "type": "audio", 
                    "file_id": audio_file_id,
                    "transcription_file_id": transcription_file_id
                })

        return {
            "message": "Diary entry successfully saved", 
            "files": entry_files
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/search")
async def search_diary_entries(query: str):
    """Search diary entries by keywords"""
    try:
        flow = get_google_flow()
        credentials = flow.credentials
        drive_service = get_drive_service(credentials)

        # Search files with given query
        results = drive_service.files().list(
            q=f"name contains '{query}'", 
            spaces='drive',
            fields='files(id, name, mimeType)'
        ).execute()

        return {
            "results": results.get('files', [])
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
