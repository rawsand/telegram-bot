<?php

function sendMessage($chat_id, $text, $keyboard = null) {
    global $apiURL;

    $data = [
        "chat_id" => $chat_id,
        "text" => $text
    ];

    if ($keyboard != null) {
        $data["reply_markup"] = json_encode($keyboard);
    }

    file_get_contents($apiURL . "sendMessage?" . http_build_query($data));
}

function answerCallback($callback_id) {
    global $apiURL;
    file_get_contents($apiURL . "answerCallbackQuery?callback_query_id=" . $callback_id);
}

function updateLinkInFile($file, $name, $newLink) {
    $lines = file($file, FILE_IGNORE_NEW_LINES);

    for ($i = 0; $i < count($lines); $i++) {
        if (trim($lines[$i]) === $name) {
            $lines[$i + 1] = $newLink;
            break;
        }
    }

    file_put_contents($file, implode(PHP_EOL, $lines));
}
?>