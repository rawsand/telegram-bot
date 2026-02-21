<?php

function uploadToDriveResumable($downloadUrl, $fileName, $chat_id) {

    debugMessage($chat_id, "Starting upload process");

    debugMessage($chat_id, "Checking download headers");
    $headers = @get_headers($downloadUrl, 1);
    debugMessage($chat_id, print_r($headers, true));

    $fileData = @file_get_contents($downloadUrl);

    if (!$fileData) {
        debugMessage($chat_id, "Download failed");
        return false;
    }

    $fileSize = strlen($fileData);
    debugMessage($chat_id, "File size detected: " . $fileSize);

    $clientEmail = getenv("GOOGLE_CLIENT_EMAIL");
    $privateKey = getenv("GOOGLE_PRIVATE_KEY");
    $folderId = getenv("GOOGLE_DRIVE_FOLDER_ID");

    $privateKey = str_replace("\\n", "\n", $privateKey);

    $now = time();
    $expiry = $now + 3600;

    $header = rtrim(strtr(base64_encode(json_encode([
        "alg" => "RS256",
        "typ" => "JWT"
    ])), '+/', '-_'), '=');

    $claim = rtrim(strtr(base64_encode(json_encode([
        "iss" => $clientEmail,
        "scope" => "https://www.googleapis.com/auth/drive.file",
        "aud" => "https://oauth2.googleapis.com/token",
        "exp" => $expiry,
        "iat" => $now
    ])), '+/', '-_'), '=');

    openssl_sign("$header.$claim", $signature, $privateKey, OPENSSL_ALGO_SHA256);
    $signature = rtrim(strtr(base64_encode($signature), '+/', '-_'), '=');

    $jwt = "$header.$claim.$signature";

    $ch = curl_init("https://oauth2.googleapis.com/token");
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_POSTFIELDS, http_build_query([
        "grant_type" => "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion" => $jwt
    ]));

    $tokenResponse = json_decode(curl_exec($ch), true);
    curl_close($ch);

    if (!isset($tokenResponse["access_token"])) {
        debugMessage($chat_id, "Access token failed");
        debugMessage($chat_id, print_r($tokenResponse, true));
        return false;
    }

    $accessToken = $tokenResponse["access_token"];
    debugMessage($chat_id, "Access token received");

    $metadata = json_encode([
        "name" => $fileName,
        "parents" => [$folderId]
    ]);

    $ch = curl_init("https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable");
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_HEADER, true);
    curl_setopt($ch, CURLOPT_POST, true);
    curl_setopt($ch, CURLOPT_HTTPHEADER, [
        "Authorization: Bearer $accessToken",
        "Content-Type: application/json; charset=UTF-8",
        "X-Upload-Content-Type: application/octet-stream",
        "X-Upload-Content-Length: $fileSize"
    ]);
    curl_setopt($ch, CURLOPT_POSTFIELDS, $metadata);

    $response = curl_exec($ch);
    $headerSize = curl_getinfo($ch, CURLINFO_HEADER_SIZE);
    $responseHeaders = substr($response, 0, $headerSize);
    curl_close($ch);

    debugMessage($chat_id, "Resumable session headers:");
    debugMessage($chat_id, $responseHeaders);

    if (!preg_match('/Location:\s*(.*)/i', $responseHeaders, $matches)) {
        debugMessage($chat_id, "Upload URL not found");
        return false;
    }

    $uploadUrl = trim($matches[1]);
    debugMessage($chat_id, "Resumable upload URL acquired");

    $ch = curl_init($uploadUrl);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_CUSTOMREQUEST, "PUT");
    curl_setopt($ch, CURLOPT_HTTPHEADER, [
        "Content-Length: $fileSize",
        "Content-Type: application/octet-stream"
    ]);
    curl_setopt($ch, CURLOPT_POSTFIELDS, $fileData);

    $uploadResponse = curl_exec($ch);
    $uploadStatus = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);

    debugMessage($chat_id, "Upload HTTP status: " . $uploadStatus);

    if ($uploadStatus == 200 || $uploadStatus == 201) {
        debugMessage($chat_id, "Upload successful");
        return true;
    }

    debugMessage($chat_id, "Upload failed response:");
    debugMessage($chat_id, $uploadResponse);

    return false;
}
?>
