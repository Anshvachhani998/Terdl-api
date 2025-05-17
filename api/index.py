from flask import Flask
import os
from flask import request, jsonify
import aiohttp
import asyncio
import logging
from urllib.parse import parse_qs, urlparse

app = Flask(__name__)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

cookies = {
    'PANWEB': '1',
    'browserid': 'Cy5EXu1Tzj6Tw3JVWDVZG57bcVB3PStNKnFq-eksnn33s0nhe8wctkVEF1g=',
    'lang': 'en',
    '__bid_n': '196d90a7ef6d98c2484207',
    'ndut_fmt': '1B38B8821B9241CF3C51E9F8141C292725EC2A049FABABB137509082AC94989B',
    '__stripe_mid': '83eb4165-8c1d-46e8-b54c-4226543a778cc1575f',
    'ndus': 'YdZTyX1peHuiljk-9FQjnM6F2ajG_vnHH4yOTLWg',
    'csrfToken': 'sgiVprBuEj979JssZlM4cNXs',
}

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Accept': '*/*',
    'Connection': 'keep-alive',
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
              #print(js_token)
              log_id = find_between(response_data, 'dp-logid=', '&')
             # print(log_id)

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

              async with session.get('https://www.1024tera.com/share/list', params=params) as response2:
                  response_data2 = await response2.json()
                #   print(response_data2)
                  #print("res2", response_data2)
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

                      async with session.get('https://www.1024tera.com/share/list', params=params) as response3:
                          response_data3 = await response3.json()
                        #   print(response_data3)
                          #print("res3", response_data3)
                          if 'list' not in response_data3:
                              return None
                          return response_data3['list']
                  #print(response_data2['list'])
                  return response_data2['list']
  except aiohttp.ClientResponseError as e:
      print(f"Error fetching download link: {e}")
      return None


def extract_thumbnail_dimensions(url: str) -> str:
    """Extract dimensions from thumbnail URL's size parameter"""
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    size_param = params.get('size', [''])[0]
    
    # Extract numbers from size format like c360_u270
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
  # Process thumbnails
    thumbnails = {}
    if 'thumbs' in link_data:
        for key, url in link_data['thumbs'].items():
            if url:  # Skip empty URLs
                dimensions = extract_thumbnail_dimensions(url)
                thumbnails[dimensions] = url
#   if link_data
    file_name = link_data["server_filename"]
    file_size = await get_formatted_size_async(link_data["size"])
    download_link = link_data["dlink"]
    sk = {
      'Title': file_name,
      'Size': file_size,
      'Direct Download Link': download_link,
      'Thumbnails': thumbnails
    }
    return sk

@app.route('/')
def hello_world():
  #result = bot.get_me()
  response = {'status': 'success', 'message': 'Working Fully',' Contact': '@ftmdeveloperz'}
  return response


@app.route(rule='/api', methods=['GET'])
async def Api():
  try:
      url = request.args.get('url', 'No URL Provided')
      logging.info(f"Received request for URL: {url}")
      link_data = await fetch_download_link_async(url)
      if link_data:
          tasks = [format_message(item) for item in link_data]
          formatted_message = await asyncio.gather(*tasks)
        #   formatted_message = await format_message(link_data[0])
          logging.info(f"Formatted message: {formatted_message}")
      else:
          formatted_message = None
      response = { 'ShortLink': url, 'Extracted Info': formatted_message,'status': 'success'}
      return jsonify(response)
  except Exception as e:
      logging.error(f"An error occurred: {e}")
      return jsonify({'status': 'error', 'message': str(e), 'Link': url})

@app.route(rule='/help', methods=['GET'])
async def help():
    try:
        response = {'Info': "There is Only one Way to Use This as Show Below",
                    'Example': 'https://terabox-dl-orcin.vercel.app/api?url=https://terafileshare.com/s/1_1SzMvaPkqZ-yWokFCrKyA',
                    'Example2': 'https://terabox-dl-orcin.vercel.app/api2?url=https://terafileshare.com/s/1_1SzMvaPkqZ-yWokFCrKyA'}
        return jsonify(response)
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        response = {'Info': "There is Only one Way to Use This as Show Below",
                    'Example': 'https://terabox-dl-orcin.vercel.app/api?url=https://terafileshare.com/s/1_1SzMvaPkqZ-yWokFCrKyA',
                    'Example2': 'https://terabox-dl-orcin.vercel.app/api2?url=https://terafileshare.com/s/1_1SzMvaPkqZ-yWokFCrKyA'}
        return jsonify(response)




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


async def fetch_download_link_async2(url):
    try:
        async with aiohttp.ClientSession(cookies=cookies, headers=headers) as session:
            async with session.get(url) as response1:
                response1.raise_for_status()
                response_data = await response1.text()
                
                # Extract jsToken & logid
                js_token = find_between(response_data, 'fn%28%22', '%22%29')
                log_id = find_between(response_data, 'dp-logid=', '&')

                if not js_token or not log_id:
                    return None

                request_url = str(response1.url)
                print(request_url)
                surl = request_url.split('surl=')[1]
                print(surl)

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

                async with session.get('https://www.1024tera.com/share/list', params=params) as response2:
                    response_data2 = await response2.json()

                    if 'list' not in response_data2:
                        return None

                    files = response_data2['list']

                    # If it's a directory, fetch contents
                    if files[0]['isdir'] == "1":
                        params.update({
                            'dir': files[0]['path'],
                            'order': 'asc',
                            'by': 'name',
                            'dplogid': log_id
                        })
                        params.pop('desc')
                        params.pop('root')

                        async with session.get('https://www.1024tera.com/share/list', params=params) as response3:
                            response_data3 = await response3.json()
                            if 'list' not in response_data3:
                                return None
                            files = response_data3['list']

                    # Fetch direct download links for each file
                    file_data = []
                    for file in files:
                        async with session.head(file["dlink"], headers=headers) as direct_link_response:
                            direct_download_url = direct_link_response.headers.get("location")

                        file_info = {
                            "file_name": file.get("server_filename"),
                            "link": file.get("dlink"),
                            "dlink": direct_download_url,  # Extracted direct download link
                            "thumb": file.get("thumbs", {}).get("url3", "https://default_thumbnail.png"),
                            "size": await get_formatted_size_async(file.get("size", 0)),
                            "sizebytes": file.get("size", 0),
                        }
                        file_data.append(file_info)

                    return file_data

    except aiohttp.ClientResponseError as e:
        print(f"Error fetching download link: {e}")
        return None



@app.route(rule='/api2', methods=['GET'])
async def Api2():
    try:
        url = request.args.get('url', 'No URL Provided')
        logging.info(f"Received request for URL: {url}")

        link_data = await fetch_download_link_async2(url)

        if link_data:
            response = {'ShortLink': url, 'Extracted Files': link_data, 'status': 'success'}
        else:
            response = {'status': 'error', 'message': 'No files found', 'ShortLink': url}

        return jsonify(response)

    except Exception as e:
        logging.error(f"An error occurred: {e}")
        return jsonify({'status': 'error', 'message': str(e), 'Link': url})
