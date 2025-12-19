from flask import Flask, Response, render_template_string
from flask_sock import Sock
import mss
import io
from PIL import Image
import pyaudiowpatch as pyaudio
import threading
import queue
import base64

app = Flask(__name__)
sock = Sock(app)

CHUNK = 4096
FORMAT = pyaudio.paInt16

audio_clients = []
audio_lock = threading.Lock()
audio_config = {'rate': 48000, 'channels': 2}

def audio_capture_thread():
    global audio_config
    p = pyaudio.PyAudio()
    
    loopback_device = None
    
    try:
        wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
        default_speakers = p.get_device_info_by_index(wasapi_info['defaultOutputDevice'])
        
        for i in range(p.get_device_count()):
            dev = p.get_device_info_by_index(i)
            if dev['maxInputChannels'] > 0 and default_speakers['name'] in dev['name']:
                loopback_device = i
                break
    except:
        pass
    
    if loopback_device is None:
        for i in range(p.get_device_count()):
            dev = p.get_device_info_by_index(i)
            if dev['maxInputChannels'] > 0 and 'loopback' in dev['name'].lower():
                loopback_device = i
                break
    
    if loopback_device is None:
        print("Could not find loopback device!")
        return
    
    dev_info = p.get_device_info_by_index(loopback_device)
    print(f"Using audio device: {dev_info['name']}")
    
    rate = int(dev_info['defaultSampleRate'])
    channels = min(2, dev_info['maxInputChannels'])
    
    audio_config['rate'] = rate
    audio_config['channels'] = channels
    
    stream = p.open(
        format=FORMAT,
        channels=channels,
        rate=rate,
        input=True,
        input_device_index=loopback_device,
        frames_per_buffer=CHUNK
    )
    
    print(f"Audio capture started! {rate}Hz, {channels}ch")
    
    while True:
        try:
            data = stream.read(CHUNK, exception_on_overflow=False)
            with audio_lock:
                for client_queue in audio_clients:
                    try:
                        client_queue.put_nowait(data)
                    except queue.Full:
                        # Drop oldest and add new
                        try:
                            client_queue.get_nowait()
                            client_queue.put_nowait(data)
                        except:
                            pass
        except Exception as e:
            print(f"Audio error: {e}")
            break

audio_thread = threading.Thread(target=audio_capture_thread, daemon=True)
audio_thread.start()

def generate_frames():
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        while True:
            img = sct.grab(monitor)
            pil_img = Image.frombytes('RGB', img.size, img.bgra, 'raw', 'BGRX')
            
            buffer = io.BytesIO()
            pil_img.save(buffer, format='JPEG', quality=70)
            frame = buffer.getvalue()
            
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

@app.route('/config')
def config():
    return audio_config

@app.route('/')
def index():
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Screen Share</title>
        <style>
            * { margin: 0; padding: 0; }
            html, body { width: 100%; height: 100%; overflow: hidden; background: #000; }
            img { width: 100%; height: 100%; object-fit: contain; }
            #startBtn { 
                position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%);
                padding: 20px 40px; font-size: 24px; cursor: pointer; z-index: 100;
                background: #4CAF50; color: white; border: none; border-radius: 10px;
            }
            #startBtn:hover { background: #45a049; }
            #status {
                position: fixed; bottom: 10px; left: 10px; color: #0f0; 
                font-family: monospace; font-size: 12px; z-index: 100;
            }
        </style>
    </head>
    <body>
        <button id="startBtn" onclick="startStream()">Click to Start (with Audio)</button>
        <img id="video" src="/stream" style="display:none;">
        <div id="status"></div>
        
        <script>
            async function startStream() {
                document.getElementById('startBtn').style.display = 'none';
                document.getElementById('video').style.display = 'block';
                
                const configResp = await fetch('/config');
                const config = await configResp.json();
                const sampleRate = config.rate;
                const channels = config.channels;
                
                console.log('Audio config:', sampleRate, 'Hz,', channels, 'ch');
                
                const audioContext = new AudioContext({ sampleRate: sampleRate });
                
                // Ring buffer for audio
                const BUFFER_SIZE = sampleRate * channels * 2; // 2 seconds
                const ringBuffer = new Float32Array(BUFFER_SIZE);
                let writePos = 0;
                let readPos = 0;
                let bufferedSamples = 0;
                let started = false;
                const MIN_BUFFER = sampleRate * channels * 0.3; // 300ms before starting
                
                // ScriptProcessor for continuous playback
                const scriptNode = audioContext.createScriptProcessor(4096, 0, channels);
                
                scriptNode.onaudioprocess = function(e) {
                    const outputBuffer = e.outputBuffer;
                    const framesToWrite = outputBuffer.length;
                    
                    if (!started && bufferedSamples < MIN_BUFFER) {
                        // Still buffering, output silence
                        for (let ch = 0; ch < channels; ch++) {
                            outputBuffer.getChannelData(ch).fill(0);
                        }
                        return;
                    }
                    
                    started = true;
                    
                    for (let i = 0; i < framesToWrite; i++) {
                        if (bufferedSamples >= channels) {
                            for (let ch = 0; ch < channels; ch++) {
                                outputBuffer.getChannelData(ch)[i] = ringBuffer[readPos];
                                readPos = (readPos + 1) % BUFFER_SIZE;
                            }
                            bufferedSamples -= channels;
                        } else {
                            // Buffer underrun - output silence
                            for (let ch = 0; ch < channels; ch++) {
                                outputBuffer.getChannelData(ch)[i] = 0;
                            }
                        }
                    }
                };
                
                scriptNode.connect(audioContext.destination);
                
                // WebSocket for audio data
                const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                const ws = new WebSocket(wsProtocol + '//' + window.location.host + '/audio');
                ws.binaryType = 'arraybuffer';
                
                ws.onmessage = function(event) {
                    const int16Array = new Int16Array(event.data);
                    
                    for (let i = 0; i < int16Array.length; i++) {
                        ringBuffer[writePos] = int16Array[i] / 32768.0;
                        writePos = (writePos + 1) % BUFFER_SIZE;
                        bufferedSamples++;
                        
                        // Prevent overflow
                        if (bufferedSamples >= BUFFER_SIZE) {
                            bufferedSamples = BUFFER_SIZE - 1;
                            readPos = (writePos + 1) % BUFFER_SIZE;
                        }
                    }
                    
                    // Update status
                    const bufferMs = Math.round(bufferedSamples / channels / sampleRate * 1000);
                    document.getElementById('status').textContent = 'Buffer: ' + bufferMs + 'ms';
                };
            }
        </script>
    </body>
    </html>
    ''')

@sock.route('/audio')
def audio(ws):
    client_queue = queue.Queue(maxsize=200)
    
    with audio_lock:
        audio_clients.append(client_queue)
    
    try:
        while True:
            try:
                data = client_queue.get(timeout=1)
                ws.send(data)
            except queue.Empty:
                continue
    except:
        pass
    finally:
        with audio_lock:
            audio_clients.remove(client_queue)

@app.route('/stream')
def stream():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    print("Screen share running at http://<your-local-ip>:5000")
    app.run(host='0.0.0.0', port=5000, threaded=True)