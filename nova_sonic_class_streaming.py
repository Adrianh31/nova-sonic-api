import asyncio
import base64
import json
import uuid
import pyaudio
from aws_sdk_bedrock_runtime.client import BedrockRuntimeClient, InvokeModelWithBidirectionalStreamOperationInput
from aws_sdk_bedrock_runtime.models import InvokeModelWithBidirectionalStreamInputChunk, BidirectionalInputPayloadPart
from aws_sdk_bedrock_runtime.config import Config, HTTPAuthSchemeResolver, SigV4AuthScheme
from smithy_aws_core.credentials_resolvers.environment import EnvironmentCredentialsResolver

class SimpleNovaSonicStreaming:
    """Clase simplificada para Nova Sonic con streaming bidireccional"""

    def __init__(self, voice_id="matthew", aws_profile=None, region="us-east-1"):
        # Audio configuration
        self.rate = 16000  # Input sample rate
        self.output_rate = 24000  # Output sample rate
        self.chunk = 1024
        self.format = pyaudio.paInt16
        self.channels = 1
        self.voice_id = voice_id
        self.region = region

        # Streaming components
        self.bedrock_client = None
        self.stream_response = None
        self.is_active = False

        # Audio queues
        self.audio_input_queue = asyncio.Queue()
        self.audio_output_queue = asyncio.Queue()

        # Session information
        self.prompt_name = str(uuid.uuid4())
        self.content_name = str(uuid.uuid4())
        self.audio_content_name = str(uuid.uuid4())

        # PyAudio
        self.p = pyaudio.PyAudio()
        self.input_stream = None
        self.output_stream = None

        # Initialize client
        self._initialize_client()

    def _initialize_client(self):
        """Initialize the Bedrock client for streaming."""
        try:
            config = Config(
                endpoint_uri=f"https://bedrock-runtime.{self.region}.amazonaws.com",
                region=self.region,
                aws_credentials_identity_resolver=EnvironmentCredentialsResolver(),
                http_auth_scheme_resolver=HTTPAuthSchemeResolver(),
                http_auth_schemes={"aws.auth#sigv4": SigV4AuthScheme()}
            )
            self.bedrock_client = BedrockRuntimeClient(config=config)
            print("✅ Bedrock streaming client initialized")
        except Exception as e:
            print(f"❌ Error initializing Bedrock client: {e}")

    async def initialize_stream(self):
        """Initialize the bidirectional stream with Bedrock."""
        if not self.bedrock_client:
            self._initialize_client()

        try:
            self.stream_response = await self.bedrock_client.invoke_model_with_bidirectional_stream(
                InvokeModelWithBidirectionalStreamOperationInput(model_id='amazon.nova-sonic-v1:0')
            )
            self.is_active = True

            # Send initialization events
            await self._send_initialization_events()

            # Start processing responses
            asyncio.create_task(self._process_responses())

            # Start processing audio input
            asyncio.create_task(self._process_audio_input())

            print("✅ Nova Sonic streaming initialized")
            return self

        except Exception as e:
            self.is_active = False
            print(f"❌ Failed to initialize stream: {str(e)}")
            raise

    async def _send_initialization_events(self):
        """Send initialization events to Nova Sonic."""

        # 1. SessionStart
        session_start = {
            "event": {
                "sessionStart": {
                    "inferenceConfiguration": {
                        "maxTokens": 1024,
                        "topP": 0.95,
                        "temperature": 0.7
                    }
                }
            }
        }
        await self._send_raw_event(json.dumps(session_start))
        await asyncio.sleep(0.1)

        # 2. PromptStart
        prompt_start = {
            "event": {
                "promptStart": {
                    "promptName": self.prompt_name,
                    "audioOutputConfiguration": {
                        "mediaType": "audio/lpcm",
                        "sampleRateHertz": 24000,
                        "sampleSizeBits": 16,
                        "channelCount": 1,
                        "voiceId": self.voice_id,
                        "encoding": "base64",
                        "audioType": "SPEECH"
                    }
                }
            }
        }
        await self._send_raw_event(json.dumps(prompt_start))
        await asyncio.sleep(0.1)

        # 3. ContentStart (SYSTEM)
        content_start_system = {
            "event": {
                "contentStart": {
                    "promptName": self.prompt_name,
                    "contentName": self.content_name,
                    "type": "TEXT",
                    "role": "SYSTEM",
                    "interactive": True,
                    "textInputConfiguration": {
                        "mediaType": "text/plain"
                    }
                }
            }
        }
        await self._send_raw_event(json.dumps(content_start_system))
        await asyncio.sleep(0.1)

        # 4. TextInput (SYSTEM)
        system_message = {
            "event": {
                "textInput": {
                    "promptName": self.prompt_name,
                    "contentName": self.content_name,
                    "content": "You are a helpful voice assistant. Greet the user and wait for their question."
                }
            }
        }
        await self._send_raw_event(json.dumps(system_message))
        await asyncio.sleep(0.1)

        # 5. ContentEnd (SYSTEM)
        content_end_system = {
            "event": {
                "contentEnd": {
                    "promptName": self.prompt_name,
                    "contentName": self.content_name
                }
            }
        }
        await self._send_raw_event(json.dumps(content_end_system))
        await asyncio.sleep(0.1)

    async def _send_raw_event(self, event_json):
        """Send a raw event JSON to the Bedrock stream."""
        if not self.stream_response or not self.is_active:
            return

        event = InvokeModelWithBidirectionalStreamInputChunk(
            value=BidirectionalInputPayloadPart(bytes_=event_json.encode('utf-8'))
        )

        try:
            await self.stream_response.input_stream.send(event)
        except Exception as e:
            print(f"❌ Error sending event: {str(e)}")

    async def send_audio_content_start(self):
        """Send audio content start event."""
        content_start = {
            "event": {
                "contentStart": {
                    "promptName": self.prompt_name,
                    "contentName": self.audio_content_name,
                    "type": "AUDIO",
                    "interactive": True,
                    "role": "USER",
                    "audioInputConfiguration": {
                        "mediaType": "audio/lpcm",
                        "sampleRateHertz": 16000,
                        "sampleSizeBits": 16,
                        "channelCount": 1,
                        "audioType": "SPEECH",
                        "encoding": "base64"
                    }
                }
            }
        }
        await self._send_raw_event(json.dumps(content_start))

    async def send_audio_content_end(self):
        """Send audio content end event."""
        content_end = {
            "event": {
                "contentEnd": {
                    "promptName": self.prompt_name,
                    "contentName": self.audio_content_name
                }
            }
        }
        await self._send_raw_event(json.dumps(content_end))

    def add_audio_chunk(self, audio_bytes):
        """Add an audio chunk to the queue."""
        try:
            self.audio_input_queue.put_nowait({
                'audio_bytes': audio_bytes,
                'prompt_name': self.prompt_name,
                'content_name': self.audio_content_name
            })
        except:
            pass  # Queue might be full

    async def _process_audio_input(self):
        """Process audio input from the queue and send to Bedrock."""
        while self.is_active:
            try:
                # Get audio data from the queue
                data = await self.audio_input_queue.get()

                audio_bytes = data.get('audio_bytes')
                if not audio_bytes:
                    continue

                # Base64 encode the audio data
                blob = base64.b64encode(audio_bytes)
                audio_event = {
                    "event": {
                        "audioInput": {
                            "promptName": self.prompt_name,
                            "contentName": self.audio_content_name,
                            "content": blob.decode('utf-8')
                        }
                    }
                }

                # Send the event
                await self._send_raw_event(json.dumps(audio_event))

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"❌ Error processing audio: {e}")

    async def _process_responses(self):
        """Process incoming responses from Bedrock."""
        try:
            while self.is_active:
                try:
                    output = await self.stream_response.await_output()
                    result = await output[1].receive()

                    if result.value and result.value.bytes_:
                        try:
                            response_data = result.value.bytes_.decode('utf-8')
                            json_data = json.loads(response_data)

                            # Handle different response types
                            if 'event' in json_data:
                                if 'audioOutput' in json_data['event']:
                                    audio_content = json_data['event']['audioOutput']['content']
                                    audio_bytes = base64.b64decode(audio_content)
                                    await self.audio_output_queue.put(audio_bytes)
                                    print("🔊 Audio chunk received from Nova Sonic")

                        except json.JSONDecodeError:
                            pass

                except StopAsyncIteration:
                    break
                except Exception as e:
                    print(f"❌ Error receiving response: {e}")
                    break

        except Exception as e:
            print(f"❌ Response processing error: {e}")
        finally:
            self.is_active = False

    def setup_audio_streams(self):
        """Setup PyAudio streams for input and output."""
        try:
            # Input stream
            self.input_stream = self.p.open(
                format=self.format,
                channels=self.channels,
                rate=self.rate,
                input=True,
                frames_per_buffer=self.chunk,
                stream_callback=self._input_callback
            )

            # Output stream
            self.output_stream = self.p.open(
                format=self.format,
                channels=self.channels,
                rate=self.output_rate,
                output=True,
                frames_per_buffer=self.chunk
            )

            print("✅ Audio streams setup complete")

        except Exception as e:
            print(f"❌ Error setting up audio streams: {e}")

    def _input_callback(self, in_data, frame_count, time_info, status):
        """Callback function for audio input."""
        if self.is_active and in_data:
            # Add audio to queue for processing
            self.add_audio_chunk(in_data)
        return (None, pyaudio.paContinue)

    async def play_output_audio(self):
        """Play audio responses from Nova Sonic."""
        while self.is_active:
            try:
                # Get audio data from the queue
                audio_data = await asyncio.wait_for(
                    self.audio_output_queue.get(),
                    timeout=0.1
                )

                if audio_data and self.is_active and self.output_stream:
                    # Write audio data to output stream
                    await asyncio.get_event_loop().run_in_executor(
                        None, self.output_stream.write, audio_data
                    )

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                if self.is_active:
                    print(f"❌ Error playing output audio: {str(e)}")
                await asyncio.sleep(0.05)

    async def start_conversation(self):
        """Start the conversation with Nova Sonic."""
        print("🚀 Starting Nova Sonic conversation...")

        # Setup audio streams
        self.setup_audio_streams()

        # Send audio content start
        await self.send_audio_content_start()

        # Start audio playback task
        playback_task = asyncio.create_task(self.play_output_audio())

        # Start input stream
        if self.input_stream:
            self.input_stream.start_stream()

        print("🎤 Speak into your microphone...")
        print("⏹️  Press Enter to stop...")

        # Wait for user to press Enter
        await asyncio.get_event_loop().run_in_executor(None, input)

        # Stop conversation
        await self.stop_conversation()

        # Cancel playback task
        playback_task.cancel()
        try:
            await playback_task
        except asyncio.CancelledError:
            pass

    async def stop_conversation(self):
        """Stop the conversation."""
        print("🛑 Stopping conversation...")

        self.is_active = False

        # Send audio content end
        await self.send_audio_content_end()

        # Stop audio streams
        if self.input_stream:
            if self.input_stream.is_active():
                self.input_stream.stop_stream()
            self.input_stream.close()

        if self.output_stream:
            if self.output_stream.is_active():
                self.output_stream.stop_stream()
            self.output_stream.close()

        # Close PyAudio
        if self.p:
            self.p.terminate()

        # Close stream
        if self.stream_response:
            await self.stream_response.input_stream.close()

        print("✅ Conversation stopped")