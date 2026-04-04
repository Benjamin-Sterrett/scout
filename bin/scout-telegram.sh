#!/bin/bash
# Scout Telegram helper — sends messages to the Scout forum topic.
# Only supports sendMessage and sendDocument. No other Telegram API methods.
# This exists to prevent the patrol Claude from calling setWebhook/getUpdates
# on the shared bot token, which killed the Uplink daemon (PRJ-389).

set -euo pipefail

CHAT_ID="-1003817797037"
TOPIC_ID=1653

_get_token() {
    security find-generic-password -s uplink -a telegram-bot-token -w
}

usage() {
    echo "Usage:"
    echo "  scout-telegram.sh send <message>"
    echo "  scout-telegram.sh file <path>"
    exit 1
}

[ $# -lt 2 ] && usage

ACTION="$1"
shift

case "$ACTION" in
    send)
        BOT_TOKEN=$(_get_token)
        curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
            -H "Content-Type: application/json" \
            -d "$(jq -n \
                --arg chat_id "$CHAT_ID" \
                --argjson thread_id "$TOPIC_ID" \
                --arg text "$*" \
                '{chat_id: $chat_id, message_thread_id: $thread_id, text: $text, parse_mode: "Markdown"}')"
        ;;
    file)
        BOT_TOKEN=$(_get_token)
        FILE_PATH="$1"
        [ ! -f "$FILE_PATH" ] && echo "File not found: $FILE_PATH" && exit 1
        curl -s \
            -F "chat_id=$CHAT_ID" \
            -F "message_thread_id=$TOPIC_ID" \
            -F "document=@${FILE_PATH}" \
            "https://api.telegram.org/bot${BOT_TOKEN}/sendDocument"
        ;;
    *)
        echo "Unknown action: $ACTION (only 'send' and 'file' are supported)"
        usage
        ;;
esac
