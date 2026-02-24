import dropbox
from dropbox.files import WriteMode


class DropboxHandler:
    
    # inside DropboxHandler
    def dropbox_cursor(self, session_start_result, offset):
        from dropbox.files import UploadSessionCursor
        return UploadSessionCursor(session_start_result.session_id, offset)
    
    def dropbox_commit_info(self, path):
        from dropbox.files import CommitInfo, WriteMode
        return CommitInfo(path=path, mode=WriteMode("overwrite"))
        
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

    def upload_stream(self, file_stream, path):
        try:
            CHUNK_SIZE = 8 * 1024 * 1024  # 8MB
            dbx = self.get_client()

            upload_session_start_result = dbx.files_upload_session_start(
                file_stream.read(CHUNK_SIZE)
            )

            cursor = dropbox.files.UploadSessionCursor(
                session_id=upload_session_start_result.session_id,
                offset=file_stream.tell(),
            )

            commit = dropbox.files.CommitInfo(
                path=path,
                mode=WriteMode("overwrite"),
            )

            while True:
                chunk = file_stream.read(CHUNK_SIZE)
                if not chunk:
                    break

                dbx.files_upload_session_append_v2(chunk, cursor)
                cursor.offset = file_stream.tell()

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
