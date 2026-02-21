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
        sendMessage($chat_id, "Send helper message.");
        exit;
    }

    /* ================= CASE 1 (UNICODE FORMAT SUPPORT) ================= */

    if (preg_match('/F.?ɪ.?ʟ.?ᴇ.?[\s_]*ɴ.?ᴀ.?ᴍ.?ᴇ\s*:\s*(.+)/iu', $text, $fileMatch) &&
        preg_match('/https?:\/\/[^\s]+/iu', $text, $linkMatch)
    ) {

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
