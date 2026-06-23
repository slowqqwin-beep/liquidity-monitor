# 如何把这个包推到你的 Git 仓库

在本地仓库根目录执行：

```bash
# 1. 解压本包，把内容覆盖/复制到仓库根目录
# 注意：它只会新增 docs/sr3-watch、scripts/build_sr3_watch_dashboard.py 和独立 workflow

# 2. 构建一次
python scripts/build_sr3_watch_dashboard.py

# 3. 本地预览
# 直接打开 docs/sr3-watch/index.html
# 或者：
python -m http.server 8000
# 浏览器打开 http://localhost:8000/docs/sr3-watch/

# 4. 提交
git add docs/sr3-watch scripts/build_sr3_watch_dashboard.py .github/workflows/sr3-watch-dashboard.yml README_SR3_WATCH.md
git commit -m "add standalone SR3 repair watch dashboard"
git push
```

GitHub Pages 访问：

```text
https://<username>.github.io/<repo>/sr3-watch/
```

重要边界：

```text
不要合并进旧 dashboard
不要接 Risk OS
不要接 run_all.py
不要影响仓位
mixed_repair / deceleration 不得显示为买入信号
```


2s10s 模块：

```bash
# 每天从 TradingView 下载 2s10s 后，放到仓库根目录，例如：
# 2s10s.csv
# 或 US10Y-US02Y, 1D.csv

python scripts/build_sr3_watch_dashboard.py
```
