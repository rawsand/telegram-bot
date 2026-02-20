<?php
require_once "drive_config.php";

function uploadToDrive($fileUrl, $fileName) {

    $accessToken = getAccessToken();
    if (!$accessToken) {
        error_log("No access token!");
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
        error_log("Cannot get file size: $fileUrl");
        return false;
    }

    error_log("File size: $totalSize");

    // STEP 2 — Start resumable session
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
        error_log("Resumable session start failed: ".curl_error($ch));
        curl_close($ch);
        return false;
    }

    $headerSize = curl_getinfo($ch, CURLINFO_HEADER_SIZE);
    $headers = substr($response, 0, $headerSize);
    $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);

    error_log("Resumable session HTTP code: $httpCode");

    if (!preg_match('/Location:\s*(.*)/i', $headers, $matches)) {
        error_log("No Location header returned");
        return false;
    }

    $uploadUrl = trim($matches[1]);
    error_log("Upload URL: $uploadUrl");

    if (!$uploadUrl) return false;

    // STEP 3 — Upload in chunks
    $chunkSize = 8*1024*1024; // 8MB
    $offset = 0;

    while ($offset < $totalSize) {
        $rangeEnd = min($offset+$chunkSize-1, $totalSize-1);

        // Download chunk
        $ch = curl_init($fileUrl);
        curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
        curl_setopt($ch, CURLOPT_HTTPHEADER, ["Range: bytes=$offset-$rangeEnd"]);
        $chunkData = curl_exec($ch);
        $downloadHttp = curl_getinfo($ch, CURLINFO_HTTP_CODE);
        curl_close($ch);

        if ($chunkData === false || $downloadHttp >= 400) {
            error_log("Failed to download chunk $offset-$rangeEnd, HTTP $downloadHttp");
            return false;
        }

        $chunkLength = strlen($chunkData);

        // Upload chunk
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

        error_log("Uploaded bytes $offset-$rangeEnd, HTTP $httpCode");

        if ($httpCode != 308 && $httpCode != 200 && $httpCode != 201) {
            error_log("Drive upload failed at bytes $offset-$rangeEnd");
            return false;
        }

        $offset += $chunkLength;
    }

    error_log("Upload complete: $fileName");
    return true;
}
?>
