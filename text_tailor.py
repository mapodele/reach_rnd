import textwrap
from PIL import Image, ImageDraw, ImageFont
import svgwrite
import os
import csv
import random
import requests
import tempfile
from IPython.display import display, Image as IPImage

def get_random_google_font():
    fonts = [
        ("Roboto", "https://fonts.gstatic.com/s/roboto/v27/KFOmCnqEu92Fr1Mu4mxK.ttf"),
        ("Open Sans", "https://fonts.gstatic.com/s/opensans/v18/mem8YaGs126MiZpBA-UFVZ0e.ttf"),
        ("Lato", "https://fonts.gstatic.com/s/lato/v17/S6uyw4BMUTPHjx4wWw.ttf"),
        ("Montserrat", "https://fonts.gstatic.com/s/montserrat/v15/JTUSjIg1_i6t8kCHKm459Wlhzg.ttf"),
        ("Raleway", "https://fonts.gstatic.com/s/raleway/v19/1Ptxg8zYS_SKggPN4iEgvnHyvveLxVvaorCIPrQ.ttf"),
        ("Poppins", "https://fonts.gstatic.com/s/poppins/v15/pxiEyp8kv8JHgFVrJJfedw.ttf"),
        ("Nunito", "https://fonts.gstatic.com/s/nunito/v16/XRXV3I6Li01BKofINeaE.ttf"),
        ("Playfair Display", "https://fonts.gstatic.com/s/playfairdisplay/v22/nuFvD-vYSZviVYUb_rj3ij__anPXJzDwcbmjWBN2PKdFvXDXbtY.ttf"),
        ("Merriweather", "https://fonts.gstatic.com/s/merriweather/v22/u-4n0qyriQwlOrhSvowK_l521wRZWMf_.ttf"),
        ("Source Sans Pro", "https://fonts.gstatic.com/s/sourcesanspro/v14/6xK3dSBYKcSV-LCoeQqfX1RYOo3qOK7g.ttf")
    ]
    return random.choice(fonts)

def download_google_font(font_url):
    font_response = requests.get(font_url)
    with tempfile.NamedTemporaryFile(delete=False, suffix='.ttf') as temp_font_file:
        temp_font_file.write(font_response.content)
        return temp_font_file.name

def get_random_copy(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        reader = csv.reader(file)
        lines = list(reader)
    random_line = random.choice(lines)
    return random_line[1] if len(random_line) > 1 else "Default Text"

def text_tailor(text, width, height, font_path, font_family, padding=10, output_svg='output.svg', output_png='output.png'):
    max_width = width - 2 * padding
    max_height = height - 2 * padding

    def try_layout(font_size, num_lines):
        font = ImageFont.truetype(font_path, font_size)
        words = text.split()
        lines = ['']
        for word in words:
            # Tentative line if the word is added
            tentative_line = lines[-1] + (' ' + word if lines[-1] else word)
            # Calculate the width using getlength
            line_width = font.getlength(tentative_line)
            if line_width <= max_width:
                lines[-1] = tentative_line
            elif len(lines) < num_lines:
                lines.append(word)
            else:
                return None
        ascent, descent = font.getmetrics()
        line_height = ascent + descent
        total_height = line_height * len(lines)
        return lines if total_height <= max_height else None

    # Find the maximum font size
    max_font_size = 1
    best_layout = None
    for num_lines in range(1, len(text.split()) + 1):
        low, high = 1, height
        while low <= high:
            mid = (low + high) // 2
            layout = try_layout(mid, num_lines)
            if layout:
                if mid > max_font_size:
                    max_font_size = mid
                    best_layout = layout
                low = mid + 1
            else:
                high = mid - 1

    if not best_layout:
        raise ValueError("Unable to fit text within the given dimensions")

    font = ImageFont.truetype(font_path, max_font_size)
    ascent, descent = font.getmetrics()
    line_height = ascent + descent

    # Create PNG image
    img = Image.new('RGB', (width, height), color='white')
    draw = ImageDraw.Draw(img)

    total_height = line_height * len(best_layout)
    y_start = (height - total_height) / 2

    y = y_start
    for line in best_layout:
        line_width = font.getlength(line)
        x = (width - line_width) / 2

        draw.text((x, y), line, font=font, fill='black')
        y += line_height

    img.save(output_png)

    # Create SVG
    dwg = svgwrite.Drawing(output_svg, size=(width, height))
    y = y_start + ascent  # Adjust for baseline in SVG
    for line in best_layout:
        line_width = font.getlength(line)
        x = (width - line_width) / 2

        # SVG text alignment is based on the baseline, so we add ascent to y
        dwg.add(dwg.text(line, insert=(x, y), font_family=font_family, font_size=max_font_size, fill='black'))
        y += line_height
    dwg.save()

    # Print metadata
    print(f"Files created: {output_svg} and {output_png}")
    print(f"Bounding box dimensions: {width}x{height}")
    print(f"Font used: {font_family}")
    print(f"Font size used: {max_font_size}")
    print(f"Text used: {text}")

    # Display the PNG
    display(IPImage(filename=output_png))

# Example usage
if __name__ == "__main__":
    font_family, font_url = get_random_google_font()
    font_path = download_google_font(font_url)

    # Replace with your actual CSV file path
    csv_file_path = 'crew_io_files/ad_copy_persona_1.csv'
    random_text = get_random_copy(csv_file_path)

    try:
        text_tailor(random_text, 300, 200, font_path, font_family)
    finally:
        os.unlink(font_path)
