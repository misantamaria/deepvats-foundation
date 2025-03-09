#!/bin/bash

# 🔧 CONFIGURACIÓN
FILES=("srv/shinylog/app.logs" "nbs_pipeline/logs.txt")  # Archivos a buscar
FILTER_MODE="all"  # Opciones: "all", "any_large", "all_large"
STOP_AT_FIRST=true #Parar cuando ya ninguno sea grande (para reconstruir a partir de ese commit con cuidado. SIEMPRE HAZ UNA RAMA DE BACKUP)


echo "🔍 Buscando commits donde los archivos cumplen la condición ($FILTER_MODE)..."

git log -n 50 --pretty=format:"%H %ad" -- "${FILES[@]}" | while read commit date; do
    echo "🔍 Analizando commit: $commit - Fecha: $date"

    found_any=false
    all_large=true
    output="✅ Archivo(s) encontrado(s) en commit: $commit - Fecha: $date"

    # Array para saber si cada archivo ha sido encontrado
    declare -A FOUND_FILES

    any_large=false
    for file in "${FILES[@]}"; do
        echo "Looking for $file"
        FOUND_FILES["$file"]=$(git ls-tree -r -l "$commit" | grep "$file")

        if [[ -n "${FOUND_FILES["$file"]}" ]]; then
            found_any=true
            cmd="git ls-tree -r -l $commit | awk -v f='$file' '\$NF == f {print \$(NF-1)}'"
            #echo "Ejecutando: $cmd"  # Muestra el comando exacto antes de ejecutarlo
            size=$(eval "$cmd")
            
            
            if [[ -n "$size" ]]; then
                size_mb=$(awk "BEGIN {printf \"%.2f\", $size / 1048576}")  # Convertir a MB con 2 decimales
                if [[ "$size" -gt 104857600 ]]; then
                    output+="\n   ⚠️ $file = $size bytes (${size_mb}MB) (Superó 100MB)"
                    any_large=true
                else
                    output+="\n   📂 $file = $size bytes (${size_mb}MB)"
                    all_large=false
                fi
            fi
        else
            all_large=false
        fi
    done
    echo "STOP $STOP_AT_FIRST any large? $any_large"
    #any_large=$([[ "$found_any" == true && "$all_large" == false ]] && echo "true" || echo "false")
    #any_large=$([[ "$found_any" == "true" && "$all_large" == "false" && "$size" -gt 104857600 ]] && echo "true" || echo "false")
    # Filtrado según `FILTER_MODE`
    if [[ "$FILTER_MODE" == "all" && "$found_any" == true ]]; then
        echo -e "$output"
    elif [[ "$FILTER_MODE" == "any_large" && "$any_large" == false ]]; then
        echo -e "$output"
    elif [[ "$FILTER_MODE" == "all_large" && "$all_large" == true ]]; then
        echo -e "$output"
    fi
    if [[ "$STOP_AT_FIRST" == "true" && "$any_large" == "false" ]]; then
        echo -e "$output"
        echo "🛑 Detenido en commit: $commit porque está habilitada la parada y no quedan ficheros largos de la lista proporcionada."
        exit 0
    fi

    echo "-----------------------------------------"
done
