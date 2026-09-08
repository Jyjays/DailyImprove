# Cache Lab 环境说明（CS:APP3e Ch6 配套实验）

> 建立时间：2026-09-08。所有命令与数字均在本机实测，不是凭印象写的。
> 未核实的部分会显式标注。

**当前工作目录：`~/LAB/CSAPP/cachelab`（WSL 原生 ext4）**
本仓库 `practice/phase0/cachelab/cachelab-handout/` 只是**原始归档副本**，不在这里编译运行。

---

## 1. 获取 start code

**官方来源**（已验证可下载）：

| 内容 | 链接 | 状态 |
|---|---|---|
| Labs 总入口 | http://csapp.cs.cmu.edu/3e/labs.html | 200 OK |
| Cache Lab handout（4,116,480 B） | https://csapp.cs.cmu.edu/3e/cachelab-handout.tar | 200 OK，已下载 |
| Writeup（实验说明书） | http://csapp.cs.cmu.edu/3e/cachelab.pdf | 200 OK（301 后跳转） |

官网说明：Self-Study Handout 是给自学者用的，**不含答案**（答案只给 instructor）。

**下载命令**：

```bash
curl -sSL -o cachelab-handout.tar https://csapp.cs.cmu.edu/3e/cachelab-handout.tar
tar xf cachelab-handout.tar      # 解出 cachelab-handout/ 目录
```

本仓库已下载并解压在 `practice/phase0/cachelab/cachelab-handout/`。

**Writeup 一定要读**——Part A/B 的要求、`-v` 输出格式、评分口径都在里面。

---

## 2. 必须放在 WSL 原生文件系统（这是最大的坑）

**结论：不要直接在 `/mnt/d/...` 项目目录里跑。**

实测对比（同一份代码、同一台机器）：

| 工作目录 | `./test-trans -M 32 -N 32` 耗时 |
|---|---|
| `/mnt/d/...`（drvfs，Windows 文件系统） | **> 300 秒未跑完**（timeout 124） |
| `~/LAB/CSAPP/cachelab`（WSL2 ext4 原生） | **1.6 秒** |

差两个数量级。原因是 test-trans 会调 valgrind 生成内存 trace 并写 `trace.tmp`，
在 drvfs 上的文件 IO 极慢。

**正确做法**：

```bash
# 在 WSL 里（已执行过，此处为重建步骤）
mkdir -p ~/LAB/CSAPP
cp -r /mnt/d/Tools/workplace/DailyImprove/DailyImprove/practice/phase0/cachelab/cachelab-handout/* ~/LAB/CSAPP/cachelab/
cd ~/LAB/CSAPP/cachelab && make
```

想用 Windows 编辑器改代码，访问 `\\wsl$\Ubuntu\home\jyjays\LAB\CSAPP\cachelab\`
（编辑没问题，但**编译和运行必须进 WSL**）。改完把 `csim.c` / `trans.c` 同步回仓库归档。

目录约定：`~/LAB/CSAPP/<lab名>/`。CSAPP 不止一个 lab，后续 malloc lab（Ch9）放
`~/LAB/CSAPP/malloclab/`，不要跟 cachelab 混在一个目录。

---

## 3. 环境（已实测通过）

| 工具 | 版本 | 备注 |
|---|---|---|
| WSL2 Ubuntu | 24.04 | `wsl -l -v` 显示 Running / VERSION 2 |
| gcc | 13.3.0 | Makefile 用 `-std=c99 -Werror` |
| make | GNU Make 4.3 | |
| valgrind | 3.22.0 | 支持 `--tool=lackey`，test-trans 依赖它 |
| python3 | 3.12.3 | |
| gdb | 15.0.50 | |
| python2 | **不存在** | 见第 4 节 |

顺带：这套环境同时解决了主线 A 的 `fio` / `io_uring` 需求（原来担心 Windows 跑不了）。

### getopt 在 `-std=c99 -Werror` 下会不会报错？

**实测不会。** 我原本担心 gcc 13 严格 c99 下 `getopt` 隐式声明会被 `-Werror` 拦掉，
写了个最小样例验证：

```bash
gcc -g -Wall -Werror -std=c99 -m64 -o probe probe.c   # 通过，无报错
```

前提是要 `#include <getopt.h>`（`<unistd.h>` 在 glibc 下通常也带，但显式 include 更稳）。

---

## 4. driver.py 是 Python 2，已迁移为 driver3.py

原 `driver.py` 的 shebang 是 `#!/usr//bin/python`（本身还有个笔误路径），且系统是 Python 3.12、
连 `python` 命令都不存在，直接跑必挂。

**已生成 `driver3.py`**，只改了三处 Python 2→3 兼容性问题，**评分逻辑一行没动**：

1. `print` 语句 → `print()` 函数
2. `map(int, ...)` → `list(map(int, ...))`（py3 的 map 是迭代器，原代码 `csim_cscore[0]` 会炸）
3. `subprocess.Popen` 加 `text=True`（py3 返回 bytes，`re` 处理不了）

```bash
python3 driver3.py          # 一次跑完 Part A + Part B 并出分
```

---

## 5. 评分口径（从 driver.py 源码读出，硬数字）

| 项 | 满分 | 满分 miss 阈值 | 零分 miss 阈值 |
|---|---|---|---|
| csim 正确性 | 27 | 全对 | — |
| Trans 32×32 | 8 | ≤ 300 | ≥ 600 |
| Trans 64×64 | 8 | ≤ 1300 | ≥ 2000 |
| Trans 61×67 | 10 | ≤ 2000 | ≥ 3000 |
| **合计** | **53** | | |

**Part B 实测 baseline**（`trans.c` 自带的朴素行扫描）：

```
32x32:  hits:869  misses:1184  evictions:1152
```

也就是说 32×32 要从 **1184 → 300** 才满分，约 4 倍改进空间。

### 三个容易踩的细节

1. **Part A 和 Part B 相互独立。** `test-trans.c` 第 140 行调用的是
   `./csim-ref`（官方参考模拟器），**不是**你写的 `csim`。所以 Part B 不依赖 Part A，
   可以分开做、分开交。
2. **Part B 的 cache 参数**（`trans.c` 注释原文）：1KB、直接映射、32B 行。
   即 s=5（32 组）、E=1、b=5。一行装 8 个 int。
3. **超时是 `alarm(120)`**（test-trans.c 第 243 行）。比一些旧资料说的 60 秒宽裕，
   但在 valgrind 下 + 慢文件系统仍可能触发，触发后 miss 记为 `2147483647`（invalid）。

---

## 6. 常用命令

```bash
cd ~/LAB/CSAPP/cachelab
make                              # 每次 make 会生成 <user>-handin.tar

./test-csim                       # 只测 Part A，和 csim-ref 逐项对比
./csim-ref -s 4 -E 1 -b 4 -t traces/yi.trace    # 参考答案：hits:4 misses:5 evictions:3

./test-trans -M 32 -N 32          # 只测 Part B 的 32x32
./test-trans -M 64 -N 64
./test-trans -M 61 -N 67

python3 driver3.py                # 全部跑完出总分
```

`traces/` 里：`yi.trace` / `yi2.trace` / `dave.trace` / `trans.trace` / `long.trace`（4MB）。

---

## 7. 待办 / 未核实

- [x] ~~Writeup PDF 下载~~ → 已下载到 `~/LAB/CSAPP/cachelab-writeup.pdf`（47,072 B）
- [ ] Part B 是否限制局部变量个数（有资料说上限 12 个）——**未核实**，以 writeup 为准

---

## 8. 顺带发现：`~/LAB` 下已有的本地资源（主线 A 用得上）

搭建环境时扫到 `~/LAB` 下已有这些仓库，与主线 A（存储/IO）直接相关，
后面做 E18（四条 IO 路径）和 E17（fio 基线）时别再去找资料，先看本地：

| 路径 | 对哪条线有用 |
|---|---|
| `~/LAB/iRangeGraph-disk`（含 `third_party/liburing`） | **io_uring 源码就在本地**，E18 直接读 |
| `~/LAB/ClickBench` | 列存 benchmark，你的列存背景可直接复用做对照数据 |
| `~/LAB/mini-lsm` | LSM 存储引擎，存储主线 |
| `~/LAB/postgres` | PostgreSQL 源码（Gamma 是它的扩展） |
| `~/LAB/mem0`、`~/LAB/graphiti`、`~/LAB/gammamem` | Agent Memory 交叉线（T1/T3） |

注：以上只记录了路径存在，内容与可用性**未核实**。
