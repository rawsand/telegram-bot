<?php

$botToken = getenv('BOT_TOKEN');
$allowedUser = getenv('OWNER_ID');

$apiURL = "https://api.telegram.org/bot$botToken/";

$githubToken = getenv('GITHUB_TOKEN');
$githubUsername = getenv('GITHUB_USERNAME');
$githubRepo = getenv('GITHUB_REPO');

?>
