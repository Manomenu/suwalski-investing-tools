# Faza 3 — Maszyna z pliku

> Roadmapa wszystkich faz: [`00-roadmapa.md`](00-roadmapa.md)

Maszyna wirtualna i Kubernetes na niej, opisane tekstem w repo
[`suwalski-platform`](https://github.com/Manomenu/suwalski-platform). Skasujesz ją przez
pomyłkę — jedno polecenie odtwarza ją identycznie.

## Czemu Terraform, a nie skrypt

Skrypt opisuje **kroki**: „stwórz maszynę, nadaj jej 6 GB". Uruchom drugi raz — spróbuje
stworzyć drugą albo wywali się, że pierwsza istnieje. Żeby był bezpieczny, musisz sam
dopisać sprawdzanie stanu, a to po roku połowa skryptu.

Terraform opisuje **stan docelowy**: „ma istnieć maszyna o tej nazwie, z 6 GB". Nie ma —
utworzy. Jest i się zgadza — nie zrobi nic. Ma 4 GB — podniesie. Porównywanie różnicy jest
wbudowane.

To rozróżnienie nazywa się **deklaratywnie** kontra **imperatywnie**, a cecha „uruchom ile
razy chcesz, wynik ten sam" to **idempotentność**.

## Stan — najczęstsza pułapka

Terraform musi wiedzieć, **które rzeczy w Proxmoksie są jego** — masz tam siedem innych
maszyn, których nie tykamy. Notuje to w `terraform.tfstate`. Przy każdym uruchomieniu
porównuje trzy źródła: pliki `.tf` (co ma być), stan (co już zrobiłem), API Proxmoksa (jak
jest naprawdę). Różnica to plan.

Stąd reguła: **cokolwiek zrobisz klikając w interfejsie, najbliższy `apply` cofnie.** To
nie złośliwość, tylko dokładnie to, o co prosisz.

Stan **nie idzie do gita**: opisuje żywą infrastrukturę i jest generowany. Lockfile
providerów przeciwnie — jest kontrolowany ręcznie i ma być commitowany.

## Skąd Terraform wie, jakie pola istnieją

```
resource "proxmox_virtual_environment_vm" "k3s" {
         └──────── TYP ────────────────┘  └─ NAZWA ─┘
            z providera, coś znaczy         moja, dowolna
```

`"k3s"` to nazwa, którą wymyśliłem — mogłaby brzmieć `"maszynka"`. Znaczenie niesie typ.

Provider zawiera **schemat** — maszynowy opis wszystkich swoich typów i pól. Terraform
czyta go przy `init` i porównuje z twoim plikiem, lokalnie. Dlatego literówka
(`nodename` zamiast `node_name`) wychodzi, zanim cokolwiek połączy się z Proxmoksem.

Schemat obejrzysz w trzech miejscach: dokumentacja providera w rejestrze (generowana
z niego), podpowiedzi w VS Code (czytane z `.terraform/`, więc **dopiero po `tofu init`**),
oraz `tofu providers schema -json`.

## cloud-init

**Obraz chmurowy** to gotowy, zainstalowany system w jednym pliku — bez instalatora. Ale
wstaje bez użytkownika, klucza i adresu. Uzupełnia to **cloud-init**: przy pierwszym
starcie czyta plik z instrukcjami i wykonuje je. To standard AWS-a, Azure'a i Google
Cloud; Proxmox robi to samo.

Dlaczego to lepsze niż zalogować się i wpisać polecenia: przepis jest w repo, a nie
w historii twojej powłoki.

## Warstwy wartości

| Gdzie | Co | W gicie |
| --- | --- | --- |
| `default` w `variables.tf` | decyzje projektowe: wersja k3s, rozmiar maszyny | tak |
| `proxmox.auto.tfvars` | fakty o instalacji: `aoostar`, `local-lvm`, `vmbr0`, `.119` | **tak** |
| `secrets.auto.tfvars` | token API i klucze | nie |

Zmienna zależna od środowiska **nie dostaje `default`** — inaczej skopiowanie repo na inny
Proxmox skończyłoby się cichą próbą postawienia maszyny na nieistniejącym węźle.

Końcówka `.auto.tfvars` powoduje automatyczne wczytanie, bez `-var-file` przy każdym
poleceniu. Reguła szczegółowa przy wielu środowiskach: patrz `docs/multiple_env.md`
w repo platformy.

## Rzeczy, które nas ugryzły

1. **`content_type = "iso"`** — Proxmox 9 rozdziela „nośnik do napędu" (`iso`) od „dysku do
   zaimportowania" (`import`). Import z `iso` kończy się odmową: *has wrong type 'iso'*.
   Po zmianie na `import` plik może wrócić do prawdziwego rozszerzenia `.qcow2`.
2. **Snippety i import wyłączone na storage'u** — `local` domyślnie ma tylko
   `iso,vztmpl,backup`. Bez `snippets` nie ma gdzie wgrać cloud-init, bez `import` nie ma
   skąd wziąć dysku.
3. **Przestarzały zasób** — `proxmox_virtual_environment_download_file` znika w 1.0.
   Zmiana na `proxmox_download_file` była darmowa, **bo stanu jeszcze nie było**; po
   `apply` wymagałaby `tofu state mv`.
4. **Wyjście do `eval`** — `output` zwracający gotową komendę wygląda wygodnie, ale
   zależy od katalogu, wymaga bycia w `terraform/`, a przy błędzie oddaje do `eval`
   komunikat z kodami kolorów. Od tego są skrypty.

## Skrypty w repo platformy

```
scripts/
├── kubeconfig.sh              pobiera kubeconfig i od razu sprawdza
├── kubectl/
│   ├── setup.sh               ustawia KUBECONFIG: na stałe i w tej powłoce
│   └── list-nodes.sh          węzły + obciążenie, działa bez KUBECONFIG
└── tofu/
    ├── validate-and-format.sh fmt + validate, lokalnie, bez Proxmoksa
    ├── plan.sh                pokazuje, co zrobi
    └── apply.sh               robi to; --yes-man pomija pytanie
```

**Czym jest kubeconfig:** plik mówiący `kubectl`, gdzie jest klaster, kim jesteś i jak się
uwierzytelnić. Bez niego `kubectl` zakłada klaster lokalny i wali w `localhost:8080` —
stąd błąd *„connection to the server localhost:8080 was refused"*. Nie znaczy on, że
klaster leży, tylko że `kubectl` nie wie o jego istnieniu.

**Czemu `setup.sh` trzeba sourcować:** proces potomny nie może ustawić zmiennej w powłoce
rodzica. Uruchomiony normalnie skrypt zapisze fragment dla nowych powłok; `source` ustawi
też bieżącą. Uwaga na `set -euo pipefail` w sourcowanym pliku — obowiązywałby twoją
interaktywną powłokę, więc skrypt włącza go tylko przy normalnym uruchomieniu.

## Trzy pojęcia, które wracają wszędzie

### Przestrzeń nazw — przegródka na *nazwy*, nie na maszyny

Przestrzeń nazw **nie dzieli sprzętu**. Pod z `kube-system` i pod z `default` mogą stać na
tym samym węźle. Dzieli **nazwy** — żeby dwie aplikacje mogły mieć usługę `api` i się o nią
nie pobić. Przy okazji jest uchwytem na uprawnienia i limity, ale **sama z siebie nie jest
ścianą**: pody z różnych przestrzeni domyślnie się dogadują.

Praktyczna konsekwencja: narzędzia pokazują *jedną* przestrzeń naraz, zwykle `default` —
u ciebie pustą. Pusty ekran wygląda wtedy jak awaria. W k9s zdejmuje to `0`, w kubectl `-A`.

### Kontekst — na co właściwie celujesz

Kubeconfig to **trzy listy**: klastry (gdzie), użytkownicy (kim jesteś), konteksty (co
z czym, plus domyślna przestrzeń). Bieżący kontekst to wskaźnik na jeden z nich.

```
clusters:  [default]        # server: https://192.168.0.119:6443
users:     [default]
contexts:  default -> cluster=default  user=default  ns=(brak → default)
current:   default
```

Przy jednym klastrze wszystko nazywa się `default` i pojęcie wygląda na zbędne. Sens
pojawia się przy kilku — kontekst na homelab, na pracę, na testy. **Dlatego narzędzia mówią
„kontekst", a nie „klaster"**: adres to za mało, trzeba wiedzieć, kim się przedstawiasz.

Stąd `No context configured` w logu k9s znaczyło: „nie mam kubeconfiga, więc nie wiem ani
gdzie, ani jako kto".

### Usługa — stała nazwa przed nietrwałymi podami

Pody są wymienne: umiera, wstaje nowy, dostaje **inny adres**. Usługa daje **stały adres
i nazwę** przed zmienną grupą podów.

```
usługa traefik   10.43.224.39      # 10.43.x — adresy usług, stałe
   └─ pod        10.42.0.8:8000    # 10.42.x — adresy podów, zmienne

nslookup traefik.kube-system.svc.cluster.local
  Address: 10.43.224.39
```

Nazwa DNS to `usługa.przestrzeń.svc.cluster.local`. W tej samej przestrzeni wystarczy sama
`traefik`. **To ten mechanizm, dzięki któremu w Fazie 5 nginx odezwie się do API po nazwie**,
nie po adresie.

### `TYPE` — trzy szczeble tej samej drabiny

Każdy typ **dokłada** coś do poprzedniego, nie zastępuje go.

| Typ | Co daje |
| --- | --- |
| `ClusterIP` | Domyślny. Adres i nazwa **tylko wewnątrz klastra**. Tak działają `kubernetes`, `kube-dns`, `metrics-server`. |
| `NodePort` | To samo **plus port na każdym węźle**. Surowe, ale działa bez żadnej infrastruktury. |
| `LoadBalancer` | To samo **plus prośba do platformy o adres zewnętrzny**. Tak zadeklarowany jest `traefik`. |

Ciekawostka twojego klastra: chmury nie ma, a `EXTERNAL-IP` i tak jest wypełnione adresem
węzła. Prośbę obsłużył `klipper-lb` z DaemonSetu `svclb-traefik` — zajął port na węźle
i przepycha ruch do usługi. Najprostsza możliwa implementacja tego samego kontraktu.

## Ściąga: co wpisać i czym to jest

k9s pokazuje pod `?` **klawisze**, ale nie ma podglądu **komend** — a to ich właśnie się
nie pamięta. Te same nazwy działają w `kubectl` po słowie `get`.

### Co uruchamia pody

| Wpisujesz | Czym to jest |
| --- | --- |
| `:po` | **Pod** — najmniejsza jednostka. Jeden lub kilka kontenerów dzielących adres IP. Pody są wymienne: umiera, wstaje nowy, z innym adresem. |
| `:deploy` | **Deployment** — „ma działać N sztuk tego poda, gdziekolwiek się zmieszczą". Obsługuje wydania: podnosi nowe pody, zanim zwinie stare. |
| `:rs` | **ReplicaSet** — warstwa pośrednia Deploymentu, jedna na każdą wersję. Sam jej nie tworzysz; służy do wycofywania zmian. |
| `:ds` | **DaemonSet** — „po jednym podzie na *każdym* węźle, zawsze". Do rzeczy, które muszą być wszędzie: zbieranie logów, sieć, `klipper-lb`. |
| `:sts` | **StatefulSet** — jak Deployment, ale pody mają trwałe nazwy (`db-0`, `db-1`) i własne dyski. Do baz danych. |
| `:jobs` | **Job** — zadanie do wykonania *raz*, do końca. Tak k3s zainstalował traefika. |
| `:cj` | **CronJob** — Job odpalany według harmonogramu. |

### Sieć

| Wpisujesz | Czym to jest |
| --- | --- |
| `:svc` | **Service** — stała nazwa i adres przed zmienną grupą podów. Kolumna `TYPE` mówi, jak daleko sięga. |
| `:ep` | **Endpoints** — konkretne adresy podów stojących w tej chwili za usługą. Pierwsze miejsce, gdy usługa nie odpowiada: pusta lista znaczy „nic nie pasuje do selektora". |
| `:ing` | **Ingress** — reguły „ta domena i ścieżka do tej usługi". Puste do Fazy 5. |
| `:no` | **Node** — maszyna. |
| `:ns` | **Namespace** — przegródka na nazwy, nie na sprzęt. |

### Konfiguracja i dyski

| Wpisujesz | Czym to jest |
| --- | --- |
| `:cm` | **ConfigMap** — ustawienia podawane podowi jako zmienne środowiskowe albo pliki. |
| `:secret` | **Secret** — to samo, ale dla haseł. Uwaga: domyślnie tylko **zakodowane base64**, nie zaszyfrowane. |
| `:pvc` | **PersistentVolumeClaim** — *prośba* o dysk: „potrzebuję 5 GB". To ty piszesz. |
| `:pv` | **PersistentVolume** — konkretny dysk, który tę prośbę zaspokoił. Zwykle powstaje sam. |
| `:sc` | **StorageClass** — *rodzaj* dysku, z którego tworzy się te konkretne. U ciebie `local-path`. |

### Reszta, na którą się natkniesz

| Wpisujesz | Czym to jest |
| --- | --- |
| `:ev` | **Event** — dziennik klastra: co utworzono, czego nie dało się zaplanować, co zrestartowano. |
| `:crd` | **CustomResourceDefinition** — nowy typ obiektu dołożony do API. Stąd `ingressroutes` i `helmcharts`. |
| `:sa` | **ServiceAccount** — tożsamość, którą pod przedstawia się API klastra. |
| `:hpa` | **HorizontalPodAutoscaler** — automatyczne zwiększanie liczby podów pod obciążeniem. |

> **Reguła, która oszczędza zapamiętywania:** skróty są te same, których używa `kubectl`.
> Jeśli działa `kubectl get ds`, to w k9s zadziała `:ds`. Pełną listę dla *twojego* klastra
> wypisuje `kubectl api-resources`.

## Zabawa w k9s

**k9s nie wymaga żadnego setupu** — czyta ten sam kubeconfig co `kubectl`. Od momentu, gdy
`KUBECONFIG` jest ustawione, po prostu działa. To nie osobne narzędzie z własnym dostępem,
tylko inny sposób patrzenia na to samo API.

Warto pozwiedzać teraz, póki klaster jest pusty i wszystko widać:

| Klawisz | Co zobaczysz |
| --- | --- |
| `:po`, potem `0` | wszystkie pody ze wszystkich przestrzeni nazw |
| `:no` | twój węzeł; `Enter` wchodzi w szczegóły |
| `:svc` | usługi — zobaczysz `traefik` z adresem węzła |
| `d` | `describe` zaznaczonego obiektu |
| `l` | logi na żywo |
| `s` | powłoka w podzie |
| `?` | ściąga ze skrótami |
| `:q` | wyjście |

Szczególnie zajrzyj do **`traefik`** — to ta niezależna warstwa brzegowa opisana w Fazie 1
przy okazji „czemu są dwa nginxy". k3s instaluje ją sam, a w Fazie 5 zacznie wpuszczać
ruch do twojej aplikacji. Warto ją zobaczyć, zanim cokolwiek zacznie robić.

Obok stoi **`local-path-provisioner`** — to on podłoży dysk pod 5-gigabajtowy wolumen
cache'a z Fazy 5.

Skórka Catppuccin Mocha **i** konfiguracja k9s są w dotfiles (`shared/.config/k9s/`). Oba,
bo bez `config.yaml` — w którym siedzi `ui.skin` — plik z kolorami leżałby nieużywany.

## k9s dalej — co jest pod spodem

Wszystko poniżej stoi **dziś** na klastrze. Nic nie trzeba instalować.

> **Dwa klawisze na start:** `?` pokazuje skróty *twojej* wersji k9s, a `Ctrl-A` listę
> wszystkich typów zasobów z ich skrótami. Przypisania klawiszy zmieniają się między
> wydaniami, więc to `?` jest źródłem prawdy, nie żadna ściąga.

> **Dwa powody, dla których widok bywa pusty — żaden nie oznacza awarii.**
>
> *Filtr przestrzeni nazw.* k9s otwiera się w jednej przestrzeni, zwykle `default` — a ta
> jest pusta, bo wszystko z k3s siedzi w `kube-system`. Wciśnij `0`, czyli „wszystkie
> przestrzenie".
>
> *Brak kontekstu.* k9s czyta `KUBECONFIG` **przy starcie**. Terminal otwarty przed
> ustawieniem zmiennej nie zobaczy klastra w ogóle.
>
> Rozstrzyga log `~/.local/state/k9s/k9s.log`: `No resources found for v1/pods in
> "default" namespace` znaczy „działa, tylko pusto", a `No context configured` znaczy „nie
> wiem, gdzie jest klaster".

### Cztery przestrzenie nazw

`:ns`. **`kube-system`** to jedyna, w której coś się dzieje — tam k3s trzyma swoje części.
**`default`** jest pusta i to do niej trafi twoja aplikacja. **`kube-public`** trzyma dane
czytelne bez logowania, a **`kube-node-lease`** to techniczne „bicie serca" węzłów.

### Łańcuch własności: skąd się bierze pod

```
Deployment  traefik
  └─ ReplicaSet  traefik-59b7647586
       └─ Pod    traefik-59b7647586-l5shx
```

> **W k9s nie zobaczysz tego jako ścieżki.** `Enter` na Deploymencie przeskakuje **od razu
> do podów** — k9s pokazuje wynik, nie drogę. ReplicaSet otwierasz wprost przez `:rs`,
> a związek widać na podzie pod `d`: `Controlled By: ReplicaSet/traefik-59b7647586`.

**Po co warstwa pośrednia?** ReplicaSet istnieje dla *wydań*. Zmiana obrazu w Deploymencie
nie przerabia istniejących podów — powstaje **nowy** ReplicaSet, w nim podnoszą się nowe
pody, a stary dopiero wtedy się zwija. Wycofanie zmiany to powrót do poprzedniego
ReplicaSetu. Hash w nazwie to skrót definicji poda.

### Deployment kontra DaemonSet

| | `traefik` | `svclb-traefik` |
| --- | --- | --- |
| typ | Deployment | DaemonSet |
| obraz | `mirrored-library-traefik:3.7.8` | `rancher/klipper-lb:v0.4.17` |
| znaczy | „ma być **N sztuk**, gdziekolwiek" | „**po jednym na każdym węźle**, zawsze" |

Dlaczego tak: `klipper-lb` nasłuchuje na porcie *węzła*, więc musi być wszędzie tam, gdzie
ruch może wejść. Traefikowi wszystko jedno, na którym węźle stoi.

### Czemu traefik wygląda, jakby był dwa razy

Na liście podów są `traefik-…` i `svclb-traefik-…`, jeden z ReplicaSetem, drugi
z DaemonSetem. To **dwa zupełnie różne programy** — myli wyłącznie nazwa.

```
traefik-59b7647586-l5shx        kontener:  traefik
                                obraz:     mirrored-library-traefik:3.7.8

svclb-traefik-5bbd9bdf-wphs2    kontenery: lb-tcp-80, lb-tcp-443
                                obraz:     rancher/klipper-lb:v0.4.17
```

**`svclb-traefik` nie zawiera traefika.** W środku siedzi `klipper-lb` — mały
przekierowywacz portów. Nazwa powstaje ze schematu `svclb-` + **nazwa usługi**, którą ten
pod obsługuje. Wystawisz jutro usługę `sklep` jako LoadBalancer i pojawi się `svclb-sklep`.

### A skąd dwa kontenery w tym jednym podzie

**Klipper-lb robi jeden kontener na każdy port usługi.** Usługa `traefik` wystawia 80 i 443,
więc powstały dwa przekierowywacze — `lb-tcp-80` i `lb-tcp-443`.

```
# kontener lb-tcp-80
port hosta  80 -> 80
SRC_PORT    80
DEST_PORT   80
DEST_IP     10.43.224.39   # ClusterIP usługi traefik
```

Cała droga żądania z zewnątrz:

```
przeglądarka -> 192.168.0.119:80    port na węźle, zajęty przez lb-tcp-80
             -> 10.43.224.39:80     ClusterIP usługi traefik
             -> 10.42.0.8:8000      pod traefika
```

Ten pod **nie** używa sieci hosta (`hostNetwork: false`) — zajmuje tylko konkretny port
(`hostPort`). Dostaje dokładnie tyle, ile trzeba, żeby złapać ruch na 80 i 443.

### Jedna usługa, wszystkie trzy szczeble naraz

Drabina `ClusterIP → NodePort → LoadBalancer` — usługa `traefik` ma je **wszystkie trzy
jednocześnie**:

```
ClusterIP      10.43.224.39      # szczebel 1: adres wewnętrzny
nodePort       30150, 30279      # szczebel 2: porty na węźle
EXTERNAL-IP    192.168.0.119     # szczebel 3: „adres zewnętrzny"
```

Porty 30150 i 30279 przydzieliły się same i nikt ich nie używa — ale istnieją, bo
LoadBalancer **nie zastępuje** NodePorta, tylko go nadbudowuje. Gdyby `klipper-lb` zniknął,
traefik byłby osiągalny pod `192.168.0.119:30150`. Brzydko, ale działa.

### Skąd `EXTERNAL-IP`, skoro nie ma chmury

```
kube-system   traefik    LoadBalancer   10.43.224.39    192.168.0.119
```

Usługa typu **LoadBalancer** w chmurze każe dostawcy postawić prawdziwy rozdzielacz ruchu
i zwrócić jego adres. Tutaj chmury nie ma, a `EXTERNAL-IP` i tak jest wypełnione — **adresem
węzła**. Robi to `klipper-lb`: zajmuje port na węźle i przepycha ruch do usługi. Dlatego
w Fazie 5 strona po prostu odpowie pod `192.168.0.119`.

### Jak k3s zainstalował traefika, nie logując się nigdzie

`:jobs` — dwa zakończone zadania: `helm-install-traefik` i `helm-install-traefik-crd`.
Ustaw się na jednym, wciśnij `l`, przeczytasz log instalacji Helmem.

Mechanizm jest wart zrozumienia, bo to **ten sam wzorzec, który w Fazie 4 przejmie Argo
CD**: w klastrze leżą obiekty `HelmChart` (`:helmchart`), kontroler je obserwuje i dla
każdego uruchamia Joba. Nikt nigdzie nie wchodzi po SSH. **Stan opisany obiektem, kontroler
doprowadza rzeczywistość do zgodności** — ta sama zasada co u Terraforma, tylko w środku
klastra i na okrągło.

### CRD — skąd 38 nowych typów

`:crd`. **CustomResourceDefinition** dokłada do API Kubernetesa nowy rodzaj obiektu. Od
tej chwili `kubectl` i k9s traktują go jak wbudowany.

- **`helm.cattle.io`** — `helmcharts`, `helmchartconfigs`: to dzięki nim działa mechanizm
  wyżej.
- **`traefik.io`** — `ingressroutes`, `middlewares`, `tlsoptions`: własny język Traefika.
  Bogatszy niż standardowy Ingress, ale działa **tylko** z Traefikiem.
- **`gateway.networking.k8s.io`** — Gateway API, następca Ingressu, niezależny od dostawcy.
  Leży gotowy, nieużywany.
- **`k3s.cattle.io`** — rzeczy wewnętrzne k3s.

### Ingress — obejrzyj *pustkę*, zanim przestanie być pusta

`:ing` pokazuje dziś **zero wpisów**. W Fazie 5 pojawi się dokładnie jeden.

Czeka nas wybór: standardowy `Ingress` czy `IngressRoute` od Traefika. Weźmiemy **Ingress**
— z tego samego powodu, dla którego obraz nie ma wpisanego na sztywno adresu API: przenośne
wygrywa z wygodnym u jednego dostawcy.

### Miejsce na dysk, którego jeszcze nie ma

`:sc` pokazuje jedną klasę: `local-path (default)`. `:pvc` jest puste. W Fazie 5 poprosimy
o 5 GB na cache i ta klasa wytnie kawałek dysku węzła.

### Dwa widoki, które ratują przy awarii

`y` na obiekcie pokazuje **pełny YAML tak, jak trzyma go API** — razem z polami, których
nikt nie wpisywał, a które dopisał serwer. Najuczciwszy obraz tego, co siedzi w klastrze.

`:events` to **własny dziennik klastra**: co utworzono, czego nie dało się zaplanować, co
zrestartowano. Gdy coś nie wstaje, a logi są puste, odpowiedź zwykle jest tutaj.

## Co faktycznie sprawdziliśmy

- `tofu plan` → `3 to add, 0 to change, 0 to destroy`, zero ostrzeżeń.
- `apply` → maszyna 119 wstała, cloud-init zostawił znacznik `/var/lib/cloud/k3s-ready`.
- `kubectl get nodes` → `k3s-1 Ready control-plane v1.36.4+k3s1` — wersja **zgodna
  z przypiętą w kodzie**, nie „jakaś najnowsza".
- Obciążenie na starcie: 872 MiB z 6 GB (14%), 2% CPU.
