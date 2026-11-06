# Créditos y licencias de `sd/`

| Archivo | Proyecto | Autores | Licencia |
|---|---|---|---|
| `atmosphere/contents/430000000000000B/exefs.nsp` | sys-botbase — https://github.com/olliz0r/sys-botbase | olliz0r y colaboradores | GPL-3.0 (`licencias/sys-botbase-LICENSE.txt`). Binario sin cambios de la release **v2.5** (`sys-botbase.nsp`, 95457 bytes); su código fuente: https://github.com/olliz0r/sys-botbase/tree/v2.5 |
| `switch/netloader-nx.nro` | basado en nx-hbmenu — https://github.com/switchbrew/nx-hbmenu | nx-hbmenu Authors (switchbrew) | ISC (`tools/netloader-nsp/src/nx-hbmenu/LICENSE.md` en el proyecto de origen) |
| `Netloader.nsp` (title ID `016DCB8E8C090000`) | forwarder que abre `sdmc:/switch/netloader-nx.nro`; armado a mano por el autor de devkitnx | — | el forwarder carga nx-hbloader (switchbrew, ISC) |

El NRO se armó con las fuentes de `tools/netloader-nsp/` del proyecto de origen. El NSP **no** sale de `build-nsp.sh` de esa carpeta (ese no anduvo): es uno hecho a mano y probado en consola. Los textos ISC de nx-hbloader y nx-hbmenu y el GPL-3.0 de sys-botbase están en `sd/licencias/` (no copiarlos a la SD; son para el repo).

El NSP se armó con las claves de la consola del autor; las claves no van en el repo.
