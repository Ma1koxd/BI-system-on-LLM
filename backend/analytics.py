import math
import sqlite3
from contextlib import closing
from datetime import date, datetime, time, timedelta
from pathlib import Path


START = datetime(2026, 10, 29, 8)
MACHINES = ("S-101", "S-102", "S-201", "S-202")
LINES = ("А", "Б")
CAUSES = ("Сбой подачи материала", "Наладка инструмента", "Проверка привода")
DEFECTS = {"Размер": "size_bad", "Поверхность": "surface_bad", "Геометрия": "shape_bad"}
ALL = "Все"
SHIFT_COUNT = 42
TOOL_DESCRIPTIONS = {
    "shift_summary": "Сводка план/факт по сменам и линиям. Поддерживает группировку по линии или станку, средний часовой выпуск и отбор активных заказов.",
    "plan_shortfalls": "Группы с отставанием от плана не менее threshold процентов. По умолчанию 10 %. Выводит долю брака; худшее отклонение первым.",
    "hourly_output": "Динамика по часам с планом, простоями и изменением к предыдущему последовательному часу.",
    "machine_ranking": "Топ станков по показателю metric. По умолчанию три станка по наибольшей доле брака.",
    "compare_week": "Сопоставление выбранных групп с теми же станками и часами на 7 дней раньше. Сохраняет текущий рейтинг и порог.",
    "downtime_events": "Журнал событий с причиной и временем начала/окончания. min задаёт строгий порог длительности события в минутах.",
    "defect_breakdown": "Число и доля бракованных изделий по трём причинам или одной выбранной причине.",
    "equipment_load": "Загрузка оборудования по станкам, сменам или линиям, взвешенная по доступным машино-минутам.",
}
DEFAULT_FILTERS = {
    "count": 5, "line": ALL, "machine": ALL, "shift": ALL,
    "status": ALL, "defect": ALL, "since": "", "until": "", "offset": 0,
    "view": "shift", "metric": "output", "compare": "plan", "lag": False,
    "top": 0, "min": 0, "threshold": 10, "grain": "shift",
    "tool": "shift_summary", "basis": "shift_summary",
}
METRICS = {
    "output": ("good", "Выпуск продукции", "шт."),
    "quality": ("rate", "Доля брака", "%"),
    "load": ("load", "Загрузка оборудования", "%"),
    "down": ("down", "Простои", "мин"),
    "average": ("average", "Средний выпуск за час", "шт./ч"),
}


def enum(*values):
    return {"type": "string", "enum": list(values)}


def integer(low, high):
    return {"type": "integer", "minimum": low, "maximum": high}


ARGUMENTS = {
    "count": {**integer(1, 42), "description": "Последние N смен относительно конца витрины"},
    "since": {"type": "string", "description": "Начальная дата YYYY-MM-DD включительно, пустая строка снимает ограничение"},
    "until": {"type": "string", "description": "Конечная дата YYYY-MM-DD включительно"},
    "line": enum(ALL, *LINES), "machine": enum(ALL, *MACHINES),
    "shift": enum(ALL, "День", "Ночь"), "status": enum(ALL, "Активен", "Завершён"),
    "defect": enum(ALL, *DEFECTS),
    "view": enum("shift", "line", "machine", "events"),
    "metric": enum(*METRICS), "grain": enum("shift", "hour"),
    "top": integer(0, 42), "min": integer(0, 1440),
    "threshold": {"type": "number", "minimum": 0, "maximum": 100,
                  "description": "Минимальное отставание, в процентах"},
    "offset": {**integer(0, 1), "description": "1 сдвигает окно выборки на 7 дней назад"},
    "compare": enum("plan", "week"), "lag": {"type": "boolean"},
}
TOOLS = [
    {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": ARGUMENTS, "additionalProperties": False},
    }}
    for name, description in TOOL_DESCRIPTIONS.items()
]


def _check_fields(fields, *, context):
    if not isinstance(fields, dict):
        raise ValueError("Фильтры должны быть объектом JSON.")
    for name, value in fields.items():
        if context and name in ("tool", "basis"):
            if not isinstance(value, str) or value not in TOOL_DESCRIPTIONS:
                raise ValueError("Неизвестный аналитический инструмент.")
            continue
        spec = ARGUMENTS.get(name)
        if spec is None:
            raise ValueError(f"Неизвестный параметр {name!r}.")
        if "enum" in spec:
            valid = value in spec["enum"]
        elif spec["type"] == "number":
            valid = type(value) in (float, int) and spec["minimum"] <= value <= spec["maximum"]
        elif spec["type"] == "integer":
            valid = type(value) is int and spec["minimum"] <= value <= spec["maximum"]
        elif spec["type"] == "boolean":
            valid = isinstance(value, bool)
        else:
            valid = isinstance(value, str) and (value == "" or len(value) == 10)
            if valid and value:
                try:
                    valid = date.fromisoformat(value).isoformat() == value
                except ValueError:
                    valid = False
        if not valid:
            raise ValueError(f"Недопустимое значение параметра {name!r}.")


def validate_filters(context):
    context = {} if context is None else context
    _check_fields(context, context=True)
    q = DEFAULT_FILTERS | context
    if q["since"] and q["until"] and q["since"] > q["until"]:
        raise ValueError("Конечная дата раньше начальной.")
    if q["line"] != ALL and q["machine"] != ALL:
        line = LINES[MACHINES.index(q["machine"]) // 2]
        if line != q["line"]:
            raise ValueError("Станок не принадлежит указанной линии.")
    return q


def _resolve(name, args, previous, defaults):
    _check_fields(args, context=False)
    q = validate_filters(previous)
    if name != "compare_week" and name != q["tool"]:
        q.update({k: DEFAULT_FILTERS[k] for k in ("lag", "top", "min", "threshold", "view", "metric", "grain", "compare")})
    if name != q["tool"]:
        q.update(defaults)
    if "count" in args and not ("since" in args or "until" in args):
        q.update(since="", until="")
    if "line" in args and "machine" not in args:
        q["machine"] = ALL
    if "machine" in args and "line" not in args:
        q["line"] = ALL
    q.update(args)
    q["tool"] = name
    if name == "compare_week":
        q["compare"] = "week"
    else:
        q["basis"] = name
    if q["basis"] == "machine_ranking":
        q.update(view="machine", top=q["top"] or 3)
    if q["basis"] == "plan_shortfalls":
        q["lag"] = True
    if q["basis"] == "downtime_events":
        q.update(view="events", metric="down")
    if q["basis"] == "defect_breakdown":
        q["metric"] = "quality"
    if q["basis"] == "equipment_load":
        q["metric"] = "load"
    return validate_filters(q)


def _seed_rows():
    seed = 23041

    def draw():
        nonlocal seed
        seed = seed * 16807 % 2147483647
        return seed / 2147483647

    for s in range(SHIFT_COUNT):
        for h in range(12):
            tick = s * 12 + h
            stamp = START + timedelta(hours=tick)
            for m, machine in enumerate(MACHINES):
                plan = 26 + m % 3 * 4 + s % 4
                troubled = (s == 38 and m < 2) or (s == 40 and m >= 2)
                down = math.floor(12 + draw() * 39) if draw() < (.23 if troubled else .033) else 0
                if (s, m, h) == (38, 1, 6):
                    down = 45
                good = math.floor(.5 + plan * (1 - down / 60) * (.86 + draw() * .24) * (.82 if troubled else 1))
                p_bad = .12 + draw() * .13 if troubled else .012 + draw() * .055
                bad = math.floor(.5 + good * p_bad)
                size = math.floor(.5 + bad * .5)
                surface = math.floor((bad - size) * .65)
                begin = stamp + timedelta(minutes=math.floor(draw() * (61 - down)))
                yield (tick, machine, s, LINES[m // 2], "Ночь" if s % 2 else "День",
                       "Активен" if (s + m) % 4 else "Завершён", plan, good, bad,
                       size, surface, bad - size - surface, down,
                       begin.isoformat(" ", timespec="minutes") if down else None,
                       (begin + timedelta(minutes=down)).isoformat(" ", timespec="minutes") if down else None,
                       CAUSES[(s + h + m) % 3] if down else None)


def init_db(db_path):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db_path, timeout=30)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        version = db.execute("PRAGMA user_version").fetchone()[0]
        if version == 1:
            return
        if version:
            raise RuntimeError(f"Неизвестная версия схемы SQLite: {version}.")
        db.execute("""
            CREATE TABLE production (
                tick INTEGER NOT NULL, machine TEXT NOT NULL, shift_id INTEGER NOT NULL,
                line TEXT NOT NULL, shift TEXT NOT NULL, status TEXT NOT NULL,
                plan INTEGER NOT NULL, good INTEGER NOT NULL, bad INTEGER NOT NULL,
                size_bad INTEGER NOT NULL, surface_bad INTEGER NOT NULL, shape_bad INTEGER NOT NULL,
                down INTEGER NOT NULL, started_at TEXT, ended_at TEXT, reason TEXT,
                PRIMARY KEY(tick, machine)
            )
        """)
        db.executemany("INSERT INTO production VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", _seed_rows())
        db.execute("CREATE INDEX production_shift ON production(shift_id,line,machine)")
        db.execute("PRAGMA user_version=1")


def _scope(db, q):
    conditions, values = [], []
    if q["since"] or q["until"]:
        for key, operator, extra in (("since", ">=", 0), ("until", "<", 24)):
            if q[key]:
                midnight = datetime.combine(date.fromisoformat(q[key]), time.min)
                tick = (midnight - START) // timedelta(hours=1)
                conditions.append(f"tick {operator} ?")
                values.append(tick + extra - 168 * q["offset"])
    else:
        last = db.execute("SELECT MAX(shift_id) FROM production").fetchone()[0]
        end = (last if last is not None else -1) - 14 * q["offset"]
        conditions.append("shift_id BETWEEN ? AND ?")
        values.extend((end - q["count"] + 1, end))
    for key in ("line", "machine", "shift", "status"):
        if q[key] != ALL:
            conditions.append(f"{key} = ?")
            values.append(q[key])
    db.execute("CREATE TEMP TABLE scope AS SELECT * FROM production WHERE " + " AND ".join(conditions), values)


def _totals(defect, *, qualified="", down_threshold=None):
    prefix = qualified
    good, plan, bad, tick, down = (prefix + k for k in ("good", "plan", "bad", "tick", "down"))
    selected = prefix + DEFECTS.get(defect, "bad")
    down_term = down if down_threshold is None else f"CASE WHEN {down}>{down_threshold} THEN {down} ELSE 0 END"
    return f"""
        COALESCE(SUM({good}),0) AS good, COALESCE(SUM({plan}),0) AS plan,
        COALESCE(SUM({selected}),0) AS bad, COALESCE(SUM({down_term}),0) AS down,
        100.0*SUM({selected})/NULLIF(SUM({good}+{bad}),0) AS rate,
        100.0*(COUNT({tick})*60-SUM({down}))/NULLIF(COUNT({tick})*60,0) AS load,
        100.0*(SUM({good})-SUM({plan}))/NULLIF(SUM({plan}),0) AS deviation,
        1.0*SUM({good})/NULLIF(COUNT(DISTINCT {tick}),0) AS average"""


GROUPS = {"shift": ("shift_id", "line"), "line": ("line",), "machine": ("machine",),
          "hour": ("tick",), "period_shift": ("shift_id",), "events": ("machine",)}


def _restrict(db, q, dims, totals):
    if not q["lag"] and not q["top"]:
        return
    cols = ", ".join(dims)
    field = METRICS[q["metric"]][0]
    having = "HAVING deviation < 0 AND deviation <= ?" if q["lag"] else ""
    order = "deviation ASC" if q["lag"] else f"{field} DESC"
    values = [-q["threshold"]] if q["lag"] else []
    db.execute(f"""CREATE TEMP TABLE chosen AS SELECT {cols}, {totals}
        FROM scope GROUP BY {cols} {having} ORDER BY {order}, {cols} LIMIT ?""",
               [*values, q["top"] or -1])
    match = " AND ".join(f"chosen.{col}=scope.{col}" for col in dims)
    db.execute(f"DELETE FROM scope WHERE NOT EXISTS(SELECT 1 FROM chosen WHERE {match})")


def _previous(db, q):
    predicate = "AND p.status = ?" if q["status"] != ALL else ""
    params = [q["status"]] if predicate else []
    db.execute(f"""CREATE TEMP TABLE historical AS
        SELECT s.tick, s.shift_id, s.line, s.machine, p.tick AS present,
               p.good, p.plan, p.bad, p.size_bad, p.surface_bad, p.shape_bad, p.down
        FROM scope AS s LEFT JOIN production AS p
        ON p.tick=s.tick-168 AND p.machine=s.machine {predicate}""", params)


def _groups(db, q, dims, *, previous=False, for_events=False):
    cols = ", ".join(dims)
    source = "historical" if previous else "scope"
    totals = _totals(q["defect"], down_threshold=q["min"] if for_events else None)
    sql = f"SELECT {cols}, {totals} FROM {source} GROUP BY {cols}"
    if previous:
        sql += " HAVING COUNT(present)=COUNT(*)"
    return [dict(row) for row in db.execute(sql + f" ORDER BY {cols}")]


def _stamp(tick):
    return START + timedelta(hours=tick)


def _label(row, dims):
    if "tick" in dims:
        return _stamp(row["tick"]).strftime("%d.%m %H:%M")
    if "shift_id" in dims:
        s = row["shift_id"]
        return _stamp(s * 12).strftime("%d.%m") + (" · ночь" if s % 2 else " · день")
    return row[dims[0]]


def _series(db, q):
    dims = GROUPS["hour" if q["grain"] == "hour" else "period_shift"]
    field = METRICS[q["metric"]][0]
    events = q["basis"] == "downtime_events"
    prior = {r[dims[0]]: r[field] for r in _groups(db, q, dims, previous=True, for_events=events)} if q["compare"] == "week" else {}
    return [{"label": _label(r, dims), "actual": r[field],
             "plan": r["plan"] if q["metric"] == "output" else None,
             "previous": prior.get(r[dims[0]]), "downtime": r["down"]}
            for r in _groups(db, q, dims, for_events=events)]


def col(key, label, unit=""):
    return {"key": key, "label": label, "unit": unit}


BASE_COLUMNS = (col("good", "Выпуск", "шт."), col("plan", "План", "шт."),
                col("deviation", "Отклонение", "%"), col("bad", "Брак", "шт."),
                col("rate", "Доля брака", "%"), col("down", "Простои", "мин"))


def _metrics_table(db, q, dims):
    field, label, unit = METRICS[q["metric"]]
    events = q["basis"] == "downtime_events"
    rows = _groups(db, q, dims, for_events=events)
    if q["lag"]:
        rows.sort(key=lambda r: r["deviation"])
    elif q["top"] or dims == GROUPS["machine"]:
        rows.sort(key=lambda r: r[field] if r[field] is not None else -math.inf, reverse=True)
    elif "shift_id" in dims:
        rows.sort(key=lambda r: -r["shift_id"])
    labels = {"tick": "Час", "line": "Линия", "shift_id": "Смена", "machine": "Станок"}
    columns = [col(k, labels[k]) for k in dims] + list(BASE_COLUMNS)
    if field in ("average", "load"):
        columns.append(col(field, label, unit))
    if "tick" in dims:
        deltas = dict(db.execute(f"""WITH hourly AS (
            SELECT tick, {_totals(q["defect"])} FROM scope GROUP BY tick
        ), pairs AS (
            SELECT tick, {field} AS value, LAG(tick) OVER w AS last_tick,
                   LAG({field}) OVER w AS last_value FROM hourly WINDOW w AS (ORDER BY tick)
        ) SELECT tick, CASE WHEN tick=last_tick+1 THEN value-last_value END FROM pairs"""))
        for row in rows:
            row["hour_change"] = deltas[row["tick"]]
        columns.append(col("hour_change", "К прошлому часу", "п.п." if unit == "%" else unit))
    if q["compare"] == "week":
        keys = lambda row: tuple(row[d] for d in dims)
        prior = {keys(r): r[field] for r in _groups(db, q, dims, previous=True, for_events=events)}
        for row in rows:
            old = prior.get(keys(row))
            row["previous"] = old
            row["difference"] = row[field] - old if old is not None and row[field] is not None else None
        columns.extend([col("previous", "Неделей ранее", unit),
                        col("difference", "Изменение", "п.п." if unit == "%" else unit)])
    for row in rows:
        if "tick" in dims or "shift_id" in dims:
            row[dims[0]] = _label(row, dims)
    return {"columns": columns, "rows": [{c["key"]: row[c["key"]] for c in columns} for row in rows]}


def _defect_table(db, q):
    columns = [col("reason", "Причина брака"), col("bad", "Брак", "шт."), col("rate", "Доля всего выпуска", "%")]
    weekly = q["compare"] == "week"
    if weekly:
        columns.extend([col("previous", "Доля неделей ранее", "%"), col("difference", "Изменение", "п.п.")])
    rows = []
    for reason in DEFECTS:
        if q["defect"] not in (ALL, reason):
            continue
        result = db.execute(f"SELECT {_totals(reason)} FROM scope HAVING COUNT(*)>0").fetchone()
        if result is None:
            continue
        row = {"reason": reason, "bad": result["bad"], "rate": result["rate"]}
        if weekly:
            prior = db.execute(f"SELECT {_totals(reason)} FROM historical HAVING COUNT(*)=COUNT(present) AND COUNT(*)>0").fetchone()
            row["previous"] = prior["rate"] if prior else None
            row["difference"] = row["rate"] - row["previous"] if row["rate"] is not None and row["previous"] is not None else None
        rows.append(row)
    rows.sort(key=lambda r: -r["bad"])
    return {"columns": columns, "rows": rows}


def _events_table(db, q):
    columns = [col("started_at", "Начало"), col("ended_at", "Окончание"), col("line", "Линия"),
               col("machine", "Станок"), col("down", "Простой", "мин"), col("reason", "Причина"),
               col("rate", "Брак на линии за час", "%")]
    bad = DEFECTS.get(q["defect"], "bad")
    rows = db.execute(f"""WITH rates AS (
        SELECT tick,line,100.0*SUM({bad})/NULLIF(SUM(good+bad),0) AS rate FROM scope GROUP BY tick,line
        ) SELECT started_at, ended_at, s.line, machine, down, reason, rate FROM scope s
        JOIN rates USING(tick,line) WHERE down>? ORDER BY down DESC,tick DESC,machine""", (q["min"],))
    return {"columns": columns, "rows": [dict(row) for row in rows]}


def _number(value):
    if value is None:
        return "нет данных"
    if isinstance(value, int):
        return str(value)
    return f"{value:.1f}".replace(".", ",")


def _facts(q, table, kpi, historical_kpi):
    rows = table["rows"]
    basis = q["basis"]
    if not rows:
        if basis == "downtime_events":
            text = f"Событий длиннее {q['min']} мин в выборке нет."
        elif q["lag"]:
            text = f"Нет групп с отставанием от плана на {q['threshold']} % и более."
        else:
            text = "Для выбранного периода и фильтров записей нет."
        return [text], "Расширьте период или снимите фильтр линии, смены либо станка."
    first = rows[0]
    if q["compare"] == "week":
        field, label, unit = METRICS[q["metric"]]
        value = kpi[field]
        if basis == "downtime_events":
            value = sum(row["down"] for row in rows)
        suffix = "" if unit.endswith(".") else "."
        fact = f"{label} за выбранный период: {_number(value)} {unit}{suffix}"
        if not historical_kpi or historical_kpi[field] is None or value is None:
            comparison = "Недостаточно сопоставимых данных за предыдущую неделю."
        else:
            prior = historical_kpi[field]
            change_unit = "п.п." if unit == "%" else unit
            change_suffix = "" if change_unit.endswith(".") else "."
            comparison = f"Неделей ранее: {_number(prior)} {unit}{suffix} Изменение: {_number(value-prior)} {change_unit}{change_suffix}"
        return [fact, comparison], "Сверьте сменные задания и журнал событий за оба периода."
    if basis == "downtime_events":
        facts = [f"Событий в журнале: {len(rows)}.",
                 f"Самый длинный простой: {first['machine']}, {first['started_at']} - {first['ended_at']}, {first['down']} мин.",
                 f"Причина в журнале: {first['reason']}. Доля брака в выборке линии {first['line']} за час события: {_number(first['rate'])} %."]
        return facts, f"Проверьте журнал обслуживания станка {first['machine']} и повторяемость причины «{first['reason']}»."
    if basis == "defect_breakdown":
        return [f"Первое место по числу дефектов: {first['reason']}, {first['bad']} шт., {_number(first['rate'])} % изготовленных деталей."], "Проверьте карты измерений и журнал настройки инструмента по этой причине брака."
    if q["lag"]:
        facts = []
        for row in rows[:2]:
            who = ", ".join(str(row[k]) for k in ("shift_id", "line", "machine") if k in row)
            facts.append(f"{who}: выпуск {row['good']} из {row['plan']} шт., отклонение {_number(row['deviation'])} %, доля брака {_number(row['rate'])} %.")
        return facts, "Сопоставьте эти смены с журналом простоев и причинами брака."
    if basis in ("machine_ranking", "equipment_load"):
        key, label, unit = METRICS[q["metric"]]
        top = max(rows, key=lambda r: -math.inf if r[key] is None else r[key])
        group = ", ".join(str(top[k]) for k in ("shift_id", "line", "machine") if k in top)
        return [f"Максимум показателя «{label}»: {group}, {_number(top[key])} {unit}."], "Сопоставьте различия между группами с заданиями смены и журналом оборудования."
    return [f"Выпуск: {kpi['good']} при плане {kpi['plan']} шт. Отклонение: {_number(kpi['deviation'])} %.",
            f"Доля брака: {_number(kpi['rate'])} %. Простои: {kpi['down']} машино-минут. Средний выпуск за час: {_number(kpi['average'])} шт."], "Изучите часы с отклонениями и проверьте соответствующие записи журнала простоев."


def _analyze(db_path, name, arguments, previous_filters, **defaults):
    q = _resolve(name, {} if arguments is None else arguments, previous_filters, defaults)
    basis = q["basis"]
    dims = GROUPS["hour" if basis == "hourly_output" else q["view"]]
    with closing(sqlite3.connect(db_path, timeout=30)) as db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN")
        _scope(db, q)
        _restrict(db, q, dims, _totals(q["defect"]))
        historical_kpi = None
        if q["compare"] == "week":
            _previous(db, q)
            totals = _totals(q["defect"], down_threshold=q["min"] if basis == "downtime_events" else None)
            historical_kpi = db.execute(f"""
                SELECT {totals} FROM historical
                HAVING COUNT(present)=COUNT(*) AND COUNT(*)>0""").fetchone()
        kpi = dict(db.execute(f'SELECT {_totals(q["defect"])} FROM scope').fetchone())
        if basis == "downtime_events" and q["compare"] != "week":
            table = _events_table(db, q)
        elif basis == "defect_breakdown":
            table = _defect_table(db, q)
        else:
            table = _metrics_table(db, q, dims)
        series = _series(db, q)
    facts, recommendation = _facts(q, table, kpi, historical_kpi)
    _, label, unit = METRICS[q["metric"]]
    return {"filters": q, "table": table, "series": series,
            "kpis": {key: kpi[key] for key in ("good", "plan", "bad", "rate", "down", "load")},
            "metric_label": label, "unit": unit, "facts": facts, "recommendation": recommendation}


def shift_summary(db_path, arguments=None, previous_filters=None):
    return _analyze(db_path, "shift_summary", arguments, previous_filters)


def plan_shortfalls(db_path, arguments=None, previous_filters=None):
    return _analyze(db_path, "plan_shortfalls", arguments, previous_filters, lag=True)


def hourly_output(db_path, arguments=None, previous_filters=None):
    return _analyze(db_path, "hourly_output", arguments, previous_filters, grain="hour")


def machine_ranking(db_path, arguments=None, previous_filters=None):
    return _analyze(db_path, "machine_ranking", arguments, previous_filters,
                    view="machine", top=3, metric="quality")


def compare_week(db_path, arguments=None, previous_filters=None):
    return _analyze(db_path, "compare_week", arguments, previous_filters, compare="week")


def downtime_events(db_path, arguments=None, previous_filters=None):
    return _analyze(db_path, "downtime_events", arguments, previous_filters, view="events", metric="down")


def defect_breakdown(db_path, arguments=None, previous_filters=None):
    return _analyze(db_path, "defect_breakdown", arguments, previous_filters, metric="quality")


def equipment_load(db_path, arguments=None, previous_filters=None):
    return _analyze(db_path, "equipment_load", arguments, previous_filters, view="machine", metric="load")


HANDLERS = {handler.__name__: handler for handler in (
    shift_summary, plan_shortfalls, hourly_output, machine_ranking,
    compare_week, downtime_events, defect_breakdown, equipment_load,
)}


def execute_tool(db_path, name, arguments, previous_filters=None):
    if not isinstance(name, str) or name not in HANDLERS:
        raise ValueError("Неизвестный аналитический инструмент.")
    if not isinstance(arguments, dict):
        raise ValueError("Аргументы функции должны быть объектом JSON.")
    return HANDLERS[name](db_path, arguments, previous_filters)
