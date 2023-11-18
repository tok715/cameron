#!/bin/bash

set -eu

cd "$(dirname "${0}")"

curl -v -XPOST -H 'Content-Type:application/json' -d '{"input_text":"你好呀世界","max_new_tokens":20}' --unix-socket ../data/service-generation.socket http://service/generation/generate
