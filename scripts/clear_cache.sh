#!/usr/bin/env bash

#* Clear pagecache, dentries, and inodes.
echo 3 | sudo tee /proc/sys/vm/drop_caches
