<?php

function base64url_encode($data) {
    return rtrim(strtr(base64_encode($data), '+/', '-_'), '=');
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

function uploadToDriveResumable($fileUrl, $fileName) {

    $accessToken = getAccessToken();
    if (!$accessToken) return false;

    $folderId = getenv("GOOGLE_DRIVE_FOLDER_ID");

    // Get file size
    $headers = get_headers($fileUrl, 1);
    if (!isset($headers["Content-Length"])) return false;
    $fileSize = (int)$headers["Content-Length"];

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
    $headerSize = curl_getinfo($ch, CURLINFO_HEADER_SIZE);
    $headersRaw = substr($response, 0, $headerSize);
    curl_close($ch);

    preg_match('/Location: (.*)/', $headersRaw, $matches);
    if (!isset($matches[1])) return false;

    $uploadUrl = trim($matches[1]);

    $fileHandle = fopen($fileUrl, "rb");
    if (!$fileHandle) return false;

    $chunkSize = 5 * 1024 * 1024;
    $offset = 0;

    while ($offset < $fileSize) {

        fseek($fileHandle, $offset);
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
        $headerSize = curl_getinfo($ch, CURLINFO_HEADER_SIZE);
        $responseHeaders = substr($response, 0, $headerSize);
        $body = substr($response, $headerSize);
        curl_close($ch);

        if ($status == 308) {
            // Upload incomplete, get range
            if (preg_match('/Range: bytes=0-(\d+)/', $responseHeaders, $rangeMatch)) {
                $offset = (int)$rangeMatch[1] + 1;
            } else {
                $offset += $chunkLength;
            }
        }
        elseif ($status == 200 || $status == 201) {
            $uploadResponse = json_decode($body, true);
            break;
        }
        else {
            fclose($fileHandle);
            return false;
        }
    }

    fclose($fileHandle);

    if (!isset($uploadResponse["id"])) return false;

    $fileId = $uploadResponse["id"];

    // Make public
    $ch = curl_init("https://www.googleapis.com/drive/v3/files/$fileId/permissions");
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_POST, true);
    curl_setopt($ch, CURLOPT_HTTPHEADER, [
        "Authorization: Bearer $accessToken",
        "Content-Type: application/json"
    ]);
    curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode([
        "role"=>"reader",
        "type"=>"anyone"
    ]));
    curl_exec($ch);
    curl_close($ch);

    return "https://drive.google.com/file/d/$fileId/view";
}
?>
