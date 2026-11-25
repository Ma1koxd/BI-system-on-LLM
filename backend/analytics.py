import math
from datetime import date, datetime, time, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import Column, Integer, String, Text, create_engine, func, Index, select
from sqlalchemy.orm import DeclarativeBase, Session

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
GROUPS = {"shift": ("shift_id", "line"), "line": ("line",), "machine": ("machine",),
          "hour": ("tick",), "period_shift": ("shift_id",), "events": ("machine",)}


class Base(DeclarativeBase):
    pass


class Production(Base):
    __tablename__ = "production"
    tick = Column(Integer, primary_key=True)
    machine = Column(String, primary_key=True)
    shift_id = Column(Integer, nullable=False)
    line = Column(String, nullable=False)
    shift = Column(String, nullable=False)
    status = Column(String, nullable=False)
    plan = Column(Integer, nullable=False)
    good = Column(Integer, nullable=False)
    bad = Column(Integer, nullable=False)
    size_bad = Column(Integer, nullable=False)
    surface_bad = Column(Integer, nullable=False)
    shape_bad = Column(Integer, nullable=False)
    down = Column(Integer, nullable=False)
    started_at = Column(Text)
    ended_at = Column(Text)
    reason = Column(Text)
    __table_args__ = (Index("production_shift", "shift_id", "line", "machine"),)


def engine_for(db_path):
    return create_engine(f"sqlite:///{db_path}", future=True)


def init_db(db_path):
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = engine_for(db_path)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        count = session.scalar(select(func.count()).select_from(Production))
        if not count:
            session.bulk_insert_mappings(Production, list(_seed_rows()))
            session.commit()
    engine.dispose()


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
                yield {
                    "tick": tick, "machine": machine, "shift_id": s, "line": LINES[m // 2],
                    "shift": "Ночь" if s % 2 else "День",
                    "status": "Активен" if (s + m) % 4 else "Завершён",
                    "plan": plan, "good": good, "bad": bad, "size_bad": size,
                    "surface_bad": surface, "shape_bad": bad - size - surface, "down": down,
                    "started_at": begin.isoformat(" ", timespec="minutes") if down else None,
                    "ended_at": (begin + timedelta(minutes=down)).isoformat(" ", timespec="minutes") if down else None,
                    "reason": CAUSES[(s + h + m) % 3] if down else None,
                }


def _load_df(db_path):
    engine = engine_for(db_path)
    df = pd.read_sql_table("production", engine)
    engine.dispose()
    return df


def _clean(value):
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if np.isnan(value) else float(value)
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


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


def _scope_df(df, q):
    if q["since"] or q["until"]:
        if q["since"]:
            midnight = datetime.combine(date.fromisoformat(q["since"]), time.min)
            tick_min = (midnight - START) // timedelta(hours=1) - 168 * q["offset"]
            df = df[df["tick"] >= tick_min]
        if q["until"]:
            midnight = datetime.combine(date.fromisoformat(q["until"]), time.min)
            tick_max = (midnight - START) // timedelta(hours=1) + 24 - 168 * q["offset"]
            df = df[df["tick"] < tick_max]
    else:
        last = int(df["shift_id"].max()) if not df.empty else -1
        end = last - 14 * q["offset"]
        df = df[(df["shift_id"] >= end - q["count"] + 1) & (df["shift_id"] <= end)]
    for key in ("line", "machine", "shift", "status"):
        if q[key] != ALL:
            df = df[df[key] == q[key]]
    return df.copy()


def _selected_defect(q):
    return DEFECTS.get(q["defect"], "bad")


def _aggregate(df, q, dims, use_prior=False, for_events=False):
    if df.empty:
        cols = list(dims) + ["good", "plan", "bad", "down", "n", "distinct_ticks",
                             "rate", "load", "deviation", "average"]
        return pd.DataFrame(columns=cols)
    defect_col = _selected_defect(q)
    is_defect = defect_col in ("size_bad", "surface_bad", "shape_bad")
    work = df.copy()
    min_threshold = q["min"] if for_events else None
    if use_prior:
        work["g_good"] = work["p_good"]
        work["g_plan"] = work["p_plan"]
        work["g_bad"] = work[f"p_{defect_col}"] if is_defect else work["p_bad"]
        work["g_down"] = work["p_down"]
        if min_threshold is not None:
            work["g_down"] = work["g_down"].where(work["g_down"] > min_threshold, 0)
        work["g_tick"] = work["p_tick"]
        work["_has_prior"] = work["p_good"].notna()
        group_ok = work.groupby(list(dims))["_has_prior"].transform("all")
        work = work[group_ok].copy()
    else:
        work["g_good"] = work["good"]
        work["g_plan"] = work["plan"]
        work["g_bad"] = work[defect_col] if is_defect else work["bad"]
        work["g_down"] = work["down"]
        if min_threshold is not None:
            work["g_down"] = work["g_down"].where(work["g_down"] > min_threshold, 0)
        work["g_tick"] = work["tick"]
    agg = work.groupby(list(dims), dropna=False, as_index=False).agg(
        good=("g_good", "sum"),
        plan=("g_plan", "sum"),
        bad=("g_bad", "sum"),
        down=("g_down", "sum"),
        n=("tick", "size"),
        distinct_ticks=("g_tick", "nunique"),
    )
    agg["rate"] = np.where(agg["good"] + agg["bad"] > 0,
                           100.0 * agg["bad"] / (agg["good"] + agg["bad"]), np.nan)
    agg["load"] = np.where(agg["n"] > 0, 100.0 * (agg["n"] * 60 - agg["down"]) / (agg["n"] * 60), np.nan)
    agg["deviation"] = np.where(agg["plan"] != 0, 100.0 * (agg["good"] - agg["plan"]) / agg["plan"], np.nan)
    agg["average"] = np.where(agg["distinct_ticks"] > 0, agg["good"] / agg["distinct_ticks"], np.nan)
    return agg


def _restrict_df(df, q, dims):
    if not q["lag"] and not q["top"]:
        return df
    g = _aggregate(df, q, dims)
    field = METRICS[q["metric"]][0]
    if q["lag"]:
        g = g[g["deviation"].notna() & (g["deviation"] < 0) & (g["deviation"] <= -q["threshold"])]
        g = g.sort_values("deviation", ascending=True)
    else:
        g = g.sort_values(field, ascending=False, na_position="last")
    limit = q["top"] or -1
    if limit >= 0:
        g = g.head(limit)
    if g.empty:
        return df.iloc[0:0].copy()
    keys = g[list(dims)]
    return df.merge(keys, on=list(dims), how="inner")


def _label(row, dims):
    if "tick" in dims:
        tick = row["tick"] if "tick" in row else row[dims[0]]
        return (START + timedelta(hours=int(tick))).strftime("%d.%m %H:%M")
    if "shift_id" in dims:
        s = int(row["shift_id"]) if "shift_id" in row else int(row[dims[0]])
        return (START + timedelta(hours=s * 12)).strftime("%d.%m") + (" · ночь" if s % 2 else " · день")
    return row[dims[0]]


def _series(df, q):
    dims = list(GROUPS["hour" if q["grain"] == "hour" else "period_shift"])
    field = METRICS[q["metric"]][0]
    events = q["basis"] == "downtime_events"
    g = _aggregate(df, q, dims, for_events=events)
    prior_map = {}
    if q["compare"] == "week":
        pg = _aggregate(df, q, dims, use_prior=True, for_events=events)
        if not pg.empty:
            pg["_key"] = pg.apply(lambda r: tuple(r[d] for d in dims), axis=1)
            prior_map = dict(zip(pg["_key"], pg[field]))
    out = []
    for _, r in g.iterrows():
        key = tuple(r[d] for d in dims)
        out.append({
            "label": _label(r.to_dict(), dims),
            "actual": _clean(r[field]),
            "plan": _clean(r["plan"]) if q["metric"] == "output" else None,
            "previous": _clean(prior_map.get(key)),
            "downtime": int(r["down"]) if not (isinstance(r["down"], float) and math.isnan(r["down"])) else 0,
        })
    return out


def col(key, label, unit=""):
    return {"key": key, "label": label, "unit": unit}


BASE_COLUMNS = (col("good", "Выпуск", "шт."), col("plan", "План", "шт."),
                col("deviation", "Отклонение", "%"), col("bad", "Брак", "шт."),
                col("rate", "Доля брака", "%"), col("down", "Простои", "мин"))


def _metrics_table(df, q, dims):
    field, label, unit = METRICS[q["metric"]]
    events = q["basis"] == "downtime_events"
    g = _aggregate(df, q, dims, for_events=events)
    if q["lag"]:
        g = g.sort_values("deviation", ascending=True)
    elif q["top"] or dims == list(GROUPS["machine"]):
        g = g.sort_values(field, ascending=False, na_position="last")
    elif "shift_id" in dims:
        g = g.sort_values("shift_id", ascending=False)
    labels = {"tick": "Час", "line": "Линия", "shift_id": "Смена", "machine": "Станок"}
    columns = [col(k, labels[k]) for k in dims] + list(BASE_COLUMNS)
    if field in ("average", "load"):
        columns.append(col(field, label, unit))
    deltas = {}
    if "tick" in dims:
        hg = _aggregate(df, q, ["tick"], for_events=events)
        hourly = dict(zip(hg["tick"], hg[field]))
        sorted_ticks = sorted(hourly)
        prev = None
        for t in sorted_ticks:
            if prev is not None and t == prev + 1:
                deltas[t] = hourly[t] - hourly[prev]
            else:
                deltas[t] = None
            prev = t
    prior_map = {}
    if q["compare"] == "week":
        pg = _aggregate(df, q, dims, use_prior=True, for_events=events)
        if not pg.empty:
            pg["_key"] = pg.apply(lambda r: tuple(r[d] for d in dims), axis=1)
            prior_map = dict(zip(pg["_key"], pg[field]))
    rows = []
    for _, r in g.iterrows():
        row = {d: _clean(r[d]) for d in dims}
        row.update({
            "good": _clean(r["good"]), "plan": _clean(r["plan"]), "bad": _clean(r["bad"]),
            "deviation": _clean(r["deviation"]), "rate": _clean(r["rate"]),
            "down": _clean(r["down"]),
        })
        if field in ("average", "load"):
            row[field] = _clean(r[field])
        if "tick" in dims:
            row["hour_change"] = _clean(deltas.get(r["tick"]))
        if q["compare"] == "week":
            key = tuple(r[d] for d in dims)
            old = prior_map.get(key)
            row["previous"] = _clean(old)
            if old is not None and not (isinstance(r[field], float) and math.isnan(r[field])):
                row["difference"] = _clean(r[field] - old)
            else:
                row["difference"] = None
        if "tick" in dims or "shift_id" in dims:
            row[dims[0]] = _label(row, dims)
        rows.append(row)
    if "tick" in dims:
        columns = columns + [col("hour_change", "К прошлому часу", "п.п." if unit == "%" else unit)]
    if q["compare"] == "week":
        columns = columns + [col("previous", "Неделей ранее", unit),
                            col("difference", "Изменение", "п.п." if unit == "%" else unit)]
    return {"columns": columns, "rows": [{c["key"]: row.get(c["key"]) for c in columns} for row in rows]}


def _defect_table(df, q):
    columns = [col("reason", "Причина брака"), col("bad", "Брак", "шт."), col("rate", "Доля всего выпуска", "%")]
    weekly = q["compare"] == "week"
    if weekly:
        columns = columns + [col("previous", "Доля неделей ранее", "%"), col("difference", "Изменение", "п.п.")]
    rows = []
    for reason in DEFECTS:
        if q["defect"] not in (ALL, reason):
            continue
        cname = DEFECTS[reason]
        good = int(df["good"].sum()) if not df.empty else 0
        bad = int(df[cname].sum()) if not df.empty else 0
        rate = (100.0 * bad / (good + bad)) if (good + bad) else None
        row = {"reason": reason, "bad": bad, "rate": _clean(rate)}
        if weekly:
            if (not df.empty) and "has_prior" in df.columns and bool(df["has_prior"].all()):
                p_good = int(df["p_good"].sum())
                p_bad = int(df[f"p_{cname}"].sum())
                p_rate = (100.0 * p_bad / (p_good + p_bad)) if (p_good + p_bad) else None
            else:
                p_rate = None
            row["previous"] = _clean(p_rate)
            row["difference"] = _clean(rate - p_rate) if (rate is not None and p_rate is not None) else None
        rows.append(row)
    rows.sort(key=lambda r: -r["bad"])
    return {"columns": columns, "rows": rows}


def _events_table(df, q):
    columns = [col("started_at", "Начало"), col("ended_at", "Окончание"), col("line", "Линия"),
               col("machine", "Станок"), col("down", "Простой", "мин"), col("reason", "Причина"),
               col("rate", "Брак на линии за час", "%")]
    defect_col = _selected_defect(q)
    is_defect = defect_col in ("size_bad", "surface_bad", "shape_bad")
    bad_col = defect_col if is_defect else "bad"
    if not df.empty:
        groups = df.groupby(["tick", "line"], as_index=False).agg(
            good=("good", "sum"),
            bad=(bad_col, "sum"),
        )
        groups["rate"] = np.where(groups["good"] + groups["bad"] > 0,
                                 100.0 * groups["bad"] / (groups["good"] + groups["bad"]), np.nan)
        rate_map = dict(zip(zip(groups["tick"], groups["line"]), groups["rate"]))
    else:
        rate_map = {}
    sub = df[df["down"] > q["min"]].copy() if not df.empty else df
    sub = sub.sort_values(["down", "tick", "machine"], ascending=[False, False, True])
    rows = []
    for _, r in sub.iterrows():
        rows.append({
            "started_at": r["started_at"], "ended_at": r["ended_at"],
            "line": r["line"], "machine": r["machine"],
            "down": _clean(r["down"]), "reason": r["reason"],
            "rate": _clean(rate_map.get((r["tick"], r["line"]))),
        })
    return {"columns": columns, "rows": rows}


def _number(value):
    if value is None:
        return "нет данных"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float) and math.isnan(value):
        return "нет данных"
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
            value = sum(row["down"] for row in rows if row["down"] is not None)
        suffix = "" if unit.endswith(".") else "."
        fact = f"{label} за выбранный период: {_number(value)} {unit}{suffix}"
        if not historical_kpi or historical_kpi.get(field) is None or value is None:
            comparison = "Недостаточно сопоставимых данных за предыдущую неделю."
        else:
            prior = historical_kpi[field]
            change_unit = "п.п." if unit == "%" else unit
            change_suffix = "" if change_unit.endswith(".") else "."
            comparison = f"Неделей ранее: {_number(prior)} {unit}{suffix} Изменение: {_number(value - prior)} {change_unit}{change_suffix}"
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
        top = max(rows, key=lambda r: float("-inf") if r[key] is None else r[key])
        group = ", ".join(str(top[k]) for k in ("shift_id", "line", "machine") if k in top)
        return [f"Максимум показателя «{label}»: {group}, {_number(top[key])} {unit}."], "Сопоставьте различия между группами с заданиями смены и журналом оборудования."
    return [f"Выпуск: {kpi['good']} при плане {kpi['plan']} шт. Отклонение: {_number(kpi['deviation'])} %.",
            f"Доля брака: {_number(kpi['rate'])} %. Простои: {kpi['down']} машино-минут. Средний выпуск за час: {_number(kpi['average'])} шт."], "Изучите часы с отклонениями и проверьте соответствующие записи журнала простоев."


def _overall_kpi(df, q):
    defect_col = _selected_defect(q)
    is_defect = defect_col in ("size_bad", "surface_bad", "shape_bad")
    if df.empty:
        good = plan = bad = down = 0
        n = distinct = 0
    else:
        good = int(df["good"].sum())
        plan = int(df["plan"].sum())
        bad = int(df[defect_col].sum()) if is_defect else int(df["bad"].sum())
        down = int(df["down"].sum())
        n = len(df)
        distinct = int(df["tick"].nunique())
    rate = (100.0 * bad / (good + bad)) if (good + bad) else None
    load = (100.0 * (n * 60 - down) / (n * 60)) if n else None
    deviation = (100.0 * (good - plan) / plan) if plan else None
    average = (1.0 * good / distinct) if distinct else None
    return {"good": good, "plan": plan, "bad": bad, "rate": rate, "down": down,
            "load": load, "deviation": deviation, "average": average}


def _overall_prior_kpi(df, q):
    if df.empty or "has_prior" not in df.columns or not bool(df["has_prior"].all()):
        return None
    defect_col = _selected_defect(q)
    is_defect = defect_col in ("size_bad", "surface_bad", "shape_bad")
    good = int(df["p_good"].sum())
    plan = int(df["p_plan"].sum())
    bad = int(df[f"p_{defect_col}"].sum()) if is_defect else int(df["p_bad"].sum())
    down = int(df["p_down"].sum())
    n = len(df)
    distinct = int(df["p_tick"].nunique())
    field = METRICS[q["metric"]][0]
    rate = (100.0 * bad / (good + bad)) if (good + bad) else None
    load = (100.0 * (n * 60 - down) / (n * 60)) if n else None
    deviation = (100.0 * (good - plan) / plan) if plan else None
    average = (1.0 * good / distinct) if distinct else None
    metric_map = {"good": good, "plan": plan, "bad": bad, "rate": rate, "down": down,
                  "load": load, "deviation": deviation, "average": average}
    result = {"good": good, "plan": plan, "bad": bad, "rate": rate, "down": down,
              "load": load, "deviation": deviation, "average": average}
    result[field] = metric_map.get(field, result.get(field))
    return result


def _analyze(db_path, name, arguments, previous_filters, **defaults):
    q = _resolve(name, {} if arguments is None else arguments, previous_filters, defaults)
    basis = q["basis"]
    dims = list(GROUPS["hour" if basis == "hourly_output" else q["view"]])
    df = _load_df(db_path)
    scoped = _scope_df(df, q)
    if q["compare"] == "week":
        prior = df[["tick", "machine", "status", "good", "plan", "bad",
                    "size_bad", "surface_bad", "shape_bad", "down"]].copy()
        prior = prior.rename(columns={
            "tick": "p_tick", "status": "p_status", "good": "p_good",
            "plan": "p_plan", "bad": "p_bad", "size_bad": "p_size_bad",
            "surface_bad": "p_surface_bad", "shape_bad": "p_shape_bad", "down": "p_down",
        })
        prior["tick"] = prior["p_tick"] + 168
        scoped = scoped.merge(prior, on=["tick", "machine"], how="left")
        if q["status"] != ALL:
            mask = scoped["p_status"] == q["status"]
            pcols = [c for c in scoped.columns if c.startswith("p_")]
            scoped.loc[~mask, pcols] = np.nan
        scoped["has_prior"] = scoped["p_good"].notna()
    scoped = _restrict_df(scoped, q, dims)
    kpi = _overall_kpi(scoped, q)
    historical_kpi = None
    if q["compare"] == "week":
        if (not scoped.empty) and bool(scoped["has_prior"].all()):
            historical_kpi = _overall_prior_kpi(scoped, q)
    if basis == "downtime_events" and q["compare"] != "week":
        table = _events_table(scoped, q)
    elif basis == "defect_breakdown":
        table = _defect_table(scoped, q)
    else:
        table = _metrics_table(scoped, q, dims)
    series = _series(scoped, q)
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