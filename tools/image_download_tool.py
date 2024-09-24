from crewai_tools import BaseTool
from pydantic import Field
from typing import Any, List, Dict
import os
import requests
import logging
from urllib.parse import urlparse, unquote
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from PIL import Image, ExifTags
from io import BytesIO
import csv
from datetime import datetime

class ImageDownloadTool(BaseTool):
    name: str = "ImageDownloadTool"
    description: str = "A tool to scrape, download, and analyze JPG or PNG images that are at least 500 pixels on any side from a website using Selenium."

    def __init__(self, **data):
        super().__init__(**data)

    def _run(self, website_url: str) -> Dict[str, Any]:
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        
        image_urls = []
        cookies = []
        download_dir = "crew_io_files/downloads"
        csv_file = "crew_io_files/images_metadata.csv"

        os.makedirs(download_dir, exist_ok=True)

        columns = [
            'filename', 'url', 'file_path', 'width', 'height', 'format', 'file_size', 'aspect_ratio', 
            'orientation', 'color_space', 'software_used', 'gps_coordinates', 'dpi', 'dominant_color', 
            'transparent', 'compression_type', 'date_of_creation'
        ]

        file_exists = os.path.isfile(csv_file)
        file_empty = file_exists and os.path.getsize(csv_file) == 0

        current_entries = 0
        if file_exists and not file_empty:
            with open(csv_file, 'r') as f:
                reader = csv.reader(f)
                current_entries = sum(1 for row in reader) - 1

        session = requests.Session()
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        session.headers.update(headers)

        try:
            driver.get(website_url)
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, 'img')))
            images = driver.find_elements(By.TAG_NAME, 'img')
            for img in images:
                src = img.get_attribute('src')
                if src and not src.endswith('.svg'):
                    image_urls.append(src)
            cookies = driver.get_cookies()
        except Exception as e:
            logging.error(f"Error scraping images: {e}")
        finally:
            driver.quit()

        for cookie in cookies:
            session.cookies.set(cookie['name'], cookie['value'])

        downloaded_images = 0

        for url in image_urls:
            parsed_url = urlparse(url)
            url_path = unquote(parsed_url.path.split('?')[0])
            if not url_path.lower().endswith(('.jpg', '.jpeg', '.png')):
                continue

            retry_count = 3
            for _ in range(retry_count):
                try:
                    response = session.get(url, allow_redirects=True)
                    if response.status_code == 200:
                        img = Image.open(BytesIO(response.content))
                        if img.format in ['JPEG', 'PNG']:
                            width, height = img.size
                            if width >= 500 or height >= 500:
                                file_extension = 'jpg' if img.format == 'JPEG' else 'png'
                                filename = os.path.basename(url_path).split('.')[0] + f'.{file_extension}'
                                file_path = os.path.join(download_dir, filename)
                                img.save(file_path, format=img.format)

                                file_size = os.path.getsize(file_path)
                                date_of_creation = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                aspect_ratio = round(width / height, 2)
                                orientation = "Landscape" if width >= height else "Portrait"

                                transparent = False
                                if img.format == 'PNG' and img.mode in ('RGBA', 'LA'):
                                    if 'transparency' in img.info or img.mode == 'RGBA':
                                        transparent = True

                                exif_data = img._getexif() if hasattr(img, '_getexif') else None
                                color_space = None
                                software_used = None
                                gps_coords = None
                                dpi = None
                                compression_type = 'Baseline'

                                if exif_data:
                                    for tag, value in exif_data.items():
                                        tag_name = ExifTags.TAGS.get(tag, tag)
                                        if tag_name == 'Software':
                                            software_used = value
                                        if tag_name == 'GPSInfo':
                                            gps_coords = value
                                        if tag_name == 'XResolution':
                                            dpi = value
                                        if tag_name == 'ColorSpace':
                                            color_space = value
                                        if tag_name == 'Compression':
                                            compression_type = 'Progressive' if value == 6 else 'Baseline'

                                dominant_color = self.get_dominant_color(img)

                                row_data = {
                                    'filename': filename,
                                    'url': url,
                                    'file_path': file_path,
                                    'width': width,
                                    'height': height,
                                    'format': img.format,
                                    'file_size': file_size,
                                    'aspect_ratio': aspect_ratio,
                                    'orientation': orientation,
                                    'color_space': color_space,
                                    'software_used': software_used,
                                    'gps_coordinates': gps_coords,
                                    'dpi': dpi,
                                    'dominant_color': dominant_color,
                                    'transparent': transparent,
                                    'compression_type': compression_type,
                                    'date_of_creation': date_of_creation
                                }

                                with open(csv_file, 'a', newline='') as f:
                                    writer = csv.DictWriter(f, fieldnames=columns)
                                    if not file_exists or file_empty:
                                        writer.writeheader()
                                        file_exists = True
                                        file_empty = False
                                    writer.writerow(row_data)

                                downloaded_images += 1
                                current_entries += 1

                            else:
                                logging.info(f"Skipped {url} (size: {width}x{height})")
                        else:
                            logging.info(f"Skipped {url} (format: {img.format})")
                        break
                    else:
                        logging.error(f"Failed to download image from {url}. Status code: {response.status_code}")
                except Exception as e:
                    logging.error(f"Error downloading {url}: {e}")

        at_least_15_images = (current_entries >= 15)

        return {
            'message': f"Downloaded {downloaded_images} JPG/PNG images (at least 500px on any side) from {website_url} into {download_dir}",
            'csv_file': csv_file,
            'total_images': current_entries,
            'at_least_15_images': at_least_15_images
        }

    @staticmethod
    def get_dominant_color(image: Image.Image) -> str:
        image = image.convert('RGB')
        colors = image.getcolors(image.size[0] * image.size[1])
        max_occurence, most_present = 0, 0
        try:
            for count, color in colors:
                if count > max_occurence:
                    max_occurence, most_present = count, color
            return '#{:02x}{:02x}{:02x}'.format(most_present[0], most_present[1], most_present[2])
        except TypeError:
            return None
