# OP8_FinaSU_SUSFS_LKM_build（分支 `finasu`）

**OnePlus 8 (instantnoodle / sm8250 / kona) · LineageOS 23.2 (4.19.325) · FinaSU LKM + SUSFS-LKM**

自动构建 **4.19 FinaSU LKM 内核** 与 **4.19 SUSFS-LKM**，产出可 `fastboot` 直刷的
**boot.img（header v2，已注入 FinaSU 的 ksuinit + kernelsu.ko）**，外加：

- `kernelsu.ko`（FinaSU 的 LKM 驱动）
- `susfs_guard_lkm.ko`（SUSFS-LKM，运行时加载）
- `susfs-lkm-module.zip`（在管理器里装一次，开机自动 `ksud insmod`）

本分支从 `master`（管理器 = BakaSU）派生，**只把管理器换成
[LyraVoid/FinaSU](https://github.com/LyraVoid/FinaSU)**；内核、SUSFS-LKM、RKX/DS、
VFS 后端等机制沿用 `master`。BakaSU 版本仍在 `master` 分支。

### 当前状态

- 分支 [`finasu`](https://github.com/Hotsteel2901/OP8_BakaSU_SUSFS_LKM_build/tree/finasu)
  已推送。
- CI 全绿（2026-10-17，`susfs_enable=true`，内核 `lineage-23.2`，
  [run 39051940060](https://github.com/Hotsteel2901/OP8_BakaSU_SUSFS_LKM_build/actions/runs/39051940060)）：
  内核 `4.19.325-...-g98a7970af-hotsteel-FinaSU-LKM`；`kernelsu.ko` 211 个未定义
  符号、`susfs_guard_lkm.ko` 89 个未定义符号全部在 `System.map` 中；boot.img
  header v2 重打包成功。
- 产物 `boot-patched-finasu-lkm.zip`（含 boot.img / kernelsu.ko / susfs_guard_lkm.ko /
  susfs-lkm-module.zip）可直接从该 run 下载。
- **尚未真机刷入验证**；刷机风险与验证清单见文末。

---

## 与 `master`（BakaSU）的区别

| | `master`（BakaSU） | `finasu`（本分支） |
|---|---|---|
| 管理器 | Baka-SU/BakaSU | **LyraVoid/FinaSU** |
| 管理器认证 | BakaSU 默认签名 | **自动从 FinaSU Release APK 提取证书**，编译进 LKM |
| LKM hook | 直接改写 `sys_call_table`（BakaSU 补丁） | FinaSU 自带的 `sys_enter` tracepoint + 影子 dispatcher（4.19 可用） |
| SELinux 策略注入 | BakaSU 4.19 实现 | **移植 BakaSU/KernelSU 的 4.19 legacy policydb 路径** |
| SELinux hide / AVC spoof | 无 | **4.19 上关闭（编译为 stub）**，见“限制” |
| ksuinit 挂载 `/proc` | 经典 `mount(2)` 补丁 | 同样改成经典 `mount(2)` |
| boot.img header | `ksud` v2 放行补丁 | FinaSU 版 `ksud` v2 放行补丁 |
| SUSFS-LKM | 相同 | 相同（与管理器无关） |

## 使用

1. Fork 本仓库，启用 Actions 的 `Read and write permissions`。
2. 准备基底 boot.img（**header v2**）：仓库内置 `base/boot.img`，默认直接用；
   想换基底在 `boot_img_url` 填直链。
3. `Actions → Build 4.19 FinaSU LKM Kernel + SUSFS-LKM → Run workflow`。
4. 下载产物、`fastboot flash boot boot-patched-finasu-lkm*.img`、重启。
5. 安装 **FinaSU 管理器**（与 `manager_ref` 对应的版本；默认最新 Release）。
6. 需要 SUSFS 时，在 FinaSU 管理器里安装 `susfs-lkm-module.zip`，重启。

### 输入参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `boot_img_url` | 空（用仓库内置 `base/boot.img`） | 基底 boot.img 直链 |
| `kernel_commit` | `lineage-23.2` | 内核拉取分支/提交（默认最新） |
| `patch_base` | `4238ee49a84b` | DS/RK 补丁在最新内核打失败时的回退基线 |
| `manager_ref` | **`latest`** | FinaSU 引用；`latest` 会解析成最新 GitHub Release 的 tag，也可填 tag/branch/commit |
| `manager_apk_url` | 空 | 管理器 APK 直链；空则用 `manager_ref` 对应 Release（找不到时用 latest）的 APK 提取签名 |
| `manager_cert_size` | 空 | 手动指定管理器签名证书 DER 大小（十六进制，如 `0x02cc`），须与 hash 同时给 |
| `manager_cert_hash` | 空 | 手动指定管理器签名证书 SHA-256，须与 size 同时给 |
| `susfs_enable` | **true** | 是否集成 SUSFS-LKM；关则产物不带 `susfs_guard_lkm.ko` / 模块 zip，产物名加 `-nosusfs` |
| `susfs_lkm_ref` | `legacy` | SUSFS-LKM 拉取引用（`Hotsteel2901/susfs4ksu-lkm`） |
| `vfs_hybridmount` | **false** | VFS 后端：Hybrid Mount（与 NoMount 互斥） |
| `vfs_nomount` | **false** | VFS 后端：NoMount（与 Hybrid Mount 互斥） |

> **管理器签名是必须的**：FinaSU 内核只信任编译进 `kernelsu.ko` 的管理器证书。
> 工作流默认下载最新 Release APK，用 `tools/apk_cert.py` 从 APK v2 签名块里取
> 第一个签名证书的 DER 大小 + SHA-256，作为 `KSU_EXPECTED_SIZE2` /
> `KSU_EXPECTED_HASH2` 编进 LKM。如果你用自己签名的管理器，必须同时传
> `manager_cert_size` / `manager_cert_hash`（或 `manager_apk_url` 指向那个 APK），
> 否则管理器会被内核判定为“非官方”，无法打开 root 授权界面。

## 产物

| 文件 | 说明 |
|---|---|
| `boot-patched-finasu-lkm[-hybridmount\|-nomount][-nosusfs].img` | **刷这个**。header v2、no-LTO 内核、ramdisk 注入 FinaSU ksuinit + kernelsu.ko |
| `kernelsu.ko` | FinaSU LKM 驱动（已带管理器签名） |
| `susfs_guard_lkm.ko` | SUSFS-LKM（运行时加载） |
| `susfs-lkm-module.zip` | 开机自动加载 SUSFS-LKM 的 KernelSU 模块 |

## 集成内容

| 组件 | 说明 |
|---|---|
| **FinaSU LKM** | [LyraVoid/FinaSU](https://github.com/LyraVoid/FinaSU) `latest` Release / 指定 ref；`CONFIG_KSU=m`，外置 `kernelsu.ko` |
| **SUSFS-LKM** | [Hotsteel2901/susfs4ksu-lkm](https://github.com/Hotsteel2901/susfs4ksu-lkm) `legacy` + 本仓库 4.19 适配补丁（见 [`Patches/SUSFS-LKM/README.md`](Patches/SUSFS-LKM/README.md)） |
| **ReKernel-X** | `Patches/RekernelX/rkx-4.19.patch` + `CONFIG_REKERNEL_X=y` |
| **DroidSpaces** | `Patches/Droidspaces/cgroup.patch` + `droidspaces.config` |
| **VFS 后端（可选）** | HybridMount **或** NoMount，**默认都关**，互斥 |

## FinaSU 的 4.19 适配

FinaSU 的 LKM 官方目标是 GKI 5.10+，虽然 README 声称 4.14+，但内核侧大量代码
直接使用 5.10+ 的 SELinux/文件布局。本分支的补丁在 **v1.0.4**（也可用于 `main`）
上做了以下适配，全部落在 [`Patches/FinaSU-419/`](Patches/FinaSU-419/README.md)：

1. **pre-5.9 API**：`TWA_RESUME`、`fsnotify_ops.handle_event`（4.19 的 8 参数
   fsnotify，文件名是 NUL 结尾的 `unsigned char *`）、`linux/minmax.h`。
2. **pre-4.20 文件操作**：`file_operations.iopoll`（5.1+）与
   `remap_file_range`（4.20+）在 4.19 不存在，按版本裁剪包装器。
3. **seccomp bitmap cache**：5.9 才引入；4.19 上编译为 no-op（不碰旧
   `struct seccomp_filter`，避免踩内存）。
4. **`disable_seccomp()`**：4.19 没有 `seccomp_filter_release()` /
   `seccomp.filter_count`，按版本跳过（逃逸 root profile 时少释放一次引用）。
5. **SELinux**：用 BakaSU/KernelSU 的 4.19 legacy policydb 实现替换 FinaSU 的
   `selinux_policy` 版本（`rules.c` / `sepolicy.c`），保留同一套 sepolicy 批量
   命令 ABI；`security_hook_heads` 仍是 4.19 的全局 hlist。**SELinux hide 与
   AVC spoof 在 4.19 上编译成空 stub**（它们深度依赖 5.10+ 的 per-policy
   结构）。
6. **PMD 段映射**：4.19 arm64 没有 `pmd_leaf()`/`pud_leaf()`，内核镜像用 2 MiB
   段映射；`phys_from_virt()` 增加 `pmd_sect()`/`pud_sect()` 分支，否则
   `sys_call_table` / `security_hook_heads` 的文本改写会失败。
7. **mount helper**：`path_mount()`/`path_umount()` 是 5.9+ 才有的内核内部函数；
   4.19 用 `do_mount()`/`ksys_umount()` + `KERNEL_DS` 的弱符号兜底，否则
   `ksuinit` 解析不到这两个符号，`init_module()` 直接失败。
8. **ksuinit**：FinaSU 用 `fsopen/fsmount/move_mount`（Linux 5.2+）挂 `/proc`，
   4.19 上 `ENOSYS`，导致读不到 `/proc/kallsyms`、`kernelsu.ko` 加载失败；
   改成经典 `mount(2)`。
9. **boot header v2**：FinaSU `ksud boot-patch` 只接受 header v3/v4；OnePlus 8
   是 v2，打补丁放行（>4 仍拒绝）。

### 为什么 LKM 的 syscall hook 在 4.19 能工作

FinaSU 用 `sys_enter` tracepoint + `ksu_dispatcher_nr` 影子槽位。4.19 arm64 的
`syscall_trace_enter()` 在 tracepoint 之后返回 **`regs->syscallno`**（见
`arch/arm64/kernel/ptrace.c`），而 FinaSU 的 handler 正好改的是
`current_regs->syscallno` 和 `x8`，所以重定向在 4.19 上成立。BakaSU 需要直接改
`sys_call_table` 是另一条实现路线，本分支不需要。

## 限制 / 已知问题

- **SELinux hide / AVC spoof 不可用**：4.19 上 `ksu_selinux_hide_*` 与
  `ksu_avc_spoof_*` 是空实现；管理器里对应开关可能显示不可用或不生效。
- **seccomp cache 不可用**：4.19 没有 bitmap cache；依赖“给 root 进程放行
  `reboot`”的极少数场景可能受 seccomp 限制。
- **FinaSU 内置 NoMount 未编译**：FinaSU 的 NoMount 是 per-KMI 的 `.ko`，本分支
  只构建 4.19 的 `kernelsu.ko` 与 SUSFS-LKM。管理器的 NoMount 后端在 4.19 上
  会回退到内置 Folk-Mount / 其他后端；工作流里的 `vfs_nomount` 是 *maxsteeel/
  nomount* 内核 VFS 后端，与 FinaSU 内置 NoMount 不是同一个东西。
- **SUSFS-LKM 仍属实验性**：上游 `legacy` 分支未针对 4.19 验证；本仓库用 CI
  编译错误迭代补丁（见 `Patches/SUSFS-LKM/README.md`），真机 `insmod` 结果以
  `/data/adb/susfs_lkm.log` 为准。
- **必须关 LTO/CFI**：工作流已强制 `LTO_NONE` 并关 CFI；CFI 内核不能加载非 CFI
  的 `.ko`。
- **管理器版本要匹配**：默认 `manager_ref=latest` 会同时取最新 Release 的内核
  源码与 APK；如果你手动指定较老的 `manager_ref` 又装了较新的管理器，supercall
  UAPI 可能不匹配。最稳妥是让两者来自同一个 Release。

## Patches

```
Patches/
├── FinaSU-419/
│   ├── 0001-kernel-api-419.patch      # TWA/fsnotify/file_operations/seccomp/PMD 等
│   ├── 0002-selinux-419.patch         # SELinux legacy policydb + hide/avc stub
│   ├── 0003-ksuinit-classic-mount.patch
│   ├── 0004-ksud-boot-header-v2.patch
│   ├── 0005-mount-helpers-419.patch   # path_mount/path_umount -> do_mount/ksys_umount
│   └── README.md                      # 适配地图与迭代方式
├── RekernelX/rkx-4.19.patch
├── HybridMount/hybridmount_patch_to_4.19.patch
├── Droidspaces/{cgroup.patch,droidspaces.config,fix_...cocci}
├── SUSFS-LKM/                         # SUSFS-LKM 的 4.19 适配（本分支不改）
└── Archive/README.md
```

## 致谢

[LyraVoid/FinaSU](https://github.com/LyraVoid/FinaSU) ·
[Hotsteel2901/OP8_KSU_LKM_build](https://github.com/Hotsteel2901/OP8_KSU_LKM_build) ·
[Hotsteel2901/susfs4ksu-lkm](https://github.com/Hotsteel2901/susfs4ksu-lkm)（上游 [inforcqb](https://github.com/inforcqb)）·
[BakaSU](https://github.com/Baka-SU/BakaSU)（SELinux 4.19 legacy 实现参考）·
[Re-Kernel / ReKernel-X](https://github.com/Sakion-Team/Re-Kernel) ·
[Hybrid Mount](https://github.com/Hybrid-Mount/meta-hybrid_mount) ·
[NoMount](https://github.com/maxsteeel/nomount) ·
[Droidspaces](https://github.com/ravindu644/Droidspaces-OSS)
