# 数析研习所 · Data Analyst Academy

面向互联网数据分析实习求职的交互式学习平台。课程、SQL/Python练习、自动判题、进度与错题笔记均在浏览器中完成。

## 学习者启动方式

双击根目录下的 `启动学习平台.bat`。首次启动会安装依赖，之后会自动打开浏览器。

也可以在终端运行：

```powershell
npm install
npm run dev
```

然后访问 `http://localhost:4173`。

## 当前内容

- 8周知识路线、8个模块、36节由浅入深的课程
- SQL从数据表、SELECT、筛选、聚合和JOIN，到窗口函数、留存、漏斗、复购和异动分析
- Python从变量、容器、函数和异常处理，到Pandas清洗、聚合、合并、时间序列和贡献归因
- 42道分层题目：20道SQL、10道Python、8道统计理论、4道业务Case
- 所有题目均包含提示、参考答案、解析或结构化评分表
- DuckDB-Wasm浏览器端SQL执行与结果判定
- Pyodide浏览器端Python/Pandas执行与隐藏测试
- 学习进度、连续学习、收藏、尝试次数及错题笔记

## 数据与隐私

SQL和Python代码均在浏览器本地执行，不会上传到远程判题服务器。学习进度保存在浏览器的 `localStorage` 中；清除浏览器站点数据会同时清除进度。

Python运行环境首次使用时需要联网下载运行时与Pandas，后续浏览器通常会缓存相关资源。

## 开发验证

```powershell
npm run lint
npm run build
```

端到端测试脚本位于 `tests/test_app.py`，覆盖首页、课程完成状态、SQL判题和Python/Pandas判题。
