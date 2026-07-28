"""
Eye-drops reminders after INTRALASIK surgery.

Everything is configurable from the bot itself: surgery date *and hour*, the
awake window (which may run past midnight), snooze length and on/off. The
protocol is split into 4 phases derived from the number of days since surgery.

Time model
----------
Hours are counted from midnight of the *treatment day*, so a window of
08:00–01:00 is stored as start_hour=8, end_hour=25 and a drop at "25:00" is
delivered at 01:00 of the next calendar day while still belonging to the
previous treatment day. Everything (schedule, tracking, panels) works on the
treatment day, which is what a patient actually thinks in.

State is stored per user in data/eyedrops_{user_id}.json so reminders survive
a bot restart. A single asyncio ticker (started from bot.py's post_init) scans
the stored plans every TICK_SECONDS and fires whatever is due, which means the
feature does not depend on APScheduler / PTB's optional JobQueue extra.
"""
import asyncio
import json
import logging
import os
import re
from datetime import date, datetime, time, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest, Forbidden, TelegramError
from telegram.ext import (
    ApplicationHandlerStop, CallbackQueryHandler, CommandHandler,
    ContextTypes, MessageHandler, filters,
)

logger = logging.getLogger(__name__)

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Asia/Jerusalem")
except Exception:  # pragma: no cover - only if the tzdata package is missing
    from datetime import timezone
    TZ = timezone(timedelta(hours=3))
    logger.warning("eyedrops: Asia/Jerusalem timezone unavailable, using UTC+3")

# ── constants ────────────────────────────────────────────────────────────────

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
FILE_PREFIX = "eyedrops_"
FILE_RE = re.compile(rf"^{FILE_PREFIX}(\d+)\.json$")

TICK_SECONDS = 30          # how often the scheduler wakes up
MISSED_AFTER_MINUTES = 60  # a dose older than this is marked missed, not sent
HISTORY_DAYS = 7           # how many days of sent/taken history to keep
MAX_SNOOZES = 20           # safety cap on pending snoozes per user

SNOOZE_CHOICES = (5, 10, 15, 30)
START_HOUR_CHOICES = (5, 6, 7, 8, 9, 10, 11, 12)
END_HOUR_CHOICES = (20, 21, 22, 23, 24, 25, 26)   # 24 = midnight, 26 = 02:00
MIN_AWAKE_HOURS = 2                               # end must be this far after start
QUICK_TIMES = ("08:00", "10:00", "12:00", "14:00", "16:00", "18:00", "20:00")

MEDS = {
    1: "1️⃣ VIGAMOX (אנטיביוטיקה)",
    2: "2️⃣ STERODEX (סטרואיד)",
    3: "3️⃣ TEARS NATURALE FREE / LIPITEAR (דמעות מלאכותיות)",
}
MEDS_SHORT = {
    1: "1️⃣ VIGAMOX",
    2: "2️⃣ STERODEX",
    3: "3️⃣ TEARS / LIPITEAR",
}

# The whole protocol lives here — edit this table (and nothing else) if the
# printed instructions differ. Each phase declares which days it covers (day 0
# is the day of surgery), the gap between rounds, and the drops of a round as
# (hour offset, minute offset, medication number) from the round's anchor hour.
# Rounds start at the user's start hour and repeat while the last drop of the
# round still fits before the end hour.
PHASES = (
    {
        "n": 1, "title": "יומיים ראשונים", "first_day": 0, "last_day": 1,
        "interval": 2, "doses": ((0, 0, 1), (0, 5, 2)),
    },
    {
        "n": 2, "title": "ימים 3–8", "first_day": 2, "last_day": 7,
        "interval": 4, "doses": ((0, 0, 1), (0, 5, 2), (1, 5, 3)),
    },
    {
        "n": 3, "title": "ימים 9–15", "first_day": 8, "last_day": 14,
        "interval": 4, "doses": ((0, 0, 2), (1, 0, 3)),
    },
    {
        "n": 4, "title": "שבועות 3–8", "first_day": 15, "last_day": 56,
        "interval": 4, "doses": ((0, 0, 3),),
    },
)
LAST_DAY = PHASES[-1]["last_day"]

SPACING_TIP = "⏳ 5 דקות בין טיפה 1️⃣ לטיפה 2️⃣, ושעה בין טיפה 2️⃣ לטיפה 3️⃣"

DEFAULTS = {
    "chat_id": None,
    "enabled": True,
    "surgery_date": None,   # "YYYY-MM-DD"
    "surgery_time": None,   # "HH:MM" — no reminders before it on the day of surgery
    "start_hour": 8,
    "end_hour": 22,         # hours from midnight; >23 means after midnight
    "snooze_minutes": 10,
    "sent": {},             # {"YYYY-MM-DD": ["0800-1", ...]} keyed by treatment day
    "taken": {},            # {"YYYY-MM-DD": ["0800-1", ...]}
    "snoozes": [],          # [{"due": "ISO", "med": 1, "slot": "0800-1"}]
    "finished_notice": None,
}


def _now() -> datetime:
    return datetime.now(TZ)


# ── time helpers ─────────────────────────────────────────────────────────────

def _day_start(day: date) -> datetime:
    return datetime.combine(day, time(0, 0), tzinfo=TZ)


def _dose_dt(day: date, hour: int, minute: int = 0) -> datetime:
    """Wall-clock moment of an hour counted from midnight of `day` (may pass 24)."""
    return _day_start(day) + timedelta(hours=hour, minutes=minute)


def _fmt_hm(hour: int, minute: int = 0) -> str:
    return f"{hour % 24:02d}:{minute:02d}"


def _fmt_hour_label(hour: int) -> str:
    """Button/label text for an awake-window hour ('01:00 ⁺' = after midnight)."""
    return f"{_fmt_hm(hour)} ⁺" if hour >= 24 else _fmt_hm(hour)


def _window_label(state: dict) -> str:
    end = _fmt_hm(state["end_hour"])
    suffix = " (למחרת)" if state["end_hour"] >= 24 else ""
    return f"{_fmt_hm(state['start_hour'])}–{end}{suffix}"


# ── state storage ────────────────────────────────────────────────────────────

def _state_path(user_id: int) -> str:
    os.makedirs(DATA_DIR, exist_ok=True)
    return os.path.join(DATA_DIR, f"{FILE_PREFIX}{user_id}.json")


def _clean_state(raw: dict) -> dict:
    """Merge stored data over the defaults and coerce every field to a sane value."""
    state = dict(DEFAULTS)
    state["sent"], state["taken"], state["snoozes"] = {}, {}, []
    if not isinstance(raw, dict):
        return state

    chat_id = raw.get("chat_id")
    if isinstance(chat_id, (int, str)):
        try:
            state["chat_id"] = int(chat_id)
        except (TypeError, ValueError):
            state["chat_id"] = None

    state["enabled"] = bool(raw.get("enabled", True))

    if _parse_iso_date(raw.get("surgery_date")):
        state["surgery_date"] = raw["surgery_date"]
    if _parse_hhmm(raw.get("surgery_time")):
        state["surgery_time"] = raw["surgery_time"]

    start = raw.get("start_hour")
    if isinstance(start, int) and 0 <= start <= 23:
        state["start_hour"] = start
    end = raw.get("end_hour")
    if isinstance(end, int) and 0 <= end <= max(END_HOUR_CHOICES):
        state["end_hour"] = end
    if state["end_hour"] < state["start_hour"] + MIN_AWAKE_HOURS:
        state["start_hour"], state["end_hour"] = DEFAULTS["start_hour"], DEFAULTS["end_hour"]

    snooze = raw.get("snooze_minutes")
    if isinstance(snooze, int) and snooze in SNOOZE_CHOICES:
        state["snooze_minutes"] = snooze

    for key in ("sent", "taken"):
        value = raw.get(key)
        if isinstance(value, dict):
            state[key] = {
                day: [s for s in slots if isinstance(s, str)]
                for day, slots in value.items()
                if isinstance(day, str) and isinstance(slots, list)
            }

    snoozes = raw.get("snoozes")
    if isinstance(snoozes, list):
        for item in snoozes[:MAX_SNOOZES]:
            if (isinstance(item, dict) and _parse_iso_dt(item.get("due"))
                    and item.get("med") in MEDS):
                state["snoozes"].append({
                    "due": item["due"],
                    "med": int(item["med"]),
                    "slot": str(item.get("slot", "")),
                })

    if _parse_iso_date(raw.get("finished_notice")):
        state["finished_notice"] = raw["finished_notice"]

    return state


def _load_state(user_id: int) -> dict:
    try:
        with open(_state_path(user_id), encoding="utf-8") as f:
            return _clean_state(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return _clean_state({})


def _save_state(user_id: int, state: dict) -> None:
    """Write atomically so a crash mid-write can never corrupt the plan."""
    path = _state_path(user_id)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _delete_state(user_id: int) -> None:
    try:
        os.remove(_state_path(user_id))
    except OSError:
        pass


def _iter_states():
    """Yield (user_id, state) for every stored plan."""
    try:
        names = os.listdir(DATA_DIR)
    except OSError:
        return
    for name in names:
        match = FILE_RE.match(name)
        if not match:
            continue
        user_id = int(match.group(1))
        yield user_id, _load_state(user_id)


# ── parsing ──────────────────────────────────────────────────────────────────

def _parse_iso_date(value) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _parse_iso_dt(value) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=TZ)


def _parse_hhmm(value) -> time | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value.strip(), "%H:%M").time()
    except ValueError:
        return None


_DATE_FORMATS = ("%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d")
_SHORT_FORMATS = ("%d/%m", "%d.%m", "%d-%m")
_KEYWORDS = {"היום": 0, "אתמול": -1, "שלשום": -2, "מחר": 1, "מחרתיים": 2}
_LOOKS_LIKE_DATE_RE = re.compile(r"\d{1,4}\s*[/.\-]\s*\d{1,2}|^\d{1,2}$")
_LOOKS_LIKE_TIME_RE = re.compile(r"^\d{1,2}\s*[:.]?\s*\d{0,2}$")
_TIME_IN_TEXT_RE = re.compile(r"(?:^|\s)(\d{1,2})[:.](\d{2})(?:\s|$)")


_TIME_RE = re.compile(r"(\d{1,2})[:.]?(\d{2})?")


def parse_user_time(text: str) -> time | None:
    """
    Parse '14:30', '14.30', '1430' or '14' into a time.
    Matched explicitly rather than with strptime, which happily reads "14" as
    01:04 under "%H%M".
    """
    normalized = re.sub(r"\s+", "", text or "")
    match = _TIME_RE.fullmatch(normalized) if normalized else None
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    if hour > 23 or minute > 59:
        return None
    return time(hour, minute)


def parse_user_date(text: str) -> date | None:
    """Parse dd/mm/yyyy, dd.mm, yyyy-mm-dd, 'היום', 'אתמול'… into a date."""
    text = (text or "").strip()
    if not text:
        return None

    if text in _KEYWORDS:
        return _now().date() + timedelta(days=_KEYWORDS[text])

    normalized = re.sub(r"\s+", "", text)
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(normalized, fmt).date()
        except ValueError:
            continue

    today = _now().date()
    for fmt in _SHORT_FORMATS:
        try:
            partial = datetime.strptime(normalized, fmt).date()
        except ValueError:
            continue
        for year in (today.year, today.year - 1):
            try:
                candidate = partial.replace(year=year)
            except ValueError:  # 29/02 on a non-leap year
                continue
            if candidate <= today + timedelta(days=30):
                return candidate
    return None


def parse_user_datetime(text: str) -> tuple[date | None, time | None]:
    """Parse '28/07/2026 14:30' — either part may be missing."""
    text = (text or "").strip()
    if not text:
        return None, None

    parsed_date = parse_user_date(text)
    if parsed_date:
        return parsed_date, None

    match = _TIME_IN_TEXT_RE.search(text)
    if match:
        rest = (text[:match.start()] + " " + text[match.end():]).strip()
        parsed_time = parse_user_time(match.group(0))
        parsed_date = parse_user_date(rest) if rest else None
        if parsed_time and (parsed_date or not rest):
            return parsed_date, parsed_time
    return None, None


# ── schedule ─────────────────────────────────────────────────────────────────

def _surgery_date(state: dict) -> date | None:
    return _parse_iso_date(state.get("surgery_date"))


def _surgery_time(state: dict) -> time | None:
    return _parse_hhmm(state.get("surgery_time"))


def _day_index(state: dict, day_date: date | None = None) -> int | None:
    """0 = surgery day, 1 = the day after, …"""
    surgery = _surgery_date(state)
    if surgery is None:
        return None
    return ((day_date or _active_day_date(state)) - surgery).days


def _phase_for_day(day: int | None) -> dict | None:
    if day is None:
        return None
    for phase in PHASES:
        if phase["first_day"] <= day <= phase["last_day"]:
            return phase
    return None


def build_schedule(phase: dict, start_hour: int, end_hour: int) -> list[tuple[int, int, int]]:
    """Return a day's doses as sorted (hour, minute, medication) tuples."""
    if not phase:
        return []
    doses: list[tuple[int, int, int]] = []
    max_offset = max(d[0] for d in phase["doses"])
    hour = start_hour
    while hour + max_offset <= end_hour:
        for hour_offset, minute_offset, med in phase["doses"]:
            doses.append((hour + hour_offset, minute_offset, med))
        hour += phase["interval"]
    doses.sort()
    return doses


def _day0_schedule(phase: dict, surgery: time, start_hour: int,
                   end_hour: int) -> list[tuple[int, int, int]]:
    """
    Day-0 rounds anchored to the surgery hour itself, not the daily grid: the
    first round is one phase-interval after surgery, then every interval
    hours after that (so surgery at 16:00 with a 2h interval gives 18:00,
    20:00, 22:00 — not whatever the fixed grid happens to land on).
    Rounds before the wake hour are skipped so a very early surgery does not
    produce a reminder before the user is expected to be awake.
    """
    interval_min = phase["interval"] * 60
    max_offset_h = max(d[0] for d in phase["doses"])
    total = surgery.hour * 60 + surgery.minute + interval_min
    doses: list[tuple[int, int, int]] = []
    for _ in range(24):  # generous cap — intervals are >=2h, so this can't loop long
        hour, minute = divmod(total, 60)
        if hour + max_offset_h > end_hour:
            break
        if hour >= start_hour:
            for hour_offset, minute_offset, med in phase["doses"]:
                extra_hour, final_minute = divmod(minute + minute_offset, 60)
                doses.append((hour + hour_offset + extra_hour, final_minute, med))
        total += interval_min
    doses.sort()
    return doses


def doses_for_date(state: dict, day_date: date) -> list[tuple[int, int, int]]:
    """The doses of one treatment day, honouring the surgery hour on day 0."""
    day = _day_index(state, day_date)
    phase = _phase_for_day(day)
    if not phase:
        return []
    if day == 0:
        surgery = _surgery_time(state)
        if surgery:
            return _day0_schedule(phase, surgery, state["start_hour"], state["end_hour"])
    return build_schedule(phase, state["start_hour"], state["end_hour"])


def _active_day_date(state: dict, now: datetime | None = None) -> date:
    """
    The treatment day whose window is currently running. With a window that
    ends after midnight, 00:30 still belongs to the previous treatment day.
    """
    now = now or _now()
    previous = now.date() - timedelta(days=1)
    if now <= _dose_dt(previous, state.get("end_hour", DEFAULTS["end_hour"])):
        return previous
    return now.date()


def _slot(hour: int, minute: int, med: int) -> str:
    return f"{hour:02d}{minute:02d}-{med}"


def _slot_parts(slot: str) -> tuple[int, int]:
    return int(slot[:2]), int(slot[2:4])


def _slot_time(slot: str) -> str:
    hour, minute = _slot_parts(slot)
    return _fmt_hm(hour, minute)


# ── reminder sending ─────────────────────────────────────────────────────────

def _reminder_keyboard(state: dict, med: int, slot: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ לקחתי", callback_data=f"ed_take_{med}_{slot[:4]}"),
            InlineKeyboardButton(f"😴 נודניק {state['snooze_minutes']} דק'",
                                 callback_data=f"ed_zzz_{med}_{slot[:4]}"),
        ],
        [InlineKeyboardButton("💧 מסך הטיפות", callback_data="ed_home")],
    ])


def _next_dose_after(state: dict, day_date: date, slot: str) -> tuple[int, int, int] | None:
    """The next drop of the same treatment day, if it is close enough to mention."""
    try:
        hour, minute = _slot_parts(slot)
    except ValueError:
        return None
    current = hour * 60 + minute
    for next_hour, next_minute, next_med in doses_for_date(state, day_date):
        offset = next_hour * 60 + next_minute
        if current < offset <= current + 65:
            return next_hour, next_minute, next_med
    return None


async def _send_reminder(bot, user_id: int, state: dict, med: int, slot: str,
                         day_date: date, *, late_minutes: int = 0,
                         snoozed: bool = False) -> bool:
    """Send one reminder. Returns False if the chat is unreachable."""
    day = _day_index(state, day_date)
    phase = _phase_for_day(day)
    header = _slot_time(slot)
    if day is not None and phase:
        header += f" · יום {day + 1} (שלב {phase['n']})"
    notes = []
    if snoozed:
        notes.append("😴 תזכורת נודניק")
    if late_minutes >= 2:
        notes.append(f"⏰ באיחור של {late_minutes} דקות")

    text = (
        "💧 *הגיע הזמן לטיפות עיניים*\n"
        f"_{header}_\n\n"
        f"*{MEDS[med]}*\n"
        "טיפה אחת"
    )
    upcoming = _next_dose_after(state, day_date, slot)
    if upcoming:
        next_hour, next_minute, next_med = upcoming
        text += f"\n\n⏭️ הבא בתור: *{_fmt_hm(next_hour, next_minute)}* · {MEDS_SHORT[next_med]}"
    if notes:
        text += "\n\n" + "\n".join(notes)

    try:
        await bot.send_message(
            chat_id=state["chat_id"], text=text, parse_mode="Markdown",
            reply_markup=_reminder_keyboard(state, med, slot),
        )
        logger.info("eyedrops: reminder sent to %s (med %s at %s)", user_id, med, _slot_time(slot))
        return True
    except Forbidden:
        logger.warning("eyedrops: user %s blocked the bot — reminders disabled", user_id)
        return False
    except TelegramError as exc:
        logger.error("eyedrops: failed to send reminder to %s: %s", user_id, exc)
        return True  # transient — keep the plan enabled


# ── scheduler ────────────────────────────────────────────────────────────────

_scheduler_task: asyncio.Task | None = None


async def start_scheduler(app) -> None:
    """Called from bot.py post_init."""
    global _scheduler_task
    if _scheduler_task and not _scheduler_task.done():
        return
    _scheduler_task = asyncio.create_task(_scheduler_loop(app), name="eyedrops-scheduler")


async def stop_scheduler(app) -> None:
    """Called from bot.py post_shutdown."""
    global _scheduler_task
    task, _scheduler_task = _scheduler_task, None
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


async def _scheduler_loop(app) -> None:
    logger.info("eyedrops: scheduler started (tick=%ss, tz=%s)", TICK_SECONDS, TZ)
    while True:
        try:
            await _tick(app)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("eyedrops: tick failed")
        await asyncio.sleep(TICK_SECONDS)


async def _tick(app) -> None:
    now = _now()
    for user_id, state in _iter_states():
        try:
            await _process_user(app, user_id, state, now)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("eyedrops: processing user %s failed", user_id)


def _days_to_scan(state: dict, now: datetime) -> list[date]:
    """
    Treatment days that can still have a due dose right now: today, plus
    yesterday while its after-midnight tail (+ catch-up grace) is alive.
    """
    today = now.date()
    days = [today]
    if state["end_hour"] >= 24:
        yesterday = today - timedelta(days=1)
        tail_end = _dose_dt(yesterday, state["end_hour"]) + timedelta(minutes=MISSED_AFTER_MINUTES)
        if now <= tail_end:
            days.insert(0, yesterday)
    return days


async def _process_user(app, user_id: int, state: dict, now: datetime) -> None:
    if not state.get("chat_id") or not state.get("enabled"):
        return

    changed = False
    pending: list[dict] = []

    # 1) snoozes that came due — these fire even after the protocol ended,
    #    so a drop snoozed on the last evening is never lost.
    still_pending = []
    for item in state["snoozes"]:
        due = _parse_iso_dt(item["due"])
        if due and due <= now:
            pending.append({
                "med": item["med"],
                "slot": item["slot"] or _slot(now.hour, now.minute, item["med"]),
                "day": _active_day_date(state, now), "late": 0, "snoozed": True,
            })
            changed = True
        else:
            still_pending.append(item)
    if changed:
        state["snoozes"] = still_pending

    # 2) scheduled doses of every treatment day that is still running
    for day_date in _days_to_scan(state, now):
        doses = doses_for_date(state, day_date)
        if not doses:
            continue
        sent_day = state["sent"].setdefault(day_date.isoformat(), [])
        for hour, minute, med in doses:
            slot = _slot(hour, minute, med)
            if slot in sent_day:
                continue
            due = _dose_dt(day_date, hour, minute)
            if now < due:
                continue
            late = int((now - due).total_seconds() // 60)
            sent_day.append(slot)
            changed = True
            if late <= MISSED_AFTER_MINUTES:
                pending.append({"med": med, "slot": slot, "day": day_date,
                                "late": late, "snoozed": False})
            else:
                logger.info("eyedrops: dose %s for %s missed by %s min", slot, user_id, late)

    if _prune_history(state, now.date()):
        changed = True

    # 3) protocol finished — congratulate once, but only after the last window
    #    (including its after-midnight tail) is over.
    active = _active_day_date(state, now)
    day = _day_index(state, active)
    finished = (day is not None and day > LAST_DAY and not state.get("finished_notice"))
    if finished:
        state["finished_notice"] = now.date().isoformat()
        state["snoozes"] = []
        changed = True

    # Persist *before* sending so a failure can never produce duplicate messages.
    if changed:
        _save_state(user_id, state)

    for item in sorted(pending, key=lambda d: (d["day"], d["slot"])):
        ok = await _send_reminder(app.bot, user_id, state, item["med"], item["slot"],
                                  item["day"], late_minutes=item["late"],
                                  snoozed=item["snoozed"])
        if not ok:
            state["enabled"] = False
            _save_state(user_id, state)
            return

    if finished:
        try:
            await app.bot.send_message(
                chat_id=state["chat_id"],
                text=("🎉 *סיימת את פרוטוקול הטיפות!*\n"
                      f"עברו {day} ימים מהניתוח — אין יותר תזכורות מתוכננות.\n"
                      "רפואה שלמה! 👁️"),
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💧 מסך הטיפות", callback_data="ed_home")]
                ]),
            )
        except (Forbidden, TelegramError) as exc:
            logger.warning("eyedrops: finish notice to %s failed: %s", user_id, exc)


def _prune_history(state: dict, today: date) -> bool:
    keep = {(today - timedelta(days=i)).isoformat() for i in range(HISTORY_DAYS)}
    changed = False
    for key in ("sent", "taken"):
        for day_key in list(state[key]):
            if day_key not in keep:
                del state[key][day_key]
                changed = True
    return changed


# ── UI: panels ───────────────────────────────────────────────────────────────

def _phase_line(day: int | None) -> str:
    phase = _phase_for_day(day)
    if phase:
        return f"שלב {phase['n']} — {phase['title']}"
    if day is None:
        return "—"
    if day < 0:
        return f"הטיפול יתחיל בעוד {abs(day)} ימים"
    return "הטיפול הסתיים ✅"


def _progress(state: dict, day_date: date) -> tuple[int, int, str]:
    """(taken, total, next dose description) for a treatment day."""
    doses = doses_for_date(state, day_date)
    if not doses:
        return 0, 0, "—"
    taken = state["taken"].get(day_date.isoformat(), [])
    taken_count = sum(1 for h, m, med in doses if _slot(h, m, med) in taken)

    now = _now()
    for hour, minute, med in doses:
        if _dose_dt(day_date, hour, minute) > now:
            return taken_count, len(doses), f"{_fmt_hm(hour, minute)} · {MEDS_SHORT[med]}"
    return taken_count, len(doses), "אין מנות נוספות היום"


def _panel_text(state: dict) -> str:
    surgery = _surgery_date(state)
    if not surgery:
        return (
            "💧 *תזכורות טיפות עיניים — INTRALASIK*\n\n"
            "כדי להתחיל, הגדר את *תאריך הניתוח*.\n"
            "מרגע ההגדרה הבוט ישלח תזכורת לכל טיפה, לפי הפרוטוקול:\n\n"
            f"• *שלב 1* (יומיים ראשונים): {MEDS_SHORT[1]} + {MEDS_SHORT[2]} כל שעתיים\n"
            f"• *שלב 2* (ימים 3–8): {MEDS_SHORT[1]} + {MEDS_SHORT[2]} + {MEDS_SHORT[3]} כל 4 שעות\n"
            f"• *שלב 3* (ימים 9–15): {MEDS_SHORT[2]} + {MEDS_SHORT[3]} כל 4 שעות\n"
            f"• *שלב 4* (שבועות 3–8): {MEDS_SHORT[3]} כל 4 שעות\n\n"
            f"{SPACING_TIP}"
        )

    active = _active_day_date(state)
    day = _day_index(state, active)
    taken, total, nxt = _progress(state, active)
    status = "🔔 פעיל" if state["enabled"] else "🔕 מושבת"
    surgery_time = _surgery_time(state)
    when = surgery.strftime("%d/%m/%Y")
    if surgery_time:
        when += f" {surgery_time.strftime('%H:%M')}"
    date_line = f"תאריך ניתוח: *{when}*"
    if day is not None and day >= 0:
        date_line += f" (יום {day + 1})"

    lines = [
        "💧 *תזכורות טיפות עיניים*",
        "",
        f"מצב: *{status}*",
        date_line,
        f"שלב נוכחי: *{_phase_line(day)}*",
        f"שעות פעילות: *{_window_label(state)}*",
        f"נודניק: *{state['snooze_minutes']} דקות*",
    ]
    if total:
        label = "היום" if active == _now().date() else "יום הטיפול הנוכחי"
        lines += ["", f"{label}: נלקחו *{taken}* מתוך *{total}* מנות",
                  f"המנה הבאה: *{nxt}*"]
    elif _phase_for_day(day):
        if day == 0 and surgery_time:
            lines += ["", f"⚠️ אין מנות נוספות היום — לוקח בחשבון את שעת הניתוח "
                          f"({surgery_time.strftime('%H:%M')}) ואת חלון השעות."]
        else:
            lines += ["", "⚠️ חלון השעות קצר מדי — אין מנות מתוכננות היום."]
    if state["snoozes"]:
        lines.append(f"😴 נודניקים ממתינים: {len(state['snoozes'])}")
    lines += ["", SPACING_TIP]
    return "\n".join(lines)


def _panel_keyboard(state: dict) -> InlineKeyboardMarkup:
    has_date = bool(_surgery_date(state))
    rows = [[InlineKeyboardButton("📅 תאריך הניתוח", callback_data="ed_setdate")]]
    if has_date:
        rows[0].append(InlineKeyboardButton("🕐 שעת הניתוח", callback_data="ed_settime"))
        rows += [
            [
                InlineKeyboardButton("⏰ שעות פעילות", callback_data="ed_hours"),
                InlineKeyboardButton("😴 זמן נודניק", callback_data="ed_snooze"),
            ],
            [InlineKeyboardButton("📋 לוח הזמנים של היום", callback_data="ed_today")],
            [InlineKeyboardButton(
                "🔕 כבה תזכורות" if state["enabled"] else "🔔 הפעל תזכורות",
                callback_data="ed_toggle")],
            [InlineKeyboardButton("🗑️ איפוס הטיפול", callback_data="ed_reset")],
        ]
    rows.append([InlineKeyboardButton("🏠 חזרה למסך הבית", callback_data="go_home")])
    return InlineKeyboardMarkup(rows)


async def _render(update: Update, text: str, keyboard: InlineKeyboardMarkup) -> None:
    """Edit the current message when possible, otherwise send a new one."""
    query = update.callback_query
    if query is not None:
        try:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)
            return
        except BadRequest as exc:
            if "not modified" in str(exc).lower():
                return
        await query.message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)
        return
    await update.effective_message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)


async def _show_panel(update: Update, state: dict) -> None:
    await _render(update, _panel_text(state), _panel_keyboard(state))


# ── UI: entry points ─────────────────────────────────────────────────────────

def _touch(update: Update, state: dict) -> dict:
    """Keep the chat id in sync with wherever the user is talking from."""
    chat = update.effective_chat
    if chat and state.get("chat_id") != chat.id:
        state["chat_id"] = chat.id
    return state


async def show_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("ed_awaiting", None)
    user_id = update.effective_user.id
    state = _touch(update, _load_state(user_id))
    _save_state(user_id, state)
    await _show_panel(update, state)


# ── UI: callbacks ────────────────────────────────────────────────────────────

_HOME_BTN = [InlineKeyboardButton("💧 חזרה למסך הטיפות", callback_data="ed_home")]


async def _ask_date(update: Update, context: ContextTypes.DEFAULT_TYPE, state: dict) -> None:
    context.user_data["ed_awaiting"] = "date"
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("היום", callback_data="ed_qdate_0"),
            InlineKeyboardButton("אתמול", callback_data="ed_qdate_-1"),
            InlineKeyboardButton("שלשום", callback_data="ed_qdate_-2"),
        ],
        [InlineKeyboardButton("מחר", callback_data="ed_qdate_1")],
        _HOME_BTN,
    ])
    current = _surgery_date(state)
    text = (
        "📅 *תאריך הניתוח*\n\n"
        "שלח את התאריך בפורמט *יום/חודש/שנה*, לדוגמה: `28/07/2026`\n"
        "אפשר להוסיף גם שעה: `28/07/2026 14:30`\n"
        "אפשר גם: `28/07`, `2026-07-28`, או פשוט לכתוב `היום` / `אתמול`."
    )
    if current:
        text += f"\n\nהתאריך הנוכחי: *{current.strftime('%d/%m/%Y')}*"
    await _render(update, text, keyboard)


async def _ask_time(update: Update, context: ContextTypes.DEFAULT_TYPE, state: dict) -> None:
    context.user_data["ed_awaiting"] = "time"
    quick = [InlineKeyboardButton(t, callback_data=f"ed_qtime_{t.replace(':', '')}")
             for t in QUICK_TIMES]
    rows = [quick[:4], quick[4:], [InlineKeyboardButton("🚫 ללא שעה", callback_data="ed_notime")],
            _HOME_BTN]
    current = _surgery_time(state)
    text = (
        "🕐 *שעת הניתוח*\n\n"
        "שלח שעה בפורמט `14:30` (או בחר מהכפתורים).\n"
        "ביום הניתוח המנה הראשונה תהיה לפי מרווח השלב הראשון אחרי שעת הניתוח "
        "(למשל: ניתוח ב-16:00 ← מנה ראשונה ב-18:00, ואז כל שעתיים) — שאר הימים לא מושפעים."
    )
    text += (f"\n\nהשעה הנוכחית: *{current.strftime('%H:%M')}*" if current
             else "\n\nכרגע לא מוגדרת שעה — ביום הניתוח התזכורות מתחילות מתחילת חלון השעות.")
    await _render(update, text, InlineKeyboardMarkup(rows))


def _mark_past_doses_handled(state: dict, now: datetime) -> None:
    """
    After the plan changes, treat everything already too late to send as
    handled, so a mid-day change never fires a burst of catch-up reminders.
    """
    for day_date in (now.date() - timedelta(days=1), now.date()):
        already = [
            _slot(h, m, med)
            for h, m, med in doses_for_date(state, day_date)
            if _dose_dt(day_date, h, m) <= now - timedelta(minutes=MISSED_AFTER_MINUTES)
        ]
        if already:
            state["sent"][day_date.isoformat()] = already


async def _apply_date(update: Update, context: ContextTypes.DEFAULT_TYPE, state: dict,
                      new_date: date, new_time: time | None = None) -> None:
    user_id = update.effective_user.id
    today = _now().date()
    if new_date > today + timedelta(days=30):
        await _render(update, "❌ התאריך רחוק מדי בעתיד. הגדר תאריך ניתוח אמיתי.",
                      InlineKeyboardMarkup([_HOME_BTN]))
        return
    if new_date < today - timedelta(days=365):
        await _render(update, "❌ התאריך רחוק מדי בעבר. הגדר תאריך ניתוח אמיתי.",
                      InlineKeyboardMarkup([_HOME_BTN]))
        return

    previous = state.get("surgery_date")
    state["surgery_date"] = new_date.isoformat()
    if new_time is not None:
        state["surgery_time"] = new_time.strftime("%H:%M")
    if previous != state["surgery_date"]:
        # A new treatment starts clean: no old history, no stale snoozes.
        state["sent"], state["taken"], state["snoozes"] = {}, {}, []
        state["finished_notice"] = None
        _mark_past_doses_handled(state, _now())
    state["enabled"] = True
    _touch(update, state)
    _save_state(user_id, state)
    context.user_data.pop("ed_awaiting", None)

    active = _active_day_date(state)
    day = _day_index(state, active)
    total = len(doses_for_date(state, active))
    surgery_time = _surgery_time(state)
    when = new_date.strftime("%d/%m/%Y") + (f" {surgery_time.strftime('%H:%M')}" if surgery_time else "")
    confirm = (
        f"✅ הניתוח נקבע ל-*{when}*\n"
        f"{_phase_line(day)} · *{total}* מנות היום\n\n"
    )
    await _render(update, confirm + _panel_text(state), _panel_keyboard(state))


async def _apply_time(update: Update, context: ContextTypes.DEFAULT_TYPE,
                      state: dict, new_time: time | None) -> None:
    user_id = update.effective_user.id
    state["surgery_time"] = new_time.strftime("%H:%M") if new_time else None
    _mark_past_doses_handled(state, _now())
    _touch(update, state)
    _save_state(user_id, state)
    context.user_data.pop("ed_awaiting", None)

    if new_time:
        head = f"✅ שעת הניתוח נקבעה ל-*{new_time.strftime('%H:%M')}*\n\n"
    else:
        head = "✅ שעת הניתוח נמחקה.\n\n"
    await _render(update, head + _panel_text(state), _panel_keyboard(state))


async def _hours_panel(update: Update, state: dict) -> None:
    def button(hour: int, prefix: str, selected: int) -> InlineKeyboardButton:
        mark = "✅ " if hour == selected else ""
        return InlineKeyboardButton(f"{mark}{_fmt_hour_label(hour)}",
                                    callback_data=f"{prefix}{hour}")

    starts = [button(h, "ed_sh_", state["start_hour"]) for h in START_HOUR_CHOICES]
    ends = [button(h, "ed_eh_", state["end_hour"]) for h in END_HOUR_CHOICES]
    text = (
        "⏰ *שעות פעילות*\n\n"
        f"התזכורות נשלחות בין *{_window_label(state)}*.\n\n"
        "🔼 שתי השורות הראשונות — שעת התחלה (מתי אתה קם)\n"
        "🔽 שתי השורות הבאות — שעת סיום (מתי אתה הולך לישון)\n\n"
        "_שעה מסומנת ב-⁺ היא אחרי חצות ושייכת לאותו יום טיפול._"
    )
    rows = [starts[:4], starts[4:], ends[:4], ends[4:], _HOME_BTN]
    await _render(update, text, InlineKeyboardMarkup(rows))


async def _snooze_panel(update: Update, state: dict) -> None:
    row = [
        InlineKeyboardButton(f"{'✅ ' if m == state['snooze_minutes'] else ''}{m} דק'",
                             callback_data=f"ed_snz_{m}")
        for m in SNOOZE_CHOICES
    ]
    text = (
        "😴 *זמן נודניק*\n\n"
        f"כשתלחץ על 'נודניק' בתזכורת, היא תחזור בעוד *{state['snooze_minutes']} דקות*.\n"
        "בחר משך אחר:"
    )
    await _render(update, text, InlineKeyboardMarkup([row, _HOME_BTN]))


async def _today_panel(update: Update, state: dict) -> None:
    active = _active_day_date(state)
    day = _day_index(state, active)
    doses = doses_for_date(state, active)
    if not doses:
        await _render(update, "📋 *לוח הזמנים של היום*\n\nאין מנות מתוכננות להיום.",
                      InlineKeyboardMarkup([_HOME_BTN]))
        return

    now = _now()
    taken = state["taken"].get(active.isoformat(), [])
    sent = state["sent"].get(active.isoformat(), [])

    header = f"📋 *לוח הזמנים של היום* — {_phase_line(day)}"
    if active != now.date():
        header += f"\n_יום הטיפול של {active.strftime('%d/%m')} — עדיין בתוך חלון השעות_"
    lines = [header, ""]
    for hour, minute, med in doses:
        slot = _slot(hour, minute, med)
        due = _dose_dt(active, hour, minute)
        if slot in taken:
            mark = "✅"
        elif due > now:
            mark = "🕐"
        elif slot in sent:
            mark = "🔔"
        else:
            mark = "⚪"
        suffix = " ⁺" if hour >= 24 else ""
        lines.append(f"{mark} `{_fmt_hm(hour, minute)}`{suffix}  {MEDS_SHORT[med]}")
    lines += ["", "✅ נלקח · 🔔 נשלחה תזכורת · 🕐 בהמשך", "", SPACING_TIP]
    await _render(update, "\n".join(lines), InlineKeyboardMarkup([_HOME_BTN]))


async def _reset_confirm(update: Update) -> None:
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑️ כן, מחק הכל", callback_data="ed_reset_yes")],
        _HOME_BTN,
    ])
    await _render(update, "⚠️ *איפוס הטיפול*\n\nפעולה זו תמחק את תאריך הניתוח, "
                          "ההגדרות והמעקב היומי. להמשיך?", keyboard)


async def _mark_taken(update: Update, state: dict, user_id: int, med: int, hhmm: str) -> None:
    query = update.callback_query
    now = _now()
    slot = f"{hhmm}-{med}"
    active = _active_day_date(state, now)
    taken = state["taken"].setdefault(active.isoformat(), [])
    if slot not in taken:
        taken.append(slot)
    # A taken dose cancels a pending snooze for the same drop.
    state["snoozes"] = [s for s in state["snoozes"] if s.get("slot") != slot]
    _save_state(user_id, state)

    text = (
        "✅ *נלקח*\n"
        f"_{_slot_time(slot)} · {now.strftime('%H:%M')}_\n\n"
        f"{MEDS[med]}"
    )
    done, total, nxt = _progress(state, active)
    if total:
        text += f"\n\nהיום: {done}/{total} · המנה הבאה: {nxt}"
    try:
        await query.edit_message_text(text, parse_mode="Markdown",
                                      reply_markup=InlineKeyboardMarkup([_HOME_BTN]))
    except BadRequest:
        pass


async def _snooze(update: Update, state: dict, user_id: int, med: int, hhmm: str) -> None:
    query = update.callback_query
    slot = f"{hhmm}-{med}"
    minutes = state["snooze_minutes"]
    due = _now() + timedelta(minutes=minutes)
    state["snoozes"] = [s for s in state["snoozes"] if s.get("slot") != slot][:MAX_SNOOZES - 1]
    state["snoozes"].append({"due": due.isoformat(), "med": med, "slot": slot})
    _touch(update, state)
    _save_state(user_id, state)

    text = (
        f"😴 *נודניק — אזכיר שוב ב-{due.strftime('%H:%M')}*\n\n"
        f"{MEDS[med]}\n"
        f"_מועד מקורי: {_slot_time(slot)}_"
    )
    try:
        await query.edit_message_text(text, parse_mode="Markdown",
                                      reply_markup=InlineKeyboardMarkup([_HOME_BTN]))
    except BadRequest:
        pass


async def router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Single entry point for every eye-drops callback button."""
    query = update.callback_query
    data = query.data or ""
    user_id = update.effective_user.id
    state = _touch(update, _load_state(user_id))

    # Hour buttons may need to answer with an alert, and a callback query can
    # only be answered once — so they run before the generic acknowledgement.
    if data.startswith(("ed_sh_", "ed_eh_")):
        try:
            hour = int(data.rsplit("_", 1)[1])
        except ValueError:
            await query.answer()
            return
        if data.startswith("ed_sh_"):
            if hour + MIN_AWAKE_HOURS > state["end_hour"]:
                await query.answer("שעת ההתחלה חייבת להיות לפחות שעתיים לפני שעת הסיום.",
                                   show_alert=True)
                return
            state["start_hour"] = hour
        else:
            if hour < state["start_hour"] + MIN_AWAKE_HOURS:
                await query.answer("שעת הסיום חייבת להיות לפחות שעתיים אחרי שעת ההתחלה.",
                                   show_alert=True)
                return
            state["end_hour"] = hour
        await query.answer()
        _mark_past_doses_handled(state, _now())
        _save_state(user_id, state)
        await _hours_panel(update, state)
        return

    await query.answer()

    if data in ("menu_eyedrops", "ed_home"):
        _save_state(user_id, state)
        await _show_panel(update, state)
        return

    if data == "ed_setdate":
        await _ask_date(update, context, state)
        return

    if data == "ed_settime":
        await _ask_time(update, context, state)
        return

    if data.startswith("ed_qdate_"):
        try:
            offset = int(data.rsplit("_", 1)[1])
        except ValueError:
            return
        await _apply_date(update, context, state, _now().date() + timedelta(days=offset))
        return

    if data.startswith("ed_qtime_"):
        chosen = parse_user_time(data.rsplit("_", 1)[1])
        if chosen:
            await _apply_time(update, context, state, chosen)
        return

    if data == "ed_notime":
        await _apply_time(update, context, state, None)
        return

    if data == "ed_hours":
        await _hours_panel(update, state)
        return

    if data == "ed_snooze":
        await _snooze_panel(update, state)
        return

    if data.startswith("ed_snz_"):
        try:
            minutes = int(data.rsplit("_", 1)[1])
        except ValueError:
            return
        if minutes in SNOOZE_CHOICES:
            state["snooze_minutes"] = minutes
            _save_state(user_id, state)
        await _snooze_panel(update, state)
        return

    if data == "ed_toggle":
        state["enabled"] = not state["enabled"]
        if state["enabled"]:
            _mark_past_doses_handled(state, _now())
        else:
            state["snoozes"] = []
        _save_state(user_id, state)
        await _show_panel(update, state)
        return

    if data == "ed_today":
        await _today_panel(update, state)
        return

    if data == "ed_reset":
        await _reset_confirm(update)
        return

    if data == "ed_reset_yes":
        _delete_state(user_id)
        context.user_data.pop("ed_awaiting", None)
        fresh = _touch(update, _clean_state({}))
        await _render(update, "🗑️ הטיפול אופס.\n\n" + _panel_text(fresh), _panel_keyboard(fresh))
        return

    match = re.fullmatch(r"ed_(take|zzz)_(\d)_(\d{4})", data)
    if match:
        action, med, hhmm = match.group(1), int(match.group(2)), match.group(3)
        if med not in MEDS:
            return
        if action == "take":
            await _mark_taken(update, state, user_id, med, hhmm)
        else:
            await _snooze(update, state, user_id, med, hhmm)


# ── text input gate (group -2) ───────────────────────────────────────────────

async def _text_gate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Consume a text message only while we are actually waiting for a date or an
    hour. Anything that clearly is not one releases the flag and falls through
    to the other features, so this can never trap the user.
    """
    awaiting = context.user_data.get("ed_awaiting")
    if awaiting not in ("date", "time"):
        return
    text = (update.message.text or "").strip()
    state = _touch(update, _load_state(update.effective_user.id))

    if awaiting == "time":
        parsed_time = parse_user_time(text)
        if parsed_time:
            await _apply_time(update, context, state, parsed_time)
            raise ApplicationHandlerStop
        if not _LOOKS_LIKE_TIME_RE.match(text):
            context.user_data.pop("ed_awaiting", None)
            return
        await update.message.reply_text(
            "❌ לא הצלחתי לקרוא את השעה.\nנסה בפורמט `14:30`.",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([_HOME_BTN]),
        )
        raise ApplicationHandlerStop

    parsed_date, parsed_time = parse_user_datetime(text)
    if parsed_date:
        await _apply_date(update, context, state, parsed_date, parsed_time)
        raise ApplicationHandlerStop

    if not _LOOKS_LIKE_DATE_RE.search(text) and text not in _KEYWORDS:
        context.user_data.pop("ed_awaiting", None)
        return  # not a date attempt — let the rest of the bot handle it
    await update.message.reply_text(
        "❌ לא הצלחתי לקרוא את התאריך.\nנסה בפורמט `28/07/2026` (אפשר גם `28/07/2026 14:30`) "
        "או כתוב `היום`.",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([_HOME_BTN]),
    )
    raise ApplicationHandlerStop


async def _callback_gate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Any button other than 'set date'/'set hour' means the user moved on."""
    data = (update.callback_query.data or "") if update.callback_query else ""
    if data not in ("ed_setdate", "ed_settime"):
        context.user_data.pop("ed_awaiting", None)


# ── register ─────────────────────────────────────────────────────────────────

def register(app) -> None:
    # group -2: runs before every other handler group, never swallows updates
    # it does not own (see _text_gate).
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _text_gate), group=-2)
    app.add_handler(CallbackQueryHandler(_callback_gate), group=-2)

    app.add_handler(CommandHandler("eyedrops", show_panel))
    app.add_handler(MessageHandler(
        filters.Regex(r"(?i)^(טיפות|טיפות עיניים|עיניים|לאסיק|לייזר)$"), show_panel))
    app.add_handler(CallbackQueryHandler(router, pattern=r"^(menu_eyedrops|ed_)"))
