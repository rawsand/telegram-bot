<?php

function getAccessToken() {

    $clientEmail = getenv("GOOGLE_CLIENT_EMAIL");
    $privateKey = str_replace("\\n", "\n", getenv("GOOGLE_PRIVATE_KEY"));

    $header = base64_encode(json_encode(["alg"=>"RS256","typ"=>"JWT"]));
    $now = time();
    $claim = base64_encode(json_encode([
        "iss"=>$clientEmail,
        "scope"=>"https://www.googleapis.com/auth/drive",
        "aud"=>"https://oauth2.googleapis.com/token",
        "exp"=>$now+3600,
        "iat"=>$now
    ]));

    $signatureInput = "$header.$claim";
    openssl_sign($signatureInput, $signature, $privateKey, "SHA256");
    $jwt = "$header.$claim.".base64_encode($signature);

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

    // Step 1: Create resumable session
    $metadata = json_encode([
        "name"=>$fileName,
        "parents"=>[$folderId]
    ]);

    $ch = curl_init("https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable");
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_POST, true);
    curl_setopt($ch, CURLOPT_HTTPHEADER, [
        "Authorization: Bearer $accessToken",
        "Content-Type: application/json; charset=UTF-8",
        "X-Upload-Content-Type: application/octet-stream"
    ]);
    curl_setopt($ch, CURLOPT_POSTFIELDS, $metadata);
    curl_setopt($ch, CURLOPT_HEADER, true);
    $response = curl_exec($ch);

    $headerSize = curl_getinfo($ch, CURLINFO_HEADER_SIZE);
    $headers = substr($response, 0, $headerSize);
    curl_close($ch);

    preg_match('/Location: (.*)/', $headers, $matches);
    if (!isset($matches[1])) return false;

    $uploadUrl = trim($matches[1]);

    // Step 2: Stream file in chunks
    $fileHandle = fopen($fileUrl, "rb");
    if (!$fileHandle) return false;

    $chunkSize = 5 * 1024 * 1024; // 5MB
    $offset = 0;

    while (!feof($fileHandle)) {

        $chunk = fread($fileHandle, $chunkSize);
        $chunkLength = strlen($chunk);

        $ch = curl_init($uploadUrl);
        curl_setopt($ch, CURLOPT_CUSTOMREQUEST, "PUT");
        curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
        curl_setopt($ch, CURLOPT_HTTPHEADER, [
            "Authorization: Bearer $accessToken",
            "Content-Length: $chunkLength",
            "Content-Range: bytes $offset-".($offset+$chunkLength-1)."/*"
        ]);
        curl_setopt($ch, CURLOPT_POSTFIELDS, $chunk);
        $result = curl_exec($ch);
        $status = curl_getinfo($ch, CURLINFO_HTTP_CODE);
        curl_close($ch);

        $offset += $chunkLength;

        if ($status == 200 || $status == 201) {
            $uploadResponse = json_decode($result, true);
            break;
        }
    }

    fclose($fileHandle);

    if (!isset($uploadResponse["id"])) return false;

    $fileId = $uploadResponse["id"];

    // Step 3: Make file public
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
