# GPX Routes – Praha a Střední Čechy

Simulace jízd MHD (tramvaj, metro, vlak) pro GPS spoofing.

## Reálný čas – komplikované (tramvaj + metro + vlak)

| # | Soubor | Trasa | Body | Doba |
|---|--------|-------|------|------|
| 01 | `01_namesti_miru-beroun_realtime.gpx` | Náměstí Míru → Beroun | 339 | ~80 min |
| 02 | `02_dejvicka-pribram_realtime.gpx` | Dejvická → Příbram | 414 | ~96 min |
| 03 | `03_zizkov-kladno_realtime.gpx` | Žižkov → Kladno | 304 | ~71 min |
| 04 | `04_namesti_miru-nymburk_realtime.gpx` | Náměstí Míru → Nymburk | 277 | ~66 min |

## Reálný čas – metro + vlak

| # | Soubor | Trasa | Body | Doba |
|---|--------|-------|------|------|
| 05 | `05_zlicin-beroun_realtime.gpx` | Zličín → Beroun | 234 | ~52 min |
| 06 | `06_dejvicka-letnany_realtime.gpx` | Dejvická → Letňany | 164 | ~30 min |
| 07 | `07_zlicin-cerny_most_realtime.gpx` | Zličín → Černý Most (celá B) | 241 | ~41 min |
| 08 | `08_hlavni_nadrazi-mlada_boleslav_realtime.gpx` | Hlavní nádraží → Mladá Boleslav | 275 | ~61 min |
| 09 | `09_hlavni_nadrazi-melnik_realtime.gpx` | Hlavní nádraží → Mělník | 240 | ~51 min |
| 10 | `10_hlavni_nadrazi-kladno_realtime.gpx` | Hlavní nádraží → Kladno | 204 | ~43 min |

## Zrychlené verze (2–3 minuty)

| # | Soubor | Trasa | Body | Doba |
|---|--------|-------|------|------|
| 11 | `11_namesti_miru-beroun_fast.gpx` | Náměstí Míru → Beroun | 73 | ~2.4 min |
| 12 | `12_dejvicka-pribram_fast.gpx` | Dejvická → Příbram | 73 | ~2.4 min |
| 13 | `13_zizkov-kladno_fast.gpx` | Žižkov → Kladno | 73 | ~2.4 min |
| 14 | `14_zlicin-cerny_most_fast.gpx` | Zličín → Černý Most | 65 | ~2.1 min |
| 15 | `15_hlavni_nadrazi-mlada_boleslav_fast.gpx` | Hlavní nádraží → Mladá Boleslav | 73 | ~2.4 min |

## Existující trasy (dříve vygenerované)

| Soubor | Trasa | Body | Doba |
|--------|-------|------|------|
| `budejovicka-kolin-fast.gpx` | Budějovická → Kolín (zrychlená) | 91 | ~3 min |
| `budejovicka-kolin_slow.gpx` | Budějovická → Kolín (reálný čas) | 14 | ~70 min |
| `budejovicka-zlicin-metro_realTime.gpx` | Budějovická → Zličín (metro) | 156 | ~43 min |

## Technické parametry

- **Formát:** GPX 1.1
- **Interval bodů (realtime):** 10–20 sekund
- **Interval bodů (fast):** 2 sekundy
- **Simulace zastávek:** 3–5 bodů s drobným posunem (~5 m)
- **Rychlosti:** tramvaj ~18 km/h, metro ~35 km/h, vlak ~70–90 km/h
- **Start:** 2024-04-16T08:00:00Z
