# Sygnały końca hossy na AI — plan

Plan implementacji notifiera poszlak końca hossy na AI (raz w miesiącu, sygnały green / red
na dwa kanały Discorda) żyje jako dokument:

**[AI Cycle Notifier — plan implementacji](https://claude.ai/artifact/6vZ58frnBqpSo2h7hUyQMn)**

Co jest w dokumencie: architektura i cykl życia checka (`read` z gotowością / `evaluate`),
repo w stylu solid-app-tpl (feature `suwinvtools_server/signals/` + CronJob na obrazie
serwera, stan w Postgresie), `just signals init`, LiteLLM ze structured output na dowolnym
endpoincie `/v1`, dokładny opis każdego sygnału (A1–A2, B1–B4, C1–C2, D1–D3, E1: źródło,
warunek gotowości, odczyt, progi RED / GREEN), format wiadomości, web (pasek ikon, zakładka
Sygnały) oraz fazy implementacji z warunkami odbioru.

Kod: `suwinvtools_server/suwinvtools_server/signals/`, `suwinvtools_web/src/signals/`,
`deploy/chart/templates/signals-cronjob.yaml`. Reguły: AGENTS.md, sekcja 12.2.

Różnice wobec dokumentu, które wyszły przy pisaniu kodu:

- B4 łączy warianty generacji (H100 SXM / NVL / PCIe, H200 / H200 NVL), bo vast.ai ma po
  kilkanaście ofert na wariant; próg ważności to 5 ofert na rodzinę.
- C1 dostaje z OpenRouter jeden dzień na miesiąc (top 20 modeli z poprzedniego dnia) — strona
  rankingów nie ma historii, więc trend buduje się od pierwszego runu.
- A1 czyta wzrost chmur z komunikatów wynikowych (8-K, exhibit 99.1), a nie z inline XBRL —
  komunikat ma też czwarty kwartał, którego 10-K nie rozbija.
- Adres modelu i webhooki są w sekrecie `signals` w klastrze (prywatna infrastruktura,
  publiczne repo), nie w `values.yaml`.
