<?php
include "config.php";
include "functions.php";
include "drive_resumable_upload.php";

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    exit;
}

$update = json_decode(file_get_contents("php://input"), true);

$user_id = $update["message"]["from"]["id"]
    ?? $update["callback_query"]["from"]["id"]
    ?? null;

$chat_id = $update["message"]["chat"]["id"]
    ?? $update["callback_query"]["message"]["chat"]["id"]
    ?? null;

if ($user_id != getenv("OWNER_ID")) {
    exit;
}

function debugMessage($chat_id, $text) {
    sendMessage($chat_id, "🔎 DEBUG:\n" . $text);
}

/* ================= MESSAGE HANDLING ================= */

if (isset($update["message"])) {

    $text = $update["message"]["text"] ?? "";

    if ($text === "/start") {
        sendMessage($chat_id, "Send formatted message:\nFile Name : xxx\nDownload : https://...");
        exit;
    }

    /* ================= CASE 1 ================= */

    if (
        stripos($text, "file name") !== false &&
        stripos($text, "download") !== false
    ) {

        preg_match('/File\s*Name\s*:\s*(.+)/i', $text, $fileMatch);
        preg_match('/https?:\/\/[^\s]+/i', $text, $linkMatch);

        if (!isset($fileMatch[1]) || !isset($linkMatch[0])) {
            sendMessage($chat_id, "Extraction failed.");
            exit;
        }

        $fileName = trim($fileMatch[1]);
        $downloadUrl = trim($linkMatch[0]);

        debugMessage($chat_id, "File Name: $fileName");
        debugMessage($chat_id, "Download URL detected");

        $success = uploadToDriveResumable($downloadUrl, $fileName, $chat_id);

        if ($success) {
            sendMessage($chat_id, "✅ Drive Upload Success");
        } else {
            sendMessage($chat_id, "❌ Drive upload failed.");
        }

        exit;
    }

    sendMessage($chat_id, "Invalid input.");
}
?>
