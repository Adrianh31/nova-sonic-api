import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asyncio
import base64
import json
import uuid
import boto3
from typing import Optional, Dict, Any
import tempfile
import wave
from nova_sonic_class_streaming import SimpleNovaSonicStreaming

# Configurar variables de entorno desde el inicio
AWS_PROFILE = os.getenv("AWS_PROFILE", "adrian.hidalgo")
DEFAULT_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1") 
PORT = int(os.getenv("PORT", 8000))
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

# Configurar AWS Profile con variables de entorno
def setup_aws_credentials(aws_profile: str = None):
    """Configurar credenciales AWS para el webhook"""
    try:
        # Si hay variables de entorno, usarlas directamente
        if os.getenv("AWS_ACCESS_KEY_ID") and os.getenv("AWS_SECRET_ACCESS_KEY"):
            print("✅ Usando credenciales AWS de variables de entorno")
            return True
            
        # Si no, intentar usar el perfil
        profile = aws_profile or AWS_PROFILE
        session = boto3.Session(profile_name=profile)
        credentials = session.get_credentials()
        
        os.environ['AWS_ACCESS_KEY_ID'] = credentials.access_key
        os.environ['AWS_SECRET_ACCESS_KEY'] = credentials.secret_key
        if credentials.token:
            os.environ['AWS_SESSION_TOKEN'] = credentials.token
        os.environ['AWS_DEFAULT_REGION'] = session.region_name or DEFAULT_REGION
        
        print(f"✅ Configurado AWS profile: {profile}")
        return True
    except Exception as e:
        print(f"❌ Error configurando AWS: {e}")
        return False

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Eventos del ciclo de vida del servidor"""
    # Startup
    print("🚀 Iniciando Nova Sonic Webhook Server...")
    setup_aws_credentials()
    print(f"✅ Servidor listo para {ENVIRONMENT}")
    yield
    # Shutdown
    print("🛑 Cerrando servidor...")

app = FastAPI(
    title="Nova Sonic Webhook API", 
    version="1.0.0", 
    lifespan=lifespan,
    description="API para integrar Nova Sonic con n8n y otras aplicaciones"
)

# CORS middleware para permitir requests desde n8n (incluyendo HTTPS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción, especifica tu dominio de n8n
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Modelos de datos
class VoiceRequest(BaseModel):
    text: str
    voice_id: Optional[str] = "lupe"
    aws_profile: Optional[str] = "adrian.hidalgo"
    region: Optional[str] = "us-east-1"

class ConversationStart(BaseModel):
    voice_id: Optional[str] = "lupe"
    aws_profile: Optional[str] = "adrian.hidalgo"
    region: Optional[str] = "us-east-1"
    system_message: Optional[str] = "You are a helpful voice assistant."

class AudioMessage(BaseModel):
    audio_base64: str
    session_id: str
    voice_id: Optional[str] = "lupe"

# Almacén de sesiones activas
active_sessions: Dict[str, SimpleNovaSonicStreaming] = {}

@app.get("/")
async def root():
    """Endpoint de salud del webhook"""
    return {
        "status": "ok",
        "message": "Nova Sonic Webhook API está funcionando",
        "environment": ENVIRONMENT,
        "endpoints": {
            "health": "/health",
            "text_to_speech": "/tts",
            "start_conversation": "/conversation/start",
            "send_audio": "/conversation/audio",
            "end_conversation": "/conversation/end"
        }
    }

@app.get("/health")
async def health_check():
    """Health check para n8n"""
    try:
        # Verificar conexión AWS
        if os.getenv("AWS_ACCESS_KEY_ID"):
            # Usar credenciales de variables de entorno
            session = boto3.Session()
        else:
            # Usar perfil
            session = boto3.Session(profile_name=AWS_PROFILE)
            
        sts = session.client('sts')
        identity = sts.get_caller_identity()
        
        return {
            "status": "healthy",
            "aws_connected": True,
            "aws_account": identity['Account'],
            "active_sessions": len(active_sessions),
            "environment": ENVIRONMENT
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "aws_connected": False,
            "error": str(e),
            "environment": ENVIRONMENT
        }

@app.post("/tts")
async def text_to_speech(request: VoiceRequest):
    """
    Endpoint para convertir texto a voz
    Uso desde n8n: POST /tts con {"text": "Hola mundo", "voice_id": "lupe"}
    """
    try:
        # Configurar AWS
        setup_aws_credentials(request.aws_profile)
        
        # Crear instancia de Nova Sonic
        nova_sonic = SimpleNovaSonicStreaming(
            voice_id=request.voice_id,
            aws_profile=request.aws_profile,
            region=request.region
        )
        
        # Inicializar stream
        await nova_sonic.initialize_stream()
        
        # Enviar texto para conversión
        # Aquí necesitarías adaptar el código para enviar texto directamente
        # Por ahora retornamos confirmación
        
        return {
            "status": "success",
            "message": "Texto procesado por Nova Sonic",
            "text": request.text,
            "voice_id": request.voice_id,
            "audio_url": None  # Aquí iría la URL del audio generado
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en TTS: {str(e)}")

@app.post("/conversation/start")
async def start_conversation(request: ConversationStart):
    """
    Iniciar una conversación con Nova Sonic
    Retorna session_id para usar en posteriores requests
    """
    try:
        session_id = str(uuid.uuid4())
        
        # Configurar AWS
        setup_aws_credentials(request.aws_profile)
        
        # Crear instancia de Nova Sonic
        nova_sonic = SimpleNovaSonicStreaming(
            voice_id=request.voice_id,
            aws_profile=request.aws_profile,
            region=request.region
        )
        
        # Inicializar stream
        await nova_sonic.initialize_stream()
        
        # Personalizar mensaje del sistema si se proporciona
        if request.system_message:
            # Aquí se podría personalizar el mensaje del sistema
            pass
        
        # Guardar sesión
        active_sessions[session_id] = nova_sonic
        
        return {
            "status": "success",
            "session_id": session_id,
            "voice_id": request.voice_id,
            "message": "Conversación iniciada correctamente"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error iniciando conversación: {str(e)}")

@app.post("/conversation/audio")
async def send_audio_message(request: AudioMessage):
    """
    Enviar audio a una conversación activa
    Espera recibir audio en base64 y retorna la respuesta
    """
    try:
        # Verificar sesión
        if request.session_id not in active_sessions:
            raise HTTPException(status_code=404, detail="Sesión no encontrada")
        
        nova_sonic = active_sessions[request.session_id]
        
        # Decodificar audio
        audio_bytes = base64.b64decode(request.audio_base64)
        
        # Enviar audio content start
        await nova_sonic.send_audio_content_start()
        
        # Procesar audio
        nova_sonic.add_audio_chunk(audio_bytes)
        
        # Esperar respuesta (esto necesitaría ser mejorado para capturar la respuesta real)
        await asyncio.sleep(1)  # Placeholder
        
        # Enviar audio content end
        await nova_sonic.send_audio_content_end()
        
        return {
            "status": "success",
            "session_id": request.session_id,
            "message": "Audio procesado",
            "response_audio": None  # Aquí iría el audio de respuesta en base64
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error procesando audio: {str(e)}")

@app.post("/conversation/end/{session_id}")
async def end_conversation(session_id: str):
    """
    Terminar una conversación activa
    """
    try:
        if session_id not in active_sessions:
            raise HTTPException(status_code=404, detail="Sesión no encontrada")
        
        nova_sonic = active_sessions[session_id]
        
        # Detener conversación
        await nova_sonic.stop_conversation()
        
        # Remover de sesiones activas
        del active_sessions[session_id]
        
        return {
            "status": "success",
            "session_id": session_id,
            "message": "Conversación terminada correctamente"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error terminando conversación: {str(e)}")

@app.get("/sessions")
async def list_active_sessions():
    """
    Listar sesiones activas (para debugging)
    """
    return {
        "active_sessions": len(active_sessions),
        "session_ids": list(active_sessions.keys())
    }

# Endpoint para subir archivo de audio
@app.post("/upload-audio")
async def upload_audio_file(file: UploadFile = File(...)):
    """
    Subir archivo de audio y procesarlo con Nova Sonic
    Útil para n8n cuando necesites enviar archivos
    """
    try:
        # Leer archivo
        audio_content = await file.read()
        
        # Convertir a base64
        audio_base64 = base64.b64encode(audio_content).decode('utf-8')
        
        return {
            "status": "success",
            "filename": file.filename,
            "size": len(audio_content),
            "audio_base64": audio_base64,
            "message": "Archivo cargado correctamente"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error cargando archivo: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    print("🎙️ Iniciando Nova Sonic Webhook Server...")
    uvicorn.run(
        "nova_sonic_webhook:app", 
        host="0.0.0.0", 
        port=PORT, 
        reload=(ENVIRONMENT == "development"),
        log_level="info"
    )