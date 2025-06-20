import asyncio
import os
import boto3
from nova_sonic_class_streaming import SimpleNovaSonicStreaming

async def main():
    """Demo principal con streaming bidireccional"""
    
    print("=" * 70)
    print("🎙️  NOVA SONIC DEMO - STREAMING BIDIRECCIONAL")
    print("=" * 70)
    
    # Verificar AWS Profile
    aws_profile = "adrian.hidalgo"  # Cambia por tu profile
    
    try:
        session = boto3.Session(profile_name=aws_profile)
        sts = session.client('sts')
        identity = sts.get_caller_identity()
        print(f"✅ AWS Profile '{aws_profile}' verificado")
        print(f"   Account: {identity['Account']}")
        print(f"   User: {identity['Arn'].split('/')[-1]}")
    except Exception as e:
        print(f"❌ Error verificando AWS profile: {e}")
        return
    
    # Configurar variables de entorno para aws_sdk_bedrock_runtime
    if aws_profile:
        session = boto3.Session(profile_name=aws_profile)
        credentials = session.get_credentials()
        os.environ['AWS_ACCESS_KEY_ID'] = credentials.access_key
        os.environ['AWS_SECRET_ACCESS_KEY'] = credentials.secret_key
        if credentials.token:
            os.environ['AWS_SESSION_TOKEN'] = credentials.token
        os.environ['AWS_DEFAULT_REGION'] = session.region_name or 'us-east-1'
    
    print("🔍 Inicializando Nova Sonic con streaming...")
    
    try:
        # Crear instancia de Nova Sonic con streaming
        nova_sonic = SimpleNovaSonicStreaming(
            voice_id="lupe",#English (US)tiffany/matthew-English(GB)amy-Spanish lupe/carlos
            aws_profile=aws_profile,
            region="us-east-1"
        )
        
        
        # Inicializar el stream
        await nova_sonic.initialize_stream()
        
        print("🚀 Nova Sonic listo para conversación")
        print("Voice ID: matthew")
        print("AWS Profile:", aws_profile)
        print("-" * 60)
        
        # Iniciar conversación
        await nova_sonic.start_conversation()
        
    except Exception as e:
        print(f"❌ Error en el demo: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\\n🛑 Demo interrumpido por el usuario")
    except Exception as e:
        print(f"❌ Error ejecutando demo: {e}")
