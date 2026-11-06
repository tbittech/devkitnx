#!/usr/bin/env python3
"""
nxlink falso para probar el runner sin Switch. Acepta los mismos argumentos que
nxlink (-a, -r, --args, -s, archivo.nro) e imprime lo que imprimiría la demo con
autotest.h. Se elige el caso con --sim=X dentro de --args:

  --sim=ok      llega a todo y termina con done code=0   (por defecto)
  --sim=hang    se queda colgado en el menú
  --sim=crash   se corta la conexión en la partida, sin done
  --sim=fail    el juego reporta una falla
"""
import random
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")  # como el juego real: manda UTF-8
argv = sys.argv[1:]
game_args = []
nro = None
i = 0
while i < len(argv):
    a = argv[i]
    if a in ("-a", "--address", "-r", "--retries", "-p", "--path"):
        i += 2
        continue
    if a == "--args":
        game_args = argv[i + 1].split()
        i += 2
        continue
    if a in ("-s", "--server"):
        i += 1
        continue
    nro = a
    i += 1

sim = next((a.split("=", 1)[1] for a in game_args if a.startswith("--sim=")), "ok")
perf = "--perf" in game_args
scenario = next((a.split("=", 1)[1] for a in game_args if a.startswith("--autotest")
                 and "=" in a), "")
t0 = time.monotonic()


def out(s):
    sys.stdout.write(s + "\n")
    sys.stdout.flush()


def ms():
    return (time.monotonic() - t0) * 1000


print(f"Sending {nro}, 297157 bytes")
print("starting server")
out(f"[AT] hello v=1 autotest=1 scenario={scenario} perf={int(perf)}")
out(f"[AT] mark boot t={ms():.1f} frame=0")
random.seed(1)
frame = 0
header = False


def frames(n, render_us):
    global frame, header
    for _ in range(n):
        if perf:
            if not header:
                out("[AT] zones,frame,total_us,logic,render")
                header = True
            logic = random.randint(1500, 2500)
            render = render_us + random.randint(-1000, 1000)
            if frame % 97 == 50:
                render += 9000  # pico: un frame que se pasa del presupuesto
            out(f"[AT] perf,{frame},{logic + render + 300},{logic},{render}")
        frame += 1
        time.sleep(0.001)


frames(1, 4000)
out(f"[AT] mark menu_ready t={ms():.1f} frame={frame}")
if sim == "hang":
    time.sleep(3600)
frames(5, 4000)
out("[AT] log modo elegido: 0")
out(f"[AT] mark match_start t={ms():.1f} frame={frame}")
frames(150, 12000)
if sim == "crash":
    sys.exit(1)
if sim == "fail":
    out("[AT] fail sprite atlas no cargó")
    out(f"[AT] done code=1 frames={frame} t={ms():.1f}")
else:
    frames(150, 12000)
    out(f"[AT] mark match_end t={ms():.1f} frame={frame}")
    out(f"[AT] done code=0 frames={frame} t={ms():.1f}")
out(f"[AT] exit frames={frame} t={ms():.1f}")
