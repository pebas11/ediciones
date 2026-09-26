# Tokens de motion y tipografía estilo Apple

Fuentes:
- Apple HIG, sección Motion: «Add motion purposefully», «Aim for brevity and precision».
- Curvas medidas en el CSS de apple.com (septiembre de 2026).
- Springs de SwiftUI, WWDC23 «Animate with springs».

## Curvas (ya registradas en `lib/stage.js`)
| Nombre GSAP | cubic-bezier | Uso |
|---|---|---|
| `apple` | 0.4, 0, 0.6, 1 | Curva de la casa: desplazamientos, cambios de estado, cámara |
| `appleOut` | 0, 0, 0.2, 1 | Entradas y revelados: arranca rápido y frena largo |
| `appleIn` | 0.4, 0, 1, 1 | Salidas: arranca lento y se va |
| `M.spring(0)` | spring, bounce 0 | Default de SwiftUI: "vivo" sin rebote |
| `M.spring(0.15)` | spring, bounce 0.15 | Rebote apenas perceptible, para un número o ícono que "aterriza" |

- Uso: `ease: M.spring(0.15)`.
- Evitar `back.out(>1.4)`, `elastic` y rebotes marcados: se ven anticuados. Las curvas viejas (`swift`, `smooth`, `settle`) siguen disponibles para las escenas 01–05.

## Duraciones (`M.D`)
| Token | Segundos | Uso |
|---|---|---|
| `micro` | 0,24 | Ticks, puntos, cambios de color |
| `fast` | 0,4 | Íconos y chips |
| `base` | 0,5 | Tarjetas y textos secundarios |
| `reveal` | 0,8 | Titulares, revelado escalonado (translateY 0,7 / opacidad 0,9 en apple.com) |
| `scene` | 1,0 | Transiciones grandes y movimientos de cámara |

- Escalonado de un grupo: el total (`items × stagger`) no debería pasar de `M.D.staggerMax` (0,5 s), así se lee como un solo beat.
- Hold después de construir cada beat: al menos `M.D.hold` (1,5 s).
- Las salidas duran entre el 60 % y el 70 % de su entrada.

## Tipografía (Inter en lugar de SF Pro, que no tiene licencia para video)
| Tamaño | Interlineado | Tracking |
|---|---|---|
| ≥ 160 px (palabra destacada) | 1,0 visual (1,25 si usa máscara SplitText) | −0,035em |
| 80 px | 1,05 | −0,015em |
| 64 px | 1,06 | −0,009em |
| 48 px | 1,08 | −0,003em |
| 32–40 px | 1,1–1,125 | 0 |
| 24 px | — | +0,009em |
| Mono (rótulos) | — | +0,2 a 0,3em, siempre en mayúsculas |

- Jerarquía: una sola protagonista por beat, con 3 o 4 veces el tamaño del texto de apoyo.
- Pesos: 800–900 para la palabra destacada, 600–700 para títulos y 400 para el cuerpo.
- Títulos de 2 líneas: `text-wrap: balance`.

## Principios
1. Cada movimiento explica algo, como una causa, una comparación o un orden. Si no explica nada, se saca.
2. Un foco por vez: lo que no es protagonista queda quieto o se atenúa.
3. La profundidad sale de capas con parallax suave, sombras largas y difusas y reflejos al 10–15 %. No se usan biseles ni 3D pesado.
4. La continuidad importa: un elemento que ya existe se transforma (por ejemplo, un título que pasa a ser header) en lugar de salir y volver a entrar.
5. En la narración, cada número aparece o termina su contador justo cuando se nombra.
