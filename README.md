# GPS Spoofer pro macOS

Desktopova aplikace pro macOS, ktera umoznuje simulovat GPS polohu na pripojenem iPhonu pres USB kabel. Vyuziva nastroj `pymobiledevice3` pro komunikaci se zarizenim.

## K cemu to slouzi

- Testovani aplikaci zavislych na poloze (mapy, navigace, fitness)
- Simulace pohybu po trase z GPX souboru
- Nastaveni libovolne GPS polohy jednim kliknutim

## Pozadavky

| Pozadavek | Minimum |
|-----------|---------|
| macOS | 12 (Monterey) nebo novejsi |
| Python | 3.9+ |
| iPhone | iOS 17+ s povolenym Developer Mode |
| Pripojeni | USB kabel (Lightning nebo USB-C) |

## Instalace

```bash
# 1. Klonuj/stahni projekt
cd gps-spoofer

# 2. Spust instalacni skript
chmod +x install.sh
./install.sh

# 3. Spust aplikaci
python3 app.py
```

Instalacni skript automaticky:
- Zkontroluje macOS a Python 3
- Nainstaluje Homebrew (pokud chybi)
- Nainstaluje pymobiledevice3

## Pouziti

### 1. Pripoj iPhone

1. Pripoj iPhone k Macu pres USB kabel
2. Na iPhonu potvrd dialog "Duverat tomuto pocitaci?"
3. V aplikaci se zobrazi zeleny indikator

### 2. Spust aplikaci

```bash
python3 app.py
```

Aplikace automaticky:
- Spusti `tunneld` daemon (vyzaduje sudo heslo)
- Detekuje pripojeny iPhone
- Zjisti RSD adresu a port

### 3. Prehrat GPX trasu

1. Klikni "Vybrat soubor" a vyber .gpx soubor
2. Klikni "Spustit trasu"
3. Poloha na iPhonu se bude pohybovat podle bodu v souboru

### 4. Nastavit jednorazovou polohu

1. Zadej souradnice (latitude a longitude)
2. Klikni "Nastavit polohu"
3. iPhone okamzite prepne na zadanou polohu

Priklady souradnic:
- Praha, Staromestske namesti: `50.0880, 14.4208`
- New York, Times Square: `40.7580, -73.9855`
- Tokio, Shibuya: `35.6595, 139.7004`

### 5. Zastavit simulaci

Klikni "Zastavit simulaci" – iPhone se vrati na skutecnou GPS polohu.

## Jak na iPhonu povolit Developer Mode

Developer Mode je nutny pro iOS 17+. Bez nej simulace GPS nebude fungovat.

1. **Pripoj iPhone k Macu** a otevri Xcode (staci otevrit a zavrit)
2. Na iPhonu jdi do **Nastaveni > Soukromi a zabezpeceni**
3. Scrolluj dolu a najdi **Rezimu vyvojare (Developer Mode)**
4. **Zapni** Developer Mode
5. iPhone se restartuje
6. Po restartu potvrd zapnuti Developer Mode

> Pokud polozka "Rezim vyvojare" neni videt, pripoj iPhone k Macu s nainstalovanym Xcode a zkus to znovu.

## GPX soubory

GPX (GPS Exchange Format) je standardni XML format pro ulozeni GPS dat. Obsahuje body trasy se souradnicemi a casovymi razitky.

### Struktura GPX souboru

```xml
<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1">
  <trk>
    <trkseg>
      <trkpt lat="50.0880" lon="14.4208">
        <time>2024-01-01T10:00:00Z</time>
      </trkpt>
      <trkpt lat="50.0868" lon="14.4190">
        <time>2024-01-01T10:01:00Z</time>
      </trkpt>
    </trkseg>
  </trk>
</gpx>
```

### Kde ziskat GPX soubory

- **gpx.studio** (https://gpx.studio) – nakresli trasu na mape a exportuj jako GPX
- **Google Maps** – naplanuj trasu a preved na GPX pomoci online konvertoru
- Slozka `examples/` obsahuje ukazkovy soubor s trasou pres Karluv most v Praze

## Reseni problemu

### iPhone neni detekovany

- Zkontroluj USB kabel (nekterke kabely jsou pouze nabijeci)
- Na iPhonu potvrd "Duverat tomuto pocitaci"
- Zkus odpojit a znovu pripojit kabel
- Restartuj iPhone i Mac

### Chyba s tunneld / sudo heslem

- `tunneld` vyzaduje administratorska opravneni (sudo)
- Pri spusteni aplikace se zobrazi systemovy dialog pro heslo
- Pokud dialog nezobrazil, restartuj aplikaci
- Pokud tunneld nestaruje, zkus rucne: `sudo python3 -m pymobiledevice3 remote tunneld`

### Simulace nefunguje v cilove aplikaci

- Nektere aplikace (napr. Pokemon GO) maji detekci spoofingu
- Zkus nejdriv jednoduchou aplikaci (Apple Mapy, Google Maps)
- Po zastaveni simulace muze trvat par sekund nez se GPS vrati

### Tunel neni pripraven

- Tunneld potrebuje cas na vytvoreni tunelu (5-15 sekund)
- Pockat na zeleny indikator a zpravu "Tunel pripraven"
- Pokud tunel nevznikne do 30 sekund, restartujte aplikaci

### iOS verze neni podporovana

- Aplikace podporuje iOS 17 a novejsi
- Pro starsi iOS verze je potreba jiny postup (bez RSD)
- Aktualizujte iPhone na nejnovejsi iOS

### pymobiledevice3 neni nalezen

- Spustte `install.sh` znovu
- Nebo rucne: `pip3 install pymobiledevice3`
- Ujistete se ze `~/.local/bin` je v PATH

## Technicke poznamky

### Jak to funguje

1. **tunneld daemon** – Aplikace spusti `pymobiledevice3 remote tunneld` se sudo opravnenimi. Tento daemon vytvori sifrovany tunel mezi Macem a iPhonem pres USB. Z jeho vystupu se ziska RSD (Remote Service Discovery) adresa a port.

2. **RSD (Remote Service Discovery)** – iOS 17+ pouziva novy protokol pro komunikaci s vyvojovymi nastroji. Kazde pripojeni iPhonu generuje novou RSD adresu a port (napr. `fd71:abcd:1234::1 12345`).

3. **DVT (Developer Tools)** – Prikazy `simulate-location` jsou soucasti Developer Tools protokolu. Umoznuji nastavit, prehrat (z GPX) nebo smazat simulovanou polohu.

4. **GPX prehravani** – `pymobiledevice3` cte body z GPX souboru a postupne nastavuje polohu podle casovych razitek. Rychlost pohybu odpovida casovym rozdilum mezi body.

### Architektura aplikace

```
app.py
  ├── TunneldManager    – Spousti/zastavuje tunneld, parsuje RSD
  ├── DeviceDetector    – Detekuje pripojeny iPhone pres usbmux
  ├── GPSSimulator      – Ovlada simulate-location prikazy
  └── GPSSpoofApp       – PyQt6 GUI, hlavni okno
```

Vsechny operace s iPhonem bezi v samostatnych threadech aby GUI nezamrzlo.
