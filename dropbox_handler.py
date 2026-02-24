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

    def upload_stream(self, file_stream, path, progress_callback=None):
        """
        Uploads a stream to Dropbox in chunks.
        Calls progress_callback(percent) if provided.
        """
        try:
            CHUNK_SIZE = 8 * 1024 * 1024  # 8MB
            dbx = self.get_client()

            first_chunk = file_stream.read(CHUNK_SIZE)
            if not first_chunk:
                return False

            # Start upload session
            session_start = dbx.files_upload_session_start(first_chunk)
            uploaded_bytes = len(first_chunk)

            cursor = UploadSessionCursor(session_start.session_id, uploaded_bytes)
            commit = CommitInfo(path=path, mode=WriteMode("overwrite"))

            # Try to get total size for progress
            try:
                current_pos = file_stream.tell()
                file_stream.seek(0, 2)  # Seek to end
                total_size = file_stream.tell()
                file_stream.seek(current_pos)
            except Exception:
                total_size = None

            next_percent = 0

            while True:
                chunk = file_stream.read(CHUNK_SIZE)
                if not chunk:
                    break

                dbx.files_upload_session_append_v2(chunk, cursor)
                uploaded_bytes += len(chunk)
                cursor.offset = uploaded_bytes

                if total_size and progress_callback:
                    percent = int(uploaded_bytes / total_size * 100)
                    if percent >= next_percent:
                        progress_callback(percent)
                        next_percent += 20 if total_size >= 700 * 1024 * 1024 else 50

            # Finish session
            dbx.files_upload_session_finish(b"", cursor, commit)
            return True

        except Exception as e:
            print("Upload error:", e)
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
