#!/bin/bash

set -eu

cd "$(dirname "${0}")/"

curl -v -XPOST -H 'Content-Type:application/json' -d '{"text":"早上好夜之城"}' --unix-socket ../data/service-synthesize.socket http://service/synthesize/stream > test-synthesize.wav.txt

cat test-synthesize.wav.txt | head -n 1 | base64 -d > test-synthesize.wav

ffplay -autoexit test-synthesize.wav

rm -f test-synthesize.wav.txt test-synthesize.wav
