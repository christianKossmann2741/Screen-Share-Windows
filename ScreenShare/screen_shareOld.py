from flask import Flask, Response
import mss
import io
from PIL import Image

app = Flask(__name__)

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

@app.route('/')
def index():
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Screen Share</title>
        <style>
            * { margin: 0; padding: 0; }
            html, body { width: 100%; height: 100%; overflow: hidden; background: #000; }
            img { width: 100%; height: 100%; object-fit: contain; }
        </style>
    </head>
    <body>
        <img src="/stream">
    </body>
    </html>
    '''

@app.route('/stream')
def stream():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    print("Screen share running at http://<your-local-ip>:5000")
    app.run(host='0.0.0.0', port=5000, threaded=True)