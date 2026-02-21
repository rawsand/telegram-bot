<?php

function base64url_encode($data) {
    return rtrim(strtr(base64_encode($data), '+/', '-_'), '=');
}

function debugMessage($chat_id, $text) {
    $botToken = getenv("BOT_TOKEN");
    $url = "https://api.telegram.org/bot$botToken/sendMessage";

    $data = [
        "chat_id" => $chat_id,
        "text" => "🔎 DEBUG:\n" . $text
    ];

    file_get_contents($url . "?" . http_build_query($data));
}

function getAccessToken() {

    $clientEmail = getenv("GOOGLE_CLIENT_EMAIL");
    $privateKeyRaw = getenv("GOOGLE_PRIVATE_KEY");

    // Rebuild private key properly
    $privateKey = "-----BEGIN PRIVATE KEY-----\n" .
        chunk_split(
            str_replace(
                ["-----BEGIN PRIVATE KEY-----", "-----END PRIVATE KEY-----", "\n", "\r", " "],
                "",
                $privateKeyRaw
            ),
            64,
            "\n"
        ) .
        "-----END PRIVATE KEY-----\n";

    $header = rtrim(strtr(base64_encode(json_encode([
        "alg"=>"RS256",
        "typ"=>"JWT"
    ])), '+/', '-_'), '=');

    $now = time();

    $claim = rtrim(strtr(base64_encode(json_encode([
        "iss"=>$clientEmail,
        "scope"=>"https://www.googleapis.com/auth/drive",
        "aud"=>"https://oauth2.googleapis.com/token",
        "exp"=>$now+3600,
        "iat"=>$now
    ])), '+/', '-_'), '=');

    $signatureInput = "$header.$claim";

    if (!openssl_sign($signatureInput, $signature, $privateKey, "SHA256")) {
        return false;
    }

    $jwt = "$header.$claim." .
        rtrim(strtr(base64_encode($signature), '+/', '-_'), '=');

    $ch = curl_init("https://oauth2.googleapis.com/token");
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_POST, true);
    curl_setopt($ch, CURLOPT_POSTFIELDS, http_build_query([
        "grant_type"=>"urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion"=>$jwt
    ]));
    $response = json_decode(curl_exec($ch), true);
    curl_close($ch);

    return $response["access_token"] ?? false;
}

function uploadToDriveResumable($fileUrl, $fileName, $chat_id) {

    debugMessage($chat_id, "Starting upload process");

    $accessToken = getAccessToken();

    if (!$accessToken) {
        debugMessage($chat_id, "❌ Access token generation FAILED");
        return false;
    }

    debugMessage($chat_id, "✅ Access token received");

    $folderId = getenv("GOOGLE_DRIVE_FOLDER_ID");

    $headers = @get_headers($fileUrl, 1);
    if (!$headers || !isset($headers["Content-Length"])) {
        debugMessage($chat_id, "❌ Could not get Content-Length from URL");
        return false;
    }

    $fileSize = (int)$headers["Content-Length"];
    debugMessage($chat_id, "File size detected: " . $fileSize);

    // Step 1: Create resumable session
    $metadata = json_encode([
        "name"=>$fileName,
        "parents"=>[$folderId]
    ]);

    $ch = curl_init("https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable");
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_POST, true);
    curl_setopt($ch, CURLOPT_HEADER, true);
    curl_setopt($ch, CURLOPT_HTTPHEADER, [
        "Authorization: Bearer $accessToken",
        "Content-Type: application/json; charset=UTF-8",
        "X-Upload-Content-Type: application/octet-stream",
        "X-Upload-Content-Length: $fileSize"
    ]);
    curl_setopt($ch, CURLOPT_POSTFIELDS, $metadata);

    $response = curl_exec($ch);
    $status = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    $headerSize = curl_getinfo($ch, CURLINFO_HEADER_SIZE);
    $headersRaw = substr($response, 0, $headerSize);
    curl_close($ch);

    if ($status != 200) {
        debugMessage($chat_id, "❌ Failed to create resumable session. HTTP: $status");
        return false;
    }

    debugMessage($chat_id, "✅ Resumable session created");

    preg_match('/Location: (.*)/', $headersRaw, $matches);
    if (!isset($matches[1])) {
        debugMessage($chat_id, "❌ Upload URL not found in response headers");
        return false;
    }

    $uploadUrl = trim($matches[1]);
    debugMessage($chat_id, "Upload URL obtained");

    $fileHandle = @fopen($fileUrl, "rb");
    if (!$fileHandle) {
        debugMessage($chat_id, "❌ fopen failed on file URL");
        return false;
    }

    debugMessage($chat_id, "Streaming started");

    $chunkSize = 5 * 1024 * 1024;
    $offset = 0;

    while ($offset < $fileSize) {

        $chunk = fread($fileHandle, $chunkSize);
        $chunkLength = strlen($chunk);

        $start = $offset;
        $end = $offset + $chunkLength - 1;

        $ch = curl_init($uploadUrl);
        curl_setopt($ch, CURLOPT_CUSTOMREQUEST, "PUT");
        curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
        curl_setopt($ch, CURLOPT_HEADER, true);
        curl_setopt($ch, CURLOPT_HTTPHEADER, [
            "Authorization: Bearer $accessToken",
            "Content-Length: $chunkLength",
            "Content-Range: bytes $start-$end/$fileSize"
        ]);
        curl_setopt($ch, CURLOPT_POSTFIELDS, $chunk);

        $response = curl_exec($ch);
        $status = curl_getinfo($ch, CURLINFO_HTTP_CODE);
        curl_close($ch);

        debugMessage($chat_id, "Chunk uploaded. HTTP: $status Offset: $offset");

        if ($status == 308) {
            $offset += $chunkLength;
        }
        elseif ($status == 200 || $status == 201) {
            $uploadResponse = json_decode(substr($response, curl_getinfo($ch, CURLINFO_HEADER_SIZE)), true);
            break;
        }
        else {
            debugMessage($chat_id, "❌ Upload failed at chunk level. HTTP: $status");
            fclose($fileHandle);
            return false;
        }
    }

    fclose($fileHandle);

    if (!isset($uploadResponse["id"])) {
        debugMessage($chat_id, "❌ File ID not returned");
        return false;
    }

    $fileId = $uploadResponse["id"];
    debugMessage($chat_id, "✅ Upload completed. File ID: $fileId");

    return "https://drive.google.com/file/d/$fileId/view";
}
?>
