from flask import Flask, request, jsonify
import os
import aiohttp
import asyncio
import logging
from urllib.parse import parse_qs, urlparse
import requests

app = Flask(__name__)

COOKIES_FILE = 'cookies.txt'

headers = {
    'Referer': 'https://www.terabox.com/',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
    'Priority': 'u=0, i',
}


def find_between(string, start, end):
    start_index = string.find(start) + len(start)
    end_index = string.find(end, start_index)
    return string[start_index:end_index]


def load_cookies():
    cookies_dict = {}
    if os.path.exists(COOKIES_FILE):
        with open(COOKIES_FILE, 'r') as f:
            for line in f:
                if not line.strip() or line.startswith('#'):
                    continue
                parts = line.strip().split('\t')
                if len(parts) >= 7:
                    cookies_dict[parts[5]] = parts[6]
    return cookies_dict


async def fetch_download_link_async(url):
    try:
        async with aiohttp.ClientSession(cookies=load_cookies(), headers=headers) as session:
            async with session.get(url) as response1:
                response1.raise_for_status()
                response_data = await response1.text()
                js_token = find_between(response_data, 'fn%28%22', '%22%29')
                log_id = find_between(response_data, 'dp-logid=', '&')

                if not js_token or not log_id:
                    return None

                request_url = str(response1.url)
                surl = request_url.split('surl=')[-1]

                params = {
                    'app_id': '250528',
                    'web': '1',
                    'channel': 'dubox',
                    'clienttype': '0',
                    'jsToken': js_token,
                    'dplogid': log_id,
                    'page': '1',
                    'num': '20',
                    'order': 'time',
                    'desc': '1',
                    'site_referer': request_url,
                    'shorturl': surl,
                    'root': '1'
                }

                async with session.get('https://www.terabox.com/share/list', params=params) as response2:
                    response_data2 = await response2.json()
                    if 'list' not in response_data2 or not response_data2['list']:
                        return None

                    first_item = response_data2['list'][0]
                    if int(first_item.get('isdir', 0)) == 1:
                        params.update({
                            'dir': first_item['path'],
                            'order': 'asc',
                            'by': 'name',
                            'dplogid': log_id
                        })
                        params.pop('desc')
                        params.pop('root')

                        async with session.get('https://www.terabox.com/share/list', params=params) as response3:
                            response_data3 = await response3.json()
                            if 'list' not in response_data3:
                                return None
                            return response_data3['list']

                    return response_data2['list']
    except Exception as e:
        print(f"[Error] fetch_download_link_async: {e}")
        return None


def extract_thumbnail_dimensions(url: str) -> str:
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    size_param = params.get('size', [''])[0]
    if size_param:
        parts = size_param.replace('c', '').split('_u')
        if len(parts) == 2:
            return f"{parts[0]}x{parts[1]}"
    return "original"


async def get_formatted_size_async(size_bytes):
    try:
        size_bytes = int(size_bytes)
        size = size_bytes / (1024 * 1024) if size_bytes >= 1024 * 1024 else (
            size_bytes / 1024 if size_bytes >= 1024 else size_bytes
        )
        unit = "MB" if size_bytes >= 1024 * 1024 else ("KB" if size_bytes >= 1024 else "bytes")
        return f"{size:.2f} {unit}"
    except Exception as e:
        print(f"[Error] get_formatted_size_async: {e}")
        return "Unknown"


async def format_message(link_data):
    thumbnails = {}
    if 'thumbs' in link_data:
        for key, url in link_data['thumbs'].items():
            if url:
                dimensions = extract_thumbnail_dimensions(url)
                thumbnails[dimensions] = url

    file_name = link_data["server_filename"]
    file_size = await get_formatted_size_async(link_data["size"])
    download_link = link_data["dlink"]

    # Try to get fast direct link
    try:
        response = requests.get(download_link, headers=headers, allow_redirects=True, stream=True, timeout=10)
        direct_link = response.url
    except Exception as e:
        direct_link = None
        print(f"[Error] Getting fast link: {e}")

    return {
        'Title': file_name,
        'Size': file_size,
        'Direct Download Link': download_link,
        'fast_link': direct_link,
        'Thumbnails': thumbnails
    }


@app.route('/')
def home():
    return {
        'status': 'success',
        'message': 'Working Fully ✅',
        'Contact': '@ftmdeveloperz || @ftmdeveloperr'
    }


@app.route('/help', methods=['GET'])
async def help():
    return {
        'Info': 'Use the API like this:',
        'Example': 'https://yourdomain.com/api?link=https://terabox.com/s/example'
    }


@app.route('/api', methods=['GET'])
async def api():
    try:
        url = request.args.get('link') or request.args.get('url')
        if not url:
            return jsonify({'status': 'error', 'message': 'No link or url parameter provided', 'Link': None})

        logging.info(f"Received request for URL: {url}")
        link_data = await fetch_download_link_async(url)

        if link_data:
            tasks = [format_message(item) for item in link_data]
            formatted_message = await asyncio.gather(*tasks)
        else:
            return jsonify({'status': 'error', 'message': 'No data found for the provided link', 'Link': url})

        return jsonify({
            'ShortLink': url,
            'Extracted Info': formatted_message,
            'status': 'success'
        })

    except Exception as e:
        logging.error(f"Error occurred: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e),
            'Link': request.args.get('link') or request.args.get('url')
        })


if __name__ == '__main__':
    app.run(debug=True)
