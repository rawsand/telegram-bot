import dropbox
from dropbox.files import WriteMode, UploadSessionCursor, CommitInfo

class DropboxHandler:

    def __init__(self, app_key, app_secret, refresh_token):
        self.app_key = app_key
        self.app_secret = app_secret
        self.refresh_token = refresh_token

    def get_client(self):
        return dropbox.Dropbox(
            oauth2_refresh_token=self.refresh_token,
            app_key=self.app_key,
            app_secret=self.app_secret,
        )

    def upload_stream(self, file_stream, path, total_size=None, progress_callback=None):
        try:
            CHUNK_SIZE = 8 * 1024 * 1024
            dbx = self.get_client()

            first_chunk = file_stream.read(CHUNK_SIZE)
            if not first_chunk:
                return False

            session = dbx.files_upload_session_start(first_chunk)
            uploaded = len(first_chunk)

            if progress_callback:
                progress_callback(uploaded)

            cursor = UploadSessionCursor(session.session_id, uploaded)
            commit = CommitInfo(path=path, mode=WriteMode("overwrite"))

            while True:
                chunk = file_stream.read(CHUNK_SIZE)
                if not chunk:
                    break

                dbx.files_upload_session_append_v2(chunk, cursor)
                uploaded += len(chunk)
                cursor.offset = uploaded

                if progress_callback:
                    progress_callback(uploaded)

            dbx.files_upload_session_finish(b"", cursor, commit)
            return True

        except Exception as e:
            print("Dropbox upload error:", e)
            return False

    def generate_share_link(self, path):
        dbx = self.get_client()
        try:
            link = dbx.sharing_create_shared_link_with_settings(path)
            return link.url.replace("?dl=0", "?dl=1")
        except:
            links = dbx.sharing_list_shared_links(path=path).links
            if links:
                return links[0].url.replace("?dl=0", "?dl=1")
            return None
