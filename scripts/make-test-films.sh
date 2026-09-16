#!/bin/sh
# Generate three short films covering the three playback cases the cinema
# spec measured: direct play, remux (video copied), and full transcode.
# Named so Jellyfin matches real TMDB metadata and posters.
#   scripts/make-test-films.sh <films-dir>
set -eu
DIR=${1:?usage: make-test-films.sh <films-dir>}
SECONDS_EACH=${SECONDS_EACH:-45}   # longer films make resume testable

mk() { # title year vcodec acodec ext
  mkdir -p "$DIR/$1 ($2)"
  ffmpeg -hide_banner -loglevel error -y \
    -f lavfi -i "testsrc2=size=1280x720:rate=24" \
    -f lavfi -i "sine=frequency=330:sample_rate=48000" -t "$SECONDS_EACH" \
    -c:v "$3" -preset ultrafast -crf 28 -c:a "$4" -b:a 128k -metadata title="$1" \
    "$DIR/$1 ($2)/$1 ($2).$5"
  echo "made: $1 ($2)  $3 / $4 / $5"
}

mk "Paper Moon"            1973 libx264 ac3 mkv   # remux: video copied, audio to aac
mk "The Lavender Hill Mob" 1951 libx265 ac3 mkv   # transcode: hevc must be re-encoded
mk "Roman Holiday"         1953 libx264 aac mp4   # direct play
