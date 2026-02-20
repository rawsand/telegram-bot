<?php
require_once "drive_config.php";
require_once "functions.php"; // for sendMessage()

/**
 * Upload a remote file to Google Drive in resumable chunks
 *
 * @param string $fileUrl  Remote file URL
 * @param string $fileName Name for the file in Drive
 * @param int    $chat_id  Telegram chat ID for debug messages
 * @return bool
 */
function uploadToDrive($fileUrl, $fileName, $chat_id = null) {

    $accessToken = getAccessToken();
    if (!$accessToken) {
        if ($chat_id) sendMessage($chat_id, "❌ No access token available!");
        return false;
    }

    $folderId = getenv("GOOGLE_DRIVE_FOLDER_ID");
    if (!$folderId) {
        if ($chat_id) sendMessage($chat_id, "❌ No Drive folder ID set!");
        return false;
    }

    // ===== Step 1: Start resumable session =====
    $metadata = [
        "name" => $fileName,
        "parents" => [$folderId]
    ];

    $ch = curl_init("https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable");
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_POST, true);
    curl_setopt($ch, CURLOPT_HEADER, true);
    curl_setopt($ch, CURLOPT_HTTPHEADER, [
        "Authorization: Bearer $accessToken",
        "Content-Type: application/json; charset=UTF-8"
    ]);
    curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($metadata));

    $response = curl_exec($ch);
    if ($response === false) {
        curl_close($ch);
        if ($chat_id) sendMessage($chat_id, "❌ Failed to start resumable session!");
        return false;
    }

    $headerSize = curl_getinfo($ch, CURLINFO_HEADER_SIZE);
    $headers = substr($response, 0, $headerSize);
    curl_close($ch);

    // Extract upload URL from Location header
    if (!preg_match('/Location:\s*(.*)/i', $headers, $matches)) {
        if ($chat_id) sendMessage($chat_id, "❌ No upload URL received!");
        return false;
    }

    $uploadUrl = trim($matches[1]);
    if ($chat_id) sendMessage($chat_id, "ℹ Upload URL received.");

    // ===== Step 2: Open remote file and detect size =====
    $fileStream = fopen($fileUrl, "rb");
    if (!$fileStream) {
        if ($chat_id) sendMessage($chat_id, "❌ Failed to open remote file!");
        return false;
    }

    // Seek to end to get total size
    fseek($fileStream, 0, SEEK_END);
    $totalSize = ftell($fileStream);
    rewind($fileStream);

    if ($chat_id) sendMessage($chat_id, "ℹ File size: $totalSize bytes");

    $chunkSize = 8 * 1024 * 1024; // 8 MB
    $offset = 0;

    // ===== Step 3: Upload in chunks =====
    while (!feof($fileStream)) {
        $chunk = fread($fileStream, $chunkSize);
        $chunkLength = strlen($chunk);
        if ($chunkLength === 0) break;

        $end = $offset + $chunkLength - 1;
        if ($end >= $totalSize) $end = $totalSize - 1;

        $ch = curl_init($uploadUrl);
        curl_setopt($ch, CURLOPT_CUSTOMREQUEST, "PUT");
        curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
        curl_setopt($ch, CURLOPT_HTTPHEADER, [
            "Authorization: Bearer $accessToken",
            "Content-Length: $chunkLength",
            "Content-Range: bytes $offset-$end/$totalSize"
        ]);
        curl_setopt($ch, CURLOPT_POSTFIELDS, $chunk);

        $uploadResponse = curl_exec($ch);
        $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
        curl_close($ch);

        if ($chat_id) sendMessage($chat_id, "ℹ Uploaded bytes $offset-$end, HTTP $httpCode");

        if (!in_array($httpCode, [308, 200, 201])) {
            fclose($fileStream);
            if ($chat_id) sendMessage($chat_id, "❌ Google Drive upload failed at bytes $offset-$end, HTTP $httpCode");
            return false;
        }

        $offset += $chunkLength;
    }

    fclose($fileStream);

    if ($chat_id) sendMessage($chat_id, "✅ Upload completed successfully!");

    return true;
}
?>
