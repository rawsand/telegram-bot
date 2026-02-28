import dropbox
from dropbox.files import WriteMode

class DropboxHandler:
    def __init__(self, app_key, app_secret, refresh_token):
        self.app_key = app_key
        self.app_secret = app_secret
        self.refresh_token = refresh_token

    def get_client(self):
        return dropbox.Dropbox(
            oauth2_refresh_token=self.refresh_token,
            app_key=self.app_key,
            app_secret=self.app_secret
        )

    def upload_stream(self, file_stream, path, overwrite=False):
        dbx = self.get_client()

        mode = WriteMode.overwrite if overwrite else WriteMode.add

        dbx.files_upload(
            file_stream.read(),
            path,
            mode=mode
        )

        return True

    def generate_share_link(self, path):
        dbx = self.get_client()
        link = dbx.sharing_create_shared_link_with_settings(path)
        return link.url.replace("?dl=0", "?dl=1")
