# -*- coding: utf-8 -*-
"""
Kindle 墨水屏日历渲染器
- 抓取 Open-Meteo 天气（免费、无需 API key）
- 读取 schedule.json 课程表
- 生成 index.html（浏览器自适应横竖屏）+ display.png（横屏 800x600）+
  display_portrait.png（竖屏 600x800），供 Kindle 显示
- 内置每日一言（按日期轮换）
"""

import datetime
import json
import os
import urllib.parse
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))

WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

# WMO 天气代码 -> 中文
WMO = {
    0: "晴", 1: "大致晴朗", 2: "多云", 3: "阴",
    45: "雾", 48: "雾凇",
    51: "毛毛雨", 53: "毛毛雨", 55: "毛毛雨",
    56: "冻毛毛雨", 57: "冻毛毛雨",
    61: "小雨", 63: "中雨", 65: "大雨",
    66: "冻雨", 67: "冻雨",
    71: "小雪", 73: "中雪", 75: "大雪", 77: "雪粒",
    80: "阵雨", 81: "阵雨", 82: "强阵雨",
    85: "阵雪", 86: "阵雪",
    95: "雷暴", 96: "雷暴伴冰雹", 99: "雷暴伴冰雹",
}

# 天气分类（用于画图标）
def weather_cat(code):
    if code in (0, 1):
        return "sun"
    if code == 2:
        return "partly"
    if code == 3:
        return "overcast"
    if code in (45, 48):
        return "fog"
    if code in (51, 53, 55, 56, 57, 80, 81, 82):
        return "rain"
    if code in (61, 63, 65, 66, 67):
        return "rain"
    if code in (71, 73, 75, 77, 85, 86):
        return "snow"
    if code in (95, 96, 99):
        return "thunder"
    return "cloud"

# 每日一言（好心情语录，按日期轮换）
QUOTES = [
    "今天也是元气满满的一天。",
    "保持热爱，奔赴山海。",
    "生活明朗，万物可爱。",
    "人间值得，未来可期。",
    "慢慢来，比较快。",
    "你笑起来真像好天气。",
    "万事顺遂，毫不蹉跎。",
    "愿今天有好事发生。",
    "今天的太阳为你而升起。",
    "所有美好都会如期而至。",
    "风很温柔，天很蓝，心情很好。",
    "一切都会好起来的，包括明天。",
    "记得微笑，好运自然来。",
    "健康平安，就是最好的一天。",
    "生活嘛，开心最重要。",
    "好运都藏在努力里。",
    "心愿如约，步履不停。",
    "做个温柔的人，遇见温柔的事。",
    "每一步都算数，每一天都值得。",
    "不慌不忙，闪闪发光。",
    "今天的风是甜的。",
    "好好吃饭，好好睡觉，好好爱自己。",
    "愿你眼里有光，心中有暖。",
    "笑一笑，没什么大不了。",
    "新的一天，新的期待。",
    "做喜欢的事，见想见的人。",
    "平凡的一天，也值得庆祝。",
    "把烦恼留在昨天，今天轻装上阵。",
    "日子甜甜，像今天的天气。",
    "今天的你也要开心呀。",
    "认真生活的人，运气不会太差。",
    "心怀期待，万事可期。",
    "山水万程，皆要好运。",
    "日日是好日，处处是好处。",
    "心之所向，素履以往。",
    "今天的星星也很亮。",
    "所求皆如愿，所行化坦途。",
    "把日子过成诗，简单而精致。",
    "早睡早起，心情美丽。",
    "愿你的努力，都有回响。",
]


def daily_quote(now):
    return QUOTES[(now.date() - datetime.date(2026, 1, 1)).days % len(QUOTES)]


def load_json(name):
    with open(os.path.join(BASE, name), "r", encoding="utf-8") as f:
        return json.load(f)


def load_config():
    return load_json("config.json")


def load_schedule():
    return load_json("schedule.json")["schedule"]


def now_local(cfg):
    from zoneinfo import ZoneInfo
    return datetime.datetime.now(ZoneInfo(cfg["timezone"]))


def current_week(cfg, now):
    """semester_start 填第 1 周的周一（ISO 日期），返回当前是第几周"""
    start = datetime.date.fromisoformat(cfg["semester_start"])
    delta = (now.date() - start).days
    return max(delta // 7 + 1, 1)


def entry_active(entry, week):
    weeks = entry.get("weeks")
    if weeks:
        return week in weeks
    rng = entry.get("weeks_range")
    if rng:
        a, b = str(rng).split("-")
        return int(a) <= week <= int(b)
    parity = entry.get("parity")
    if parity == "odd":
        return week % 2 == 1
    if parity == "even":
        return week % 2 == 0
    return True


def day_schedule(schedule, cfg, when):
    week = current_week(cfg, when)
    items = [e for e in schedule if e["day"] == when.weekday() and entry_active(e, week)]
    items.sort(key=lambda e: e["start"])
    return items


def next_item(items, now):
    """今天正在进行/即将开始的下一节课（结束时间晚于当前时间的第一节）"""
    hm = f"{now.hour:02d}:{now.minute:02d}"
    for e in items:
        if e["end"] > hm:
            return e
    return None


def fetch_weather(cfg):
    lat = cfg["latitude"]
    lon = cfg["longitude"]
    tz = cfg["timezone"]
    url = ("https://api.open-meteo.com/v1/forecast"
           f"?latitude={lat}&longitude={lon}"
           "&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m,apparent_temperature"
           "&daily=weather_code,temperature_2m_max,temperature_2m_min"
           f"&timezone={urllib.parse.quote(tz)}&forecast_days=4")
    req = urllib.request.Request(url, headers={"User-Agent": "kindle-calendar/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def find_font():
    candidates = [
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\msyhbd.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\simsun.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


# ---------------------------------------------------------------- HTML ----

def schedule_rows_html(items, next_e=None, badge="下一节", empty_text="今天没有课，好好休息 ☺"):
    if not items:
        return f'<div class="empty">{empty_text}</div>'
    rows = []
    for e in items:
        loc = e.get("location") or ""
        name = e.get("name") or ""
        t = f"{e['start']}–{e['end']}"
        is_next = next_e is not None and e is next_e
        badge_html = f'<span class="nb">{badge}</span>' if is_next else ""
        cls = " row next" if is_next else "row"
        rows.append(
            f'<div class="{cls}">{badge_html}<span class="t">{t}</span>'
            f'<span class="n">{name}</span>'
            f'<span class="l">{loc}</span></div>'
        )
    return "\n".join(rows)


def render_html(cfg, weather, schedule, now):
    city = cfg["city_name"]
    title = cfg.get("title", "日历")
    date_str = f"{now.month}月{now.day}日 {WEEKDAYS[now.weekday()]}"
    time_str = f"{now.hour:02d}:{now.minute:02d}"
    refresh = int(cfg.get("refresh_minutes", 15)) * 60
    quote = daily_quote(now)

    if weather:
        cur = weather["current"]
        daily = weather["daily"]
        wtxt = WMO.get(cur.get("weather_code"), "未知")
        temp = round(cur["temperature_2m"])
        tmax = round(daily["temperature_2m_max"][0])
        tmin = round(daily["temperature_2m_min"][0])
        parts = []
        if cur.get("relative_humidity_2m") is not None:
            parts.append(f"湿度 {round(cur['relative_humidity_2m'])}%")
        if cur.get("wind_speed_10m") is not None:
            parts.append(f"风速 {cur['wind_speed_10m']:.0f} km/h")
        detail_line = "　".join(parts) + f"　最高{tmax}° 最低{tmin}°"
        wx_big = f"{wtxt} {temp}°"
        fc = []
        for i in range(1, 4):
            d = now.date() + datetime.timedelta(days=i)
            fc.append(
                f'<div class="fcell"><span class="fd">{WEEKDAYS[d.weekday()]}</span>'
                f'<span class="fw">{WMO.get(daily["weather_code"][i], "?")}</span>'
                f'<span class="ft2">{round(daily["temperature_2m_max"][i])}°/{round(daily["temperature_2m_min"][i])}°</span></div>'
            )
        fc_html = "".join(fc)
    else:
        wx_big = "天气获取失败"
        detail_line = "请检查网络或 API"
        fc_html = ""

    today_items = day_schedule(schedule, cfg, now)
    tomorrow_items = day_schedule(schedule, cfg, now + datetime.timedelta(days=1))
    nxt = next_item(today_items, now)
    hm = f"{now.hour:02d}:{now.minute:02d}"
    badge = "进行中" if nxt and nxt["start"] <= hm < nxt["end"] else "下一节"

    return """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="%d">
<title>%s</title>
<style>
*{box-sizing:border-box;}
body{background:#fff;color:#111;font-family:sans-serif;margin:0;padding:16px;}
.hd{font-size:46px;font-weight:bold;border-bottom:3px solid #111;padding-bottom:10px;overflow:hidden;}
#clock{float:right;font-weight:normal;}
.left{float:left;width:31%%;}
.right{float:right;width:66%%;}
.wx{margin-top:14px;}
.wxbig{font-size:56px;font-weight:bold;line-height:1.1;}
.wxd{font-size:22px;color:#444;margin-top:8px;line-height:1.5;}
.quote{border:2px solid #111;padding:12px 14px;margin-top:22px;}
.quote .qt{font-size:16px;color:#666;letter-spacing:2px;}
.quote .qx{font-size:24px;margin-top:6px;line-height:1.5;}
.sec{font-size:26px;font-weight:bold;margin-top:20px;}
.sec::before{content:"";display:inline-block;width:8px;height:22px;background:#111;margin-right:10px;}
.row{display:block;border-bottom:1px solid #ccc;padding:10px 0;font-size:26px;overflow:hidden;}
.row.next{background:#111;color:#fff;padding:10px 8px;border-bottom:none;}
.row.next .t{color:#ddd;}
.row.next .n{color:#fff;}
.row.next .l{color:#ccc;}
.nb{display:inline-block;background:#fff;color:#111;font-size:15px;padding:1px 8px;margin-right:10px;vertical-align:middle;}
.row .t{float:left;width:33%%;color:#333;}
.row .n{float:left;width:45%%;}
.row .l{float:right;color:#666;text-align:right;}
.empty{font-size:24px;color:#888;padding:10px 0;}
.fc{margin-top:10px;border-top:2px solid #111;padding-top:10px;}
.fcell{float:left;width:33%%;text-align:center;font-size:22px;}
.fd{display:block;font-weight:bold;}
.fw{display:block;color:#444;margin:4px 0;}
.ft2{display:block;color:#111;}
.ft{clear:both;font-size:16px;color:#888;margin-top:20px;}
@media (max-width:640px){
  .left,.right{float:none;width:100%%;}
  .left{border-bottom:2px solid #111;padding-bottom:14px;}
}
</style>
</head>
<body>
<div class="hd">%s<span id="clock">%s</span></div>
<div class="left">
  <div class="wx">
    <div class="wxbig">%s</div>
    <div class="wxd">%s<br>%s</div>
  </div>
  <div class="quote">
    <div class="qt">每日一言</div>
    <div class="qx">%s</div>
  </div>
</div>
<div class="right">
  <div class="sec">今日课程</div>
  %s
  <div class="sec">明日课程</div>
  %s
  <div class="sec">未来三天</div>
  <div class="fc">%s</div>
</div>
<div class="ft">更新于 %s（每 %d 分钟自动刷新）</div>
<script>
var c=document.getElementById("clock");
function t(){var n=new Date();var h=n.getHours();var m=n.getMinutes();if(m<10)m="0"+m;c.innerHTML=h+":"+m;}
t();setInterval(t,1000);
</script>
</body>
</html>""" % (
        refresh, title, date_str, time_str, wx_big, city, detail_line, quote,
        schedule_rows_html(today_items, nxt, badge),
        schedule_rows_html(tomorrow_items, empty_text="明天没有课，睡个好觉 ☺"),
        fc_html, f"{now.hour:02d}:{now.minute:02d}", int(cfg.get("refresh_minutes", 15)),
    )


# ---------------------------------------------------------------- PNG -----

def draw_cloud(d, x, y, s, black, lw):
    """弧线拼一朵云（只画顶部弧 + 底部基线，避免内部交叉线）"""
    yb = y + int(s * 0.64)
    rA, rB, rC = int(s * 0.13), int(s * 0.23), int(s * 0.15)
    xa = x + int(s * 0.14)
    xc = x + int(s * 0.34)
    x3 = x + int(s * 0.84)
    d.arc([xa - rA, yb - 2 * rA, xa + rA, yb], 180, 350, fill=black, width=lw)
    d.arc([xc - rB, yb - 2 * rB, xc + rB, yb], 185, 360, fill=black, width=lw)
    d.arc([x3 - 2 * rC, yb - 2 * rC, x3, yb], 200, 360, fill=black, width=lw)
    d.line([xa - rA, yb, x3, yb], fill=black, width=lw)


def draw_weather_icon(d, cat, x, y, s, black=0, lw=None):
    """e-ink 风格天气图标，s 为边长"""
    if lw is None:
        lw = max(2, s // 14)

    def sun(cx, cy, r):
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=black, width=lw)
        import math
        for k in range(8):
            a = math.pi / 4 * k
            x1 = cx + int((r + lw * 2) * math.cos(a))
            y1 = cy + int((r + lw * 2) * math.sin(a))
            x2 = cx + int((r + s * 0.16) * math.cos(a))
            y2 = cy + int((r + s * 0.16) * math.sin(a))
            d.line([x1, y1, x2, y2], fill=black, width=lw)

    cx, cy = x + s // 2, y + s // 2

    if cat == "sun":
        sun(cx, cy, int(s * 0.26))
    elif cat == "partly":
        sun(cx + s // 4, cy - s // 5, int(s * 0.16))
        draw_cloud(d, x + int(s * 0.02), y + int(s * 0.26), int(s * 0.72), black, lw)
    elif cat == "cloud":
        draw_cloud(d, x + int(s * 0.08), y + int(s * 0.12), int(s * 0.84), black, lw)
    elif cat == "overcast":
        draw_cloud(d, x + int(s * 0.08), y + int(s * 0.02), int(s * 0.84), black, lw)
        d.line([x + s * 0.15, y + s * 0.82, x + s * 0.85, y + s * 0.82], fill=black, width=lw)
        d.line([x + s * 0.25, y + s * 0.94, x + s * 0.75, y + s * 0.94], fill=black, width=lw)
    elif cat == "fog":
        for i, fr in enumerate((0.3, 0.45, 0.6, 0.75)):
            d.line([x + s * 0.12, y + s * fr, x + s * (0.88 - 0.2 * (i % 2)), y + s * fr],
                   fill=black, width=lw)
    else:
        draw_cloud(d, x + int(s * 0.08), y + int(s * 0.02), int(s * 0.84), black, lw)
        if cat == "rain":
            for i in range(3):
                lx = x + s * (0.3 + 0.2 * i)
                d.line([lx, y + s * 0.66, lx - s * 0.06, y + s * 0.84], fill=black, width=lw)
        elif cat == "snow":
            for i in range(3):
                lx = x + s * (0.3 + 0.2 * i)
                ly = y + s * (0.72 + 0.08 * (i % 2))
                r2 = max(2, s // 22)
                d.ellipse([lx - r2, ly - r2, lx + r2, ly + r2], fill=black)
        elif cat == "thunder":
            zy = y + s * 0.6
            pts = [(cx + s * 0.05, zy), (cx - s * 0.1, zy + s * 0.15),
                   (cx + s * 0.02, zy + s * 0.15), (cx - s * 0.12, zy + s * 0.3)]
            d.line(pts, fill=black, width=lw)


def wrap_text(d, text, f, max_w):
    lines, cur = [], ""
    for ch in text:
        if d.textlength(cur + ch, font=f) <= max_w:
            cur += ch
        else:
            lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    return lines


class Ctx:
    """封装字体和常用绘图助手"""

    def __init__(self, d, fp):
        self.d = d
        self.fp = fp

    def f(self, size):
        if self.fp:
            try:
                return ImageFont.truetype(self.fp, size)
            except Exception:
                pass
        return ImageFont.load_default()

    def text(self, xy, s, size, fill=0):
        self.d.text(xy, s, fill=fill, font=self.f(size))

    def rtext(self, x_right, y, s, size, fill=0):
        w = self.d.textlength(s, font=self.f(size))
        self.d.text((x_right - w, y), s, fill=fill, font=self.f(size))

    def ctext(self, cx, y, s, size, fill=0):
        w = self.d.textlength(s, font=self.f(size))
        self.d.text((cx - w // 2, y), s, fill=fill, font=self.f(size))


def draw_header(c, W, now):
    d = c.d
    mx = 36
    date_str = f"{now.month}月{now.day}日 {WEEKDAYS[now.weekday()]}"
    time_str = f"{now.hour:02d}:{now.minute:02d}"
    c.text((mx, 20), date_str, 46)
    c.rtext(W - mx, 24, time_str, 44)
    d.line([(mx, 92), (W - mx, 92)], fill=0, width=3)
    return mx


def draw_course_rows(c, x, y, w, items, row_h=46, name_size=26, next_e=None,
                     max_rows=None, empty_text="今天没有课，好好休息", badge="下一节"):
    """课程行：时间 | 名称 | 地点；空间不足时优先保留下一节课，返回结束 y"""
    d = c.d
    right = x + w
    if not items:
        c.text((x, y), empty_text, 24, fill=120)
        return y + 38

    shown = list(items)
    if max_rows is not None and len(shown) > max_rows:
        keep = []
        if next_e in shown:
            keep.append(next_e)
        for e in shown:
            if len(keep) >= max_rows:
                break
            if e not in keep:
                keep.append(e)
        omitted = len(shown) - len(keep)
        shown = [e for e in shown if e in keep]
    else:
        omitted = 0

    for e in shown:
        t = f"{e['start']}–{e['end']}"
        name = e.get("name") or ""
        loc = e.get("location") or ""
        is_next = next_e is not None and e is next_e
        c.text((x, y + 2), t, 22)
        tx = x + 180
        if is_next:
            # 黑底白字「下一节/进行中」标签
            bw = 66 if len(badge) <= 3 else 88
            d.rectangle([tx, y + 1, tx + bw, y + 29], fill=0)
            c.ctext(tx + bw // 2, y + 4, badge, 17, fill=255)
            tx += bw + 12
        locw = 0
        if loc:
            locw = d.textlength(loc, font=c.f(20))
            c.rtext(right, y + 5, loc, 20, fill=120)
        maxw = right - locw - 16 - tx
        # 名称放不下时先缩小字号，仍放不下再截断加省略号
        fs = name_size
        while fs > 20 and name and d.textlength(name, font=c.f(fs)) > maxw:
            fs -= 4
        nf = c.f(fs)
        nm = name
        while nm and d.textlength(nm, font=nf) > maxw:
            nm = nm[:-1]
        if nm != name and nm:
            nm = nm[:-1] + "…"
        c.text((tx, y + 3), nm, fs)
        d.line([(x, y + row_h - 6), (right, y + row_h - 6)], fill=210, width=1)
        y += row_h

    if omitted > 0:
        c.text((x, y + 2), f"…还有 {omitted} 节未显示", 20, fill=120)
        y += 34
    return y


def draw_section_label(c, x, y, label):
    c.d.rectangle([x, y + 4, x + 8, y + 28], fill=0)
    c.text((x + 20, y), label, 28)
    return y + 44


def draw_forecast_strip(c, x, y, w, weather, now):
    """底部三日预报，返回结束 y"""
    d = c.d
    d.line([(x, y), (x + w, y)], fill=210, width=2)
    y += 12
    col_w = w // 3
    daily = weather["daily"]
    for k, i in enumerate(range(1, 4)):
        dd = now.date() + datetime.timedelta(days=i)
        cx = x + k * col_w + col_w // 2
        c.ctext(cx, y, WEEKDAYS[dd.weekday()], 22)
        c.ctext(cx, y + 32, WMO.get(daily["weather_code"][i], "?"), 20, fill=120)
        c.ctext(cx, y + 60, f"{round(daily['temperature_2m_max'][i])}° / {round(daily['temperature_2m_min'][i])}°", 22)
        if k < 2:
            d.line([(x + (k + 1) * col_w, y + 2), (x + (k + 1) * col_w, y + 82)], fill=210, width=1)
    return y + 90


def render_png(cfg, weather, schedule, now, out_path, portrait=False):
    from PIL import Image, ImageDraw, ImageFont

    if portrait:
        W, H = cfg["display"]["height"], cfg["display"]["width"]
    else:
        W, H = cfg["display"]["width"], cfg["display"]["height"]

    img = Image.new("L", (W, H), 255)
    d = ImageDraw.Draw(img)
    c = Ctx(d, find_font())
    quote = daily_quote(now)
    mx = 36
    right = W - mx

    draw_header(c, W, now)

    if weather:
        cur = weather["current"]
        daily = weather["daily"]
        wtxt = WMO.get(cur.get("weather_code"), "未知")
        temp = round(cur["temperature_2m"])
        tmax = round(daily["temperature_2m_max"][0])
        tmin = round(daily["temperature_2m_min"][0])
        cat = weather_cat(cur.get("weather_code", 3))
        parts = []
        if cur.get("relative_humidity_2m") is not None:
            parts.append(f"湿度 {round(cur['relative_humidity_2m'])}%")
        if cur.get("wind_speed_10m") is not None:
            parts.append(f"风速 {cur['wind_speed_10m']:.0f} km/h")
        detail2 = f"最高{tmax}° 最低{tmin}°"
        detail = "　".join(parts) + "　" + detail2
    else:
        wtxt, temp, detail, detail2, cat = "天气获取失败", "--", "", "", "cloud"
        parts = []

    if not portrait:
        # ============ 横屏 800x600：左天气/语录，右课程 ============
        col_split = 296
        d.line([(col_split, 116), (col_split, 470)], fill=210, width=2)

        # 左栏：天气
        c.text((mx, 112), cfg["city_name"], 30)
        draw_weather_icon(d, cat, mx, 156, 96)
        c.text((mx + 116, 160), f"{temp}°", 72)
        c.text((mx + 116, 244), wtxt, 26)
        c.text((mx, 282), "　".join(parts), 20, fill=120)
        c.text((mx, 310), detail2, 20, fill=120)
        y = 344
        d.line([(mx, y), (col_split - 24, y)], fill=210, width=2)
        y += 14
        c.text((mx, y), "每日一言", 18, fill=120)
        y += 30
        qf = c.f(24)
        for ln in wrap_text(d, f"「{quote}」", qf, col_split - 24 - mx):
            c.text((mx, y), ln, 24, fill=60)
            y += 34

        # 右栏：课程（空间不足时优先显示下一节课）
        cx0 = col_split + 28
        cw = right - cx0
        t_items = day_schedule(schedule, cfg, now)
        nxt = next_item(t_items, now)
        hm = f"{now.hour:02d}:{now.minute:02d}"
        badge = "进行中" if nxt and nxt["start"] <= hm < nxt["end"] else "下一节"
        tm_items = day_schedule(schedule, cfg, now + datetime.timedelta(days=1))
        tm_max = min(len(tm_items), 2)
        y = 112
        y = draw_section_label(c, cx0, y, "今日课程")
        # 预留明日区域 + 底部预报条的空间
        today_space = 478 - y - (16 + 44 + tm_max * 42) - 40
        t_max = max(1, today_space // 46)
        y = draw_course_rows(c, cx0, y, cw, t_items, next_e=nxt, max_rows=t_max, badge=badge)
        y += 16
        y = draw_section_label(c, cx0, y, "明日课程")
        y = draw_course_rows(c, cx0, y, cw, tm_items, row_h=42, max_rows=tm_max,
                             empty_text="明天没有课")

        # 底部：三日预报（横跨全宽）
        if weather:
            y = max(y + 12, 478)
            draw_forecast_strip(c, mx, y, W - 2 * mx, weather, now)

        c.rtext(right, H - 26, f"更新于 {now.hour:02d}:{now.minute:02d}", 16, fill=150)
    else:
        # ============ 竖屏 600x800：自上而下 ============
        c.text((mx, 110), cfg["city_name"], 30)
        draw_weather_icon(d, cat, mx, 152, 84)
        c.text((mx + 104, 156), f"{temp}°", 64)
        c.text((mx + 104, 232), wtxt, 26)
        c.text((mx, 262), detail, 20, fill=120)

        y = 306
        d.line([(mx, y), (right, y)], fill=210, width=2)
        y += 16
        t_items = day_schedule(schedule, cfg, now)
        nxt = next_item(t_items, now)
        hm = f"{now.hour:02d}:{now.minute:02d}"
        badge = "进行中" if nxt and nxt["start"] <= hm < nxt["end"] else "下一节"
        tm_items = day_schedule(schedule, cfg, now + datetime.timedelta(days=1))
        tm_max = min(len(tm_items), 2)
        y = draw_section_label(c, mx, y, "今日课程")
        today_space = 560 - y - (14 + 44 + tm_max * 42) - 40
        t_max = max(1, today_space // 46)
        y = draw_course_rows(c, mx, y, W - 2 * mx, t_items, next_e=nxt, max_rows=t_max, badge=badge)
        y += 14
        y = draw_section_label(c, mx, y, "明日课程")
        y = draw_course_rows(c, mx, y, W - 2 * mx, tm_items, row_h=42, max_rows=tm_max,
                             empty_text="明天没有课")

        if weather:
            y = max(y + 8, 560)
            y = draw_forecast_strip(c, mx, y, W - 2 * mx, weather, now)

        # 语录框
        qy = max(y + 10, H - 150)
        d.rectangle([mx, qy, right, H - 44], outline=0, width=2)
        c.text((mx + 14, qy + 8), "每日一言", 16, fill=120)
        qf = c.f(24)
        qy2 = qy + 32
        for ln in wrap_text(d, f"「{quote}」", qf, W - 2 * mx - 28)[:2]:
            c.text((mx + 14, qy2), ln, 24, fill=60)
            qy2 += 34

        c.rtext(right, H - 36, f"更新于 {now.hour:02d}:{now.minute:02d}", 16, fill=150)

    img.save(out_path)


def main():
    cfg = load_config()
    schedule = load_schedule()
    now = now_local(cfg)

    try:
        weather = fetch_weather(cfg)
    except Exception as e:
        weather = None
        print("天气获取失败:", e)

    html_path = os.path.join(BASE, "index.html")
    png_path = os.path.join(BASE, "display.png")
    png_p_path = os.path.join(BASE, "display_portrait.png")

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(render_html(cfg, weather, schedule, now))
    render_png(cfg, weather, schedule, now, png_path, portrait=False)
    render_png(cfg, weather, schedule, now, png_p_path, portrait=True)

    # 横屏旋转版：display.png(800x600) 精确转置成 600x800，供 Kindle 横放显示
    # fbink 不做软件旋转，旋转必须在渲染端完成；两个方向供用户按挂放方向二选一
    from PIL import Image
    _land = Image.open(png_path)
    _land.transpose(Image.ROTATE_270).save(os.path.join(BASE, "display_landscape_cw.png"))
    _land.transpose(Image.ROTATE_90).save(os.path.join(BASE, "display_landscape_ccw.png"))

    print(f"渲染完成: {now.isoformat()}")
    print(f"  HTML -> {html_path}")
    print(f"  PNG  -> {png_path}")
    print(f"  PNG  -> {png_p_path}")


from PIL import ImageFont  # noqa: E402  (Ctx 使用)

if __name__ == "__main__":
    main()
