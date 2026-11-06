#!/usr/bin/env python3
"""
devkitnx — runner de pruebas para ports homebrew de Switch.

  python nxtest.py run   configs/mi_juego.json [--no-build] [--ip 192.168.0.50]
  python nxtest.py analyze runs/mi_juego/20261105-120000/perf.csv [--budget 16.667]
  python nxtest.py bot   192.168.0.50 click A          (probar sys-botbase a mano)
  python nxtest.py bot   192.168.0.50 screenshot captura.jpg

Flujo de `run`: compila -> (sys-botbase abre el netloader) -> nxlink manda el .nro
-> sigue las líneas [AT] que imprime el juego -> chequea los avisos esperados con
tiempo límite -> guarda log, CSV de frames y resumen en runs/<juego>/<fecha>/.

Códigos de salida: 0 pasó, 1 falló, 2 error de configuración, 3 falló la compilación.
"""
import argparse
import csv
import json
import os
import queue
import shutil
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXIT_PASS, EXIT_FAIL, EXIT_CONFIG, EXIT_BUILD = 0, 1, 2, 3

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def die(msg, code=EXIT_CONFIG):
    print(f"[devkitnx] ERROR: {msg}")
    sys.exit(code)


# --------------------------------------------------------------------------- #
# sys-botbase
# --------------------------------------------------------------------------- #

BOT_BUTTONS = {"A", "B", "X", "Y", "L", "R", "ZL", "ZR", "PLUS", "MINUS",
               "LSTICK", "RSTICK", "DUP", "DDOWN", "DLEFT", "DRIGHT", "HOME", "CAPTURE"}


class SysBot:
    """Cliente mínimo de sys-botbase (TCP, comandos de texto terminados en \\r\\n)."""

    def __init__(self, ip, port=6000, timeout=10.0):
        self.sock = socket.create_connection((ip, port), timeout=timeout)

    def cmd(self, text):
        self.sock.sendall((text + "\r\n").encode())

    @staticmethod
    def _btn(b):
        b = b.upper()
        if b not in BOT_BUTTONS:
            raise ValueError(f"botón de sys-botbase desconocido: {b} (válidos: {sorted(BOT_BUTTONS)})")
        return b

    def click(self, b):
        self.cmd(f"click {self._btn(b)}")

    def press(self, b):
        self.cmd(f"press {self._btn(b)}")

    def release(self, b):
        self.cmd(f"release {self._btn(b)}")

    def stick(self, side, x, y):
        self.cmd(f"setStick {side.upper()} {int(x)} {int(y)}")

    def screenshot(self, path):
        self.cmd("pixelPeek")
        buf = bytearray()
        while not buf.endswith(b"\n"):
            chunk = self.sock.recv(1 << 16)
            if not chunk:
                break
            buf += chunk
        data = bytes.fromhex(buf.strip().decode("ascii", "replace"))
        Path(path).write_bytes(data)
        return path

    def close(self):
        try:
            self.cmd("detachController")
        except OSError:
            pass
        self.sock.close()


def run_actions(bot, actions, run_dir, log):
    """Ejecuta una lista de acciones: click/press/release/wait/stick/screenshot."""
    for act in actions:
        try:
            if "wait" in act:
                time.sleep(float(act["wait"]))
            elif "click" in act:
                bot.click(act["click"])
            elif "press" in act:
                bot.press(act["press"])
            elif "release" in act:
                bot.release(act["release"])
            elif "stick" in act:
                side, x, y = act["stick"]
                bot.stick(side, x, y)
            elif "screenshot" in act:
                p = bot.screenshot(run_dir / f"{act['screenshot']}.jpg")
                log(f"[devkitnx] captura guardada: {p.name}")
            else:
                log(f"[devkitnx] acción desconocida: {act}")
            if "wait" not in act:
                time.sleep(float(act.get("delay", 0.15)))
        except (OSError, ValueError) as e:
            log(f"[devkitnx] sys-botbase falló en {act}: {e}")
            return False
    return True


# --------------------------------------------------------------------------- #
# Análisis de frames
# --------------------------------------------------------------------------- #

def percentile(sorted_vals, p):
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def analyze(columns, rows, budget_ms):
    """columns: ['frame','total_us',zona...]; rows: listas de int (faltantes = 0)."""
    if not rows:
        return {"frames": 0}
    out = {"frames": len(rows), "budget_ms": budget_ms, "columns": {}}
    for ci, name in enumerate(columns[1:], start=1):
        vals = sorted(r[ci] / 1000.0 for r in rows)
        out["columns"][name] = {
            "avg_ms": round(sum(vals) / len(vals), 3),
            "p95_ms": round(percentile(vals, 0.95), 3),
            "p99_ms": round(percentile(vals, 0.99), 3),
            "max_ms": round(vals[-1], 3),
        }
    total_avg = out["columns"].get("total_us", {}).get("avg_ms", 0)
    out["fps_avg"] = round(1000.0 / total_avg, 2) if total_avg > 0 else 0.0
    over = [r for r in rows if r[1] / 1000.0 > budget_ms]
    out["over_budget"] = len(over)
    out["over_budget_pct"] = round(100.0 * len(over) / len(rows), 2)
    worst = sorted(rows, key=lambda r: r[1], reverse=True)[:10]
    out["worst_frames"] = [
        {columns[i]: (r[i] if i == 0 else round(r[i] / 1000.0, 3)) for i in range(len(columns))}
        for r in worst
    ]
    return out


def print_analysis(a):
    if not a.get("frames"):
        print("[devkitnx] sin datos de frames (¿faltó --perf o at_frame_end?)")
        return
    print(f"\n== Frames: {a['frames']}  |  {a.get('fps_avg', 0):.1f} fps prom  |  presupuesto {a['budget_ms']:.2f} ms  |  "
          f"se pasaron: {a['over_budget']} ({a['over_budget_pct']}%)")
    print(f"{'zona':<16}{'prom':>9}{'p95':>9}{'p99':>9}{'max':>9}   (ms)")
    for name, s in a["columns"].items():
        label = "FRAME TOTAL" if name == "total_us" else name
        print(f"{label:<16}{s['avg_ms']:>9.2f}{s['p95_ms']:>9.2f}{s['p99_ms']:>9.2f}{s['max_ms']:>9.2f}")
    print("\nPeores frames:")
    for w in a["worst_frames"][:5]:
        parts = ", ".join(f"{k}={v}" for k, v in w.items() if k not in ("frame", "total_us"))
        print(f"  frame {w['frame']}: {w['total_us']} ms  [{parts}]")


def read_perf_csv(path):
    with open(path, newline="") as f:
        r = csv.reader(f)
        columns = next(r)
        rows = [[int(x or 0) for x in row] + [0] * (len(columns) - len(row)) for row in r]
    return columns, rows


# --------------------------------------------------------------------------- #
# run
# --------------------------------------------------------------------------- #

def find_nxlink(cfg):
    if cfg.get("nxlink"):
        v = cfg["nxlink"]
        return v if isinstance(v, list) else [v]
    candidates = []
    dkp = os.environ.get("DEVKITPRO", "")
    if dkp and not dkp.startswith("/opt/"):
        candidates.append(Path(dkp) / "tools" / "bin" / "nxlink.exe")
        candidates.append(Path(dkp) / "tools" / "bin" / "nxlink")
    candidates += [Path("C:/devkitPro/tools/bin/nxlink.exe"), Path("/opt/devkitpro/tools/bin/nxlink")]
    for c in candidates:
        if c.exists():
            return [str(c)]
    w = shutil.which("nxlink")
    if w:
        return [w]
    die("no encuentro nxlink. Instalá switch-tools de devkitPro o poné \"nxlink\" en la config.")


def load_config(path):
    path = Path(path).resolve()
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        die(f"no pude leer la config {path}: {e}")
    base = path.parent

    def rel(p):
        return str((base / p).resolve()) if p and not Path(p).is_absolute() else p

    cfg["nro"] = rel(cfg.get("nro"))
    if cfg.get("nxlink"):
        nx = cfg["nxlink"] if isinstance(cfg["nxlink"], list) else [cfg["nxlink"]]
        cfg["nxlink"] = [sys.executable if x == "python" else (rel(x) if (base / x).exists() else x)
                         for x in nx]
    if "build" in cfg and cfg["build"].get("cwd"):
        cfg["build"]["cwd"] = rel(cfg["build"]["cwd"])
    cfg.setdefault("name", path.stem)
    return cfg


def reader_thread(stream, q):
    for raw in iter(stream.readline, b""):
        q.put((time.monotonic(), raw.decode("utf-8", "replace").rstrip("\r\n")))
    q.put((time.monotonic(), None))


def cmd_run(args):
    cfg = load_config(args.config)
    ip = args.ip or cfg.get("switch_ip")
    name = cfg["name"]
    run_dir = ROOT / "runs" / name / datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    logf = open(run_dir / "log.txt", "w", encoding="utf-8")
    t_start = time.monotonic()

    log_lock = threading.Lock()

    def log(line, echo=True):
        with log_lock:  # también lo llaman los hilos de sys-botbase
            logf.write(f"{time.monotonic() - t_start:9.3f}  {line}\n")
            logf.flush()
            if echo:
                print(line)

    # 1. Compilar
    build = cfg.get("build")
    if build and not args.no_build:
        log(f"[devkitnx] compilando: {build['cmd']}")
        r = subprocess.run(build["cmd"], shell=True, cwd=build.get("cwd"))
        if r.returncode != 0:
            log(f"[devkitnx] la compilación falló (código {r.returncode})")
            sys.exit(EXIT_BUILD)

    nro = cfg.get("nro")
    if not nro or not Path(nro).exists():
        die(f"no existe el .nro: {nro}")

    # 2. sys-botbase (opcional)
    bcfg = cfg.get("sysbotbase") or {}
    bot = None
    if bcfg.get("enabled"):
        if not ip:
            die("sys-botbase necesita switch_ip en la config o --ip")
        try:
            bot = SysBot(ip, int(bcfg.get("port", 6000)))
            log(f"[devkitnx] conectado a sys-botbase en {ip}")
        except OSError as e:
            die(f"no pude conectar a sys-botbase en {ip}: {e}")
        if bcfg.get("before_run"):
            # ej. volver a abrir hbmenu en modo título cuando el port cierra el juego entero al salir
            log("[devkitnx] acciones before_run")
            run_actions(bot, bcfg["before_run"], run_dir, log)
        if bcfg.get("open_netloader", True):
            log("[devkitnx] abriendo el netloader de hbmenu (Y)")
            bot.click("Y")
            time.sleep(float(bcfg.get("netloader_wait", 1.5)))

    # 3. nxlink
    cmd = find_nxlink(cfg)
    if ip:
        cmd += ["-a", ip]
    if cfg.get("retries"):
        cmd += ["-r", str(cfg["retries"])]
    if cfg.get("upload_path"):
        cmd += ["-p", cfg["upload_path"]]  # dónde queda en la SD (ej. junto a su TOML)
    game_args = list(cfg.get("args", [])) + list(args.extra or [])
    if any(" " in a for a in game_args):
        die("los argumentos del juego no pueden tener espacios (nxlink --args los separa por espacio)")
    if game_args:
        cmd += ["--args", " ".join(game_args)]
    cmd += ["-s", nro]
    log(f"[devkitnx] {' '.join(cmd)}")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    q = queue.Queue()
    reader = threading.Thread(target=reader_thread, args=(proc.stdout, q), daemon=True)
    reader.start()

    expect = list(cfg.get("expect", []))
    on_mark = bcfg.get("on_mark", {}) if bot else {}
    timeout_total = float(cfg.get("timeout_total", 300))
    stop_after_expect = bool(cfg.get("stop_after_expect", False))
    budget_ms = float(cfg.get("budget_ms", 1000.0 / 60))
    # Las estadísticas cuentan solo los frames desde este aviso (ej. "match_start": sin menús ni cargas).
    perf_from_mark = cfg.get("perf_from_mark")
    perf_from_frame = None

    marks, fails, columns, rows = [], [], None, []
    exp_i, exp_since = 0, time.monotonic()
    done_code, reason, ended = None, None, False
    bot_threads = []
    bot_lock = threading.Lock()

    def bot_async(actions):
        def work():
            with bot_lock:
                run_actions(bot, actions, run_dir, log)
        t = threading.Thread(target=work, daemon=True)
        t.start()
        bot_threads.append(t)

    while True:
        now = time.monotonic()
        if now - t_start > timeout_total:
            reason = f"se pasó el tiempo total ({timeout_total:.0f} s)"
            break
        if exp_i < len(expect):
            within = float(expect[exp_i].get("within", 60))
            if now - exp_since > within:
                reason = f"no llegó el aviso '{expect[exp_i]['mark']}' en {within:.0f} s"
                break
        try:
            ts, line = q.get(timeout=0.25)
        except queue.Empty:
            continue
        if line is None:
            ended = True
            break

        is_perf = line.startswith("[AT] perf,")
        log(line, echo=not is_perf)
        if not line.startswith("[AT] "):
            continue
        body = line[5:]

        if is_perf:
            vals = [int(x or 0) for x in body.split(",")[1:]]
            if columns:
                vals += [0] * (len(columns) - len(vals))
                rows.append(vals[:len(columns)])
        elif body.startswith("zones,"):
            new_cols = body.split(",")[1:]
            columns = new_cols  # las zonas solo se agregan al final, las filas viejas se completan con 0
            for r in rows:
                r += [0] * (len(columns) - len(r))
        elif body.startswith("mark "):
            mname = body[5:].split(" ", 1)[0]
            marks.append({"mark": mname, "t": round(ts - t_start, 3)})
            if perf_from_mark and mname == perf_from_mark and perf_from_frame is None and "frame=" in body:
                try:
                    perf_from_frame = int(body.split("frame=")[1].split()[0])
                except ValueError:
                    pass
            if exp_i < len(expect) and expect[exp_i]["mark"] == mname:
                exp_i += 1
                exp_since = ts
            if bot and mname in on_mark:
                bot_async(on_mark[mname])
            if stop_after_expect and expect and exp_i == len(expect):
                done_code = 0
                break
        elif body.startswith("fail"):
            fails.append(body[4:].strip())
        elif body.startswith("done"):
            try:
                done_code = int(body.split("code=")[1].split()[0])
            except (IndexError, ValueError):
                done_code = 1
            # esperar un poco a que nxlink cierre solo
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
            break

    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
    reader.join(timeout=3)  # que termine de pasar a la cola lo que quedó en el pipe

    # Leer lo que haya quedado en la cola (filas de perf del último envío, etc.)
    while True:
        try:
            _, line = q.get_nowait()
        except queue.Empty:
            break
        if line is None:
            break
        log(line, echo=False)
        if line.startswith("[AT] perf,") and columns:
            vals = [int(x or 0) for x in line[10:].split(",")]
            vals += [0] * (len(columns) - len(vals))
            rows.append(vals[:len(columns)])

    for t in bot_threads:
        t.join(timeout=10)
    if bot:
        if bcfg.get("on_finish"):
            run_actions(bot, bcfg["on_finish"], run_dir, log)
        bot.close()

    # 4. Resultado
    missing = [e["mark"] for e in expect[exp_i:]]
    if reason is None:
        if done_code is None and ended:
            reason = "se cortó la conexión sin [AT] done (¿crash, o nxlink no pudo conectar?)"
        elif done_code not in (None, 0):
            reason = f"el juego terminó con code={done_code}"
        elif missing:
            reason = f"faltaron avisos: {', '.join(missing)}"
    if fails and reason is None:
        reason = "el juego reportó fallas"
    passed = reason is None

    analysis = None
    if columns and rows:
        with open(run_dir / "perf.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(columns)
            w.writerows(rows)
        stat_rows = rows
        if perf_from_mark:
            if perf_from_frame is None:
                log(f"[devkitnx] no llegó '{perf_from_mark}': las estadísticas usan todos los frames")
            else:
                stat_rows = [r for r in rows if r and r[0] >= perf_from_frame]
                log(f"[devkitnx] estadísticas desde '{perf_from_mark}' (frame {perf_from_frame}): "
                    f"{len(stat_rows)} de {len(rows)} frames")
        if stat_rows:
            analysis = analyze(columns, stat_rows, budget_ms)
            if perf_from_frame is not None:
                analysis["from_mark"] = perf_from_mark
                analysis["from_frame"] = perf_from_frame
            print_analysis(analysis)

    summary = {
        "game": name, "passed": passed, "reason": reason, "done_code": done_code,
        "marks": marks, "missing_marks": missing, "fails": fails,
        "duration_s": round(time.monotonic() - t_start, 2), "perf": analysis,
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    logf.close()

    print(f"\n[devkitnx] {'PASÓ' if passed else 'FALLÓ'}" + ("" if passed else f": {reason}"))
    print(f"[devkitnx] resultados en {run_dir}")
    sys.exit(EXIT_PASS if passed else EXIT_FAIL)


def cmd_analyze(args):
    columns, rows = read_perf_csv(args.csv)
    a = analyze(columns, rows, args.budget)
    print_analysis(a)


def cmd_bot(args):
    bot = SysBot(args.ip, args.port)
    try:
        if args.action == "screenshot":
            out = args.value or "captura.jpg"
            bot.screenshot(out)
            print(f"guardada {out}")
        elif args.action == "raw":
            bot.cmd(args.value)
        else:
            getattr(bot, args.action)(args.value)
    finally:
        bot.close()


def main():
    ap = argparse.ArgumentParser(description="devkitnx: pruebas automáticas de ports homebrew de Switch")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="compilar, mandar con nxlink y verificar avisos")
    r.add_argument("config")
    r.add_argument("--ip", help="IP de la Switch (pisa switch_ip de la config)")
    r.add_argument("--no-build", action="store_true", help="no compilar, usar el .nro que hay")
    r.set_defaults(func=cmd_run)

    a = sub.add_parser("analyze", help="volver a analizar un perf.csv")
    a.add_argument("csv")
    a.add_argument("--budget", type=float, default=1000.0 / 60, help="ms por frame (por defecto 16.667)")
    a.set_defaults(func=cmd_analyze)

    b = sub.add_parser("bot", help="mandar un comando suelto a sys-botbase")
    b.add_argument("ip")
    b.add_argument("action", choices=["click", "press", "release", "screenshot", "raw"])
    b.add_argument("value", nargs="?")
    b.add_argument("--port", type=int, default=6000)
    b.set_defaults(func=cmd_bot)

    # Todo lo que va después de "--" son argumentos extra para el juego.
    argv = sys.argv[1:]
    extra = []
    if "--" in argv:
        k = argv.index("--")
        argv, extra = argv[:k], argv[k + 1:]
    args = ap.parse_args(argv)
    args.extra = extra
    args.func(args)


if __name__ == "__main__":
    main()
