#!/bin/bash

echo "🔍 Rastreo de tamaños de archivos en los últimos 50 commits..."

git log -n 50 --pretty=format:"%H %ad" -- srv/shinylog/app.log nbs_pipeline/logs.txt | while read commit date; do
    size1=$(git ls-tree -r -l "$commit" | awk '$4 == "srv/shinylog/app.log" {print $5}')
    size2=$(git ls-tree -r -l "$commit" | awk '$4 == "nbs_pipeline/logs.txt" {print $5}')
    
    echo "Commit: $commit - Fecha: $date"
    echo "   📂 srv/shinylog/app.log = ${size1:-No encontrado} bytes"
    echo "   📂 nbs_pipeline/logs.txt = ${size2:-No encontrado} bytes"
    echo "-----------------------------------------"
done

