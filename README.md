# Znajomy

Postać, z którą rozmawiasz jak z człowiekiem. Nie dostaje roli, tylko ją odkrywa: z tego, jak się do niej zwracasz, dobiera płeć i imię, a z całej rozmowy wynika, kim dla Ciebie jest (kumpel, bliska osoba, rodzic, powiernik). Ma własny charakter, nastroje, dzień, pamięć z wpadkami i potrafi się obrazić, a nawet zamknąć relację.

**Uwaga: to repozytorium jest publiczne.** Nigdy nie wrzucaj do niego haseł, kluczy ani kodu dostępu. Konfiguracja i klucz Gemini zostają na serwerze.

## Jak to działa

- Serwer (Python, bez dodatkowych bibliotek) trzyma "życie" postaci całą dobę: pamięć, nastrój dnia, sen, plany, które się sypią, pisanie pierwszej.
- **Konsekwencję liczy kod**, nie model. Model (Gemini) dostaje tylko stan ("dziś jesteś zły, ostatnio Cię zlał, jesteś urażony") i mówi głosem postaci. Dzięki temu nie jest ugodowy z natury.
- Aplikacja (PWA, `web/`) to tylko ekran rozmowy. Bez suwaków, paneli i wskaźników relacji.

## Wdrożenie na NOWYM serwerze (root@lewym90)

Wklejaj po jednym poleceniu i sprawdzaj, że prompt to `root@lewym90`.

1. Pobranie kodu:
   `git clone https://github.com/lewym90/znajomy.git /opt/znajomy`
2. Plik ustawień:
   `cp /opt/znajomy/deploy/znajomy.env.example /etc/znajomy.env`
3. Wpisanie własnego kodu dostępu (ten kod wpisujesz w aplikacji przy pierwszym uruchomieniu):
   `nano /etc/znajomy.env`
   Zmień linię `ZNAJOMY_CODES=...` na swój kod. Zapis: Ctrl+O, Enter. Wyjście: Ctrl+X. Kodu nie wklejaj do czatu.
4. Zabezpieczenie pliku:
   `chmod 600 /etc/znajomy.env`
5. Uruchomienie usługi:
   `cp /opt/znajomy/deploy/znajomy.service /etc/systemd/system/ && systemctl daemon-reload && systemctl enable --now znajomy`
6. Sprawdzenie, czy działa lokalnie:
   `curl -s http://127.0.0.1:8095/api/health`
   Powinno wyjść `{"ok": true}`.
7. Podpięcie pod Caddy: fragment z `deploy/Caddyfile.snippet` wchodzi do bloku `188-68-247-201.sslip.io`. Wklej wynik `cat /etc/caddy/Caddyfile`, a powiem dokładnie, gdzie go wstawić. Potem: `systemctl reload caddy`.
8. Sprawdzenie z zewnątrz:
   `curl -s https://188-68-247-201.sslip.io/znajomy/api/health`
9. Na iPhonie: otwórz w Safari `https://188-68-247-201.sslip.io/znajomy/`, wpisz kod, potem Udostępnij, "Do ekranu początkowego".

### Powiadomienia (postać pisze pierwsza, gdy aplikacja jest zamknięta)

`pip install --break-system-packages pywebpush` oraz `systemctl restart znajomy`. Potem w aplikacji: menu (⋮), "Włącz powiadomienia". Na iPhonie działa tylko po dodaniu do ekranu początkowego. Bez tego postać pisze pierwsza, ale zobaczysz to dopiero po otwarciu aplikacji.

## Ustawienia (zmienne w `/etc/znajomy.env`)

| Zmienna | Znaczenie |
|---|---|
| `ZNAJOMY_CODES` | kody dostępu, po przecinku |
| `ZNAJOMY_LLM` | `gemini` (domyślnie), `openai` (dowolny model zgodny z API OpenAI, np. Ollama), `mock` (testy) |
| `ZNAJOMY_GEMINI_MODEL` | nazwa modelu Gemini; sprawdź aktualną w dokumentacji Google |
| `ZNAJOMY_INTIMATE_LLM` | opcjonalny osobny dostawca dla rozmów intymnych (patrz niżej) |
| `ZNAJOMY_OPENAI_BASE`, `ZNAJOMY_OPENAI_MODEL` | adres i model dla dostawcy `openai` |

Klucz Gemini jest czytany z `/opt/typer/gemini_key` albo ze zmiennej `GEMINI_API_KEY`.

## Prywatność

Rozmowy są w bazie `/var/lib/znajomy/znajomy.db` na serwerze. Do logów nie trafiają treści wiadomości. W menu jest "Zacznij od nowa (zapomnij wszystko)", które kasuje wszystko o użytkowniku. **Darmowy poziom Gemini może wykorzystywać rozmowy do ulepszania usług Google.** Przy bardzo osobistych treściach rozważ płatny wariant.

## Zasady, które postać zachowuje

- Gdy ktoś szczerze zapyta, czy rozmawia z człowiekiem, odpowiada, że jest postacią stworzoną przez AI (i rozmowa toczy się dalej).
- Przy sygnałach kryzysu (wykrywanych lokalnie i przez analizę) zostaje przy człowieku, mówi prosto i ciepło, odpisuje szybko i nie zbywa numerem telefonu. Przy realnym ryzyku pomaga wciągnąć kogoś bliskiego albo 112 / 116 123 jako część rozmowy.
- Rejestracja wymaga potwierdzenia 18+ i tego, że to AI. Sygnały niepełnoletności wyłączają romans i wątki seksualne na stałe.
- Wątki seksualne: o tym, czy postać ma ochotę ("nie dziś", "za wcześnie"), decyduje kod (nastrój, zaufanie, charakter, wcześniejsze tarcia). Domyślny dostawca nie dostaje poleceń opisywania aktu.

## Testy

`python3 -m unittest tests.test_all` (atrapa modelu, bez sieci i bez klucza).

## Czego jeszcze nie sprawdzono

- Rozmowa z prawdziwym Gemini (adapter sprawdzony tylko na lokalnej atrapie serwera). Pierwsze rozmowy testuj sam i zobacz, czy ton Ci pasuje.
- Powiadomienia push na prawdziwym iPhonie.
- Jakość polszczyzny i "ludzkość" odpowiedzi: to zależy od modelu i będzie wymagało strojenia opisów w `zn/prompts.py` oraz `zn/day.py`.
