<?php
require_once "drive_config.php";
require_once "functions.php";

function uploadToDrive($fileUrl, $fileName, $chat_id = null) {

    $accessToken = getAccessToken();
    if (!$accessToken) {
        if ($chat_id) sendMessage($chat_id, "❌ No access token available!");
        return false;
    }

    $folderId = getenv("GOOGLE_DRIVE_FOLDER_ID");
    if (!$folderId) {
        if ($chat_id) sendMessage($chat_id, "❌ Drive folder ID missing!");
        return false;
    }

    /* ==============================
       STEP 1 — Download to temp file
       ============================== */

    $tempPath = "/tmp/" . uniqid() . "_" . $fileName;

    if ($chat_id) sendMessage($chat_id, "⬇ Downloading file...");

    $fp = fopen($tempPath, "w");
    $ch = curl_init($fileUrl);
    curl_setopt($ch, CURLOPT_FILE, $fp);
    curl_setopt($ch, CURLOPT_FOLLOWLOCATION, true);
    curl_exec($ch);

    if (curl_errno($ch)) {
        fclose($fp);
        curl_close($ch);
        if ($chat_id) sendMessage($chat_id, "❌ Download failed!");
        return false;
    }

    curl_close($ch);
    fclose($fp);

    $totalSize = filesize($tempPath);

    if ($chat_id) sendMessage($chat_id, "ℹ File size: $totalSize bytes");

    if ($totalSize <= 0) {
        unlink($tempPath);
        if ($chat_id) sendMessage($chat_id, "❌ Downloaded file is empty!");
        return false;
    }

    /* ==============================
       STEP 2 — Start resumable session
       ============================== */

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
    $headerSize = curl_getinfo($ch, CURLINFO_HEADER_SIZE);
    $headers = substr($response, 0, $headerSize);
    curl_close($ch);

    if (!preg_match('/Location:\s*(.*)/i', $headers, $matches)) {
        unlink($tempPath);
        if ($chat_id) sendMessage($chat_id, "❌ Failed to get upload URL!");
        return false;
    }

    $uploadUrl = trim($matches[1]);

    if ($chat_id) sendMessage($chat_id, "🚀 Upload started...");

    /* ==============================
       STEP 3 — Upload in chunks
       ============================== */

    $chunkSize = 8 * 1024 * 1024; // 8MB
    $offset = 0;

    $fileStream = fopen($tempPath, "rb");

    while (!feof($fileStream)) {

        $chunk = fread($fileStream, $chunkSize);
        $chunkLength = strlen($chunk);
        if ($chunkLength == 0) break;

        $end = $offset + $chunkLength - 1;

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

        if ($chat_id) sendMessage($chat_id, "📤 Uploaded $offset-$end (HTTP $httpCode)");

        if (!in_array($httpCode, [308, 200, 201])) {
            fclose($fileStream);
            unlink($tempPath);
            if ($chat_id) sendMessage($chat_id, "❌ Upload failed!");
            return false;
        }

        $offset += $chunkLength;
    }

    fclose($fileStream);
    unlink($tempPath);

    if ($chat_id) sendMessage($chat_id, "✅ Upload completed successfully!");

    return true;
}
?>
