"""IntentDetector V2 — unified V1+V3+ESP32+Inventory."""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple


class IntentType(str, Enum):
    SAVE="save"; SEARCH="search"; UPDATE="update"; DELETE="delete"
    UNDO="undo"; EXIT="exit"; HELP="help"; SUMMARY="summary"
    MODE_TEXT="mode_text"; MODE_VOICE="mode_voice"
    EKSPORT="eksport"; IMPORT="import"; HISTORIA="historia"
    PREFERENCJE="preferencje"; WZORCE="wzorce"
    ADAPT_STYLE="adapt_style"; ADAPT_INSTRUCTION="adapt_instruction"
    ADAPT_ALIAS="adapt_alias"; ADAPT_REMOVE="adapt_remove"
    ADAPT_SHOW="adapt_show"; ADAPT_RESET="adapt_reset"; ADAPT_SIGNAL="adapt_signal"
    WEATHER="weather"; WEATHER_WEEK="weather_week"
    TIMER_SET="timer_set"; TIMER_LIST="timer_list"; TIMER_CANCEL="timer_cancel"
    STOPWATCH_START="stopwatch_start"; STOPWATCH_STOP="stopwatch_stop"
    STOPWATCH_RESET="stopwatch_reset"; STOPWATCH_READ="stopwatch_read"
    TODO_ADD="todo_add"; TODO_LIST="todo_list"; TODO_DONE="todo_done"; TODO_CLEAR="todo_clear"
    HEALTH_STATUS="health_status"; BACKUP_NOW="backup_now"; BACKUP_STATUS="backup_status"
    UNIT_CONVERT="unit_convert"; WEB_SEARCH="web_search"; BRIEFING="briefing"
    INV_ADD="inv_add"; INV_FIND="inv_find"; INV_WHERE="inv_where"
    INV_HOW_MANY="inv_how_many"; INV_STATS="inv_stats"; INV_PRICE="inv_price"
    ESP32_ON="esp32_on"; ESP32_OFF="esp32_off"; ESP32_SET="esp32_set"
    ESP32_STATUS="esp32_status"; ESP32_LIST="esp32_list"
    CHAT="chat"

    # ── V3 — nowe ──────────────────────────────────────────────────────
    REMINDER_SET="reminder_set"; REMINDER_LIST="reminder_list"; REMINDER_CANCEL="reminder_cancel"
    CALENDAR_ADD="calendar_add"; CALENDAR_TODAY="calendar_today"
    CALENDAR_LIST="calendar_list"; CALENDAR_NEXT="calendar_next"; CALENDAR_REMOVE="calendar_remove"
    RESEARCH_SET="research_set"; RESEARCH_LIST="research_list"
    RESEARCH_NOW="research_now"; RESEARCH_CANCEL="research_cancel"; RESEARCH_LATEST="research_latest"
    TTS_STOP="tts_stop"
    HISTORY_SHOW="history_show"; HISTORY_CLEAR="history_clear"


@dataclass
class Intent:
    typ: IntentType
    tresc: str = ""
    stara: str = ""
    nowa: str = ""
    argument: str = ""
    param: str = ""
    wartosc: str = ""
    surowy_tekst: str = ""
    tagi: List[str] = field(default_factory=list)


_KOMENDY: List[Tuple[re.Pattern, IntentType]] = [
    (re.compile(r"^\s*(koniec|wyjdź|wyjdz|zakończ|stop|exit|quit|bye)\s*[.!?]*\s*$", re.I), IntentType.EXIT),
    (re.compile(r"^\s*(pomoc|help|\?)\s*$", re.I), IntentType.HELP),
    (re.compile(r"^\s*(podsumuj |pokaż |pokaz )?pami[eę][cć]?\s*$", re.I), IntentType.SUMMARY),
    (re.compile(r"^\s*tryb\s+tekstowy\s*$", re.I), IntentType.MODE_TEXT),
    (re.compile(r"^\s*tryb\s+(głosowy|glosowy)\s*$", re.I), IntentType.MODE_VOICE),
    (re.compile(r"^\s*(cofnij|undo)\b", re.I), IntentType.UNDO),
    (re.compile(r"^\s*(historia|log)\s*$", re.I), IntentType.HISTORIA),
    (re.compile(r"^\s*(preferencje|moje preferencje)\s*$", re.I), IntentType.PREFERENCJE),
    (re.compile(r"^\s*(wzorce|profil)\s*$", re.I), IntentType.WZORCE),
    (re.compile(r"^\s*(eksport(uj)?|backup)(\s+(.+))?$", re.I), IntentType.EKSPORT),
    (re.compile(r"^\s*(import(uj)?|wczytaj backup)\s+(.+)$", re.I), IntentType.IMPORT),
]

_TR_SAVE   = re.compile(r"\b(zapamiętaj|zapamietaj|zapisz|zanotuj|pami[eę]taj\s+(?:że|ze))\b", re.I)
_TR_UPDATE = re.compile(r"\b(zmień|zmien|popraw|aktualizuj|nadpisz|jednak\s+(jest|mam)|teraz\s+(jest|mam))\b", re.I)
_TR_DELETE = re.compile(r"\b(zapomnij\s+(o|że|ze)|usuń\s+(wpis|notatkę)|skasuj\s+(wpis|to))\b", re.I)
_TR_SEARCH = re.compile(r"\b(gdzie\s+(jest|mam|trzymam)|znajdź|szukaj|co\s+wiesz\s+o|przypomnij)\b", re.I)
_TR_PREF   = re.compile(r"^\s*(wolę|preferuję|lubię|nie lubię)\b", re.I)

_RX_STYLE_LEN  = re.compile(r"^\s*(pisz|odpowiadaj|mów)\s+(krócej|krocej|dłużej|dluzej|normalnie)\s*[.!?]*\s*$", re.I)
_RX_STYLE_TONE = re.compile(r"^\s*(ton|mów)\s+(formalny|formalnie|swobodny|swobodnie|luźniej)\s*[.!?]*\s*$", re.I)
_RX_INSTRUCTION= re.compile(r"^\s*(zawsze|nigdy(?:\s+nie)?|od\s+teraz)\s+(.+?)\s*[.!?]*\s*$", re.I)
_RX_ALIAS_ADD  = re.compile(r"^\s*(alias|skrót)\s+(.+?)\s*[=:]\s*(.+?)\s*[.!?]*\s*$", re.I)
_RX_ADAPT_SHOW = re.compile(r"^\s*(pokaż|moje)?\s*(adaptacje|ustawienia)\s*$", re.I)
_RX_ADAPT_RST  = re.compile(r"^\s*(zresetuj|wyczyść)\s+(adaptacje|ustawienia)\s*$", re.I)
_RX_ADAPT_DEL  = re.compile(r"^\s*usuń\s+(alias|instrukcję)\s+(.+?)\s*[.!?]*\s*$", re.I)

_RX_WEATHER      = re.compile(r"\b(pogoda|temperatura|prognoza|deszcz|śnieg|jaka\s+pogoda)\b", re.I)
_RX_WEATHER_WEEK = re.compile(r"\bprognoza\s+na\s+(tydzień|tydzie[nń])\b", re.I)

_RX_TIMER_SET    = re.compile(r"\b(ustaw|nastaw)\s+(timer|alarm|minutnik)\b|timer\s+\d|\btimer\s+na\s+\d", re.I)
_RX_TIMER_LIST   = re.compile(r"^\s*(moje\s+)?(timery|minutniki)\s*[?!.]*$", re.I)
_RX_TIMER_CANCEL = re.compile(r"\b(anuluj|zatrzymaj|stop)\s+(timer|minutnik)\b", re.I)
_RX_SW_START     = re.compile(r"\bstoper\s+(start|uruchom|włącz)\b", re.I)
_RX_SW_STOP      = re.compile(r"\bstoper\s+(stop|zatrzymaj|pauza)\b", re.I)
_RX_SW_RESET     = re.compile(r"\bstoper\s+(reset|zeruj)\b", re.I)
_RX_SW_READ      = re.compile(r"\b(ile\s+)?stoper\b|\bczas\s+stopera\b", re.I)

_RX_TODO_ADD   = re.compile(r"\b(dodaj\s+(do\s+)?listy?|dodaj\s+zadanie|muszę\s+pamiętać)\b", re.I)
_RX_TODO_LIST  = re.compile(r"^\s*(co\s+mam|moje\s+)?(zadania|todo|lista\s+zadań|do\s+zrobienia)\s*[?!.]*$", re.I)
_RX_TODO_DONE  = re.compile(r"\b(zrobiłem|odznacz|gotowe)\s+(zadanie|numer|#)?\s*(\d+)\b", re.I)
_RX_TODO_CLEAR = re.compile(r"\b(wyczyść|usuń)\s+(ukończone|zrobione)\s+zadania?\b", re.I)

_RX_HEALTH       = re.compile(r"\b(stan\s+systemu|cpu|ram|dysk|temperatura\s+(cpu|systemu)|zasoby|zdrowie\s+systemu)\b", re.I)
_RX_BACKUP_NOW   = re.compile(r"\b(zrób|wykonaj|uruchom)\s+backup\b|backup\s+teraz\b", re.I)
_RX_BACKUP_STAT  = re.compile(r"\b(status|kiedy\s+ostatni)\s+backup\b", re.I)
_RX_UNIT         = re.compile(r"\b(przelicz|ile\s+(to\s+)?jest|ile\s+wynosi)\b|\b\d+\s*(nm|psi|bar|cali?|kw|hp|°[fc])\b", re.I)
_RX_BRIEFING     = re.compile(r"^\s*(dzień\s+dobry|dobry\s+ranek|dobry\s+wieczór|cześć)\s*[!.]*$|\bbriefing\b", re.I)

_RX_INV_ADD      = re.compile(r"\b(dodaj\s+do\s+spisu|dodaj\s+do\s+magazynu|wpisz\s+do\s+spisu)\b", re.I)
_RX_INV_WHERE    = re.compile(r"\bgdzie\s+(jest|mam|leży)\b", re.I)
_RX_INV_HOW_MANY = re.compile(r"\bile\s+(mam|jest|zostało)\b", re.I)
_RX_INV_STATS    = re.compile(r"^\s*(pokaż\s+)?(spis|stan\s+magazynu|magazyn|inwentarz)\s*[?!.]*$", re.I)
_RX_INV_PRICE    = re.compile(r"\b(szukaj\s+ceny|ile\s+kosztuje|cena)\b", re.I)

_RX_ESP32_ON  = re.compile(r"\b(włącz|zapal|aktywuj|otwórz)\s+(przekaźnik[eę]?|relay|pomp[ęa]|wentylator|led|światł[ao]|zasilanie)(\s+\d+)?\b", re.I)
_RX_ESP32_OFF = re.compile(r"\b(wyłącz|zgaś|dezaktywuj|zamknij|odetnij)\s+(przekaźnik[eę]?|relay|pomp[ęa]|wentylator|led|światł[ao]|zasilanie)(\s+\d+)?\b", re.I)
_RX_ESP32_SET = re.compile(r"\b(ustaw|nastaw|zmień)\s+(napięcie|pwm|jasność|prędkość)\s+(\d+)", re.I)
_RX_ESP32_STAT= re.compile(r"\b(status|stan)\s+(esp|esp32|urządzenia|sterownika)\b", re.I)
_RX_ESP32_LIST= re.compile(r"^\s*(pokaż|lista)?\s*(esp32|urządzenia|przekaźniki)\s*[?!.]*$", re.I)

# ── V3 — nowe wzorce ──────────────────────────────────────────────────────────
_RX_REMINDER_SET = re.compile(
    r"\b(przypomnij(\s+mi)?|ustaw\s+przypomnienie|dodaj\s+przypomnienie"
    r"|codzienn(?:ie|y|i)?\s+o\s+\d|co\s+tydzień|co\s+tydzie[nń])\b",
    re.I,
)
_RX_REMINDER_LIST = re.compile(
    r"^\s*(moje\s+)?(przypomnienia|alarmy)\s*[?!.]*$", re.I
)
_RX_REMINDER_CANCEL = re.compile(
    r"\b(anuluj|usuń|skasuj)\s+(przypomnienie|alarm)\b", re.I
)
_RX_CALENDAR_ADD = re.compile(
    r"\b(dodaj\s+(do\s+)?kalendarza?|dodaj\s+wydarzenie|zaplanuj|zapisz\s+w\s+kalendarzu)\b", re.I
)
_RX_CALENDAR_TODAY = re.compile(
    r"\b(co\s+mam\s+dziś|dzisiaj\s+w\s+kalendarzu|plan\s+na\s+dziś)\b|^\s*(dzisiaj|dziś|plan\s+dnia)\s*[?!.]*$", re.I
)
_RX_CALENDAR_LIST = re.compile(
    r"\b(mój\s+kalendarz|nadchodzące\s+wydarzenia|co\s+mam\s+w\s+tym\s+tygodniu|pokaż\s+kalendarz)\b|^\s*kalendarz\s*[?!.]*$", re.I
)
_RX_CALENDAR_NEXT = re.compile(
    r"\b(następne\s+wydarzenie|co\s+mam\s+następne|następna\s+wizyta)\b", re.I
)
_RX_CALENDAR_REMOVE = re.compile(
    r"\b(usuń\s+(z\s+kalendarza?|wydarzenie)|skasuj\s+wydarzenie)\b", re.I
)
_RX_RESEARCH_SET = re.compile(
    r"\b(śledź\s+temat|dodaj\s+temat\s+(badań\s*)?|codzienn[yi]\s+research|śledź\s+[:\s])\b", re.I
)
_RX_RESEARCH_LIST = re.compile(
    r"^\s*(moje\s+)?(?:tematy|research[ue]?|śledzone\s+tematy)\s*[?!.]*$", re.I
)
_RX_RESEARCH_NOW = re.compile(
    r"\b(zrób|uruchom|wykonaj)\s+research\b|\bresearch\s+teraz\b", re.I
)
_RX_RESEARCH_CANCEL = re.compile(
    r"\b(usuń\s+temat|przestań\s+śledzić)\b", re.I
)
_RX_RESEARCH_LATEST = re.compile(
    r"\b(ostatni\s+research|wyniki\s+research|pokaż\s+research)\b", re.I
)
_RX_TTS_STOP = re.compile(
    r"^\s*(cisza|stop\s+mów(ienie)?|przerwij|milcz|zamknij\s+się|przestań\s+mówić|stop\s+jarvis)\s*[!.?]*$", re.I
)
_RX_HISTORY_SHOW = re.compile(
    r"^\s*(historia\s+(rozmów?)?|pokaż\s+historię?|log\s+rozmów?)\s*(\d+)?\s*[?!.]*$", re.I
)
_RX_HISTORY_CLEAR = re.compile(
    r"\b(wyczyść|usuń)\s+historię\b", re.I
)


class IntentDetector:
    _custom: List[Tuple[re.Pattern, any]] = []

    @classmethod
    def register_pattern(cls, intent: IntentType, pattern: re.Pattern) -> None:
        cls._custom.append((pattern, intent))

    def detect(self, tekst: str) -> Intent:
        t = (tekst or "").strip()
        if not t:
            return Intent(typ=IntentType.CHAT, surowy_tekst="")

        for rx, typ in self._custom:
            if rx.search(t):
                # typ może być IntentType lub zwykłym stringiem
                if isinstance(typ, IntentType):
                    return Intent(typ=typ, tresc=t, surowy_tekst=t)
                else:
                    # Dla stringów tworzymy Intent z surowym typem w argumencie
                    i = Intent(typ=IntentType.CHAT, tresc=t, surowy_tekst=t)
                    i._custom_typ = typ  # przechowujemy custom string
                    return i

        r = self._detect_adaptation(t)
        if r: return r

        for rx, typ in _KOMENDY:
            m = rx.match(t)
            if m:
                arg = ""
                if typ == IntentType.EKSPORT: arg = (m.group(4) or "").strip()
                if typ == IntentType.IMPORT:  arg = (m.group(3) or "").strip()
                return Intent(typ=typ, argument=arg, surowy_tekst=t)

        r = self._detect_esp32(t)
        if r: return r

        r = self._detect_inventory(t)
        if r: return r

        # ── V3 ──────────────────────────────────────────────────────────
        r = self._detect_v3(t)
        if r: return r

        if _RX_WEATHER_WEEK.search(t):
            return Intent(typ=IntentType.WEATHER_WEEK, surowy_tekst=t)
        if _RX_WEATHER.search(t):
            return Intent(typ=IntentType.WEATHER, surowy_tekst=t)
        if _RX_BRIEFING.search(t):
            return Intent(typ=IntentType.BRIEFING, surowy_tekst=t)

        r = self._detect_timer(t)
        if r: return r
        r = self._detect_todo(t)
        if r: return r

        if _RX_BACKUP_STAT.search(t):  return Intent(typ=IntentType.BACKUP_STATUS, surowy_tekst=t)
        if _RX_BACKUP_NOW.search(t):   return Intent(typ=IntentType.BACKUP_NOW, surowy_tekst=t)
        if _RX_HEALTH.search(t):       return Intent(typ=IntentType.HEALTH_STATUS, surowy_tekst=t)
        if _RX_UNIT.search(t):         return Intent(typ=IntentType.UNIT_CONVERT, tresc=t, surowy_tekst=t)

        if _TR_UPDATE.search(t):
            stara, nowa = _rozbij_update(t)
            return Intent(typ=IntentType.UPDATE, tresc=t, stara=stara, nowa=nowa, surowy_tekst=t)
        if _TR_DELETE.search(t):
            return Intent(typ=IntentType.DELETE, tresc=_wytnij_cel(t), surowy_tekst=t)
        if _TR_SAVE.search(t):
            return Intent(typ=IntentType.SAVE, tresc=_wytnij_zapis(t), surowy_tekst=t)
        if _TR_PREF.match(t):
            return Intent(typ=IntentType.SAVE, tresc=t, tagi=["preferencja"], surowy_tekst=t)
        if _TR_SEARCH.search(t):
            return Intent(typ=IntentType.SEARCH, tresc=_wytnij_szukanie(t), surowy_tekst=t)

        return Intent(typ=IntentType.CHAT, tresc=t, surowy_tekst=t)

    def _detect_adaptation(self, t: str) -> Optional[Intent]:
        if _RX_ADAPT_SHOW.match(t): return Intent(typ=IntentType.ADAPT_SHOW, surowy_tekst=t)
        if _RX_ADAPT_RST.match(t):  return Intent(typ=IntentType.ADAPT_RESET, surowy_tekst=t)
        m = _RX_ADAPT_DEL.match(t)
        if m:
            return Intent(typ=IntentType.ADAPT_REMOVE,
                          param="alias" if "alias" in m.group(1) else "instruction",
                          tresc=m.group(2).strip(), surowy_tekst=t)
        m = _RX_ALIAS_ADD.match(t)
        if m:
            return Intent(typ=IntentType.ADAPT_ALIAS,
                          stara=m.group(2).strip().strip("'\""),
                          nowa=m.group(3).strip().strip("'\""), surowy_tekst=t)
        m = _RX_STYLE_LEN.match(t)
        if m:
            tl = t.lower()
            v = "krótko" if any(w in tl for w in ("krócej","krotko","krótko")) \
                else "szczegółowo" if any(w in tl for w in ("dłużej","dluzej")) else "normalnie"
            return Intent(typ=IntentType.ADAPT_STYLE, param="length", wartosc=v, surowy_tekst=t)
        m = _RX_STYLE_TONE.match(t)
        if m:
            v = "formalny" if any(w in t.lower() for w in ("formal","oficjaln")) else "swobodny"
            return Intent(typ=IntentType.ADAPT_STYLE, param="tone", wartosc=v, surowy_tekst=t)
        m = _RX_INSTRUCTION.match(t)
        if m and len(m.group(2).split()) >= 2:
            return Intent(typ=IntentType.ADAPT_INSTRUCTION, tresc=t, surowy_tekst=t)
        return None

    def _detect_timer(self, t: str) -> Optional[Intent]:
        if _RX_SW_START.search(t): return Intent(typ=IntentType.STOPWATCH_START, surowy_tekst=t)
        if _RX_SW_STOP.search(t):  return Intent(typ=IntentType.STOPWATCH_STOP, surowy_tekst=t)
        if _RX_SW_RESET.search(t): return Intent(typ=IntentType.STOPWATCH_RESET, surowy_tekst=t)
        if _RX_SW_READ.search(t):  return Intent(typ=IntentType.STOPWATCH_READ, surowy_tekst=t)
        if _RX_TIMER_LIST.match(t): return Intent(typ=IntentType.TIMER_LIST, surowy_tekst=t)
        if _RX_TIMER_CANCEL.search(t):
            m = re.search(r"(\w+)\s*$", t)
            return Intent(typ=IntentType.TIMER_CANCEL, argument=m.group(1) if m else "", surowy_tekst=t)
        if _RX_TIMER_SET.search(t): return Intent(typ=IntentType.TIMER_SET, surowy_tekst=t)
        return None

    def _detect_todo(self, t: str) -> Optional[Intent]:
        m = _RX_TODO_DONE.search(t)
        if m: return Intent(typ=IntentType.TODO_DONE, argument=m.group(3), surowy_tekst=t)
        if _RX_TODO_CLEAR.search(t): return Intent(typ=IntentType.TODO_CLEAR, surowy_tekst=t)
        if _RX_TODO_LIST.match(t):   return Intent(typ=IntentType.TODO_LIST, surowy_tekst=t)
        if _RX_TODO_ADD.search(t):
            task = re.sub(r"^.*(dodaj\s+(do\s+)?listy?|dodaj\s+zadanie|muszę\s+pamiętać)[:\s]*",
                          "", t, flags=re.I).strip(" :,")
            pri = 2
            for kw, p in {"ważne":3,"pilne":3,"niskie":1}.items():
                if kw in t.lower(): pri=p; break
            return Intent(typ=IntentType.TODO_ADD, tresc=task, argument=str(pri), surowy_tekst=t)
        return None

    def _detect_inventory(self, t: str) -> Optional[Intent]:
        if _RX_INV_ADD.search(t):
            content = re.sub(r"^.*(dodaj\s+do\s+spisu|wpisz\s+do\s+spisu)[:\s]*","",t,flags=re.I).strip()
            return Intent(typ=IntentType.INV_ADD, tresc=content, surowy_tekst=t)
        if _RX_INV_WHERE.search(t):
            q = re.sub(r"\bgdzie\s+(jest|mam|leży)\b","",t,flags=re.I).strip()
            return Intent(typ=IntentType.INV_WHERE, tresc=q, surowy_tekst=t)
        if _RX_INV_HOW_MANY.search(t):
            q = re.sub(r"\bile\s+(mam|jest|zostało)\b","",t,flags=re.I).strip()
            return Intent(typ=IntentType.INV_HOW_MANY, tresc=q, surowy_tekst=t)
        if _RX_INV_PRICE.search(t):
            q = re.sub(r"\b(szukaj\s+ceny|ile\s+kosztuje|cena)[:\s]*","",t,flags=re.I).strip()
            return Intent(typ=IntentType.INV_PRICE, tresc=q, surowy_tekst=t)
        if _RX_INV_STATS.match(t): return Intent(typ=IntentType.INV_STATS, surowy_tekst=t)
        return None

    def _detect_v3(self, t: str) -> Optional[Intent]:
        """Detekcja intencji V3: przypomnienia, kalendarz, research, TTS stop, historia."""
        # TTS interrupt — najwyższy priorytet wśród V3
        if _RX_TTS_STOP.match(t):
            return Intent(typ=IntentType.TTS_STOP, surowy_tekst=t)

        # Historia
        if _RX_HISTORY_CLEAR.search(t):
            return Intent(typ=IntentType.HISTORY_CLEAR, surowy_tekst=t)
        if _RX_HISTORY_SHOW.match(t):
            return Intent(typ=IntentType.HISTORY_SHOW, surowy_tekst=t)

        # Przypomnienia
        if _RX_REMINDER_CANCEL.search(t):
            q = re.sub(r"^.*(anuluj|usuń|skasuj)\s+(przypomnienie|alarm)\s*", "", t, flags=re.I).strip()
            return Intent(typ=IntentType.REMINDER_CANCEL, argument=q, surowy_tekst=t)
        if _RX_REMINDER_LIST.match(t):
            return Intent(typ=IntentType.REMINDER_LIST, surowy_tekst=t)
        if _RX_REMINDER_SET.search(t):
            return Intent(typ=IntentType.REMINDER_SET, surowy_tekst=t)

        # Kalendarz
        if _RX_CALENDAR_REMOVE.search(t):
            return Intent(typ=IntentType.CALENDAR_REMOVE, surowy_tekst=t)
        if _RX_CALENDAR_TODAY.search(t):
            return Intent(typ=IntentType.CALENDAR_TODAY, surowy_tekst=t)
        if _RX_CALENDAR_NEXT.search(t):
            return Intent(typ=IntentType.CALENDAR_NEXT, surowy_tekst=t)
        if _RX_CALENDAR_LIST.search(t):
            return Intent(typ=IntentType.CALENDAR_LIST, surowy_tekst=t)
        if _RX_CALENDAR_ADD.search(t):
            return Intent(typ=IntentType.CALENDAR_ADD, surowy_tekst=t)

        # Research
        if _RX_RESEARCH_CANCEL.search(t):
            return Intent(typ=IntentType.RESEARCH_CANCEL, surowy_tekst=t)
        if _RX_RESEARCH_LATEST.search(t):
            return Intent(typ=IntentType.RESEARCH_LATEST, surowy_tekst=t)
        if _RX_RESEARCH_NOW.search(t):
            return Intent(typ=IntentType.RESEARCH_NOW, surowy_tekst=t)
        if _RX_RESEARCH_LIST.match(t):
            return Intent(typ=IntentType.RESEARCH_LIST, surowy_tekst=t)
        if _RX_RESEARCH_SET.search(t):
            return Intent(typ=IntentType.RESEARCH_SET, surowy_tekst=t)

        return None

    def _detect_esp32(self, t: str) -> Optional[Intent]:
        if _RX_ESP32_LIST.match(t):  return Intent(typ=IntentType.ESP32_LIST, surowy_tekst=t)
        if _RX_ESP32_STAT.search(t): return Intent(typ=IntentType.ESP32_STATUS, surowy_tekst=t)
        m = _RX_ESP32_SET.search(t)
        if m:
            return Intent(typ=IntentType.ESP32_SET, param=m.group(2).lower(),
                          wartosc=m.group(3), surowy_tekst=t)
        if _RX_ESP32_ON.search(t):
            num = re.search(r"\b(\d+)\b", t)
            return Intent(typ=IntentType.ESP32_ON, argument=num.group(1) if num else "1",
                          tresc=t, surowy_tekst=t)
        if _RX_ESP32_OFF.search(t):
            num = re.search(r"\b(\d+)\b", t)
            return Intent(typ=IntentType.ESP32_OFF, argument=num.group(1) if num else "1",
                          tresc=t, surowy_tekst=t)
        return None


def _wytnij_zapis(t):
    return re.sub(r"^\s*(zapamiętaj|zapamietaj|zapisz|zanotuj|pami[eę]taj\s+(?:że|ze))\b[\s:,\-]*","",t,flags=re.I).strip()

def _wytnij_szukanie(t):
    return re.sub(r"^\s*(gdzie\s+(jest|mam|trzymam)|znajdź|szukaj|co\s+wiesz\s+o|przypomnij\s*(mi)?)\b[\s:,\-]*","",t,flags=re.I).strip(" ?.!")

def _wytnij_cel(t):
    return re.sub(r"^\s*(zapomnij\s+(o|że|ze)|usuń\s+(wpis|notatkę)|skasuj\s+(wpis|to))\b[\s:,\-]*","",t,flags=re.I).strip(" ?.!")

def _rozbij_update(t):
    rdzen = re.sub(r"^\s*(zmień|popraw|aktualizuj|nadpisz)\b[\s:,\-]*","",t,flags=re.I).strip()
    for laczy in (r"jednak",r"teraz",r"już\s+nie"):
        m = re.search(rf"^(.+?)\s+{laczy}\s+(.+)$",rdzen,re.I)
        if m: return m.group(1).strip(), f"{m.group(1).strip()} {m.group(2).strip()}"
    slowa = rdzen.split()
    return " ".join(slowa[:3]), rdzen
