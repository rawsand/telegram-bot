<?php
require_once "drive_config.php";

function uploadToDrive($fileUrl, $fileName) {

    $accessToken = getAccessToken();
    if (!$accessToken) {
        return false;
    }

    $folderId = getenv("GOOGLE_DRIVE_FOLDER_ID");

    /* =========================================
       STEP 1 — START RESUMABLE SESSION
       ========================================= */

    $metadata = [
        "name" => $fileName,
        "parents" => [$folderId]
    ];

    $ch = curl_init("https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable");

    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_POST, true);
    curl_setopt($ch, CURLOPT_HEADER, true); // IMPORTANT
    curl_setopt($ch, CURLOPT_HTTPHEADER, [
        "Authorization: Bearer $accessToken",
        "Content-Type: application/json; charset=UTF-8"
    ]);
    curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($metadata));

    $response = curl_exec($ch);

    if ($response === false) {
        curl_close($ch);
        return false;
    }

    $headerSize = curl_getinfo($ch, CURLINFO_HEADER_SIZE);
    $headers = substr($response, 0, $headerSize);

    curl_close($ch);

    // Extract upload URL from Location header
    if (!preg_match('/Location:\s*(.*)/i', $headers, $matches)) {
        return false;
    }

    $uploadUrl = trim($matches[1]);

    if (!$uploadUrl) {
        return false;
    }

    /* =========================================
       STEP 2 — STREAM DOWNLOAD + UPLOAD
       ========================================= */

    $chunkSize = 8 * 1024 * 1024; // 8MB
    $offset = 0;

    // Get file size (important for proper Content-Range)
    $headers = get_headers($fileUrl, 1);
    $totalSize = isset($headers["Content-Length"]) ? (int)$headers["Content-Length"] : null;

    if (!$totalSize) {
        return false;
    }

    $fileStream = fopen($fileUrl, "rb");
    if (!$fileStream) {
        return false;
    }

    while (!feof($fileStream)) {

        $chunk = fread($fileStream, $chunkSize);
        $chunkLength = strlen($chunk);

        if ($chunkLength == 0) {
            break;
        }

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

        // Google returns 308 until final chunk
        if ($httpCode != 308 && $httpCode != 200 && $httpCode != 201) {
            fclose($fileStream);
            return false;
        }

        $offset += $chunkLength;
    }

    fclose($fileStream);

    return true;
}
?>
