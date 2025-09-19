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
    if video_id not in video_storage:
        video_url = "https://effective-zebra-wqr496wpv6p3g6vx.github.dev/"
        filename = "Expired"
        return render_template('player.html', video_url=video_url, original_url=video_url, filename=filename)

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

from flask import Flask, request, jsonify, url_for
import os
import uuid

# Temp folder for storing .m3u8 files
TEMP_FOLDER = "temp"
os.makedirs(TEMP_FOLDER, exist_ok=True)

# Route to serve m3u8 file
@app.route("/temp/<filename>")
def get_m3u8(filename):
    return app.send_static_file(os.path.join(TEMP_FOLDER, filename))
    

@app.route("/generate", methods=["GET"])
def generate_m3u8():
    
    video_url = "https://rr1---sn-ci5gup-qxae6.googlevideo.com/videoplayback?expire=1758285271&ei=d_nMaN_ENpKX4t4P-Yrt0Qk&ip=122.180.245.197&id=o-AGrSIeJnn9PetaVTgEKzbKxw2rHBt17X9OzEV3KygyHG&itag=278&aitags=133%2C134%2C135%2C136%2C160%2C242%2C243%2C244%2C247%2C278%2C298%2C299%2C302%2C303%2C308%2C315%2C394%2C395%2C396%2C397%2C398%2C399%2C400%2C401&source=youtube&requiressl=yes&xpc=EgVo2aDSNQ%3D%3D&met=1758263671%2C&mh=43&mm=31%2C26&mn=sn-ci5gup-qxae6%2Csn-cvhelnls&ms=au%2Conr&mv=m&mvi=1&pl=24&rms=au%2Cau&initcwndbps=1755000&bui=ATw7iSXZ2q1AclB6b0t9cy4n1CLFdMUP0Ha9YhspGFsML2dFyzpCtdXjh84UI8DwTTooornjDesX0cOy&spc=hcYD5b_LkwV4&vprv=1&svpuc=1&mime=video%2Fwebm&ns=5hQPH7bEqpPu99TCyiYxE7QQ&rqh=1&gir=yes&clen=8768624&dur=899.533&lmt=1757154593499384&mt=1758263119&fvip=5&keepalive=yes&fexp=51552689%2C51565116%2C51565682%2C51580968&c=TVHTML5_SIMPLY&sefc=1&txp=4537534&n=J_PlBKkLqJyXIQ&sparams=expire%2Cei%2Cip%2Cid%2Caitags%2Csource%2Crequiressl%2Cxpc%2Cbui%2Cspc%2Cvprv%2Csvpuc%2Cmime%2Cns%2Crqh%2Cgir%2Cclen%2Cdur%2Clmt&sig=AJfQdSswRgIhAP71z-DwnEaaqpd__lq5qVpM5pAdWjqaUp3D8CLt98mMAiEA6NHScg6pTdWWVWas9wzGKaWDKx1EUJgim3ih4gwAFa8%3D&lsparams=met%2Cmh%2Cmm%2Cmn%2Cms%2Cmv%2Cmvi%2Cpl%2Crms%2Cinitcwndbps&lsig=APaTxxMwRQIhANAF2hyJmOSV_f_UpBW22dZ3xEnkwPy7FX6v1Hu1Pb63AiAqDPA-X9Iu9daPNlwRTm3zKQi4q85Jy6xNztDyU7GEuw%3D%3D"
    audio_url = "https://rr1---sn-ci5gup-qxae6.googlevideo.com/videoplayback?expire=1758285241&ei=WfnMaJnqGrmPssUP-YjH4AU&ip=122.180.245.197&id=o-AGL3myi-5lFKUYvQLAG2DssLaxEWR5b9RR1Gxgt2P7ju&itag=250&source=youtube&requiressl=yes&xpc=EgVo2aDSNQ%3D%3D&met=1758263641%2C&mh=43&mm=31%2C26&mn=sn-ci5gup-qxae6%2Csn-cvh7kn6l&ms=au%2Conr&mv=m&mvi=1&pl=24&rms=au%2Cau&initcwndbps=1755000&bui=ATw7iSUtNHFUA87sMfrP9l9Zdsiy1eRV9MhBKfokK2M3mSpVdHEHVqb2WneXkU7E5CuZLKQWUCSzPDny&spc=hcYD5cQ03LdM&vprv=1&svpuc=1&xtags=drc%3D1&mime=audio%2Fwebm&ns=C2kT1l3C9SVg22CsW4P7F3sQ&rqh=1&gir=yes&clen=7771949&dur=899.561&lmt=1757143656780220&mt=1758263119&fvip=3&keepalive=yes&fexp=51552689%2C51565116%2C51565682%2C51580968&c=TVHTML5_SIMPLY&sefc=1&txp=4532534&n=_FBwBI8yP5QJUw&sparams=expire%2Cei%2Cip%2Cid%2Citag%2Csource%2Crequiressl%2Cxpc%2Cbui%2Cspc%2Cvprv%2Csvpuc%2Cxtags%2Cmime%2Cns%2Crqh%2Cgir%2Cclen%2Cdur%2Clmt&sig=AJfQdSswRQIgaywNnxHn5pGHgi4d-AoNVew4P2zempIB59wnMtitbN8CIQDEWZG6_3NvOowPSNiy1HsGhsDSEC-sqqEYBFuEzTzKqQ%3D%3D&lsparams=met%2Cmh%2Cmm%2Cmn%2Cms%2Cmv%2Cmvi%2Cpl%2Crms%2Cinitcwndbps&lsig=APaTxxMwRgIhALvMFVlOgokQxfSVTlPjP4Y3fwhDig37O25SJxXHURx7AiEAs4wwlu6ZcL5HMxlCfRZNNtLVnq1_oc6a1JSazVzQAos%3D"


    # Generate unique filename
    filename = f"{uuid.uuid4().hex}.m3u8"
    file_path = os.path.join(TEMP_FOLDER, filename)

    # Create m3u8 content
    m3u8_content = f"""#EXTM3U

# Audio track
#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio_group",NAME="English",DEFAULT=YES,AUTOSELECT=YES,URI="{audio_url}"

# Video stream
#EXT-X-STREAM-INF:BANDWIDTH=2000000,RESOLUTION=1280x720,AUDIO="audio_group"
{video_url}
"""

    # Save to temp folder
    with open(file_path, "w") as f:
        f.write(m3u8_content)

    # Generate full URL
    m3u8_link = url_for("get_m3u8", filename=filename, _external=True)

    return jsonify({"m3u8_link": m3u8_link})



