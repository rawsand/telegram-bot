<?php
include "config.php";
include "functions.php";

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    exit;
}

$update = json_decode(file_get_contents("php://input"), true);

$user_id = $update["message"]["from"]["id"]
    ?? $update["callback_query"]["from"]["id"]
    ?? null;

if ($user_id != $allowedUser) {
    exit;
}

/* ================= CALLBACK (CASE 2 BUTTON) ================= */

if (isset($update["callback_query"])) {

    $callback = $update["callback_query"];
    $chat_id = $callback["message"]["chat"]["id"];
    $title = $callback["data"];
    $callback_id = $callback["id"];

    answerCallback($callback_id);

    $link = getTempLink($chat_id);

    if (!$link) {
        sendMessage($chat_id, "Expired. Send link again.");
        exit;
    }

    updateLinkInFile("links.txt", $title, $link);

    if (pushFileToGitHub("links.txt")) {
        // ✅ LOAD DRIVE MODULE
        require_once "drive_upload.php";

        // ✅ Upload to Google Drive (Case 1 only)
        $result = uploadToDrive($downloadLink, $fileName);

    if ($result) {
        sendMessage($chat_id, "✅ $title updated, synced & uploaded to Drive.");
    } else {
        sendMessage($chat_id, "❌ GitHub updated but Drive upload failed.");
    }
    } else {
        sendMessage($chat_id, "⚠ Updated locally but GitHub push failed.");
    }

    clearTempLink($chat_id);
    exit;
}

/* ================= MESSAGE HANDLING ================= */

if (isset($update["message"])) {

    $chat_id = $update["message"]["chat"]["id"];
    $text = $update["message"]["text"] ?? "";

    /* ===== START COMMAND ===== */

    if ($text === "/start") {
        sendMessage($chat_id, "Send helper bot message (Case 1) or direct link (Case 2).");
        exit;
    }

    /* =======================================================
       ================= CASE 1 ==============================
       Forwarded helper bot message with:
       - File name
       - Download link
       ======================================================= */

    if (strpos($text, "Fɪʟᴇ ɴᴀᴍᴇ") !== false && strpos($text, "Dᴏᴡɴʟᴏᴀᴅ") !== false) {

        // Extract file name
        preg_match('/Fɪʟᴇ ɴᴀᴍᴇ\s*:\s*(.+)/u', $text, $fileMatch);

        // Extract download link
        preg_match('/https?:\/\/[^\s]+/', $text, $linkMatch);

        if (!isset($fileMatch[1]) || !isset($linkMatch[0])) {
            sendMessage($chat_id, "Could not extract file name or link.");
            exit;
        }

        $fileName = trim($fileMatch[1]);
        $downloadLink = trim($linkMatch[0]);

        $titles = [
            "Master Chef",
            "Wheel of fortune",
            "50",
            "Laughter Chef"
        ];

        foreach ($titles as $title) {

            if (titleMatches($title, $fileName)) {

                updateLinkInFile("links.txt", $title, $downloadLink);

                if (pushFileToGitHub("links.txt")) {
                    sendMessage($chat_id, "✅ $title updated & synced to GitHub.");
                } else {
                    sendMessage($chat_id, "⚠ Updated locally but GitHub push failed.");
                }

                exit;
            }
        }

        sendMessage($chat_id, "No matching title found.");
        exit;
    }

    /* =======================================================
       ================= CASE 2 ==============================
       Direct link + button selection
       ======================================================= */

    if (filter_var($text, FILTER_VALIDATE_URL)) {

        saveTempLink($chat_id, $text);

        $keyboard = [
            "inline_keyboard" => [
                [
                    ["text"=>"Sky","callback_data"=>"Sky"],
                    ["text"=>"Willow","callback_data"=>"Willow"]
                ],
                [
                    ["text"=>"Prime1","callback_data"=>"Prime1"],
                    ["text"=>"Prime2","callback_data"=>"Prime2"]
                ]
            ]
        ];

        sendMessage($chat_id, "Select title:", $keyboard);
        exit;
    }

    sendMessage($chat_id, "Invalid input.");
}
?>
