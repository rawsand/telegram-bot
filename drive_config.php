<?php
function base64UrlEncode($data) {
    return rtrim(strtr(base64_encode($data), '+/', '-_'), '=');
}

function getAccessToken() {
    $clientEmail = getenv("GOOGLE_CLIENT_EMAIL");
    $privateKey = getenv("GOOGLE_PRIVATE_KEY");

    if (!$clientEmail || !$privateKey) return false;

    // Convert escaped newlines to real newlines
    $privateKey = str_replace("\\n", "\n", $privateKey);

    $now = time();

    $header = base64UrlEncode(json_encode([
        "alg" => "RS256",
        "typ" => "JWT"
    ]));

    $claim = base64UrlEncode(json_encode([
        "iss" => $clientEmail,
        "scope" => "https://www.googleapis.com/auth/drive",
        "aud" => "https://oauth2.googleapis.com/token",
        "exp" => $now + 3600,
        "iat" => $now
    ]));

    $signatureInput = $header . "." . $claim;

    $signature = "";
    openssl_sign($signatureInput, $signature, $privateKey, "sha256WithRSAEncryption");

    $jwt = $signatureInput . "." . base64UrlEncode($signature);

    $ch = curl_init("https://oauth2.googleapis.com/token");
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_POSTFIELDS, http_build_query([
        "grant_type" => "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion" => $jwt
    ]));
    $response = json_decode(curl_exec($ch), true);
    curl_close($ch);

    return $response["access_token"] ?? false;
}
?>
