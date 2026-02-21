<?php
include "config.php";
include "functions.php";
include "drive_resumable_upload.php";

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    exit;
}

$update = json_decode(file_get_contents("php://input"), true);

$chat_id = $update["message"]["chat"]["id"] ?? null;
$user_id = $update["message"]["from"]["id"] ?? null;

if ($user_id != getenv("OWNER_ID")) {
    exit;
}

function debugMessage($chat_id, $text) {
    sendMessage($chat_id, "🔎 DEBUG:\n" . $text);
}

if (isset($update["message"])) {

    $text = $update["message"]["text"] ?? "";

    if ($text === "/start") {
        sendMessage($chat_id, "Send formatted message.");
        exit;
    }

    if (strpos($text, "File Name") !== false && strpos($text, "Download") !== false) {

        preg_match('/File Name\s*:\s*(.+)/i', $text, $fileMatch);
        preg_match('/https?:\/\/[^\s]+/', $text, $linkMatch);

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
