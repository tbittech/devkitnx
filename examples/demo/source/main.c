/*
 * Demo de devkitnx: un "juego" mínimo con intro -> menú -> partida,
 * para ver cómo se integra autotest.h en un port.
 *
 * En Switch:  make            (genera demo.nro)
 * En PC:      gcc -I../../include source/main.c -o demo   (para probar el runner sin consola)
 */
#define AUTOTEST_IMPLEMENTATION
#include "autotest.h"

#include <stdio.h>
#include <string.h>

#ifdef __SWITCH__
#include <switch.h>
#endif

enum { ST_INTRO, ST_MENU, ST_MATCH };

/* Trabajo falso para que las zonas midan algo. */
static volatile unsigned sink;
static void fake_work(unsigned n) { unsigned i; for (i = 0; i < n; i++) sink += i * 2654435761u; }

int main(int argc, char **argv)
{
    int state = ST_INTRO, menu_cursor = 0;
    unsigned state_frames = 0;
    uint64_t prev = 0;

    /* 1. Primero que nada: inicializa sockets + nxlinkStdio y lee los argumentos. */
    at_init(argc, argv, 0);

#ifdef __SWITCH__
    PadState pad;
    consoleInit(NULL);
    padConfigureInput(1, HidNpadStyleSet_NpadStandard);
    padInitializeDefault(&pad);
    while (appletMainLoop() && !at_should_quit())
#else
    while (!at_should_quit())
#endif
    {
        uint64_t buttons = 0, scripted, down;

        at_frame_begin();

        /* 2. Input: lo real, salvo que el replay (--at-input) diga otra cosa. */
#ifdef __SWITCH__
        padUpdate(&pad);
        buttons = padGetButtons(&pad);
        if (buttons & HidNpadButton_Plus) break;
#endif
        if (at_input(&scripted)) buttons = scripted;
        down = buttons & ~prev;
        prev = buttons;

        /* 3. Lógica, medida como zona. */
        at_zone_begin("logic");
        fake_work(20000);
        state_frames++;
        switch (state) {
        case ST_INTRO:
            /* Con --autotest se salta la intro, como haría un port con sus logos. */
            if (state_frames > 90 || at_enabled() || (down & AT_BTN_A)) {
                state = ST_MENU; state_frames = 0;
                at_mark("menu_ready");
            }
            break;
        case ST_MENU:
            if (down & AT_BTN_DOWN) menu_cursor = (menu_cursor + 1) % 3;
            if (down & AT_BTN_UP)   menu_cursor = (menu_cursor + 2) % 3;
            /* --autotest=practica entra directo; si no, espera A (de la persona, del replay o de sys-botbase). */
            if ((down & AT_BTN_A) || strcmp(at_scenario(), "practica") == 0) {
                state = ST_MATCH; state_frames = 0;
                at_log("modo elegido: %d", menu_cursor);
                at_mark("match_start");
            }
            break;
        case ST_MATCH:
            if (at_enabled() && state_frames >= 300) {
                at_mark("match_end");
                at_done(0);           /* fin de la prueba, el loop sale solo */
            }
            break;
        }
        at_zone_end("logic");

        /* 4. Render, también como zona. En la partida "cuesta" más. */
        at_zone_begin("render");
        fake_work(state == ST_MATCH ? 120000 : 40000);
#ifdef __SWITCH__
        printf("\x1b[1;1Hdevkitnx demo  estado=%d  cursor=%d  frame=%llu   \n",
               state, menu_cursor, (unsigned long long)at_frame());
        consoleUpdate(NULL);
#endif
        at_zone_end("render");

        at_frame_end();
    }

#ifdef __SWITCH__
    consoleExit(NULL);
#endif
    at_shutdown();
    return 0;
}
