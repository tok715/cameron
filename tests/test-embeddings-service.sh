#!/bin/bash

set -eu

cd "$(dirname "${0}")"

curl -v -XPOST -H 'Content-Type:application/json' -d '{"text":"你好呀世界"}' --unix-socket ../data/service-embeddings.socket http://service/embeddings/encode
