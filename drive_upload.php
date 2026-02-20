<?php
require_once "drive_config.php";
require_once "functions.php"; // for sendMessage function

/**
 * Upload a file from a URL to Google Drive in chunks, with live Telegram debugging.
 *
 * @param string $fileUrl - The URL of the source file to upload
 * @param string $fileName - The target file name on Drive
 * @param int $chat_id - Telegram chat_id to send debug messages
 * @return bool - true if upload completed, false if failed
 */
function uploadToDrive($fileUrl, $fileName, $chat_id) {

    $accessToken = getAccessToken();
    if (!$accessToken) {
        sendMessage($chat_id, "❌ No access token available!");
        return false;
    }

    $folderId = getenv("GOOGLE_DRIVE_FOLDER_ID");

    // STEP 1 — Get file size
    $ch = curl_init($fileUrl);
    curl_setopt($ch, CURLOPT_NOBODY, true);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_exec($ch);
    $totalSize = curl_getinfo($ch, CURLINFO_CONTENT_LENGTH_DOWNLOAD);
    curl_close($ch);

    if ($totalSize <= 0) {
        sendMessage($chat_id, "❌ Cannot get file size for URL: $fileUrl");
        return false;
    }

    sendMessage($chat_id, "ℹ File size: $totalSize bytes");

    // STEP 2 — Start Resumable Upload Session
    $metadata = ["name"=>$fileName, "parents"=>[$folderId]];

    $ch = curl_init("https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable");
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_POST, true);
    curl_setopt($ch, CURLOPT_HEADER, true);
    curl_setopt($ch, CURLOPT_HTTPHEADER, [
        "Authorization: Bearer $accessToken",
        "Content-Type: application/json; charset=UTF-8",
        "X-Upload-Content-Length: $totalSize"
    ]);
    curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($metadata));

    $response = curl_exec($ch);
    if ($response === false) {
        sendMessage($chat_id, "❌ Resumable session start failed: " . curl_error($ch));
        curl_close($ch);
        return false;
    }

    $headerSize = curl_getinfo($ch, CURLINFO_HEADER_SIZE);
    $headers = substr($response, 0, $headerSize);
    $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);

    sendMessage($chat_id, "ℹ Resumable session HTTP code: $httpCode");

    if (!preg_match('/Location:\s*(.*)/i', $headers, $matches)) {
        sendMessage($chat_id, "❌ No upload URL returned by Google Drive!");
        return false;
    }

    $uploadUrl = trim($matches[1]);
    sendMessage($chat_id, "ℹ Upload URL received.");

    if (!$uploadUrl) return false;

    // STEP 3 — Upload in chunks
    $chunkSize = 8*1024*1024; // 8MB
    $offset = 0;

    while ($offset < $totalSize) {
        $rangeEnd = min($offset+$chunkSize-1, $totalSize-1);

        // Download chunk from source
        $ch = curl_init($fileUrl);
        curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
        curl_setopt($ch, CURLOPT_HTTPHEADER, ["Range: bytes=$offset-$rangeEnd"]);
        $chunkData = curl_exec($ch);
        $downloadHttp = curl_getinfo($ch, CURLINFO_HTTP_CODE);
        curl_close($ch);

        if ($chunkData === false || $downloadHttp >= 400) {
            sendMessage($chat_id, "❌ Failed to download chunk $offset-$rangeEnd, HTTP $downloadHttp");
            return false;
        }

        $chunkLength = strlen($chunkData);

        // Upload chunk to Drive
        $ch = curl_init($uploadUrl);
        curl_setopt($ch, CURLOPT_CUSTOMREQUEST, "PUT");
        curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
        curl_setopt($ch, CURLOPT_HTTPHEADER, [
            "Authorization: Bearer $accessToken",
            "Content-Length: $chunkLength",
            "Content-Range: bytes $offset-$rangeEnd/$totalSize"
        ]);
        $uploadResponse = curl_exec($ch);
        $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
        curl_close($ch);

        sendMessage($chat_id, "ℹ Uploaded bytes $offset-$rangeEnd, HTTP $httpCode");

        if ($httpCode != 308 && $httpCode != 200 && $httpCode != 201) {
            sendMessage($chat_id, "❌ Google Drive upload failed at bytes $offset-$rangeEnd");
            return false;
        }

        $offset += $chunkLength;
    }

    sendMessage($chat_id, "✅ Upload complete: $fileName");
    return true;
}
?>
