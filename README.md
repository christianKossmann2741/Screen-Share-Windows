# Screen Share

A simple Python-based screen sharing solution that streams your Windows desktop with audio to any device on your local network via browser.

## Features

- Real-time screen capture using MJPEG streaming
- System audio capture via WASAPI loopback
- Browser-based viewer (no client installation needed)
- Works on any device with a modern browser
- Low latency with adaptive audio buffering

## Requirements

- Windows 10/11
- Python 3.8+

## Installation

```bash
pip install -r requirements.txt
```

## Usage

1. Run the server:
```bash
python screen_share.py
```

2. Find your local IP address:
```bash
ipconfig
```
Look for the IPv4 address (e.g., `192.168.1.100`)

3. On another device connected to the same network, open a browser and go to:
```
http://<your-ip>:5000
```

4. Click the "Click to Start (with Audio)" button to begin streaming.

## Firewall Configuration

If you can't connect from other devices, allow the port through Windows Firewall:

```powershell
netsh advfirewall firewall add rule name="ScreenShare" dir=in action=allow protocol=tcp localport=5000
```

## Configuration

You can adjust these parameters in `screen_share.py`:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `CHUNK` | 4096 | Audio buffer size |
| `quality` | 70 | JPEG quality (1-100) |
| `port` | 5000 | Server port |

### Video Quality

In the `generate_frames()` function, adjust the JPEG quality:
```python
pil_img.save(buffer, format='JPEG', quality=70)  # Lower = smaller/faster, higher = better quality
```

### Audio Buffer

The client buffers 300ms of audio before playback. Adjust `MIN_BUFFER` in the JavaScript if needed:
```javascript
const MIN_BUFFER = sampleRate * channels * 0.3; // 300ms
```

## Troubleshooting

### No audio
- Make sure something is playing on your PC
- Check that the correct loopback device is detected in the console output
- Some virtual audio devices may not support loopback

### Choppy video
- Lower the JPEG quality
- Ensure you're on a stable WiFi connection or use ethernet

### Can't connect from other devices
- Verify both devices are on the same network
- Check Windows Firewall settings
- Try disabling VPN if active

### Audio device not found
- The script looks for WASAPI loopback devices
- If using non-standard audio setup, you may need to manually specify the device index

## How It Works

- **Video**: Uses `mss` for fast screen capture, compresses frames as JPEG, and streams via MJPEG over HTTP
- **Audio**: Captures system audio using `pyaudiowpatch` (WASAPI loopback), streams raw PCM data over WebSocket, client uses a ring buffer with `ScriptProcessorNode` for smooth playback

## Limitations

- View-only (no remote control)
- Single monitor support (primary monitor)
- ~200-400ms audio latency due to buffering
- Windows only (due to WASAPI loopback)

## License

MIT
