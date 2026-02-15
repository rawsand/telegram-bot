<?php
include "config.php";
include "functions.php";

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    exit;
}

$update = json_decode(file_get_contents("php://input"), true);

$stateFile = "user_state.json";
$states = file_exists($stateFile) ? json_decode(file_get_contents($stateFile), true) : [];

$user_id = $update["message"]["from"]["id"] 
    ?? $update["callback_query"]["from"]["id"] 
    ?? null;

if ($user_id != $allowedUser) {
    exit;
}

/* CALLBACK */
if (isset($update["callback_query"])) {

    $callback = $update["callback_query"];
    $data = $callback["data"];
    $chat_id = $callback["message"]["chat"]["id"];
    $callback_id = $callback["id"];

    answerCallback($callback_id);

    if ($data == "back_files") {
        unset($states[$chat_id]);
        file_put_contents($stateFile, json_encode($states));

        $keyboard = [
            "inline_keyboard" => [
                [["text"=>"1 - CLinks.txt","callback_data"=>"file1"]],
                [["text"=>"2 - MLinks.txt","callback_data"=>"file2"]]
            ]
        ];
        sendMessage($chat_id,"Select file:",$keyboard);
        exit;
    }

    if ($data == "file1") {
        $states[$chat_id]["file"] = "CLinks.txt";
        file_put_contents($stateFile,json_encode($states));

        $keyboard = [
            "inline_keyboard" => [
                [["text"=>"Sky","callback_data"=>"Sky"],
                 ["text"=>"Willow","callback_data"=>"Willow"]],
                [["text"=>"Prime 1","callback_data"=>"Prime 1"],
                 ["text"=>"Prime 2","callback_data"=>"Prime 2"]],
                [["text"=>"⬅ Back","callback_data"=>"back_files"]]
            ]
        ];
        sendMessage($chat_id,"Select channel:",$keyboard);
        exit;
    }

    if ($data == "file2") {
        $states[$chat_id]["file"] = "MLinks.txt";
        file_put_contents($stateFile,json_encode($states));

        $keyboard = [
            "inline_keyboard" => [
                [["text"=>"MC","callback_data"=>"MC"],
                 ["text"=>"FOW","callback_data"=>"FOW"]],
                [["text"=>"50","callback_data"=>"50"],
                 ["text"=>"4","callback_data"=>"4"],
                 ["text"=>"5","callback_data"=>"5"]],
                [["text"=>"⬅ Back","callback_data"=>"back_files"]]
            ]
        ];
        sendMessage($chat_id,"Select channel:",$keyboard);
        exit;
    }

    $states[$chat_id]["channel"] = $data;
    file_put_contents($stateFile,json_encode($states));

    sendMessage($chat_id,"Send new link:");
    exit;
}

/* MESSAGE */
if (isset($update["message"])) {

    $chat_id = $update["message"]["chat"]["id"];
    $text = $update["message"]["text"];

    if ($text == "/start") {
        $keyboard = [
            "inline_keyboard" => [
                [["text"=>"1 - CLinks.txt","callback_data"=>"file1"]],
                [["text"=>"2 - MLinks.txt","callback_data"=>"file2"]]
            ]
        ];
        sendMessage($chat_id,"Select file:",$keyboard);
        exit;
    }

    if (isset($states[$chat_id]["channel"])) {

        $file = $states[$chat_id]["file"];
        $channel = $states[$chat_id]["channel"];

        updateLinkInFile($file,$channel,$text);

        unset($states[$chat_id]);
        file_put_contents($stateFile,json_encode($states));

        sendMessage($chat_id,"✅ Updated successfully!");
        exit;
    }
}
?>