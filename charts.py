"""Render a report from its calculated series. No client or provider data fetches."""
from base64 import b64encode
from io import BytesIO
from math import nan
from threading import Lock

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator


_render_lock = Lock()  # Shared Matplotlib font and renderer caches.


def chart_for(report: dict) -> dict:
    points = report["series"]
    label = report["metric_label"]
    unit = report["unit"]
    hourly = report["filters"]["grain"] == "hour"
    alt = f"{label}, {unit}. Точек на графике: {len(points)}."
    with _render_lock:
        fig = Figure(figsize=(9.0, 3.35), dpi=115, layout="constrained")
        FigureCanvasAgg(fig)
        ax = fig.subplots()
        if points:
            x = list(range(len(points)))
            actual = [p["actual"] if p["actual"] is not None else nan for p in points]
            marker = "o" if len(points) <= 30 else None
            ax.plot(x, actual, color="#c1582a", linewidth=2.1, marker=marker,
                    markersize=4, label="Факт", zorder=3)
            for key, name, color in (("plan", "План", "#62798c"),
                                     ("previous", "Неделей ранее", "#397557")):
                if not any(p.get(key) is not None for p in points):
                    continue
                values = [p[key] if p.get(key) is not None else nan for p in points]
                ax.plot(x, values, linestyle="--", color=color, linewidth=1.5,
                        marker=marker, markersize=3, label=name)
                if key == "plan" and hourly:
                    ax.fill_between(x, [0.9 * v for v in values], values,
                                    color=color, alpha=0.14, label="90-100 % плана")
            if hourly:
                stops = [i for i, p in enumerate(points) if p["downtime"] > 0]
                if stops:
                    ax.scatter(stops, [0.025] * len(stops), marker="D", s=16,
                               transform=ax.get_xaxis_transform(), color="#8e4030",
                               label="Час с простоем", zorder=4)
            elif report["filters"]["metric"] == "output":
                misses = [i for i, p in enumerate(points) if p.get("plan")
                          and p.get("actual") is not None and p["actual"] <= p["plan"] * .9]
                if misses:
                    ax.scatter(misses, [actual[i] for i in misses], color="#933b2e",
                               s=30, label="Отставание от 10 %", zorder=5)
            ticks = sorted({round(i * (len(points) - 1) / 5) for i in range(6)})
            tick_labels = [str(points[i]["label"]).replace(" · ", "\n") for i in ticks]
            ax.set_xticks(ticks, tick_labels, fontsize=8)
            ax.set_ylabel(unit, color="#58635a", fontsize=9)
            ax.set_ylim(bottom=0)
            ax.yaxis.set_major_locator(MaxNLocator(nbins=5))
            ax.grid(axis="y", linestyle=":", color="#d7ded7")
            ax.legend(loc="upper center", bbox_to_anchor=(.5, 1.22), ncol=4,
                      fontsize=8, frameon=False)
            ax.spines[["top", "right", "left"]].set_visible(False)
            ax.spines["bottom"].set_color("#d2dad2")
            ax.tick_params(colors="#576359", length=0, pad=6)
        else:
            ax.set_axis_off()
            ax.text(.5, .5, "Нет данных для выбранных условий", ha="center",
                    va="center", transform=ax.transAxes, color="#58635a")
        with BytesIO() as stream:
            fig.savefig(stream, format="png", facecolor="white")
            data = b64encode(stream.getvalue()).decode("ascii")
        fig.clear()
    return {"mime_type": "image/png", "data": data, "alt": alt}
