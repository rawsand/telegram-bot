<?php
file_put_contents("debug_log.txt", date("Y-m-d H:i:s") . " - called\n", FILE_APPEND);
echo "Hello";
