import re

def extract_link_from_formatted_message(text):
    filename_match = re.search(r'Fɪʟᴇ ɴᴀᴍᴇ\s*:\s*(.+)', text)
    if not filename_match:
        return None, None

    filename = filename_match.group(1).strip().lower()

    detected_show = None

    if "master" in filename and "chef" in filename:
        detected_show = "MC"
    elif "laughter" in filename and "chef" in filename:
        detected_show = "LC"
    elif "wheel" in filename and "fortune" in filename:
        detected_show = "WOF"

    if not detected_show:
        return None, None

    link_match = re.search(r'(https?://[^\s]+)', text)
    if not link_match:
        return None, None

    return link_match.group(1), detected_show
