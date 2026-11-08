#!/bin/sh
# Downloads the kaikki.org extracts into DIR/en and DIR/pt (laptop only).
# Usage: ./fetch.sh [DIR] [LANGS]    e.g. ./fetch.sh data "pt es"
set -eu

dir="${1:-data}"
langs="${2:-pt es de fr en}"
mkdir -p "$dir/en" "$dir/pt"

en_name() {
    case "$1" in
        pt) echo Portuguese ;; es) echo Spanish ;; de) echo German ;; fr) echo French ;; en) echo English ;;
    esac
}
pt_name() {
    case "$1" in
        pt) echo 'Portugu%C3%AAs' ;; es) echo Espanhol ;; de) echo 'Alem%C3%A3o' ;;
        fr) echo 'Franc%C3%AAs' ;; en) echo 'Ingl%C3%AAs' ;;
    esac
}

get() {
    echo "-> $2"
    curl -fL --retry 3 -C - -o "$2" "$1"
}

for l in $langs; do
    n=$(en_name "$l")
    [ -n "$n" ] || { echo "unknown language: $l" >&2; exit 2; }
    get "https://kaikki.org/dictionary/$n/kaikki.org-dictionary-$n.jsonl" "$dir/en/$l.jsonl"
    p=$(pt_name "$l")
    get "https://kaikki.org/ptwiktionary/$p/kaikki.org-dictionary-$p.jsonl" "$dir/pt/$l.jsonl"
done
date -u +%Y-%m-%dT%H:%M:%SZ > "$dir/fetched_at"
