# Faza 1 — Konteneryzacja

> Roadmapa wszystkich faz: [`00-roadmapa.md`](00-roadmapa.md)

> Przewodnik po tym, co zbudowaliśmy i dlaczego. Uwaga: reszta `docs/` jest po angielsku,
> ten katalog świadomie po polsku — to notatki do nauki, nie dokumentacja API.

Dwa obrazy kontenerowe i sposób, w jaki się ze sobą komunikują. Każda decyzja wynika
z jednej zasady: **ten sam obraz, bit w bit, ma działać na laptopie, w CI i w klastrze**,
a wszystko, co różni te miejsca, dociera do niego dopiero przy starcie, jako zmienna
środowiskowa.

## Co powstało

| Plik | Rola |
| --- | --- |
| `suwalski_investing_server/Dockerfile` | FastAPI jako wheel na slim Pythonie. Dwa etapy, nie-root, 382 MB. |
| `suwalski_investing_web/Dockerfile` | `vite build` w Node, a potem już tylko statyczne pliki pod nginx. 56 MB. |
| `suwalski_investing_web/nginx.conf.template` | Jak nginx serwuje SPA i gdzie przekazuje `/api`. |
| `compose.yaml` | Oba obrazy spięte tak, jak spnie je ingress. Harness weryfikacyjny, nie deployment. |
| `.dockerignore` | Trzyma `.venv`, `node_modules` i `.env` poza kontekstem budowania. |

## Zasada, z której wynika cała reszta

W dojrzałym pipelinie obraz jest **artefaktem niezmiennym**. Budujesz go raz, testujesz,
i ten sam obraz promujesz dalej. Jeśli cokolwiek, co różni środowiska, wpadnie do środka
obrazu w trakcie budowania, tracisz tę własność: „przetestowany obraz" i „obraz na
produkcji" stają się dwiema różnymi rzeczami, a testy przestają cokolwiek dowodzić.

Dlatego adres API, katalog cache i user-agent do SEC nie są wypalone w obrazie. Wchodzą
przez środowisko przy starcie kontenera.

> **Praktyczny test:** czy potrafisz wziąć obraz z rejestru, uruchomić go u siebie i
> w klastrze, a jedyną różnicą będzie zestaw zmiennych? Jeśli tak — masz artefakt
> deployowalny. Jeśli musisz przebudować obraz „bo tu jest inny adres" — nie masz.

## Jak lecą requesty

```
                    ┌──────── web · nginx :8080 ────────┐
przeglądarka ──────►│  location /      → dist/          │
 (jeden origin)     │  location /api/  → server :6100 ──┼──► FastAPI ──► Yahoo, SEC
                    └───────────────────────────────────┘
```

Tylko `web` publikuje port. `server` nie jest widoczny z zewnątrz — ani w compose, ani
później w klastrze, gdzie będzie zwykłym ClusterIP.

## Czym właściwie jest nginx — i czemu jest ich dwa

nginx wykonuje dwie zupełnie różne prace, a nazywa się tak samo:

1. **Brama wjazdowa.** Stoi przed wszystkim, kończy TLS, rozdziela ruch po domenie
   i ścieżce. To niezależna warstwa, należąca do infrastruktury.
2. **Serwer HTTP jednej aplikacji.** Ma jeden katalog plików i wysyła je przez HTTP.
   To ta praca, którą wykonuje nginx w naszym obrazie — jest częścią aplikacji.

Na klasycznej maszynie wirtualnej był *jeden* nginx robiący obie prace naraz: serwował
`/var/www/html` i proxował `/api` do gunicorna. Dlatego „nginx" brzmi jak warstwa — przez
dwadzieścia lat nią był. Kontenery to rozdzielają, bo te prace mają różnych właścicieli
i różne cykle życia: routing brzegowy zmienia się przy zmianie domeny, a serwowanie
bundla przy każdym wydaniu frontu.

**Analogia:** nginx jest dla `dist/` tym, czym uvicorn dla FastAPI. Obraz kontenera to
„proces plus wszystko, czego potrzebuje, żeby wstać". Obraz serwera niesie uvicorna i nikt
nie mówi, że uvicorn powinien być osobną warstwą stacku.

Niezależna warstwa nie zniknęła — przeprowadziła się. W klastrze tę pracę wykonuje
**Ingress Controller** (w k3s domyślnie Traefik), jeden na cały klaster, mieszkający
w repo homelabu. Ingress nie mógłby zresztą przejąć serwowania plików: on rozdziela ruch,
a bundla nie ma na dysku.

```
        Ingress Controller (Traefik)      warstwa niezależna, własność platformy
                    │
                    ▼
     ┌─ pod: web ──────────┐        ┌─ pod: server ───────┐
     │  nginx + dist/      │──/api──►  uvicorn + FastAPI  │   runtime aplikacji,
     └─────────────────────┘        └─────────────────────┘   własność repo aplikacji
```

## nginx.conf.template

### 1. Który serwer i dlaczego ten

Po `vite build` zostaje katalog `dist/` — martwy HTML, CSS, JS i fonty. Nie ma już czego
uruchamiać, ale ktoś musi te bajty wysłać przez HTTP.

| Sposób | Waga runtime'u | Co z tym nie tak |
| --- | --- | --- |
| serwer Node (`vite preview`) | ~150 MB + node_modules | Vite wprost pisze, że `preview` nie jest do produkcji. |
| statyki z FastAPI (`StaticFiles`) | 0 MB ekstra | Uczciwa alternatywa. Ale wiąże wydanie frontu z wydaniem backendu. |
| **nginx** | 56 MB | Nic. SPA fallback, cache i proxy deklaratywnie, bez linijki kodu. |

### 2. Po co konfiguracja

Domyślny nginx potrafi wysłać plik spod ścieżki, która istnieje. Potrzebujemy trzech
rzeczy ponad to:

- **SPA fallback.** Pod `/cokolwiek` nie ma pliku — jest tylko `index.html`, a resztę
  rozstrzyga React. Bez `try_files … /index.html` każde odświeżenie poza korzeniem to 404.
- **Przekazanie `/api`.** To, co w developmencie robi proxy w `vite.config.ts`.
- **Polityka cache'owania.** Vite nadaje plikom nazwy z hashem treści, więc te można
  cache'ować na rok. Ale `index.html` nigdy — bo to on wskazuje, który hash jest aktualny.

### 3. Po co `.template`, a nie `.conf`

Bo adres serwera API jest inny w każdym środowisku, a `nginx.conf` nie umie czytać
zmiennych środowiskowych. Składnia `$zmienna` w nginx to *jego własne* zmienne requestu
(`$host`, `$uri`) — bez związku ze środowiskiem procesu.

Obraz nginx rozwiązuje to entrypointem: wszystko z `/etc/nginx/templates/*.template`
przepuszcza przez `envsubst` i zapisuje do `/etc/nginx/conf.d/` — **przy każdym starcie
kontenera**.

```nginx
location /api/ {
    proxy_pass ${API_UPSTREAM}/;        # ← dziura wypełniana przy starcie
    proxy_set_header Host $host;        # ← to zostaje nietknięte
}
```

### 4. Po co filtr `NGINX_ENVSUBST_FILTER`

Tu łatwo o mit. Skrypt entrypointu buduje listę nazw do podstawienia z *całego*
środowiska, przefiltrowaną tym wyrażeniem, i podaje ją `envsubst` jawnie. Bez filtra ta
lista to wszystkie zmienne środowiskowe — a że żadna nie nazywa się `host` ani `scheme`,
nginxowe `$host` i `$scheme` normalnie przeżywają.

Czyli **filtr nie ratuje przed czymś, co dzieje się domyślnie**. Ratuje przed kolizją
nazw, gdy taka zmienna się w środowisku pojawi:

```
# bez filtra, gdy istnieje host=cokolwiek
proxy_set_header Host cokolwiek;
proxy_set_header X-Forwarded-Proto bzdura;

# z filtrem, te same zmienne
proxy_set_header Host $host;
proxy_set_header X-Forwarded-Proto $scheme;
```

To whitelist. Kubernetes sam wstrzykuje zmienne dla każdego Service'u w namespace, Helm
dokłada swoje — a plik ma jedną dziurę i ma z nią zostać. Tanie zabezpieczenie przed
awarią, która nie daje żadnego komunikatu błędu.

## Czemu przeglądarka nie woła API bezpośrednio

`import.meta.env.VITE_API_BASE` jest wkompilowywane w bundle **w momencie builda**. Gdyby
przeglądarka uderzała wprost w API, jego adres zostałby zamrożony w pliku `.js` podczas
budowania obrazu — i obraz przestałby być przenośny.

Origin to schemat + host + port w adresie, pod który uderza **przeglądarka**. Przy proxy
przez `/api` przeglądarka widzi tylko `:8080`; przeskok na `:6100` robi nginx po stronie
serwera. CORS jest mechanizmem wyłącznie przeglądarkowym, więc ruchu serwer→serwer nie
dotyczy.

## Dockerfile serwera, warstwa po warstwie

**Kontekst budowania to katalog główny solucji.** Serwer zależy od biblioteki przez
ścieżkę workspace'u uv, a jedyny `uv.lock` leży w korzeniu. Stąd
`-f suwalski_investing_server/Dockerfile .` — plik mieszka przy projekcie, który opisuje,
ale buduje się z góry. Tak robi każde monorepo z lockfile'em w korzeniu.

**Manifesty przed źródłami.** Warstwa z zależnościami jest droga i zmienia się rzadko;
źródła zmieniają się co commit. Rozdzielenie tych dwóch `COPY` sprawia, że zwykły commit
przebudowuje kilka sekund zamiast kilku minut.

**Dwa etapy.** Etap budujący ma uv, kompilatory i cache. Do finalnego obrazu przechodzi
wyłącznie gotowy `/app/.venv`.

**Nie-root.** `uid=10001` dla serwera, `uid=101` dla nginx — stąd obraz
`nginx-unprivileged` i port 8080 zamiast 80, bo porty poniżej 1024 wymagają roota.

## Cache, który nie jest stanem

W `/var/cache/suwalski-market` mieszkają dwie rzeczy o różnej trwałości, co kod już
rozróżnia: cena i dane TTM starzeją się w minutach, historia roczna ze SEC — w miesiącach.
Ta druga jest droga: 3–5 MB na spółkę i wolne pobranie.

Dlatego w klastrze ten katalog dostanie własny dysk (5 GB) zamiast znikać razem z podem.
To nadal **nie jest stan**: możesz ten dysk skasować i nie stracisz żadnej informacji —
aplikacja pobierze dane jeszcze raz. Tracisz czas, nie dane. Backup jest niepotrzebny, bo
źródłem prawdy są Yahoo i SEC.

**Sztywny rozmiar dysku zastępuje mechanizm sprzątania.** 5 GB to około tysiąca spółek,
a system plików nie pozwoli tego przekroczyć — nie ma scenariusza „rośnie w nieskończoność"
i nie trzeba pisać kasowania najstarszych wpisów. Gdy się zapełni, nic się nie psuje:
`provider.py` traktuje cache jako wygodę, nigdy jako zależność, więc nieudany zapis
degraduje się do zwykłego pobrania z sieci.

Haczyk: taki dysk w k3s obsługuje jeden pod naraz. Przy jednej replice bez znaczenia.

## Rzeczy, które nas ugryzły

1. **`SOLUTION_ROOT`** — biblioteka wylicza korzeń solucji z własnego `__file__`, co działa
   tylko dla instalacji editable. W obrazie pakiet siedzi w site-packages. Stąd jawne
   `SUWALSKI_SOLUTION_ROOT=/app`.
2. **Nazwy obrazów bazowych** — podman odmawia rozwiązywania krótkich nazw bez TTY.
   Wszystkie bazy są pełne (`docker.io/library/python:3.14-slim`), co jest i tak lepszą
   praktyką.
3. **Zdublowany `Cache-Control`** — dyrektywa `expires 1y` sama emituje ten nagłówek,
   a nasz `add_header` dokładał drugi.
4. **`SEC_USER_AGENT`** — czytany bezpośrednio z `os.environ`, nie przez pydantic-settings,
   bo biblioteka nie zależy od `Settings` serwera (używa jej też CLI). Musi być prawdziwą
   zmienną środowiskową, nie samym wpisem w `.env`.

## Co faktycznie sprawdziliśmy

- Pełne przejście przeglądarka → nginx → `/api` → FastAPI → solver: implied growth 4,39%
  dla NVDA.
- `/api/market/NVDA` — 200, snapshot zapisany w cache przez użytkownika `app`.
- SPA fallback: nieistniejąca ścieżka zwraca 200 z `index.html`.
- Nagłówki cache: `no-cache` na `index.html`, `immutable` na hashowanych assetach.
- Oba kontenery nie-root: `uid=10001(app)` i `uid=101(nginx)`.
- `./scripts/test-solution.sh` — sześć kroków, wszystkie PASS.
