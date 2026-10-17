# 变更存档 / Patches Archive

本目录记录对补丁与工作流的**结构性变更**及其原因、验证方式与踩坑。每次大改追加一节，不删旧记录。

---

## 2026-10-05:上游核对 + Re:Kernel → ReKernel-X + VFS 后端开关

### 1. 上游核对结论（全部实测，非推断）

| 组件 | 上游 | 结论 |
|---|---|---|
| Re:Kernel (`Sakion-Team/Re-Kernel`) | `ac08296` (2026-09-20) | **整体替换为 ReKernel-X**（见下）。旧 `rekernel_extra.patch` 的内嵌源码与上游 Integrate 版基本逐字节一致，且含两处本地更优修正（`static` 收敛符号导出、补 `<linux/sched/jobctl.h>` include——正是上游 README 提示的已知坑），但已弃用 |
| ReKernel-X | `Patches/RekernelX/rkx-4.19.patch`（本组织 4.19 移植版，源自 NonGKI_Kernel_Build_OP8） | 新采用。改 `binder.c`/`binder_alloc.c`/`kernel/signal.c` + 新增 `drivers/rekernel_x/`（12 文件）；Kconfig/Makefile 接线 hunk 已从补丁剔除，由工作流手动完成（避免与其他步骤对 `drivers/Kconfig` 的文本注入互相踩） |
| DroidSpaces cgroup 补丁 | 上游 `02.fix_restore cgroup file prefix handling .patch`（2026-02-22 起未改） | 与本地 `cgroup.patch` 语义等价（仅缩进规范化），不更新 |
| DroidSpaces config | 上游 `Documentation/Kernel-Configuration.md` 已扩充 | **补齐 8 项**：`CFS_BANDWIDTH`、`CGROUP_CPUACCT`、`IPV6`、`IPV6_MULTIPLE_TABLES`、`IP6_NF_IPTABLES/FILTER/MANGLE/NAT/TARGET_MASQUERADE`。注意：上游还列了 `NF_CONNTRACK_IPV6`/`NF_NAT_IPV6`，但这两个符号在 4.19 **不存在**（4.18 起 nf_conntrack_ipv6/nf_nat_ipv6 已并入通用 nf_conntrack/nf_nat），写入是 no-op，故省略并注释说明 |
| `ksud-v2.patch` | backslashxx `148139e`（KSU_VERSION 32657） | `boot_patch.rs:enforce_bootimage_version` 目标代码逐字未变，dry-run RC=0，**不更新** |
| `xt_qtaguid` 相关 | — | **删除死文件** `fix_kernel_panic_in_xt_qtaguid.cocci`：本内核（sm8250 kona）根本没有 `net/netfilter/xt_qtaguid.c`，补丁无从应用；workflow 从未自动应用过它（原步骤自己写明 "not auto-applied"） |
| 内核 lineage-23.2 | `98a7970af93b` (2026-10-04) | 基线 `4238ee49a84b` 落后约 1200 提交，但 RKX/DS 补丁在最新树上实测仍干净应用（`binder.c` 仅 17 行 offset，0 fuzz 0 reject），`patch_base` 回退机制本次保留不动 |

### 2. Re:Kernel → ReKernel-X 替换

- 两套补丁都改 `drivers/android/binder.c`，**互斥**，必须替换而非叠加。
- config：`CONFIG_REKERNEL=y` + `CONFIG_REKERNEL_NETWORK=n` → `CONFIG_REKERNEL_X=y`（rkx 无独立 network 开关，netfilter/netuid 对象随主模块一起编）。
- 事件通道：Generic Netlink family `rekernel_x2`（旧 Re:Kernel 是自己的 proc/netlink 方案），用户空间接收端需配套 ReKernel-X。
- **实测**：4238ee49a84b 干净树上 0 offset 应用；`CONFIG_REKERNEL_X=y` 后 `make drivers/rekernel_x/` 全部 8 个 .o + `built-in.a` 编译通过，0 错误。

### 3. VFS 后端开关（HybridMount / NoMount，二选一，默认关）

实现：

- 新增 `workflow_dispatch` 输入 `vfs_hybridmount` / `vfs_nomount`（默认 `false`）。
- 新增 `Validate VFS backend selection` 步骤：互斥校验（>1 立即 fail）+ 组产物后缀 `VFS_LABEL`（`-hybridmount` / `-nomount` / 空）写入 `$GITHUB_ENV`，Upload 步骤用 `boot-patched-kernelsu-ds-rk${{ env.VFS_LABEL }}` 命名。
- HybridMount：内置补丁 `Patches/HybridMount/hybridmount_patch_to_4.19.patch`（复用 NonGKI_Kernel_Build_OP8 的已验证版本，5 个纯新增文件 + fs/Kconfig、fs/Makefile 各一处接线）。应用后 `.rej` 检查 + 三重校验（源文件 / Makefile 接线 / Kconfig 接线）。
- NoMount：在线 `curl .../kernel/setup.sh | bash -s "$NOMOUNT_COMMIT"`，**commit 固定**为 `a159c0c225e67f180b7fb55ad78a77b0f98beb5b`（2026-10-04 dev HEAD）——上游几乎每日提交，跟 dev 头会让构建不可复现。该 commit 已实测：setup.sh 在本内核树正常落 symlink + 双接线。
- 配置注入：在 `merge_config.sh` 之后、`olddefconfig` **之前**，按 `VFS_LABEL` 分支追加：
  - 共同硬依赖：`CONFIG_KEYS=y`（keyring `register_key_type`）、`CONFIG_ASSOCIATIVE_ARRAY=y`（KEYS select 它，显式写出防将来 `FS_ENCRYPTION` 关闭时连带丢失）
  - `CONFIG_HYBRIDMOUNT=y` 或 `CONFIG_NOMOUNT=y`
  - 4.19 无预编译 .ko，两后端必须 built-in
  - `olddefconfig` 后逐项 grep 校验，写错符号名不会静默跳过
- **实测**（真实 4.19 树，kona-perf_defconfig + oplus + droidspaces + no-LTO/CFI 链）：
  - HybridMount：补丁 0 rej 0 fuzz，`fs/hybridmount/hybridmount.o` 编译通过（311KB ARM64 ELF，0 错误 0 警告）
  - NoMount：`fs/nomount/nomount.o` 编译通过（0 错误）
  - 端到端模拟：按 CI 精确顺序执行 RKX → HM → config 三步（脚本从 YAML 原样提取），`CONFIG_HYBRIDMOUNT=y`/`CONFIG_KEYS=y` 全部 stick，新增 droidspaces config 项确认生效

### 4. 踩坑记录

| 坑 | 说明 |
|---|---|
| **VFS 步骤必须在 ReKernel-X 步骤之后** | RKX 步骤的 fallback 逻辑跑 `git clean -fd`，会把先打的 VFS 补丁产物（`fs/hybridmount/`、`fs/nomount` 链接、`NoMount/` 这些未跟踪文件）全部清掉。VFS 打补丁必须在内核 commit 定型（fallback 结束）之后 |
| **VFS CONFIG 必须在 olddefconfig 之前写入** | 这些符号在 defconfig 里没有被引用，olddefconfig 会丢 orphan symbol；先写进 .config 再 olddefconfig 才保留。写入位置在 .config 末尾会有 kconfig "override: reassigning" 警告，属正常（kconfig 取最后一个值） |
| **`make O=` 要求源树绝对干净** | 源树里只要有 in-tree 构建残留（`include/config/`、`arch/*/include/generated/`、`scripts/basic/fixdep` 等，gitignore 所以 `git status` 看不见），O= 构建就会以各种诡异方式失败（本机复现：`asm/types.h not found`）。清理用 `git clean -fdx`。**CI 全新 clone 无此问题**；本地复测务必先 clean |
| **上游 NM `NF_CONNTRACK_IPV6` 符号不存在** | 上游文档在 4.19 上照抄会写入无效配置项，已在本仓库 config 里注释说明 |
| coccinelle 死文件 | 从上游搬 `.cocci` 文件不代表能用：Coccinelle 需要单独安装且从未进工作流。能用的是上游已转正的 `.patch` |

### 5. 回归验证清单（后续改动照此执行）

1. `/tmp/actionlint -oneline .github/workflows/build-lkm.yml` — 工作流静态校验
2. 从 YAML 提取 run 块逐个 `bash -n` — shell 语法
3. 干净 4.19 树：RKX + cgroup 干跑/实跑 → `CONFIG_REKERNEL_X=y` → `make drivers/rekernel_x/`
4. 同树：HM 补丁 0 rej → `CONFIG_HYBRIDMOUNT=y` → `make fs/hybridmount/`；NM setup.sh 固定 commit → `CONFIG_NOMOUNT=y` → `make fs/nomount/`
5. CI 双跑：`vfs_hybridmount=true` 与 `vfs_nomount=true` 各出一份 boot.img

---

## 2026-10-17:CI 全绿但刷入后两个 LKM 都不加载——ksuinit 的 pre-5.2 mount API + 缺失符号

### 1. 现象

- 工作流（含 `susfs_enable=true`、`vfs_nomount=true`）全部 success，所有校验步骤通过。
- 刷入 `boot-patched-bakasu-lkm-nomount.img` 后设备**能正常开机**，但：
  - BakaSU 管理器显示内核未安装 / 无 root；
  - `susfs-lkm-module.zip` 的脚本没有实际效果（它依赖内核 root 才能执行 `ksud insmod`）。
- 没有 bootloop、没有明显内核 panic —— 所以第一眼看起来像“模块本身有问题”，实际是
  **第一阶段的 ksuinit 根本没把 `kernelsu.ko` 交进内核**。

### 2. 定位过程（可复现）

1. 从 CI 下载产物，`tools/boot_info.py` 确认 header v2、kernel/ramdisk 正常；
   解 LZ4 ramdisk 后确认 `init`(ksuinit)、`init.real`、`kernelsu.ko`、`ksu_block_modules`
   都已注入 —— **注入流程本身没问题**。
2. 反汇编 ramdisk 里的 `init`：发现它发出 syscall **429/430/431/432**
   （`move_mount`/`fsopen`/`fsconfig`/`fsmount`）。这些是 **Linux 5.2+** 的 mount API；
   本项目的 4.19 内核源码里根本没有这些 syscall（`tgrep __NR_fsopen` 为空）。
3. 对照 backslashxx/KernelSU（参考仓库，已验证可在 4.19 跑 LKM）的 ksuinit：
   它用的是经典 `mount(2)`。BakaSU `main` 的 `userspace/ksuinit/src/init.rs` 在
   某次重构中换成了新 mount API，只面向 GKI 5.10+。
4. 因果链：新 API 在 4.19 返回 `ENOSYS` → ksuinit 的 `prepare_mount()` 挂不上 `/proc`
   （只打一行 `Cannot mount procfs`，**不致命、继续走**）→ Android init 要到
   `first_stage_init.cpp` 才挂 `/proc`，但那已经是 ksuinit exec 真 init 之后 →
   `kernel_symbols_iter()` 打不开 `/proc/kallsyms` → `load_module()` 失败 →
   `kernelsu.ko` 从未 `init_module()` → 没有内核 root → SUSFS 的模块脚本也永远不会
   被执行。
5. 第二个独立问题：把两个 `.ko` 的未定义符号与本次内核 `System.map` 逐一对比。
   旧产物里的 `susfs_guard_lkm.ko` 引用了 **`saved_boot_config`**；4.19 没有 bootconfig，
   该符号不存在。`ksud insmod` 从 `/proc/kallsyms` 解析不到它，`init_module()` 返回
   `-ENOENT`。`make modules` 对未定义符号只给 WARNING，所以构建一直“成功”。

### 3. 修复

| 修复 | 文件 |
|---|---|
| ksuinit 换回经典 `mount(2)`（与已验证的 backslashxx 实现一致） | 新增 `Patches/BakaSU-419/0003-ksuinit-mount-proc-pre52.patch` |
| `<5.10` 不再引用 `saved_boot_config`（no-op stub） | 已有 `Patches/SUSFS-LKM/0005-...patch`（`62302e3`） |
| CI 增加**硬校验**：每个 `.ko` 的未定义符号必须存在于本次 `System.map`，vermagic 必须匹配 `UTS_RELEASE` | `.github/workflows/build-lkm.yml` 的 `Verify external modules` 步骤 |
| SUSFS 模块脚本用 `/sys/module/susfs_guard_lkm` 判重 | `susfs-module/{post-fs-data,service}.sh` |

### 4. 踩坑记录

| 坑 | 说明 |
|---|---|
| **`make modules` 的 `WARNING: "sym" undefined` 不是无害的** | 外置模块的未定义符号由 ksuinit/ksud 在加载时用 `/proc/kallsyms` 重写成 `SHN_ABS`；**解析不到任何一个**都会让 `init_module()` 失败。构建阶段只是 WARNING，必须自己拿 `System.map` 做集合校验（`KALLSYMS_ALL=y` 才会有数据符号） |
| **ksuinit 的失败是“软失败”** | `prepare_mount()` 失败只 log，然后继续 exec 真 init，所以设备照常开机；症状被伪装成“管理器不认内核”，而不是“模块加载失败”。排查时一定要看 `dmesg` 里的 `Cannot mount procfs` / `Cannot parse kallsyms` |
| **Android init 挂 `/proc` 的时机** | `/proc` 是 `first_stage_init.cpp` 里由**真 init**挂的；任何替换 `/init` 的第一阶段程序都必须自己挂 `/proc` 才能读 kallsyms |
| **新 mount API 的适用内核** | `fsopen/fsconfig/fsmount/move_mount` 全部要 5.2+；4.19 上返回 ENOSYS。不要假设“BakaSU main 面向 Android 就能在 4.19 跑”——它的默认目标是 GKI 5.10+ |
| **bootconfig 也是 5.x 特性** | `saved_boot_config` 在 4.19 不存在。任何引用它的模块都会在 `insmod` 时挂；需要按 `LINUX_VERSION_CODE < 5.10` 门控 |
| **vermagic / localversion 必须与内核一致** | `.scmversion` 会进 `UTS_RELEASE`；内核和模块必须在同一棵树、同一 `out/` 下构建。`git rev-parse --short` 在浅克隆里长度可能不同，但只要内核和模块同批构建就一致 |
| **SUSFS 会从 `/proc/modules` 自隐藏** | 模块加载成功后 `lsmod`/`/proc/modules` 都看不到它（包括 root）。判重必须看 `/sys/module/susfs_guard_lkm`，`/proc/modules` 的检查永远为假 |
| **本地 O= 构建的源树要求干净** | 见上一节：in-tree 残留会让 O= 构建出现 `asm/types.h not found` 之类的怪错；本地复测先 `git clean -fdx`（本仓库用独立 worktree 规避） |
| **本地 Rust 交叉编译 musl** | 主机没有 `aarch64-linux-gnu-gcc` 时，可给 rustup 的 `aarch64-unknown-linux-musl` 目标设 `CARGO_TARGET_AARCH64_UNKNOWN_LINUX_MUSL_LINKER=rust-lld` + `RUSTFLAGS=-C link-self-contained=yes`；CI 走的是 `aarch64-linux-gnu-gcc` |
| **NoMount 的固定 commit 拉取可能瞬时 TLS 失败** | 本项目 `setup.sh` 会先 clone 再 `fetch --all --tags`；网络抖动会让脚本在 fetch 阶段退出。重试 fetch / 手动 checkout 固定 commit，然后补做 symlink + 两处接线即可（脚本是幂等的） |

### 5. 本地验证（2026-10-17，全部通过）

构建组合：内核 `98a7970af93b`（= 新基底 boot.img 的内核 commit）+ RKX/DroidSpaces +
`CONFIG_NOMOUNT=y` + `CONFIG_KEYS/ASSOCIATIVE_ARRAY=y` + no-LTO/CFI；BakaSU `main`
`2489b385` + 3 个 4.19 补丁；SUSFS `legacy` `0b197bf` + 5 个补丁。

| 校验 | 结果 |
|---|---|
| 内核 Image | 编译成功，`4.19.325-cip136-st20-perf-g98a7970af93b-hotsteel-BakaSU-LKM` |
| `CONFIG_NOMOUNT` / `KEYS` / `ASSOCIATIVE_ARRAY` / `REKERNEL_X` | 全部 `=y`（olddefconfig 后复核） |
| `kernelsu.ko` | 222 个未定义符号，对 `System.map` **0 缺失** |
| `susfs_guard_lkm.ko` | 89 个未定义符号，**0 缺失**；无 `saved_boot_config` |
| vermagic | 两个模块均与内核 `UTS_RELEASE` 完全一致 |
| ksuinit | 反汇编 0 处 syscall 429–432，存在 `mount(2)`（syscall 40） |
| 端到端 | `swap_kernel.py`（新基底）+ `ksud boot-patch` 成功；最终 boot.img 100663296 B、header v2，ramdisk 内 init/kernelsu.ko 的 md5 与构建产物一致 |
| NoMount 内置确认 | `CONFIG_NOMOUNT=y` 进了 `.config`，`fs/nomount/nomount.o` 参与链接，`vmlinux` 中有 `__initcall_nomount_init5`；最终 boot.img 的 kernel 里 `extract-ikconfig` 仍能看到 `CONFIG_NOMOUNT=y` |

本地产物（2026-10-17，nomount 组合）位于 `~/桌面/op8-local-build-nomount/`：

| 文件 | sha256 |
|---|---|
| `boot-patched-bakasu-lkm-nomount-local.img` | `02c961d209353702cb19d8b49bca15d6476c3b2a9f004cbd5103358c92d1351d` |
| `kernelsu.ko` | `3aafebd489abbfaa890f562bdf733a03c29ec0d99ed5296a59392f1329a99311` |
| `susfs_guard_lkm.ko` | `418b1b947a0659c61abe4030e4b1af98b0693078393c3a001033adf0e05d5d5a` |
| `susfs-lkm-module-nomount.zip` | `6c4c2a521aa3650f8ec72bbca25b6991743c0fe1113487fb120c6df96bfd8c53` |

> 设备侧验证仍未做（本机无法启动该 arm64 Android 内核）。刷入后按
> `dmesg | grep -iE 'KernelSU|kernelsu|Cannot mount procfs'`、
> `[ -d /sys/module/kernelsu ]`、`/data/adb/susfs_lkm.log`、
> `[ -d /sys/module/susfs_guard_lkm ]` 检查。

### 6. 回归清单增量

1. 任何一个 `.ko` 出现 `WARNING: "..." undefined` 时，必须对照本次 `vmlinux`/`System.map`
   确认该符号真实存在（CI 的 `Verify external modules` 已自动化）。
2. 修改 ksuinit 后检查：编译出的 aarch64 二进制不应含 syscall 429–432（可用
   `llvm-objdump -d` 搜 `w8, #0x1ad..0x1b0`），且应包含经典 `mount(2)`。
3. `vfs_nomount=true` 构建后确认 `.config` 里 `CONFIG_NOMOUNT=y` 且
   `fs/nomount/nomount.o` 被编译进 `vmlinux`。
