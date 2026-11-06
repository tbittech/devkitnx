# devkitnx — pruebas automáticas y medición de FPS para ports homebrew de Nintendo Switch

**Automatizar pruebas de ports de Switch en la consola real**: compilar, mandar el `.nro` por WiFi (nxlink), arrancarlo solo (sys-botbase + NSP forwarder del netloader), reproducir una partida grabada y medir el tiempo de cada frame, sin copiar nada a la SD ni tocar la consola. Para ports con libnx/devkitPro (C/C++, recompilaciones estáticas, emuladores), y con instrucciones para que una IA (Claude, Codex, Gemini…) lo instale y lo use: ver `AGENTS.md`.

*Nintendo Switch homebrew port test automation · FPS / frame time benchmark · performance profiling on real hardware · nxlink · sys-botbase · input record & replay · libnx · devkitPro · AI agent instructions (AGENTS.md).*

```
compilar  →  nxlink manda el .nro por WiFi  →  el juego imprime avisos [AT]  →  el runner los sigue
                                                                              →  OK / FALLÓ + log + CSV de frames
```

| Carpeta | Qué hay |
|---|---|
| `include/autotest.h` | Header único que va en cada port (avisos, zonas de tiempo, replay de inputs) |
| `runner/nxtest.py` | Runner en Python (sin dependencias, Python 3.8+) |
| `configs/` | Una config JSON por juego |
| `inputs/` | Replays de inputs de ejemplo |
| `examples/demo/` | Demo mínima ya integrada (`make` → `demo.nro`) |
| `tests/` | nxlink falso para probar el runner sin consola |
| `runs/` | Resultados de cada corrida (se crea solo) |

---

## 1. Preparar la Switch (una sola vez)

1. **Atmosphère** con hbmenu.
2. Abrir hbmenu **en modo título**: abrí cualquier juego manteniendo **R**. Desde el Álbum (modo applet) hay muy poca RAM y un port grande falla por eso.
3. *(Opcional, para apretar botones desde la PC)* instalar **sys-botbase**: copiar su carpeta a `sdmc:/atmosphere/contents/` y reiniciar. Escucha en el puerto 6000.
4. Anotar la IP de la Switch (Configuración → Internet).

## 2. Integrar en un port (5 líneas)

```c
#define AUTOTEST_IMPLEMENTATION     // solo en UN archivo
#include "autotest.h"

int main(int argc, char **argv) {
    at_init(argc, argv, 0);         // primero: sockets + nxlinkStdio + argumentos
    ...
    while (appletMainLoop() && !at_should_quit()) {
        at_frame_begin();
        ...
        uint64_t scripted;
        if (at_input(&scripted)) buttons = scripted;   // replay (--at-input)

        at_zone_begin("logic");   update();  at_zone_end("logic");
        at_zone_begin("sprites"); draw();    at_zone_end("sprites");
        at_zone_begin("present"); swap();    at_zone_end("present");

        if (menu_cargado_por_primera_vez) at_mark("menu_ready");
        at_frame_end();
    }
    at_shutdown();
}
```

En el Makefile del port: agregar la carpeta `include` de devkitnx a `INCLUDES`.
Si el port **ya** inicializa sockets o `nxlinkStdio()`, usá `at_init(argc, argv, AT_INIT_NO_SOCKETS)`.
Para el build final: `-DAUTOTEST_DISABLE` y todo queda en nada.
En C++ también está `AT_SCOPE("zona");`, que cierra la zona sola al salir del bloque.

### API

| Función | Para qué |
|---|---|
| `at_mark("nombre")` | Aviso de "llegué acá". El runner lo espera con tiempo límite |
| `at_enabled()` / `at_scenario()` | `--autotest` / `--autotest=practica`: saltar intros, ir directo a un modo |
| `at_arg("p1")` | Argumento libre: `--p1=maxima` → `"maxima"` |
| `at_zone_begin/end("x")` | Tiempo por parte del frame (máx. 16 zonas). Solo mide con `--perf` |
| `at_zone_add("x", us)` | Suma al frame actual un tiempo medido aparte (ej. la GPU, medida en otro hilo) |
| `at_input(&mask)` | Replay de inputs desde un archivo. Bits iguales a `HidNpadButton`. Se puede llamar desde el hilo que lee el pad |
| `mask = at_record(mask)` | Con `--at-record=archivo`, graba los cambios de botones en el formato del replay y devuelve los botones para el juego (sin el de `--at-record-mark`). También desde el hilo del pad |
| `at_vblank()` | Un tick de la lógica del juego (ej. el vblank de un emulador o recompilación). Solo hace falta para `--at-clock=vblank`. Se puede llamar desde su propio hilo |
| `at_log(fmt, ...)` | Línea de log que queda en el log de la corrida |
| `at_done(0)` / `at_fail("motivo")` | Terminar la prueba. Después de esto, `at_should_quit()` da 1 |

### Argumentos que entiende el juego

| Argumento | Efecto |
|---|---|
| `--autotest[=escenario]` | Modo prueba |
| `--perf` | Manda una fila de tiempos por frame |
| `--at-input=sdmc:/ruta.txt` | Replay de inputs (formato en `inputs/ejemplo_menu_a_partida.txt`). Una línea `<frame> @nombre` manda `[AT] mark nombre` en ese frame |
| `--at-record=sdmc:/ruta.txt` | Graba lo que apretás, listo para usar como `--at-input` (solo botones, no el stick analógico) |
| `--at-exit-after=N` | `at_done(0)` solo después de N frames |
| `--at-exit-at-end` | `at_done(0)` cuando el replay llega a `END` |
| `--at-record-mark=BOTON:nombre` | Al grabar, apretar BOTON escribe `<frame> @nombre` en vez de grabarse |
| `--at-clock=vblank` | El replay, las marcas y la grabación cuentan ticks de `at_vblank()` en vez de frames mostrados: la misma entrada cae en el mismo momento del juego a cualquier fps. Grabá y reproducí con el mismo reloj |
| `--at-convert=sdmc:/ruta.txt` | Con el reloj normal, reproduce `--at-input` y escribe el mismo replay contado en ticks de `at_vblank()` (para pasar una grabación vieja a `--at-clock=vblank`) |
| `--loquesea=valor` | Lo leés vos con `at_arg("loquesea")` |

## 3. Correr una prueba

Copiá `configs/plantilla.json` (o `plantilla_grabar.json` / `plantilla_bench.json`), completá cada `<...>`, y:

```bash
python runner/nxtest.py run configs/mi_juego.json
```

Si sys-botbase está desactivado, antes apretá **Y** en hbmenu (netloader). Si está activado, lo aprieta el runner.

```bash
python runner/nxtest.py run configs/mi_juego.json --no-build -- --autotest=versus
```

Lo que va después de `--` se suma a los `args` de la config. Los argumentos no pueden tener espacios: nxlink los separa por espacio.

Cada corrida deja en `runs/<juego>/<fecha>/`:
- `log.txt`: todo lo que imprimió el juego, con tiempo desde el arranque.
- `perf.csv`: una fila por frame, una columna por zona (en microsegundos).
- `summary.json`: pasó/falló, motivo, avisos, estadísticas.
- `*.jpg`: capturas de sys-botbase, si las pediste.

Códigos de salida: `0` pasó · `1` falló · `2` error de config · `3` falló la compilación.

### Config

| Clave | Qué es |
|---|---|
| `build.cmd`, `build.cwd` | Comando de compilación (se saltea con `--no-build`) |
| `nro`, `switch_ip` | Archivo a mandar e IP. Sin IP, nxlink busca la consola por broadcast |
| `upload_path` | Dónde queda el `.nro` en la SD (nxlink `-p`), **relativo a `sdmc:/switch/`**: hbmenu le agrega `switch/` adelante y no crea carpetas (`kof2002um-nx/x.nro` → `sdmc:/switch/kof2002um-nx/x.nro`; si la carpeta no existe, el netloader da `open: err=2` y nxlink sale con 1 sin mensaje). Usalo si el port busca su TOML o sus datos al lado del `.nro` |
| `args` | Argumentos para el juego |
| `expect` | Avisos en orden; `within` = segundos máximos desde el aviso anterior |
| `timeout_total` | Corte duro en segundos |
| `stop_after_expect` | `true` = da OK apenas llegan todos los avisos, sin esperar `done` |
| `budget_ms` | Presupuesto por frame (16.667 = 60 fps) |
| `perf_from_mark` | Las estadísticas cuentan solo desde este aviso (ej. `match_start`: sin menús ni cargas). El CSV queda completo |
| `sysbotbase.before_run` | Acciones antes de abrir el netloader (ej. reabrir hbmenu si el port cierra el juego entero al salir) |
| `sysbotbase.on_mark` | Acciones cuando llega un aviso: `click`, `press`, `release`, `wait`, `stick` (`["LEFT", x, y]`), `screenshot` |
| `sysbotbase.on_finish` | Acciones al terminar (ej. salir del juego) |

Botones de sys-botbase: `A B X Y L R ZL ZR PLUS MINUS LSTICK RSTICK DUP DDOWN DLEFT DRIGHT HOME CAPTURE`.

### Otros comandos

```bash
python runner/nxtest.py analyze runs/mi_juego/20261105-120000/perf.csv --budget 16.667
```

```bash
python runner/nxtest.py bot 192.168.0.50 click A
```

```bash
python runner/nxtest.py bot 192.168.0.50 screenshot pantalla.jpg
```

## 4. Probar sin consola

```bash
python runner/nxtest.py run tests/simulacro.json --no-build -- --sim=hang
```

`--sim=ok|hang|crash|fail` simula cada caso con un nxlink falso.

## Para qué sirve cada forma de detectar el menú

1. **`at_mark` en el código**: lo más fiable. Usalo siempre que tengas el código.
2. **`--autotest=escenario`**: el juego navega solo. No hace falta sys-botbase.
3. **sys-botbase + capturas**: para cuando no podés tocar el código. Más frágil.

## Límites

- Si el juego se cuelga feo o salta el error de Atmosphère, el runner lo detecta (no llega el aviso), pero la consola se reinicia a mano.
- Al terminar el `.nro`, hbmenu vuelve y hay que reabrir el netloader (Y). Con sys-botbase el runner lo hace solo.
- Las zonas miden tiempo de CPU del hilo principal. La GPU trabaja en paralelo: si `present` (el swap) tarda mucho, el cuello está en la GPU.
- Frame y zonas son de un solo hilo: llamalas desde el loop principal. `at_input` y `at_record` pueden ir en el hilo del pad, y `at_vblank` en el del tick del juego.

## Ejemplo: un port multihilo (recompilación estática de Xbox 360)

En un port donde el frame termina en otro hilo (el swap de la guest) y la GPU se mide aparte: `at_frame_end(); at_frame_begin();` en el swap; los tiempos de la GPU y de otros hilos se pasan por atómicos y entran al frame con `at_zone_add` en ese mismo swap; `at_record`/`at_input` en la lectura del pad del jugador 1; `at_should_quit()` dispara el mismo cierre que HOME → cerrar (cierra el título entero, por eso `before_run` reabre el netloader). Grabación y bench: `AGENTS.md`, paso 6, con `configs/plantilla_grabar.json` y `configs/plantilla_bench.json`.

## Licencia

devkitnx (header, runner, plantillas, demo y docs) es MIT: ver `LICENSE`. Los binarios de `sd/` tienen sus propias licencias (sys-botbase GPL-3.0, nx-hbmenu/nx-hbloader ISC): ver `sd/CREDITOS.md`.
