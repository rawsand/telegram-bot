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

    def upload_from_telegram_stream(
        self,
        telegram_response,
        total_size,
        path,
        progress_callback=None,
    ):
        try:
            dbx = self.get_client()
            CHUNK_SIZE = 8 * 1024 * 1024  # 8MB

            uploaded = 0

            # Start session
            first_chunk = next(
                telegram_response.iter_content(CHUNK_SIZE)
            )

            session_start = dbx.files_upload_session_start(first_chunk)
            uploaded += len(first_chunk)

            if progress_callback:
                progress_callback(uploaded, total_size)

            cursor = UploadSessionCursor(
                session_id=session_start.session_id,
                offset=uploaded,
            )

            commit = CommitInfo(
                path=path,
                mode=WriteMode("overwrite"),
            )

            # Append chunks
            for chunk in telegram_response.iter_content(CHUNK_SIZE):
                if not chunk:
                    break

                dbx.files_upload_session_append_v2(chunk, cursor)
                uploaded += len(chunk)
                cursor.offset = uploaded

                if progress_callback:
                    progress_callback(uploaded, total_size)

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
