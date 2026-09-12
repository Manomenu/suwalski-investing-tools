# Roadmapa deploymentu

Jedyne miejsce, gdzie trzymamy podział na fazy. Pozostałe pliki w tym katalogu opisują
*jak* i *dlaczego* dla pojedynczej fazy — nie powtarzają tej listy.

Cel: aplikacja chodzi non stop na homelabie, postawiona tak, jak stawia się na chmurze —
tylko chmurą jest Proxmox.

## Fazy

| # | Faza | Co powstaje | Warunek odbioru |
| --- | --- | --- | --- |
| 1 ✅ | Konteneryzacja | Dwa obrazy, jeden origin, compose jako harness | `./scripts/infra/up.sh` → strona i solver działają |
| 2 ✅ | CI w GitHub Actions | Lint i testy na PR; na masterze obrazy do GHCR z tagiem `sha-<commit>` | Tag widoczny w Packages, testy blokują merge |
| 3 | Terraform: VM i k3s | `bpg/proxmox` stawia VM z cloud-init, cloud-init instaluje k3s | k9s z laptopa pokazuje węzeł Ready |
| 4 | Terraform: Argo CD | Ostatnia rzecz robiona Terraformem — dalej klaster zarządza sobą sam | UI Argo dostępne przez Tailscale |
| 5 | Helm chart i Argo Application | Chart w tym repo, pinowane tagi w repo homelabu. Cache dostaje dysk 5 GB | Synced / Healthy, cache przeżywa restart poda |
| 6 | Pętla deployu | Push → obraz → commit `chore(deploy)` w repo homelabu → Argo podmienia pody | Commit → nowy pod bez ręcznej komendy |
| 7 | Widoczność i higiena | `kube-prometheus-stack`, alerty na Discorda, retencja obrazów w GHCR | Zapchany dysk → powiadomienie; stare tagi znikają same |
| 8 | Nice to have | Rzeczy opcjonalne, bez terminu — patrz niżej | — |

## Dwa repo

- **`suwalski-investing-tools`** (to repo) — kod, Dockerfile'e, CI, a od Fazy 5 także Helm
  chart. Repo **publikuje obrazy**; nie decyduje, co biegnie.
- **`suwalski-platform`** — Terraform (VM, k3s, Argo CD) i pliki Argo z pinowanymi tagami.
  Repo **decyduje, co biegnie**.

Chart mieszka przy kodzie, bo kształt deploymentu zmienia się razem z nim (nowy env var =
jeden PR). Wersje mieszkają w repo homelabu, bo „która wersja gdzie stoi" to stan
środowiska.

## Decyzje obowiązujące we wszystkich fazach

- **Deploy jest pull-based.** Argo CD w klastrze sam odpytuje GitHuba. Nic z zewnątrz nie
  wchodzi do klastra, więc API Kubernetesa nigdy nie trafia do internetu.
- **Budowanie to nie deployowanie.** Każdy commit na masterze dostaje obraz, ale nic go nie
  uruchamia. Co biegnie, wynika z pliku w repo homelabu.
- **Tag obrazu to `sha-<commit>`, nigdy `latest`.** Tag musi wskazywać dokładnie jeden
  build, inaczej „uruchom tę wersję" przestaje cokolwiek znaczyć. **Bez wersjonowania
  semver** — numery produktu nie niosą tu żadnej informacji ponad skrót commita.
- **Historia deployów to historia pliku**, nie wskaźnik gałęzi. `git log` na pliku z tagiem
  mówi kiedy, co i czyją ręką; rollback to `git revert`.
- **Sekrety nie wchodzą do obrazów.** W klastrze przychodzą jako Secret.
- **Nic nie rośnie bez limitu.** Cache ma dysk stałego rozmiaru, rejestr ma retencję, a to,
  co i tak może puchnąć, ma alert.

## Retencja obrazów (Faza 7)

Osobna notka, bo temat łatwo przecenić albo przeoczyć.

Każdy commit na masterze zostawia dwa obrazy. Brzmi groźnie, ale **obrazy współdzielą
warstwy**: zmiana w kodzie Pythona podmienia tylko ostatnią warstwę, nie całe 382 MB.
Realny przyrost na commit to megabajty, nie setki megabajtów.

Dlatego retencja nie jest pilna i świadomie czeka do Fazy 7 — wtedy będzie widać prawdziwe
liczby zamiast zgadywanego progu. Plan: reguła „trzymaj N ostatnich wersji, kasuj
starsze", z wyjątkiem tagów, na które wskazuje aktualnie repo homelabu. Kasowanie obrazu,
który stoi w klastrze, jest jedynym realnym sposobem, żeby sobie tym zaszkodzić.

## Faza 8 — nice to have

Nie blokują niczego i żadna nie ma terminu. Trafiają tu rzeczy, które świadomie odłożyliśmy,
żeby nie zginęły w historii rozmowy.

**Wyniki testów widoczne w pull requeście.** Dziś, żeby zobaczyć, co padło, trzeba wejść
w logi przebiegu. Ładniej byłoby mieć podsumowanie na samej stronie pull requesta — tabelę
z testami, czasami i tym, który konkretnie się wywalił.

Czeka, bo **dotyka kodu repo, nie tylko CI**: `test-solution.sh` musiałby produkować raport
w formacie maszynowym (`pytest --junitxml`), a to zmiana w skrypcie, którego dziś używamy
lokalnie i w CI dokładnie tak samo. Dopiero na tym akcja raportująca mogłaby coś narysować.
Trzeba więc najpierw rozstrzygnąć, czy skrypt ma zawsze zapisywać plik z wynikami, czy
tylko na żądanie — i nie zepsuć przy tym prostoty „jedna komenda, ta sama u ciebie i w CI".

**Przypięcie akcji do konkretnego SHA.** `@v4` to gałąź, którą autor może przesunąć.
Przypięcie do skrótu commita jest odporniejsze, ale wymaga narzędzia, które to odświeża —
czyli w praktyce razem z Dependabotem.

**Skanowanie podatności obrazów.** Naturalne rozszerzenie CI, ale sensowne dopiero, gdy
pipeline stoi i wiadomo, co właściwie skanujemy oraz co robimy ze znalezieniem.
