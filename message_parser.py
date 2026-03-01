import re

def extract_link_from_formatted_message(text):
    """
    Extracts download link only if filename matches:
    - master + chef
    - laughter + chef
    - wheel + fortune
    """

    # Extract filename
    filename_match = re.search(r'Fɪʟᴇ ɴᴀᴍᴇ\s*:\s*(.+)', text)
    if not filename_match:
        return None

    filename = filename_match.group(1).strip().lower()

    # Check required word combinations
    valid = False

    if "master" in filename and "chef" in filename:
        valid = True
    elif "laughter" in filename and "chef" in filename:
        valid = True
    elif "wheel" in filename and "fortune" in filename:
        valid = True

    if not valid:
        return None

    # Extract download link
    link_match = re.search(r'(https?://[^\s]+)', text)
    if not link_match:
        return None

    return link_match.group(1)
