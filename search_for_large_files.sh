#!/bin/bash

echo "🔍 Buscando archivos grandes en los últimos 50 commits..."
echo "------------------------------------------------------"

# Carpeta temporal para almacenar las rutas de archivos grandes
temp_file=$(mktemp)

# Buscar en los últimos 50 commits
git log -n 50 --pretty=format:"%H %ad" | while read commit date; do
    echo "🔍 Analizando commit: $commit - Fecha: $date"
    
    # Buscar archivos grandes en este commit, filtrando por tamaño y extensión
    git ls-tree -r -l "$commit" | awk '$5 > 104857600 && ($4 ~ /\.log$/ || $4 ~ /\.logs$/ || $4 ~ /\.txt$/) {print $5, $4}' | while read size file; do
        echo "   📂 Archivo grande encontrado: $file ($size bytes)"
        
        # Guardar la carpeta donde está el archivo
        dirname "$file" >> "$temp_file"
    done
    
    echo "-----------------------------------------"
done

# Mostrar las carpetas afectadas al final del análisis
echo "📂 **Carpetas con archivos grandes:**"
sort "$temp_file" | uniq

# Eliminar archivo temporal
rm -f "$temp_file"
