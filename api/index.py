from flask import Flask, request, jsonify
import os
import aiohttp
import asyncio
import logging
from urllib.parse import parse_qs, urlparse
from requests import Session
import requests

app = Flask(__name__)


AUTHORIZED_CODES = [
    "ansh123",
    "ftm321",
    "code786",
    "terabox99",
    "vps777",
    "secret101",
    "junagadh2025",
    "ftmdev@api"
]


cookies = {
    'ndus': 'YdZTyX1peHuigYYPUsTqgsGZULZ-eb2ZczrIytvZ',
    'ndut_fmt': 'F098715D4C56B1FE6EC126EF18922FFC9B0638DF2B642A62D37971B89F5871A7',
    'browserid': 'LIcG5gnjd4bOoF7jVUn_1FB4G1-j5fArTpoOSruTfkTFJvI_g4MzOPkG-BE=',
    '_ga': 'GA1.1.520080140.1746853034',
    '_ga_06ZNKL8C2E': 'GS2.1.s1746853033$o1$g1$t1746853361$j60$l0$h0',
    'ab_ymg_result': '{"data":"da8926eb8716ff12c51c9bf40086f24127c2e3126b3a8c66530a42d50daa40797711e2873fe863d994f415fc0335acaddfb3aaeae3cc0a05231c5ffff2168e9b6f0aadbd833774602694a2e0fb899e27ca7e5aa108da809a42d639020c86fc40a4e654c247c7540d7f1d0351c9fcc8ddc5552b1725e3fd561dd7da231b71da32","key_id":"66","sign":"df7288fe"}',
    'csrfToken': 'FG1s4DRQ7Smd4xl9-jpYcz4f',
    '__bid_n': '196b885ed7339790814207',
    'ab_sr': '1.0.1_YTE2YmFhNjM5YzdkMzM2ZmNjYWI4Yjg3ZjYzYmNhMGQyMmVkYjA1YThlNGY3ZjBiNzE5NjIxMmFlZGViODc5YWI5MDZlNWMzOGYxZDNlODVhMjg5NzE4NmY5OTNmOTRiMzUxNTdiZTk0NTVlMTAxYTRjOTE5NGQ3OTY5NmZjZjgzYzk0MGJlMDljN2I3NmJkYmExYzQzZGIyNDczMWU5Ng==',
    'lang': 'en',
    'TSID': 'UpjfKdxM5uYyISlGPUGknRioYswY5qq4',
}


headers = {
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


async def fetch_download_link_async(url):
    try:
        async with aiohttp.ClientSession(cookies=cookies, headers=headers) as session:
            async with session.get(url) as response1:
                response1.raise_for_status()
                response_data = await response1.text()
                js_token = find_between(response_data, 'fn%28%22', '%22%29')
                log_id = find_between(response_data, 'dp-logid=', '&')

                if not js_token or not log_id:
                    return None

                request_url = str(response1.url)
                surl = request_url.split('surl=')[1]
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
                    if 'list' not in response_data2:
                        return None

                    if response_data2['list'][0]['isdir'] == "1":
                        params.update({
                            'dir': response_data2['list'][0]['path'],
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
    except aiohttp.ClientResponseError as e:
        print(f"Error fetching download link: {e}")
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
        print(f"Error getting formatted size: {e}")
        return None


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

    # Get direct fast download link using HEAD request
    try:
        r = requests.Session()
        response = r.head(download_link, headers=headers, allow_redirects=False)
        direct_link = response.headers.get("Location")
    except Exception as e:
        direct_link = None

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
        'message': 'Working Fully',
        'Contact': '@ftmdeveloperz || @ftmdeveloperr'
    }


@app.route('/help', methods=['GET'])
async def help():
    return {
        'Info': 'Use the API like this:',
        'Example': 'https://yourdomain.com/api?link=https://1024terabox.com/s/example'
    }


@app.route('/api', methods=['GET'])
async def api():
    try:
        # Accept both `link` and `url`
        url = request.args.get('link') or request.args.get('url')
        if not url:
            return jsonify({'status': 'error', 'message': 'No link or url parameter provided', 'Link': None})

        logging.info(f"Received request for URL: {url}")
        link_data = await fetch_download_link_async(url)

        if link_data:
            tasks = [format_message(item) for item in link_data]
            formatted_message = await asyncio.gather(*tasks)
        else:
            formatted_message = None

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
