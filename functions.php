<?php

function sendMessage($chat_id, $text, $keyboard = null) {
    global $apiURL;

    $data = [
        "chat_id" => $chat_id,
        "text" => $text
    ];

    if ($keyboard) {
        $data["reply_markup"] = json_encode($keyboard);
    }

    file_get_contents($apiURL . "sendMessage?" . http_build_query($data));
}

function answerCallback($callback_id) {
    global $apiURL;
    file_get_contents($apiURL . "answerCallbackQuery?callback_query_id=" . $callback_id);
}

/* ================= TITLE MATCH ================= */

function titleMatches($title, $fileName) {

    $normalized = preg_replace("/[^a-z0-9]/", "", strtolower($fileName));

    if ($title === "50") {
        return preg_match("/the50/", $normalized);
    }

    $words = explode(" ", strtolower($title));

    foreach ($words as $word) {
        $cleanWord = preg_replace("/[^a-z0-9]/","",$word);
        if (strpos($normalized, $cleanWord) === false) return false;
    }

    return true;
}

/* ================= UPDATE FILE ================= */

function updateLinkInFile($file, $title, $newLink) {

    $lines = file($file, FILE_IGNORE_NEW_LINES);
    $output = [];
    $i = 0;

    while ($i < count($lines)) {

        if (trim($lines[$i]) === $title) {
            $output[] = $title;
            $output[] = $newLink;
            $output[] = "";
            $i += 3;
        } else {
            $output[] = $lines[$i];
            $i++;
        }
    }

    file_put_contents($file, implode(PHP_EOL, $output) . PHP_EOL);
}

/* ================= TELEGRAM DOWNLOAD ================= */

function generateTelegramDownloadLink($file_id) {

    $botToken = getenv("BOT_TOKEN");

    $url = "https://api.telegram.org/bot$botToken/getFile?file_id=$file_id";

    $ch = curl_init($url);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    $response = curl_exec($ch);
    curl_close($ch);

    $data = json_decode($response, true);

    if (!isset($data["result"]["file_path"])) {
        return false;
    }

    $filePath = $data["result"]["file_path"];

    return "https://api.telegram.org/file/bot$botToken/$filePath";
}

/* ================= GITHUB PUSH ================= */

function pushFileToGitHub($filePath, $branch = "main") {

    $token = getenv("GITHUB_TOKEN");
    $username = getenv("GITHUB_USERNAME");
    $repo = getenv("GITHUB_REPO");

    $fileName = basename($filePath);
    $content = base64_encode(file_get_contents($filePath));

    $api = "https://api.github.com/repos/$username/$repo/contents/$fileName?ref=$branch";

    $ch = curl_init($api);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_USERAGENT, "TelegramBot");
    curl_setopt($ch, CURLOPT_HTTPHEADER, ["Authorization: token $token"]);
    $response = json_decode(curl_exec($ch), true);
    curl_close($ch);

    $sha = $response["sha"] ?? null;
    if (!$sha) return false;

    $data = [
        "message" => "Updated $fileName via Telegram bot",
        "content" => $content,
        "sha" => $sha,
        "branch" => $branch
    ];

    $ch = curl_init("https://api.github.com/repos/$username/$repo/contents/$fileName");
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_USERAGENT, "TelegramBot");
    curl_setopt($ch, CURLOPT_HTTPHEADER, [
        "Authorization: token $token",
        "Content-Type: application/json"
    ]);
    curl_setopt($ch, CURLOPT_CUSTOMREQUEST, "PUT");
    curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($data));
    curl_exec($ch);
    curl_close($ch);

    return true;
}

/* ================= TEMP LINK ================= */

function saveTempLink($chat_id, $link) {
    file_put_contents("temp_$chat_id.txt", $link);
}

function getTempLink($chat_id) {
    $file = "temp_$chat_id.txt";
    return file_exists($file) ? file_get_contents($file) : false;
}

function clearTempLink($chat_id) {
    $file = "temp_$chat_id.txt";
    if (file_exists($file)) unlink($file);
}
?>
