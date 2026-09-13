# Faza 4 — Klaster, który sam się pilnuje

> Roadmapa wszystkich faz: [`00-roadmapa.md`](00-roadmapa.md)

W klastrze stoi program, który bez przerwy porównuje repozytorium git z rzeczywistością
i wyrównuje różnicę. I — co ważniejsze — **nic z zewnątrz nie musi wchodzić do klastra**.

## Czym jest Argo CD

Wzorzec widziany już dwa razy. **Terraform:** w pliku piszesz „ma być maszyna z 6 GB",
narzędzie porównuje z rzeczywistością i wyrównuje. **Kontroler HelmChart w k3s:**
w klastrze leży obiekt, kontroler go widzi i instaluje traefika.

Argo CD to ten sam pomysł dla aplikacji, z jedną różnicą: **nie czeka, aż ktoś uruchomi
polecenie**. Siedzi w klastrze i sprawdza repozytorium co kilka minut, w kółko.

### Po co odwracać kierunek

| Bez Argo — push | Z Argo — pull |
| --- | --- |
| Ktoś uruchamia `kubectl apply`: ty z laptopa albo CI. | Klaster **sam pyta** GitHuba. |
| Żeby CI mogło to zrobić, musi mieć **dostęp do API klastra** — czyli trzeba je wystawić do internetu albo wpuścić runnera przez VPN. | Ruch idzie wyłącznie od środka na zewnątrz. Firewall zostaje zamknięty. |

To jest ten argument, od którego zaczęła się cała rozmowa o homelabie.

### Czy to się realnie stosuje

Argo CD jest dziś narzędziem dominującym — projekt CNCF na najwyższym poziomie
dojrzałości, tym samym co Kubernetes.

| Podejście | Kiedy ma sens |
| --- | --- |
| **Argo CD** | Ma interfejs graficzny z podglądem różnic i historią. Cięższy, ale widać, co się dzieje. |
| Flux | Ta sama idea, bez interfejsu. Lżejszy, złożony z małych kontrolerów. |
| bez GitOpsa | CI robi `kubectl apply`. Prościej, ale wraca problem wystawiania API klastra. |

Tryb `core` (bez interfejsu i API) odpadł świadomie — wyrzuciłby dokładnie to, po co
bierzemy akurat Argo.

## Czym jest chart

**Chart to paczka.** Tym dla Kubernetesa, czym `.rpm` dla Fedory: ktoś spakował komplet
plików potrzebnych do zainstalowania programu, nadał temu wersję i wystawił
w repozytorium. Bez charta instalacja Argo CD znaczy napisanie ręcznie kilkudziesięciu
plików YAML.

**Chart to paczka, Helm to instalator.** Helm bierze chart, dokłada twoje ustawienia
(`values`) i wypluwa gotowy YAML.

Dwie wersje, które łatwo pomylić:

```hcl
default = "10.9.0"   # Argo CD v3.5.2
```

`10.9.0` to wersja **paczki**, `v3.5.2` wersja **programu w środku**. Autor charta może
poprawić szablon i wydać `10.9.1` z tym samym Argo CD. Przypinamy wersję paczki.

Ty już masz charty na klastrze: te dwa zakończone zadania `helm-install-traefik`, widoczne
w k9s pod `:jobs`, to chart w akcji.

## Pułapka, która wymusiła podział repo

Najciekawsza rzecz w tej fazie — i lekcja o Terraformie, nie o Argo.

Żeby zainstalować cokolwiek w klastrze, Terraform potrzebuje **kubeconfiga** — a ten
powstaje dopiero po utworzeniu maszyny. Naturalny odruch to dopisać Argo do istniejącej
konfiguracji, i to **nie zadziała**:

> **Konfiguracja providera musi być znana na etapie planowania**, zanim cokolwiek
> powstanie. Nie może zależeć od zasobu tworzonego w tym samym przebiegu. Terraform
> przerwie komunikatem o wartości nieznanej do czasu `apply`, i nie da się tego obejść
> zależnościami.

Rozwiązaniem jest **podział na dwie konfiguracje główne**, każda z własnym stanem:

```
terraform/
├── cluster/     maszyna i k3s      # stan: co stoi na Proxmoksie
└── platform/    Argo CD            # stan: co stoi w klastrze

kolejność: cluster -> kubectl-setup.sh -> platform
```

To nie obejście, tylko właściwy kształt. Te warstwy mają różne cykle życia: maszynę
stawiasz raz na rok, rzeczy w klastrze zmieniasz co tydzień. Osobny stan znaczy też, że
pomyłka w jednej nie dotknie drugiej.

**Przeniesienie nic nie kosztowało** — stan Terraforma to plik leżący w katalogu
konfiguracji, więc przeniesienie katalogu zabiera stan ze sobą. Żadnego `state mv`; po
przenosinach `tofu state list` pokazał te same trzy zasoby.

To także struktura, którą `docs/multiple_env.md` przewidywał dla wielu środowisk. Wyszła
wcześniej i z innego powodu, ale ten sam podział.

## Co konkretnie stawiamy

```hcl
kubernetes_namespace    argocd         # własna przegródka, jak kube-system dla k3s
helm_release            argocd         # chart 10.9.0 -> Argo CD v3.5.2
kubernetes_ingress_v1   argocd-ui      # traefik -> interfejs
```

| Decyzja | Dlaczego |
| --- | --- |
| namespace osobno | Nie zostawiamy jej chartowi, żeby cykl życia był jawny: usunięcie konfiguracji ma po sobie posprzątać. |
| wersja przypięta | Odczytana z repozytorium Helma, nie zgadnięta. Ta sama reguła co przy k3s i obrazach. |
| `server.insecure` | Argo domyślnie podaje własny certyfikat samopodpisany. Za traefikiem dawałoby to podwójne szyfrowanie i ostrzeżenie w przeglądarce. |
| dex wyłączony | Logowanie przez GitHuba czy Google. Bez SSO to pod, który stoi i nic nie robi. |
| ingress własny | Piszemy go sami zamiast włączać ten z charta — widać wprost, co traefik ma robić. |

### Trzy nazwy, które łatwo pomylić

```hcl
resource "kubernetes_ingress_v1" "argocd" {        # ← etykieta dla Terraforma
  metadata {
    name = "argocd-ui"                             # ← nazwa obiektu w klastrze
  }
      service {
        name = "${helm_release.argocd.name}-server"   # ← jedyne prawdziwe odwołanie
      }
```

Pierwsza istnieje tylko w plikach `.tf`. Druga to nazwa widoczna w `:ing`. **Trzecia jako
jedyna na coś wskazuje** — i jest wyliczana, bo chart nazywa zasoby wzorcem
`<wydanie>-<komponent>`. Wpisana na sztywno rozspoiłaby się po cichu przy zmianie nazwy
wydania.

Odwołanie samo tworzy zależność, więc `depends_on` jest zbędne — ta sama zasada co przy
`import_from` w Fazie 3.

## Jak działa Ingress — i czego *nie* robi

> **Ingress nie tworzy żadnego wpisu w DNS.** To najczęstsze nieporozumienie i dokładnie
> powód, dla którego wildcard trzeba dodać ręcznie. Ingress nie ma nawet jak tego zrobić —
> nie wie o istnieniu AdGuarda.

### Dwa niezależne kroki

```
1. DNS — dowiedz się, DO KTÓREJ MASZYNY iść
   argocd.k8s.suwalski.internal  ->  192.168.0.119      (AdGuard, wildcard)

2. HTTP — powiedz maszynie, CZEGO chcesz
   GET / HTTP/1.1
   Host: argocd.k8s.suwalski.internal                   (traefik, Ingress)
```

Pole `host` w Ingressie dopasowuje się do **nagłówka `Host`** w żądaniu HTTP, a nie do
niczego w DNS. Przeglądarka wysyła ten nagłówek zawsze — wpisuje tam nazwę z paska adresu.

### Dowód doświadczalny

| Żądanie | Wynik |
| --- | --- |
| na IP + `Host: argocd.k8s…` | **200** — działa **bez udziału DNS**, nazwa poszła w nagłówku |
| na IP, bez nagłówka | **404** — traefik nie wie, o co chodzi |
| na IP + nieznana nazwa | **404** — żadna reguła nie pasuje |
| przez nazwę | **200** — oba kroki naraz |

Pierwszy wiersz jest najważniejszy: **ten sam adres IP, a odpowiedź zależy wyłącznie od
nagłówka**.

### Dlaczego to dobra wiadomość

Stąd bierze się cała oszczędność. **Wszystkie nazwy wskazują na jeden adres** — i dlatego
jeden wpis wieloznaczny wystarcza na zawsze. Rozróżnianie usług dzieje się dopiero na
maszynie, na podstawie nagłówka, i jest opisane w Ingressach, czyli w kodzie.

To nie wynalazek Kubernetesa. Tak samo działa *virtual hosting* w nginx i Apache od
dwudziestu lat: jeden serwer, jeden adres, wiele stron rozróżnianych nagłówkiem.

**A przy HTTPS?** Nagłówek `Host` jest zaszyfrowany, więc do rozróżnienia służy **SNI** —
nazwa podawana jawnie na początku uzgadniania TLS, zanim ruszy szyfrowanie. Ten sam pomysł,
o warstwę niżej.

**Istnieją narzędzia, które *jednak* tworzą wpisy DNS.** `external-dns` obserwuje Ingressy
i zakłada odpowiadające im rekordy w serwerze DNS — kandydat do zadania „deklaratywny DNS"
z `TODO.md` platformy. Wtedy nawet ten jeden wildcard przestałby być potrzebny.

## Jedna zmiana w DNS i koniec z DNS-em

Interfejs Argo to usługa `ClusterIP` — osiągalna tylko od środka. Zamiast tunelu
`port-forward`, który trzeba trzymać, **jeden wpis wieloznaczny**:

```
*.k8s.suwalski.internal   ->   192.168.0.119
```

Od tej chwili **nie wracasz do DNS-u**. Nowa usługa dostaje Ingress, traefik rozstrzyga
resztę.

### Czemu akurat taka nazwa

- **`.internal`** — ICANN zarezerwowało tę końcówkę do użytku prywatnego, nigdy nie
  stanie się prawdziwą domeną. `.local` jest zajęte przez mDNS i potrafi psuć
  rozwiązywanie nazw.
- **`suwalski`** — bo tak nazywają się istniejące usługi. Skracanie do `suw` daje trzy
  znaki, a kosztuje spójność.
- **podomena `k8s`** — wildcard na płaskim `*.suwalski.internal` **przechwyciłby
  literówki** w nazwach istniejących usług: wpiszesz `nsa` zamiast `nas` i zamiast błędu
  dostaniesz klaster.

> **Na później:** przy `.internal` nigdy nie dostaniesz publicznego certyfikatu — Let's
> Encrypt wystawia tylko dla domen realnie posiadanych. Zapisane w `TODO.md` platformy.

## Pułapka spoza Kubernetesa: VPN przejmujący DNS

Przy pierwszej próbie `dig` nie rozwiązywał **żadnej** nazwy `.internal` — także tych,
które działały od dawna. Przyczyna nie leżała w klastrze:

```
Link 7 (work)
  Current DNS Server: 192.168.3.1
          DNS Domain: ~.
```

Zapis `~.` znaczy „kieruj tu **wszystkie** zapytania domyślnie". Interfejs firmowego VPN-a
zgłosił się jako resolwer dla całego DNS-u, więc pytania o domowe nazwy trafiały do
resolwera, który ich nie zna. AdGuard miał poprawne odpowiedzi — tylko nikt go nie pytał.

Dwie rzeczy warte zapamiętania:

- **„Mój DNS pierwszy, firmowy zapasowy" nie istnieje.** Jeśli resolwer odpowie „nie ma
  takiej nazwy", to pełnoprawna odpowiedź i nikt już nie pyta dalej. Właściwy model to
  **kierowanie po domenach**: nazwy firmowe do firmowego, reszta do domowego.
- **Naprawa przez `resolvectl` nie przeżywa ponownego zestawienia tunelu.** Trwałe
  rozwiązanie wymaga ustawienia domeny kierującej na profilu połączenia.

## Kroki

1. **Wpis wieloznaczny w AdGuardzie** — `*.k8s.suwalski.internal → 192.168.0.119`.
2. **Sprawdź nazwę, zanim cokolwiek zbudujesz** — `dig +short argocd.k8s.suwalski.internal`.
   Jeśli tu nie wyjdzie, interfejs się nie otworzy, choćby Argo wstało bez zarzutu.
3. **Postaw** — `./scripts/platform/tofu-apply.sh`.
4. **Obejrzyj** — k9s: `:po`, `:ing`, `:applications`.
5. **Zaloguj się** — `./scripts/platform/argocd-password.sh`, użytkownik `admin`.

## Jak wyszło naprawdę

```
argocd-application-controller-0        1/1  Running    32Mi
argocd-applicationset-controller-…     1/1  Running    34Mi
argocd-redis-…                         1/1  Running     9Mi
argocd-repo-server-…                   1/1  Running    25Mi
argocd-server-…                        1/1  Running    47Mi
                                                     ──────
                                                      147Mi
```

- **Interfejs odpowiada** — `http://argocd.k8s.suwalski.internal` zwraca HTTP 200.
- **Nazwa usługi zgadła się z konwencją** — chart utworzył `argocd-server`, więc
  wyliczanie z `helm_release.argocd.name` trafiło. Port 80 też.
- **Wpis wieloznaczny wystarczył** — Ingress `argocd-ui` wskazuje na `192.168.0.119`.

**Przeszacowałem pamięć trzykrotnie.** Pisałem „400–500 MiB", wyszło **147 MiB**. Węzeł ma
6 GB, więc pytanie o wymianę kości na 32 GB, wiszące od Fazy 3, można odłożyć.

**Sprostowanie:** `argocd-applicationset-controller` wstał mimo że mowa była o wyłączonych
dodatkach. `dex` i `notifications` faktycznie nie ma, ale ApplicationSet to **osobny
przełącznik w chartcie**, którego nie ruszono. Zostaje — przyda się do generowania wielu
aplikacji z jednego wzorca — ale to było przeoczenie, nie decyzja.

## Czego tu świadomie nie ma

- **Żadnej aplikacji.** Argo stoi, ale niczym jeszcze nie zarządza. Pierwszy
  `Application` to Faza 5.
- **HTTPS.** Ruch w sieci domowej idzie po HTTP; przy `.internal` certyfikat wymagałby
  własnego CA.
- **Logowania przez GitHuba.** Jeden użytkownik `admin` wystarczy.
- **Deklaratywnego DNS-u.** Wpis wieloznaczny dodaje się ręcznie raz. Migracja AdGuarda
  została w `TODO.md` platformy — blokowałaby tę fazę na kilka godzin.
