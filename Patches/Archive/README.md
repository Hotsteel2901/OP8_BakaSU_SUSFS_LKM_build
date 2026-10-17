# 变更存档 / Patches Archive

本目录记录对补丁与工作流的**结构性变更**及其原因、验证方式与踩坑。每次大改追加一节，不删旧记录。

> 说明：本目录是 `master`（管理器 = BakaSU）时期的变更存档。`finasu` 分支沿用其中
> 内核 / SUSFS-LKM 的结论；凡提到 BakaSU 管理器、`boot-patched-bakasu-*` 或
> `Patches/BakaSU-419` 的地方均为历史记录，当前分支对应物见 `Patches/FinaSU-419`。

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
| `susfs_guard_lkm.ko` | `8fb40093e58140721953775572e9c30b8cda86b2a3365681aaadca9fc65c6dc0`（含 `0006` 修复） |
| `susfs-lkm-module-nomount.zip` | `02fdcac17e94fafcfbb0d784d35bb6849f39dfcebd9d0b3943f699548db3667b`（含 `0006` 修复） |

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

---

## 2026-10-17（续）：BakaSU 正常后，SUSFS-LKM 仍被内核拒绝——4.19 没有 `pmd_leaf`

### 1. 现象与日志

修复 ksuinit 后，BakaSU 正常加载并工作（`/proc/modules` 可见 `kernelsu`），但
`susfs_guard_lkm.ko` 仍然 `insmod` 失败。`/data/adb/susfs_lkm.log`：

```
init_module failed without vermagic mismatch
No such file or directory (os error 2)
```

用 root 读 dmesg（`kptr_restrict=2` 时普通 `dmesg`/`kallsyms` 全是 0，需先
`echo 0 > /proc/sys/kernel/kptr_restrict`）：

```
susfs_guard_lkm: init v2.3.0-gki
susfs_guard_lkm: symbol_resolver: kprobe bootstrap (1 = usable): lookup_name=1 lookup=1 walker=1 match=0
susfs_guard_lkm: lsm_hook: init, tracked hooks=0
susfs_guard_lkm: sus_path: hooks deferred until the first rule
susfs_guard_lkm: failed to find phy addr for patch dst 0xffffff96d2b2e000
susfs_guard_lkm: lsm_hook: failed to insert inode_getattr at the head of its list: -2
susfs_guard_lkm: sus_path: getattr hook failed -2 - nothing would be hidden, refusing to load
susfs_guard_lkm: susfs_guard_lkm: sus_path init failed -2, refusing to load
```

说明：**符号全部解析成功、vermagic 也匹配**（否则错误不同），模块已进入
`susfs_init()`；失败点是 fatal 的 `sus_path` 层在往 `security_hook_heads` 插入 LSM
hook 时，`ksu_patch_text()` 找不到目标地址的物理页。

### 2. 定位

真机运行地址（root + `kptr_restrict=0`）：

| 符号 | 运行时地址 |
|---|---|
| `_text` | `0xffffff96d0280000` |
| `security_hook_heads` | `0xffffff96d2b2de68` |
| 失败 patch dst | `0xffffff96d2b2e000`（= `security_hook_heads + 0x198`，即 `offsetof(inode_getattr)`） |

关键事实：

1. arm64 39-bit VA + KASLR 把内核镜像映射到 vmalloc 区（`0xffffff96d0...`），内核
   text/rodata 用 **2 MiB PMD 段映射**。
2. 4.19 arm64 的页表头文件只提供 `pmd_sect()` / `pud_sect()`，**没有**
   `pmd_leaf()` / `pud_leaf()`（后者是 5.x 才统一的命名）。
3. SUSFS 的 `kernel/patch_memory.c::phys_from_virt()` 只写了
   `#if defined(pmd_leaf)` / `#if defined(pud_leaf)` 分支；在 4.19 上这些分支被
   预处理器整体去掉，段映射继续走到 `pmd_bad()`。`pmd_bad()` 对 section 表项
   （`PMD_TABLE_BIT` 未置位）返回 true → `goto fail` → `-ENOENT`。
4. BakaSU 的 `kernelsu.ko` 之所以能改 `sys_call_table`，是因为它的
   `hook/arm64/patch_memory.c` 本来就有 `#elif defined(pmd_sect)` /
   `#elif defined(pud_sect)` 兜底（正是为 4.19 的 rodata 段映射加的）。SUSFS 的
   移植版本把这段丢了。

### 3. 修复

`Patches/SUSFS-LKM/0006-patch_memory-pmd_sect-pre54.patch`：

```c
#if defined(pud_leaf)
    if (pud_leaf(*pud)) ...
#elif defined(pud_sect)
    if (pud_sect(*pud))
        return __pud_to_phys(*pud) + (addr & ~PUD_MASK);
#endif
...
#if defined(pmd_leaf)
    if (pmd_leaf(*pmd)) ...
#elif defined(pmd_sect)
    if (pmd_sect(*pmd))
        return __pmd_to_phys(*pmd) + (addr & ~PMD_MASK);
#endif
```

`__pmd_to_phys()` / `__pud_to_phys()` / `pmd_pte()` 在 4.19 arm64 都已存在，无需额外 shim。

### 4. 真机验证（2026-10-17）

```
# ksud insmod /data/local/tmp/susfs_fixed.ko
Loaded kernel module: /data/local/tmp/susfs_fixed.ko

# dmesg | tail
susfs_guard_lkm: sus_path: listing filter armed (2/2 ABIs: l64=__arm64_sys_getdents64 compat=__arm64_compat_sys_getdents)
susfs_guard_lkm: sus_path: hooks armed (LSM + dirent kretprobes)
susfs_guard_lkm: susfs supercall: armed (reboot ABI, version v2.3.0)
susfs_guard_lkm: loaded. This module is filtered out of /proc/modules ...

# ls -ld /sys/module/susfs_guard_lkm
drwxr-xr-x 6 root root 0 ... /sys/module/susfs_guard_lkm
# ls /proc/susfs_*        -> avc_spoof enable_log hide_modules hide_mounts kstat open_redirect path
# grep -c susfs /proc/modules    -> 0   (自隐藏生效)
```

用 `ksud module install` 把修好的 zip 装到 `/data/adb/modules_update/susfs_lkm/`
（md5 与本地构建一致），下次重启由 post-fs-data 自动加载。

### 5. 本次新增踩坑

| 坑 | 说明 |
|---|---|
| **`pmd_leaf` ≠ `pmd_sect`** | 4.19 arm64 只有 `pmd_sect`/`pud_sect`。任何从 5.x/6.x 抄来的 `phys_from_virt` 都必须补 `#elif defined(pmd_sect)`，否则 2 MiB 段映射的内核 text/rodata 无法被 fixmap 改写 |
| **KASLR 后内核镜像在 vmalloc 区** | 39-bit VA 下 `_text` 可能在 `0xffffff96...`，不要用链接地址（`ffffff80...`）判断映射方式；用 `kptr_restrict=0` 后的 `/proc/kallsyms` 读真实地址 |
| **fatal 层会把真实错误淹没** | `sus_path` 是 fatal 层，它的失败让整个模块 `init` 返回 `-2`；ksud 只显示 `init_module failed`。必须看 dmesg 里 `susfs_guard_lkm:` 开头的逐层日志 |
| **`kptr_restrict=2` 时连 root 都看到 0** | 排查时先 `echo 0 > /proc/sys/kernel/kptr_restrict`（root/CAP_SYSLOG），否则 `/proc/kallsyms` 地址全为 0 |
| **`ksud module install` 是延迟生效** | 新文件被放进 `/data/adb/modules_update/<id>/`，活动目录里的旧 `.ko` 不会立即替换，并写入 `update` 标记，重启后才切换。验证时对比两边 md5 |
| **已加载模块不要重复 insmod** | SUSFS 从 `/proc/modules` 自隐藏，重复 `insmod` 返回 `-EEXIST`，看起来像“被拒”；判重看 `/sys/module/susfs_guard_lkm` |

---

## 2026-10-17（分支 `finasu`）：管理器换成 FinaSU

### 1. 分支目标

`master`（BakaSU）验证通过后，用户要求为 **LyraVoid/FinaSU** 构建 LKM。新建
`finasu` 分支，内核/SUSFS/RKX/DS 机制不动，只替换管理器与对应的 4.19 适配。

### 2. 关键差异

- FinaSU 内核用 **APK 签名证书（DER 大小 + SHA-256）** 认证管理器；工作流默认从
  最新 Release APK 的 v2 签名块提取（`tools/apk_cert.py`），编译成
  `KSU_EXPECTED_SIZE2` / `KSU_EXPECTED_HASH2`，并设
  `KSU_SECOND_SIGNATURE_RELEASE=1`。没有这一步官方管理器不会被识别。
- FinaSU 的 `ksuinit` 用 5.2+ 的 `fsopen/fsmount/move_mount` 挂 `/proc`，4.19 上
  失败 → 改成经典 `mount(2)`（`0003`），与 master 的 BakaSU 修复同因。
- FinaSU 的 `ksud boot-patch` 只接受 header v3/v4 → 放行 v2（`0004`）。
- FinaSU 的 SELinux `rules.c`/`sepolicy.c` 直接操作 5.10+ 的
  `selinux_state.policy` → 换成 BakaSU/KernelSU 的 4.19 legacy 全局 policydb
  实现（`0002`）；sepolicy 批量命令 ABI 保持不变。
- FinaSU 的 SELinux hide / AVC spoof 和 seccomp bitmap cache 在 4.19 上编译为
  no-op / stub（`0001`、`0002`），功能降级见根 README“限制”。
- FinaSU 直接调用 5.9+ 的 `path_mount()` / `path_umount()`；4.19 没有这两个符号，
  模块能编译但 `ksuinit` 解析不到，`init_module()` 必败。`0005` 用 BakaSU 同款
  弱符号兜底：`d_path()` + `KERNEL_DS` + `do_mount()` / `ksys_umount()`。
- FinaSU 的 syscall hook 走 `sys_enter` tracepoint + 影子 dispatcher；4.19 的
  `syscall_trace_enter()` 返回 `regs->syscallno`，因此**不需要** master 的直接
  `sys_call_table` hook。

### 3. 本地验证（未真机）

使用 lineage-23.2 内核树 `98a7970af93b`、FinaSU v1.0.4（= main `40c97e2`）、
Patches/FinaSU-419 全部补丁：

| 校验 | 结果 |
|---|---|
| FinaSU `kernelsu.ko` | 编译成功，0 error；vermagic 与 `UTS_RELEASE` 一致；未定义符号里 `path_mount`/`path_umount` 已被 0005 消除，改为 4.19 存在的 `do_mount`/`ksys_umount` |
| `ksuinit`（aarch64-musl） | 编译成功，421 KB 静态 ELF；反汇编/源码确认使用 `mount(2)` |
| host `ksud` | aarch64 与 x86_64 宿主均编译成功；`ksud boot-patch` 正常 |
| APK 证书提取 | v1.0.4 APK → `0x02cc` / `2d89b5...d448458` |
| boot-patch（v2 基座） | 成功；ramdisk 内 `init` 与新编 `ksuinit` 逐字节一致，`init.real` + `kernelsu.ko` 均在 |
| 符号/vermagic 自检 | CI 全绿（run 39051940060）：kernelsu.ko 211 / SUSFS 89 个未定义符号全部命中 System.map，vermagic 一致 |
| GitHub Actions | 26m49s 全绿，artifact `boot-patched-finasu-lkm` 上传成功 |

> CI 已全绿（2026-10-17，run 39051940060），产物 boot.img 的 ramdisk 内
> `init`（ksuinit）与 `kernelsu.ko` 已核对；尚未真机刷入。刷入后优先看 `dmesg | grep -iE 'KernelSU|kernelsu|Cannot mount procfs'`、
> 管理器是否识别 LKM、`/data/adb/susfs_lkm.log`。FinaSU 管理器需与构建时
> `manager_ref` 对应（默认 `latest` = 最新 Release）。
