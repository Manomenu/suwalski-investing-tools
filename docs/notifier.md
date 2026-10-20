# AI cycle notifier — plan

Plan implementacji notifiera poszlak końca hossy na AI (raz w miesiącu, sygnały green / red
na dwa kanały Discorda) żyje jako dokument:

**[AI Cycle Notifier — plan implementacji](https://claude.ai/artifact/6vZ58frnBqpSo2h7hUyQMn)**

Co jest w dokumencie: architektura i cykl życia checka (`ready` / `read` / `evaluate`), miejsce
w repo (`suwalski_investing_notifier` + czyste funkcje w libce), `just init`, LiteLLM ze
structured output na dowolnym endpoincie `/v1`, dokładny opis każdego sygnału (A1–A2, B1–B4,
C1–C2, D1–D3: źródło, warunek gotowości, odczyt, progi RED / GREEN), format wiadomości,
docker compose i późniejszy Helm CronJob oraz fazy implementacji z warunkami odbioru.

Kod powstaje na branchu `feature/ai-cycle-notifier`.
