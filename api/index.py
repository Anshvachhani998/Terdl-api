from flask import Flask, request, render_template, jsonify, Response, stream_with_context, redirect
import os
import hashlib
import requests
from urllib.parse import urlparse, unquote

app = Flask(__name__)

# In-memory storage (use DB for persistence in production)
video_storage = {}

def validate_url(url):
    """Validate URL to prevent XSS and ensure it's a proper HTTP/HTTPS URL"""
    try:
        decoded_url = unquote(url)
        parsed = urlparse(decoded_url)
        if parsed.scheme not in ['http', 'https']:
            return False
        if not parsed.netloc:
            return False
        return True
    except Exception:
        return False

def generate_video_id(url):
    """Generate a unique ID for a video URL"""
    # shorter stable id using md5
    return hashlib.md5(url.encode()).hexdigest()[:12]

def extract_full_url(request):
    """Extract the full URL from request, handling truncation issues"""
    query_string = request.query_string.decode('utf-8')
    if 'url=' in query_string:
        url_start = query_string.find('url=') + 4
        full_url = query_string[url_start:]
        return unquote(full_url)
    return None

video_counter = 1
video_storage = {}  # {id: {"url":..., "filename":...}}

def store_video_url(url, filename=None):
    global video_counter
    vid = video_counter
    video_storage[vid] = {"url": url, "filename": filename or "video.mp4"}
    video_counter += 1
    return vid
@app.route('/')
def home():
    return '''
    <html>
    <head>
        <title>Video Player & Download API</title>
        <style>
            body { background: #000; color: #fff; font-family: Arial, sans-serif; text-align: center; padding: 50px; }
            h1 { color: #4A90E2; }
            .endpoint { background: #1a1a1a; padding: 20px; margin: 20px auto; border-radius: 8px; max-width: 800px; }
            code { background: #333; padding: 5px 10px; border-radius: 4px; color: #4A90E2; }
            a { color: #7dc3ff; }
        </style>
    </head>
    <body>
        <h1>Video Player & Download API</h1>
        <div class="endpoint">
            <h3>Player Endpoint</h3>
            <p>Open player with long URL: <code>/player?url=VIDEO_LINK</code></p>
            <p>Open player with id: <code>/player?vid=VIDEO_ID</code></p>
        </div>
        <div class="endpoint">
            <h3>Shorten Endpoint</h3>
            <p>Create a short link: <code>/shorten?url=VIDEO_LINK</code> (GET) or POST JSON <code>{"url":"..."}</code></p>
        </div>
        <div class="endpoint">
            <h3>Short Link</h3>
            <p>Short link format: <code>/s/&lt;VIDEO_ID&gt;</code> (redirects to player)</p>
        </div>
    </body>
    </html>
    '''
@app.route('/shorten', methods=['GET','POST'])
def shorten():
    long_url = None
    filename = None
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        long_url = data.get('url')
        filename = data.get('name')
    if not long_url:
        long_url = extract_full_url(request) or request.args.get('url')
        filename = request.args.get('name')

    if not long_url:
        return jsonify({"success": False, "error": "No URL provided."}), 400
    if not validate_url(long_url):
        return jsonify({"success": False, "error": "Invalid URL."}), 400

    vid = store_video_url(long_url, filename)
    host = request.host_url.rstrip('/')
    
    short_url = f"{host}/{filename or 'video.mp4'}/download/{vid}"
    player_url = f"{host}/player?vid={vid}&name={filename or 'video.mp4'}"
    cdn_url = f"{host}/cdn/{vid}"

    return jsonify({
        "success": True,
        "video_id": vid,
        "short_url": short_url,
        "player_url": player_url,
        "cdn_url": cdn_url,
        "filename": filename or "video.mp4"
    })

@app.route('/s/<video_id>')
def short_redirect(video_id):
    # Redirect to player so opening short link launches the player
    return redirect(f"/player?vid={video_id}", code=302)

@app.route('/<filename>/download/<int:video_id>')
def download_or_play(filename, video_id):
    """
    Short link format: /filename/download/video_id
    Instead of direct download, render the player with the stored video URL.
    """
    video_info = video_storage[video_id]
    video_url = video_info["url"]
    filename = filename or video_info.get("filename", "video.mp4")

    # Render player.html instead of direct download
    return render_template('player.html', video_url=video_url, original_url=video_url, filename=filename)


@app.route('/api')
def api():
    video_url = extract_full_url(request) or request.args.get('url')
    if not video_url:
        return jsonify({"error": "No URL provided. Use ?url=VIDEO_LINK"}), 400
    if not validate_url(video_url):
        return jsonify({"error": "Invalid URL. Only HTTP/HTTPS URLs are allowed."}), 400
    return jsonify({"success": True, "download_link": video_url})

@app.route('/cdn/<video_id>')
def stream_video(video_id):
    if video_id not in video_storage:
        return jsonify({"error": "Video not found"}), 404

    original_url = video_storage[video_id]
    try:
        range_header = request.headers.get('Range')
        headers = {
            'User-Agent': request.headers.get('User-Agent', 'Mozilla/5.0'),
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'identity',
            'Connection': 'keep-alive'
        }
        if range_header:
            headers['Range'] = range_header

        response = requests.get(original_url, headers=headers, stream=True, timeout=30)

        def generate():
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    yield chunk

        response_headers = {
            'Content-Type': response.headers.get('Content-Type', 'video/mp4'),
            'Accept-Ranges': 'bytes',
            'Cache-Control': 'public, max-age=3600'
        }
        content_length = response.headers.get('Content-Length')
        if content_length:
            response_headers['Content-Length'] = content_length

        flask_response = Response(
            stream_with_context(generate()),
            status=response.status_code,
            headers=response_headers
        )
        if 'Content-Range' in response.headers:
            flask_response.headers['Content-Range'] = response.headers['Content-Range']

        return flask_response

    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"Failed to stream video: {str(e)}"}), 500
