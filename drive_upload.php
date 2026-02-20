<?php
require_once "drive_config.php";

function uploadToDrive($fileUrl, $fileName) {

    $accessToken = getAccessToken();
    if (!$accessToken) return false;

    $folderId = getenv("GOOGLE_DRIVE_FOLDER_ID");

    /* ===============================
       STEP 1 — Get File Size
    =============================== */

    $ch = curl_init($fileUrl);
    curl_setopt($ch, CURLOPT_NOBODY, true);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_exec($ch);

    $totalSize = curl_getinfo($ch, CURLINFO_CONTENT_LENGTH_DOWNLOAD);
    curl_close($ch);

    if ($totalSize <= 0) {
        return false;
    }

    /* ===============================
       STEP 2 — Start Resumable Session
    =============================== */

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
        "Content-Type: application/json; charset=UTF-8",
        "X-Upload-Content-Length: $totalSize"
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

    if (!preg_match('/Location:\s*(.*)/i', $headers, $matches)) {
        return false;
    }

    $uploadUrl = trim($matches[1]);

    if (!$uploadUrl) return false;

    /* ===============================
       STEP 3 — Upload in Chunks
    =============================== */

    $chunkSize = 8 * 1024 * 1024; // 8MB
    $offset = 0;

    while ($offset < $totalSize) {

        $rangeEnd = min($offset + $chunkSize - 1, $totalSize - 1);

        // Download chunk from source
        $ch = curl_init($fileUrl);
        curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
        curl_setopt($ch, CURLOPT_HTTPHEADER, [
            "Range: bytes=$offset-$rangeEnd"
        ]);

        $chunkData = curl_exec($ch);
        curl_close($ch);

        if ($chunkData === false) {
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
        curl_setopt($ch, CURLOPT_POSTFIELDS, $chunkData);

        curl_exec($ch);
        $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
        curl_close($ch);

        if ($httpCode != 308 && $httpCode != 200 && $httpCode != 201) {
            return false;
        }

        $offset += $chunkLength;
    }

    return true;
}
?>
