import requests
import dropbox
from dropbox.files import WriteMode
from dropbox.exceptions import ApiError


class DropboxHandler:
    def __init__(self, app_key, app_secret, refresh_token):
        self.app_key = app_key
        self.app_secret = app_secret
        self.refresh_token = refresh_token

    def get_access_token(self):
        url = "https://api.dropboxapi.com/oauth2/token"
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "client_id": self.app_key,
            "client_secret": self.app_secret,
        }

        response = requests.post(url, data=data)
        response.raise_for_status()
        return response.json()["access_token"]

    def upload_file(self, file_bytes, dropbox_path):
        access_token = self.get_access_token()
        dbx = dropbox.Dropbox(access_token)

        try:
            dbx.files_upload(
                file_bytes,
                dropbox_path,
                mode=WriteMode("overwrite")
            )
            return True
        except ApiError as e:
            print("Upload failed:", e)
            return False

    def generate_share_link(self, dropbox_path):
        access_token = self.get_access_token()
        dbx = dropbox.Dropbox(access_token)

        try:
            link = dbx.sharing_create_shared_link_with_settings(dropbox_path)
            return link.url.replace("?dl=0", "?raw=1")
        except ApiError:
            links = dbx.sharing_list_shared_links(path=dropbox_path)
            if links.links:
                return links.links[0].url.replace("?dl=0", "?raw=1")
            return None
