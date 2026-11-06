# devkitnx — instrucciones para IA: automatizar pruebas y medir FPS de un port homebrew de Nintendo Switch

*AGENTS.md for AI coding agents: Nintendo Switch homebrew port test automation, FPS benchmark on real hardware, nxlink + sys-botbase, input record/replay.*

Sos una IA ayudando a un dev a medir y probar **su** port homebrew de Switch con devkitnx, en la consola real, sin copiar el `.nro` a mano. Seguí los pasos en orden. Cada paso tiene una verificación: no pases al siguiente si falla. Detalles de la API y del runner: `README.md`.

## Reglas fijas

- **No instales nada en la PC del dev.** Si falta algo, decile qué instalar y esperá.
- **No escribas en la SD del dev ni instales el sysmodule sin un "sí" explícito** para esa acción.
- **Nada del juego en este repo**: ROMs, ISOs, XEX/XBE, assets extraídos, packs (`*.nxpack`, `*.nxidx`), claves (`prod.keys`), ni el `.nro` del port. Las corridas (`runs/`) tampoco. Antes de un commit, mirá `git status` y respetá `.gitignore`; si el port del dev genera otro tipo de archivo con contenido del juego, agregalo a `.gitignore`.
- **Nunca abras una conexión de prueba al puerto 28280** (netloader) con `Test-NetConnection`, `nc`, etc.: hbmenu la acepta, falla con "error 11" y cierra el netloader. Para saber si la consola está, usá ping o el puerto 6000 de sys-botbase.
- `nxlink -p` es **relativo a `sdmc:/switch/`**: `-p miport/miport.nro` queda en `sdmc:/switch/miport/miport.nro`. Con `-p switch/...` el netloader da `open: err=2` y nxlink sale con exit 1 sin explicar nada.
- Los argumentos del juego no pueden tener espacios (nxlink los separa por espacio).

## 1. Revisar la PC

| Qué | Cómo verificar | Si falta |
|---|---|---|
| devkitPro (devkitA64 + libnx) | existe `$DEVKITPRO` o `C:\devkitPro`, y `devkitA64/bin/aarch64-none-elf-gcc --version` responde | instalar devkitPro (pacman `switch-dev`) |
| nxlink | `nxlink --help` (está en `devkitPro/tools/bin/`) | viene con `switch-tools` |
| Python 3.8+ | `python --version` | instalar Python 3 |
| Firewall (Windows) | regla de entrada para **el `nxlink.exe` que va a usar la config** | sin esto el `.nro` sube pero no llega nada de stdout (`-s`) |

Si el firewall solo deja pasar un `nxlink.exe` (puede haber dos copias, ej. `C:\devkitPro\...` y otra), fijá ese en la clave `"nxlink"` de la config.

## 2. Preguntarle al dev

Juntá estas respuestas antes de tocar nada:

1. IP de la Switch (Configuración → Internet).
2. Carpeta del port, ruta del `.nro` que genera y comando de build.
3. ¿Tiene el código fuente del port?
   - **Sí** → se integra `include/autotest.h` (paso 5): marcas `at_mark`, tiempos por zona, replay de inputs.
   - **No** → solo se puede lanzar el `.nro`, esperar y sacar capturas con sys-botbase (`on_mark`/`on_finish` con `screenshot`). Decile que sin fuente no hay medición de frames.
4. Qué escena quiere medir y cómo se llega a ella desde el arranque (lo usás en el paso 6).
5. Dónde busca el port sus datos y su config en la SD (para elegir `upload_path`: tiene que quedar al lado de ellos).

## 3. Preparar la SD (con permiso)

`sd/` tiene la estructura de la raíz de la SD:

| Archivo | Para qué |
|---|---|
| `Netloader.nsp` | Forwarder (title ID `016DCB8E8C090000`, probado en consola) que se instala (DBI, Tinfoil, etc.) y queda como ícono en el HOME. Abre `sdmc:/switch/netloader-nx.nro` en **modo título** (toda la RAM, a diferencia del Álbum). El NSP no se copia a la SD como archivo: se instala |
| `switch/netloader-nx.nro` | El netloader que lanza ese NSP: espera el `.nro` de nxlink en el puerto 28280 |
| `atmosphere/contents/430000000000000B/` | sys-botbase (sysmodule): botones, capturas, puerto 6000. `flags/boot2.flag` lo arranca con la consola |

Pasos:
1. Pedile permiso para copiar `sd/switch/` y `sd/atmosphere/` a la raíz de su SD (lector de tarjeta o MTP) y para instalar el sysmodule. Copiá solo después del "sí". No pises archivos que ya tenga sin preguntar.
2. Que instale el NSP con su instalador de títulos y reinicie la consola (sys-botbase arranca en el boot).
3. Pedile que deje el ícono "Netloader" **primero en la fila del HOME** (abrirlo una vez alcanza: el último título usado queda primero).

Cómo se abre el netloader sin tocar la consola (con sys-botbase andando):
```
python runner/nxtest.py bot <IP> click HOME
python runner/nxtest.py bot <IP> click A
```
HOME vuelve al menú y A abre el primer ícono, que es el NSP, y `netloader-nx.nro` queda escuchando directo, sin apretar Y. Hacelo antes de cada corrida, también cuando el port terminó y la consola quedó en el HOME. Las plantillas de `configs/` ya lo traen: `sysbotbase.before_run: [{"click":"HOME"},{"wait":2},{"click":"A"},{"wait":4}]` con `"open_netloader": false` (`open_netloader` aprieta Y, que es para el netloader de hbmenu, no para este NRO).

Verificación: con `bot <IP> screenshot pantalla.jpg` tiene que verse el netloader esperando.

## 4. Probar la conexión, en este orden

1. **Sin consola**: `python runner/nxtest.py run tests/simulacro.json --no-build -- --sim=ok` → exit 0 y `PASÓ`. Probá también `--sim=hang` y `--sim=crash` (deben dar exit 1).
2. **Comando inofensivo contra la consola**: `python runner/nxtest.py bot <IP> screenshot prueba.jpg` → aparece el JPG. Si no conecta: ¿sys-botbase instalado, consola reiniciada, misma red?
3. **Demo**: compilá `examples/demo` (`make`), abrí el netloader (paso 3) y corré una copia de `configs/plantilla.json` con `"nro": "../examples/demo/demo.nro"`, `"upload_path": "devkitnx-demo/demo.nro"`, sin `build` y con la IP y el nxlink del dev. Tiene que llegar `[AT] mark boot` y terminar con `done code=0`.

## 5. Integrar en el port (solo con fuente)

1. Copiá `include/autotest.h` al port (o agregá `include/` a sus includes). En **un** `.c/.cpp`: `#define AUTOTEST_IMPLEMENTATION` antes del include.
2. Al principio de `main`: `at_init(argc, argv, 0)`. Usá `AT_INIT_NO_SOCKETS` si el port ya hace `socketInitialize`/`nxlinkStdio`. Si el port manda stdout a otro lado (un log por TCP con `dup2`), que no lo haga cuando `at_enabled()`.
3. Loop principal: `at_frame_begin()` / `at_frame_end()` por frame, zonas `at_zone_begin/end("nombre")` (máx. 16). Si el frame termina en otro hilo (ej. el swap de un emulador), poné `at_frame_end(); at_frame_begin();` en el swap y llevá ahí con `at_zone_add` los tiempos medidos en otros hilos.
4. Lectura del pad del jugador 1, después de leer los botones:
   ```c
   buttons = at_record(buttons);                 // --at-record (devuelve sin el botón de marca)
   uint64_t s; if (at_input(&s)) buttons = s;    // --at-input
   ```
   Estas dos sí se pueden llamar desde otro hilo. El resto, desde el hilo del frame.
5. `at_mark("...")` en los puntos que el runner tiene que esperar (menú listo, escena cargada).
6. Salida: cuando `at_should_quit()` da 1, que el port cierre como lo cierra el usuario, y que llame a `at_shutdown()` antes de salir (escribe el `END` de la grabación).
7. Config: copiá `configs/plantilla.json` a `configs/<port>.json` y completá cada `<...>` con lo que sabés del proyecto del dev: lo que te respondió en el paso 2 y lo que ves en su repo (Makefile o CMake para el build y la ruta del `.nro`, dónde busca sus datos para el `upload_path`, que es relativo a `sdmc:/switch/`). Agregá a `expect` las marcas `at_mark` que pusiste y a `args` los flags propios del port que haga falta. Lo que no puedas deducir, preguntalo; no inventes rutas. Las configs de cada dev no se suben al repo (`.gitignore`); solo las plantillas.

Verificación: el build del port compila sin warnings nuevos, y una corrida con `--autotest --perf --at-exit-after=600` da `PASÓ` y deja `perf.csv` con filas.

## 6. Grabación y replay de la escena (guía para el dev)

Preguntale al dev el camino exacto desde el arranque hasta la escena (qué menús, qué opciones, cuánto dura la escena que quiere medir) y armale estos pasos con sus palabras:

1. Config de grabación: copiá `configs/plantilla_grabar.json` a `configs/<port>_grabar.json` y completala igual que en el paso 5. `<escena>` es un nombre corto sin espacios para la escena (ej. `pelea`, `nivel1`).
   Si el port tiene una opción para que la lógica avance una vez por frame mostrado (ej. en un emulador o recompilación, un vblank por swap), usala igual al grabar y al reproducir: el replay cuenta frames, no segundos.
   Si la lógica del juego corre a su propio ritmo (no un tick por frame mostrado), llamá `at_vblank()` en cada tick de la lógica y agregá `--at-clock=vblank` a los `args` de grabar **y** del bench: así el replay no se desfasa cuando cambian los fps. Una grabación hecha sin ese reloj se convierte reproduciéndola una vez con `--at-convert=sdmc:/.../bench_input_vb.txt`.
2. Abrí el netloader y corré `python runner/nxtest.py run configs/<port>_grabar.json --no-build`.
3. El dev juega **desde el arranque**, con la cruceta o el stick izquierdo (el stick queda grabado como cruceta; el stick derecho y la posición analógica no se graban). Solo botones del jugador 1.
4. Cuando empieza la escena, el dev aprieta **MINUS** una vez. Eso escribe `<frame> @<escena>` en el archivo y el juego no lo recibe (el replay tampoco lo aprieta). Si MINUS hace algo en ese juego, elegí otro botón que no use (`--at-record-mark=ZR:<escena>`).
5. Juega la escena el tiempo que se quiera medir y cierra el juego de la forma normal del port (la que llega a `at_shutdown`). Al cerrar se escribe `<frame> END`.
6. El archivo queda en la SD, en `sdmc:/switch/<port>/bench_input.txt`. No hace falta traerlo a la PC: el replay lo lee de ahí. Si el juego se colgó al cerrar y falta el `END`, la corrida del bench termina por `--at-exit-after`.
7. Config del bench: copiá `configs/plantilla_bench.json` a `configs/<port>_bench.json` y completala (misma `<escena>` y misma carpeta que en la grabación). Ya trae `--at-exit-at-end`, `"perf_from_mark"` (las estadísticas cuentan desde la marca) y la escena en `expect`.
8. `python runner/nxtest.py run configs/<port>_bench.json --no-build` → `runs/<name>/<fecha>/summary.json` (fps promedio, p95/p99 por zona) y `perf.csv`.

Formato del archivo (se puede editar a mano): una línea `<frame> <botones>` por cambio, botones `A B X Y L R ZL ZR PLUS MINUS UP DOWN LEFT RIGHT LSTICK RSTICK` unidos con `+`, `-` = nada, `<frame> @nombre` = marca, `<frame> END` = fin. Ejemplo en `inputs/ejemplo_menu_a_partida.txt`.

Si el replay se desincroniza (las cargas tardan distinto y los botones caen en otro menú), revisá en `log.txt` en qué frame llegó cada marca y agregá esperas en el archivo: corré todos los frames siguientes hacia adelante.

## Créditos y licencias de lo que hay en `sd/`

Ver `sd/CREDITOS.md`. Si cambiás algo de `sd/`, mantené ese archivo al día.
