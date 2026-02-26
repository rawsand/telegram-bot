import re

def extract_filename_and_url(text):
    # Extract first .mp4 filename
    filename_match = re.search(r'([A-Za-z0-9_\-\.]+\.mp4)', text, re.IGNORECASE)

    # Extract first http/https link
    url_match = re.search(r'(https?://[^\s]+)', text)

    if not filename_match or not url_match:
        return None, None

    filename = filename_match.group(1).strip()
    url = url_match.group(1).strip()

    return filename, url
