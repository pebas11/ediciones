---
name: motion-copy
description: Economía de texto en pantalla para motion graphics y videos explicativos. Usar SIEMPRE antes de escribir o revisar textos de una animación (títulos, rótulos, datos, anotaciones) para evitar la verborragia, la sobrecarga de información y el look de "paper" o "infografía de IA".
---

# Texto en pantalla: menos, más grande, más tarde

La **voz en off** explica y la **pantalla** ancla. El espectador no puede leer y escuchar a la vez: cada palabra en pantalla le quita atención a la imagen y a la narración.

## Reglas duras
1. **Una idea por beat y un solo foco.** Nunca hay más de **2 elementos de texto visibles** a la vez, por ejemplo titular + un número.
2. **Presupuesto de palabras:**
   - Titular: **≤ 5 palabras**.
   - Apoyo: **≤ 7 palabras**, y solo si dice algo que la imagen no muestra.
   - Dato: número + unidad + **≤ 3 palabras**.
   - Total por escena: **≤ 18 palabras** entre todos los beats.
3. **Tiempo de lectura:** cada texto queda visible al menos `0,3 s × palabras + 1 s`. Si no hay tiempo, sobra texto.
4. **Mostrar en vez de rotular.** Si la imagen ya lo dice, no se escribe. No hace falta rotular "sombrero" si se ve el sombrero.
5. **Tamaño mínimo, pensado para teléfono:** titular ≥ 110 px, apoyo ≥ 40 px y dato ≥ 160 px (en 1080p). Si no entra a ese tamaño, sobra texto.

## Lista negra (borrar sin discutir)
- Números de figura o lámina ("FIG. 01", "LÁMINA 01"), códigos, marcas de esquina decorativas y rótulos de sección técnicos.
- **Fuentes y citas en pantalla**: van en la descripción del video.
- Kickers o eyebrows que repiten el título. Nombre científico y título a la vez: elegí uno.
- Rótulos de cosas obvias, como "nivel del suelo" o "lo que ves / lo que no ves" cuando la imagen ya lo muestra.
- Texto mono decorativo que no se va a leer.
- Descripciones debajo de cada rótulo. Si hace falta explicar, lo dice la voz.
- Paréntesis, siglas sin necesidad y aclaraciones.

## Cómo reescribir (proceso)
1. Escribí lo que dice la narración en ese beat.
2. Subrayá la **palabra ancla** (o el número) que el espectador tiene que recordar.
3. En pantalla va **solo** la ancla, con 1 o 2 palabras de contexto como mucho.
4. Leé la escena completa en voz alta. Si el texto en pantalla compite con la voz, cortá la mitad.

## Ejemplo (h01)
- **Antes (mal):** "PSILOCYBE CUBENSIS — FIG. 01" + "Hongos mágicos" + "Un organismo que casi nunca vemos completo" + 3 rótulos con descripciones + "LO QUE VES / El fruto / Dura unos días: su trabajo es soltar esporas" + "LO QUE NO VES / El micelio / Una red de hilos que vive bajo tierra" + "NIVEL DEL SUELO" + "+200 / especies de hongos producen psilocibina / Van Court et al., 2022 · Guzmán et al., 1998" + "LÁMINA 01 · PSILOCYBE CUBENSIS". Son unas 70 palabras.
- **Después (bien):**
  - Beat 1: "Hongos mágicos".
  - Beat 2: "Solo el fruto" → "La red, bajo tierra".
  - Beat 3: "+200 especies".
  - En total, 9 palabras.

## Chequeo automático
`node qa.mjs <escena>` avisa si en un tramo quieto hay más de 12 palabras visibles o más de 3 bloques de texto.
