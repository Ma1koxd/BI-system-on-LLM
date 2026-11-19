"""Offline Russian intent parsing for the no-key mode; uses the same SQL tools."""
import re
from datetime import date, timedelta

from analytics import DEFAULT_FILTERS


def parse_question(question: str, context: dict) -> tuple[str, dict]:
    text = question.lower().replace("ё", "е").replace("\u2013", "-").replace("\u2014", "-")
    if re.search(r"сброс|сначала|общий обзор", text):
        return "shift_summary", {k: v for k, v in DEFAULT_FILTERS.items() if k not in {"tool", "basis"}}
    tool = context.get("tool", "shift_summary")
    args = {}
    match = re.search(r"(\d+)\s*смен", text)
    if match:
        args.update(count=int(match[1]), since="", until="", offset=0)
    elif re.search(r"последн\w* смен[уаы]", text):
        args.update(count=1, since="", until="", offset=0)
    if re.search(r"последн\w* (?:недел|7 дн)|за неделю", text):
        args.update(count=14, since="", until="", offset=0)
    for word, days in (("позавчера", 2), ("вчера", 1), ("сегодня", 0)):
        if word in text:
            day = (date(2026, 11, 19) - timedelta(days=days)).isoformat()
            args.update(since=day, until=day, offset=0)
            break
    normalized = re.sub(r"(\d{1,2})\.(\d{1,2})\.(\d{4})",
                        lambda m: f"{m[3]}-{int(m[2]):02}-{int(m[1]):02}", text)
    dates = re.findall(r"\d{4}-\d{2}-\d{2}", normalized)
    if dates:
        if len(dates) > 2:
            raise ValueError("Укажите одну дату или один интервал.")
        args.update(since=dates[0], until=dates[-1], offset=0)
    if re.search(r"ночн|ночь|ночам", text):
        args["shift"] = "Ночь"
    elif re.search(r"дневн|днем", text):
        args["shift"] = "День"
    elif re.search(r"все смены|обе смены", text):
        args["shift"] = "Все"
    line = re.search(r"(?:лини\w*|участ\w*)\s+([a-zа-я])\b", text)
    if line:
        args.update(line={"a": "А", "а": "А", "б": "Б", "b": "Б"}.get(line[1], line[1]), machine="Все")
    elif re.search(r"все лини|обе лини", text):
        args.update(line="Все", machine="Все")
    machine = re.search(r"[sс]-?\s*(\d+)\b", text)
    if machine:
        args.update(machine="S-" + machine[1], line=args.get("line", "Все"))
    if re.search(r"активн\w* заказ", text):
        args["status"] = "Активен"
    elif re.search(r"завершен\w* заказ", text):
        args["status"] = "Завершён"
    elif "все заказы" in text:
        args["status"] = "Все"
    if re.search(r"выпуск|план|сводк|производител", text):
        tool = "shift_summary"
        args["metric"] = "average" if re.search(r"средн\w* выпуск|выпуск в среднем", text) else "output"
    if re.search(r"брак|дефект", text):
        tool = "shift_summary"
        args["metric"] = "quality"
    for fragment, reason in (("размер", "Размер"), ("поверхност", "Поверхность"), ("геометри", "Геометрия")):
        if fragment in text:
            tool = "defect_breakdown"
            args.update(defect=reason, metric="quality")
    if re.search(r"брак.*причин|причин\w* брака", text):
        tool = "defect_breakdown"
    if re.search(r"просто[ийеяю]|инцидент", text):
        tool = "downtime_events"
        args["metric"] = "down"
    duration = re.search(r"(?:длиннее|дольше|свыше|более|больше|>)\s*(\d+)\s*мин", text)
    if duration:
        tool = "downtime_events"
        args["min"] = int(duration[1])
    if "загруз" in text:
        tool = "equipment_load"
        args["metric"] = "load"
    if re.search(r"по линиям|между линиями", text):
        args["view"] = "line"
    if re.search(r"по сменам|между сменами|сравни\w* смен[уы]", text):
        args.update(view="shift", grain="shift")
    if re.search(r"по станкам|по оборудованию", text):
        args["view"] = "machine"
    top = re.search(r"топ[ -]*(\d+)", text)
    if top:
        tool = "machine_ranking"
        args.update(top=int(top[1]), view="machine")
    if re.search(r"отста[еюв]|отставани|ниже плана", text):
        tool = "plan_shortfalls"
        args.update(lag=True, metric="output", compare="plan")
        threshold = re.search(r"(\d+(?:[,.]\d+)?)\s*%", text)
        if threshold:
            args["threshold"] = float(threshold[1].replace(",", "."))
    if re.search(r"по часам|почасов|к предыдущему часу", text):
        args["grain"] = "hour"
        if tool == "shift_summary":
            tool = "hourly_output"
    if re.search(r"прошл\w* недел|предыдущ\w* недел", text):
        if re.search(r"сравн|сопостав|относительно|к прошл", text):
            tool = "compare_week"
            args["compare"] = "week"
        else:
            args.update(offset=1, count=14, since="", until="")
    if not args and tool == context.get("tool", "shift_summary"):
        raise ValueError("Уточните показатель или фильтр. Например: «Топ-3 станка по доле брака».")
    return tool, args
