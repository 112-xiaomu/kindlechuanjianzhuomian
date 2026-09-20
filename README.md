# Kindle 墨水屏日历

把一块电池坏掉的 Kindle 8（2016，KT3）改造成挂墙墨水屏日历，显示日期、天气、课程表。

## 整体架构

```
天气(Open-Meteo) + 课程表(schedule.json)
        │
        ▼
GitHub Actions 每 15 分钟跑一次 render.py  → 生成 index.html + display.png
        │
        ▼
GitHub Pages 托管（公网静态地址）
        │
        ▼
Kindle（已越狱）通过 WiFi 定时拉取刷新
        │
        ▼
供电：充电头 / 带"小电流模式"的移动电源（勿插电脑 USB）
```

## 一、云端部署（GitHub，免费）

1. **新建公开仓库**：把本目录推到一个**公开(public)**的 GitHub 仓库（公开仓库 Actions 免费不限时长）。
   ```bash
   git init && git add . && git commit -m "init"
   git remote add origin https://github.com/<你的用户名>/<仓库名>.git
   git push -u origin main
   ```
2. **开启 GitHub Pages**：仓库 Settings → Pages → Source 选 `Deploy from a branch` → 分支选 `main`、目录 `/ (root)` → Save。等 1 分钟后，访问 `https://<你的用户名>.github.io/<仓库名>/` 就能看到页面，`/display.png` 是图片。
3. **让定时任务跑起来**：第一次推送后，进 Actions 页看 `Update Display` 工作流是否跑通（也可以点 "Run workflow" 手动触发一次）。之后它会**每 15 分钟**自动抓天气、重新渲染、提交到 Pages。

> 访问慢 / 被墙的备选：GitHub 在国内偶尔不稳。如果 Kindle 连不上 github.io，可考虑镜像到 Gitee Pages（需实名审核）或 Cloudflare Pages，二选一替换即可，脚本本身不用改。

## 二、配置数据

- **显示内容**：`render.py` 每次生成三个文件——
  - `index.html`：浏览器页面，**横竖屏自适应**（Kindle 浏览器横过来拿也好看）；
  - `display.png`：横屏 800×600 墨水屏图；
  - `display_portrait.png`：竖屏 600×800 墨水屏图。
  - 内置 **每日一言**（好心情语录，按日期自动轮换，改 `render.py` 顶部 `QUOTES` 列表可自定义）。
  - 课程多显示不下时，**优先保证下一节课**：正在上的课标「进行中」，接下来要上的标「下一节」，放不下的折叠为「…还有 n 节未显示」。

- **`config.json`**：
  - `city_name` / `latitude` / `longitude`：你的城市与经纬度（经纬度去 [Open-Meteo](https://open-meteo.com/en/docs) 或百度地图拾取）。我也可以帮你查。
  - `semester_start`：**第 1 周的周一**日期（ISO 格式），用于算"当前第几周"。当前值 `2026-08-31`，即 **9 月 1 日所在周算第 1 周**。
  - `timezone`：时区，国内用 `Asia/Shanghai`。
  - `refresh_minutes`：自动刷新间隔（分钟）。
- **`schedule.json`**：课程表。`day` 用 `0=周一 … 6=周日`：
  - `weeks_range`：周次范围，如 `"1-10"`（第 1~10 周有课）；最常用。
  - `weeks`：上这些周的列表，如 `[2,4,6]`（第 2、4、6 周有课）；留 `null` = 每周。
  - `parity`：`"odd"` 单周 / `"even"` 双周，用于单双周课程。
  - 有课表文件（Excel/图片）的话发给我，我帮你转成这份 JSON。

## 三、Kindle 端（越狱 + 常亮显示）

### 1. 越狱（;installHtml，适用出厂固件 5.8.0）

你的 Kindle 8 = KT3，实测固件 **5.8.0 出厂初始固件**（`D:\system\version.txt`），无需降级，直接用经典工厂固件越狱法：

1. 下载 `kindle-jb-factory`（MobileRead 官方发布，已验证 MD5 `fd23...c379`），解压得到 **`main-htmlviewer.tar.gz`**（保持 .tar.gz 不解包）。
2. 拷到 Kindle 根目录（`D:\`，与 documents 同级）。
3. 弹出 Kindle，在**搜索框**输入 `;installHtml`（分号 + 大写 H + 小写 l）回车 → 屏幕闪动并重启 = 越狱成功。
4. 装 **JailBreak Hotfix**（`Update_jailbreak_hotfix_*.bin` 拷根目录 → 设置 → 菜单 → 更新您的 Kindle）保持越狱，并**关闭自动更新**。
5. 验证：根目录建 `RUNME.sh`（内容 `eips 0 0 "Hello"`），搜索框 `;log runme`，屏幕左上出现文字即成功。

> 本地已下载好：`_jb\extract\FactoryJB\main-htmlviewer.tar.gz` 和 `_jb\JailBreak-1.16.N-FW-5.x-hotfix.zip`，后者解压出 .bin 后拷到根目录即可。

### 2. 常亮显示（二选一）

**方式 A：浏览器 + 关闭屏保（推荐，最简单）**

1. 越狱后，在 Kindle 主页**搜索框**输入 `~ds` 回车 → 关闭屏保（永不锁屏；再输一次恢复）。
2. 连 WiFi，打开**体验版浏览器**，地址输入 `https://<用户名>.github.io/<仓库名>/`。
3. 页面自带 15 分钟自动刷新 + 秒级走时。把它加收藏/设为首页即可。

**方式 B：屏保显示图片（更稳，无浏览器边框）**

1. 越狱后安装 **KUAL** + **fbink**（NiLuJe 出品，见 MobileRead 论坛）。
2. 写一个拉图脚本，用 cron（`;log`）每 15 分钟执行一次：
   ```sh
   #!/bin/sh
   wget -O /mnt/us/display.png "https://<用户名>.github.io/<仓库名>/display.png"
   fbink -g file=/mnt/us/display.png,halign=center,valign=center
   ```
3. 让 Kindle 快速进入屏保即可常驻显示。

## 四、供电与常见问题

- **供电**：必须插**墙充头**或**带"小电流/涓流模式"的移动电源**。插电脑 USB 会进 U 盘模式、屏幕无法显示。
- **电池彻底失效可能无法开机**：先确认"插电能正常进主界面"。若开机循环，可在 Kindle 根目录建一个空文件 `DONT_CHECK_BATTERY` 绕过电池检测（越狱指南里也有提到）。
- **移动电源自动断电**：Kindle 常亮耗电很小，普通充电宝会误判关机。换带小电流模式的，或直接用墙充。
- **时间戳**：GitHub Actions 用 UTC，但脚本已按 `timezone` 转成本地时间，无需额外设置。
- **字号想调**：改 `render.py` 里 HTML 的 `<style>` 或 PNG 的 `font(...)` 参数。
