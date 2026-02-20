<?php
require_once "drive_config.php";

function uploadToDrive($fileUrl, $fileName) {

    $accessToken = getAccessToken();
    if (!$accessToken) return false;

    $folderId = getenv("GOOGLE_DRIVE_FOLDER_ID");

    // Step 1: Start resumable session
    $metadata = [
        "name" => $fileName,
        "parents" => [$folderId]
    ];

    $ch = curl_init("https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable");
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_POST, true);
    curl_setopt($ch, CURLOPT_HTTPHEADER, [
        "Authorization: Bearer $accessToken",
        "Content-Type: application/json; charset=UTF-8"
    ]);
    curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($metadata));

    $response = curl_exec($ch);
    $uploadUrl = curl_getinfo($ch, CURLINFO_REDIRECT_URL);

    if (!$uploadUrl) {
        $headers = curl_getinfo($ch);
        $uploadUrl = $headers["redirect_url"] ?? null;
    }

    curl_close($ch);

    if (!$uploadUrl) return false;

    // Step 2: Stream download + upload
    $chunkSize = 8 * 1024 * 1024; // 8MB

    $fp = fopen($fileUrl, "rb");
    if (!$fp) return false;

    $offset = 0;

    while (!feof($fp)) {

        $chunk = fread($fp, $chunkSize);
        $length = strlen($chunk);

        $ch = curl_init($uploadUrl);
        curl_setopt($ch, CURLOPT_CUSTOMREQUEST, "PUT");
        curl_setopt($ch, CURLOPT_HTTPHEADER, [
            "Authorization: Bearer $accessToken",
            "Content-Length: $length",
            "Content-Range: bytes $offset-" . ($offset + $length - 1) . "/*"
        ]);
        curl_setopt($ch, CURLOPT_POSTFIELDS, $chunk);
        curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);

        curl_exec($ch);
        curl_close($ch);

        $offset += $length;
    }

    fclose($fp);

    return true;
}
?>