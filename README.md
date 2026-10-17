# OP8_BakaSU_SUSFS_LKM_build

**OnePlus 8 (instantnoodle / sm8250 / kona) · LineageOS 23.2 (4.19.325) · BakaSU LKM + SUSFS-LKM**

自动构建 **4.19 BakaSU LKM 内核** 与 **4.19 SUSFS-LKM**，产出可 `fastboot` 直刷的
**boot.img（header v2，已注入 BakaSU 的 ksuinit + kernelsu.ko）**，外加：
- `kernelsu.ko`（BakaSU 的 LKM 驱动）
- `susfs_guard_lkm.ko`（SUSFS-LKM，运行时加载）

基于 [Hotsteel2901/OP8_KSU_LKM_build](https://github.com/Hotsteel2901/OP8_KSU_LKM_build)
（已验证可用，管理器 = backslashxx/KernelSU）改造而来。

---

## 与参考仓库的区别

| | 参考仓库 OP8_KSU_LKM_build | 本仓库 |
|---|---|---|
| 管理器 | backslashxx/KernelSU | **BakaSU（Baka-SU/BakaSU）** |
| 管理器形态 | LKM（`CONFIG_KSU=m`） | LKM（`CONFIG_KSU=m`） |
| SUSFS | 无（或不涉及） | **额外构建 `susfs_guard_lkm.ko`** |
| VFS 后端 | HybridMount / NoMount 可选 | 同（默认都关，互斥） |

## 使用

1. Fork 本仓库，启用 Actions 的 `Read and write permissions`。
2. 准备基底 boot.img（**header v2**）：仓库内置 `base/boot.img`，默认直接用；
   想换基底在 `boot_img_url` 填直链。
3. `Actions → Build 4.19 BakaSU LKM Kernel + SUSFS-LKM → Run workflow`。
4. 下载产物、`fastboot flash boot boot-patched-bakasu-lkm*.img`、重启。
5. 安装 BakaSU 管理器；SUSFS-LKM 由 userspace 在开机后加载（见下）。

### 输入参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `boot_img_url` | 空（用仓库内置 `base/boot.img`） | 基底 boot.img 直链 |
| `kernel_commit` | `lineage-23.2` | 内核拉取分支/提交（默认最新） |
| `patch_base` | `4238ee49a84b` | DS/RK 补丁在最新内核打失败时的回退基线 |
| `manager_ref` | `main` | BakaSU 拉取引用 |
| `susfs_enable` | **true** | 是否集成 SUSFS-LKM；**关**则跳过其克隆/打补丁/编译，产物不带 `susfs_guard_lkm.ko`（内核本身不含 SUSFS，它只是外置模块），产物名加 `-nosusfs` |
| `susfs_lkm_ref` | `legacy` | SUSFS-LKM 拉取引用（`Hotsteel2901/susfs4ksu-lkm`） |
| `vfs_hybridmount` | **false** | VFS 后端：Hybrid Mount（与 NoMount 互斥，最多开一个） |
| `vfs_nomount` | **false** | VFS 后端：NoMount（与 Hybrid Mount 互斥，最多开一个） |

## 产物

| 文件 | 说明 |
|---|---|
| `boot-patched-bakasu-lkm[-hybridmount\|-nomount].img` | **刷这个**。header v2、no-LTO 内核、ramdisk 注入 BakaSU 的 ksuinit + kernelsu.ko |
| `kernelsu.ko` | BakaSU LKM 驱动 |
| `susfs_guard_lkm.ko` | SUSFS-LKM（运行时加载） |

## 集成内容

| 组件 | 说明 |
|---|---|
| **BakaSU LKM** | [Baka-SU/BakaSU](https://github.com/Baka-SU/BakaSU) `main`；`CONFIG_KSU=m`，外置 `kernelsu.ko`；`ksud` 打 v2 补丁（放行 OnePlus 8 的 v2 boot header） |
| **SUSFS-LKM** | [Hotsteel2901/susfs4ksu-lkm](https://github.com/Hotsteel2901/susfs4ksu-lkm) `legacy` + 本仓库 4.19 适配补丁（见 [`Patches/SUSFS-LKM/README.md`](Patches/SUSFS-LKM/README.md)） |
| **ReKernel-X** | `Patches/RekernelX/rkx-4.19.patch` + `CONFIG_REKERNEL_X=y` |
| **DroidSpaces** | `Patches/Droidspaces/cgroup.patch` + `droidspaces.config` |
| **VFS 后端（可选）** | HybridMount **或** NoMount，**默认都关**，互斥 |

## VFS 后端（HybridMount / NoMount，二选一，默认都不开）

| 后端 | 上游 | 集成方式 | CONFIG | keyring |
|---|---|---|---|---|
| **Hybrid Mount** | [Hybrid-Mount/meta-hybrid_mount](https://github.com/Hybrid-Mount/meta-hybrid_mount) | 内置补丁 `Patches/HybridMount/hybridmount_patch_to_4.19.patch`（已同步上游 `dev`：`parent_path` 生命周期 + inode 竞态修复，保留 4.19 `name_snapshot` shim） | `CONFIG_HYBRIDMOUNT=y` | `hm1` / magic `HYBRIDMO` |
| **NoMount** | [maxsteeel/nomount](https://github.com/maxsteeel/nomount) | 在线 `kernel/setup.sh`，固定 commit（`NOMOUNT_COMMIT`） | `CONFIG_NOMOUNT=y` | `NOMOUNT` |

- **互斥**：都劫持同一层 VFS（`inode_operations` / `file_operations` / `dentry_operations`）
  且 keyring 协议不兼容，同开互抢 hook。工作流前置校验，开两个直接 fail。
- **必须内置（=y）**：上游只给 5.10+ 预编译 `.ko`，4.19 属 legacy，无现成模块。
  共同硬依赖 `CONFIG_KEYS=y`（+ 其 select 的 `CONFIG_ASSOCIATIVE_ARRAY=y`）。

## 关键实现要点 / 坑

1. **LKM 模式的 hook 机制**：BakaSU 的 `KSU_MANUAL_HOOK` 明确 `depends on KSU != m`，
   即 LKM 下不能用手动 hook；它走自带的 syscall hook（`hook/syscall_hook_manager.c`，
   kretprobe + syscall tracepoints）。因此内核必须开 `CONFIG_KPROBES` /
   `CONFIG_KRETPROBES` / `CONFIG_FTRACE_SYSCALLS`（本工作流已开）。
2. **必须关 LTO/CFI**：`kona-perf_defconfig` 有 `CONFIG_LTO_CLANG` / `CFI_CLANG`；
   非 CFI 的 `.ko` 在 CFI 内核上首次间接调用即 panic。本工作流强制 `LTO_NONE` 并关 CFI。
3. **`CC=clang` 必须作为 make 命令行参数**（内核 Makefile 会覆盖环境变量）；
   `merge_config.sh` 内部再调 make，故通过 `MAKEFLAGS` 注入。
4. **内核准备顺序**：`modules_prepare` + `init/version.o` + `security/selinux/avc.o`
   （生成 `flask.h`，缺失会 `fatal error: 'flask.h' file not found`）。
5. **SUSFS-LKM 的加载**：复用 BakaSU `ksud insmod`（它会用 `/proc/kallsyms` 预解析未定义
   符号并改写 vermagic）。boot.img 里注入的是 `kernelsu.ko`；`susfs_guard_lkm.ko` 单独下发，
   由 userspace（KernelSU 模块 / `ksud insmod`）在开机后加载。
6. **SUSFS-LKM 4.19 适配进行中**：上游 `legacy` 分支未构建未验证；本仓库以 CI 编译错误
   为输入迭代补丁（见 `Patches/SUSFS-LKM/README.md`）。
7. **ksuinit 必须用经典 `mount(2)` 挂 `/proc`**：BakaSU `main` 的 ksuinit 用
   `fsopen/fsconfig/fsmount/move_mount`（Linux 5.2+），在 4.19 上返回 `ENOSYS`，
   导致 `/proc/kallsyms` 不可读、`kernelsu.ko` 加载失败（设备能开机但无 root）。
   本仓库补丁 `Patches/BakaSU-419/0003` 换回经典 mount(2)。
8. **构建产物会做符号自检**：CI 在打包前把两个 `.ko` 的未定义符号逐个对照
   `vmlinux`/`System.map`。`make modules` 对未解析符号只给 WARNING；只要有一个符号
   在运行内核里不存在（例如 4.19 没有 bootconfig 时的 `saved_boot_config`），
   `init_module()` 就会失败。自检不通过直接 fail。

## Patches

```
Patches/
├── ksud-v2.patch                        # ksud boot-patch 放行 v2 头（BakaSU 同源，原样可用）
├── RekernelX/rkx-4.19.patch             # ReKernel-X 4.19 移植
├── HybridMount/hybridmount_patch_to_4.19.patch  # Hybrid Mount 4.19 移植（已更新到上游 dev）
├── Droidspaces/{cgroup.patch,droidspaces.config,fix_...cocci}
├── BakaSU-419/0001-pkg_observer-pre59-fsnotify.patch  # BakaSU LKM 的 4.19 API 适配
├── BakaSU-419/README.md                 # BakaSU 4.19 适配说明
├── SUSFS-LKM/README.md                  # SUSFS-LKM 的 4.19 适配地图与迭代方式（补丁迭代中）
└── Archive/README.md
```

## 致谢

[Hotsteel2901/OP8_KSU_LKM_build](https://github.com/Hotsteel2901/OP8_KSU_LKM_build) ·
[BakaSU](https://github.com/Baka-SU/BakaSU) ·
[Hotsteel2901/susfs4ksu-lkm](https://github.com/Hotsteel2901/susfs4ksu-lkm)（上游 [inforcqb](https://github.com/inforcqb)）·
[Re-Kernel / ReKernel-X](https://github.com/Sakion-Team/Re-Kernel) ·
[Hybrid Mount](https://github.com/Hybrid-Mount/meta-hybrid_mount) ·
[NoMount](https://github.com/maxsteeel/nomount) ·
[Droidspaces](https://github.com/ravindu644/Droidspaces-OSS)
