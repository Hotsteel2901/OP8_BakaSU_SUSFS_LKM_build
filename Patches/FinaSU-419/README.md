# FinaSU 的 4.19 适配补丁

FinaSU 官方 LKM 面向 **GKI 5.10+**；在 **non-GKI 4.19（OnePlus 8 / LineageOS 23.2）**
上，内核模块可以按外置模块（`CONFIG_KSU=m`）构建，但源码里有一批 5.x API 和
SELinux 内部结构需要适配。本目录的补丁由工作流在克隆 FinaSU 之后、编译之前按
文件名顺序用 `patch -p1` 应用，失败即整条构建失败。

补丁基线：FinaSU **v1.0.4**（也可干净应用到 `main` 的 40c97e2）。

## 0001 — 通用 4.19 API 适配

### TWA_RESUME（4.19：`task_work_add(..., bool)`）

`TWA_*` 枚举是 5.9+ 的；4.19 的 `task_work_add()` 第三个参数是 `bool notify`。
在 `manager/pkg_observer.c`、`manager/dynamic_manager.c`、
`supercall/supercall.c`、`policy/allowlist.c` 里补：

```c
#ifndef TWA_RESUME
#define TWA_RESUME true
#endif
```

### fsnotify（pre-5.9）

`manager/pkg_observer.c` 用 5.9+ 的 `fsnotify_ops.handle_inode_event`。4.19 是
8 参数的 `handle_event(group, inode, mask, data, data_type, file_name, cookie,
iter_info)`，文件名是 `const unsigned char *`（NUL 结尾），不是 `struct qstr *`。
补丁按 `LINUX_VERSION_CODE >= 5.9` 分叉，用 `strncmp(..., "packages.list", 13)`
匹配。

### `linux/minmax.h`（5.8+）

`sulog/event.c` 改为按版本 include `<linux/kernel.h>`（4.19 的 `min/max` 在那里）。

### `file_operations`（4.19）

`infra/file_wrapper.c` 包装 VFS 操作，但 4.19 的 `struct file_operations` 没有：

- `iopoll`（5.1+）：跳过包装；
- `remap_file_range`（4.20+，4.19 叫 `dedupe_file_range`，签名也不同）：跳过包装。

`mmap_supported_flags`、`copy_file_range`、`fadvise` 在 4.19 已存在，保留。

### seccomp bitmap cache（5.9+）

`infra/seccomp_cache.c` 的 `struct action_cache` / `SECCOMP_ARCH_NATIVE_NR` 是
5.9 引入的；4.19 的 `struct seccomp_filter` 完全是另一个布局，硬套会踩内存。
补丁在 `< 5.9` 时把 `ksu_seccomp_clear_cache()` / `ksu_seccomp_allow_cache()`
编译成 no-op。代价：极少数依赖“给 root 进程放行 `reboot`”的 seccomp 场景可能
受影响。

### `disable_seccomp()`

`policy/app_profile.c` 用 `seccomp.filter_count`（6.x）和
`seccomp_filter_release()`（5.9+）。4.19 上跳过这两个操作；detach 后的 filter
引用会泄漏一次（只在启用“逃逸 root profile 时禁用 seccomp”的应用上发生）。

### `uapi/linux/mount.h`（5.2+）

`infra/su_mount_ns.c` 只为 `MS_PRIVATE` include 它；4.19 用
`<uapi/linux/fs.h>` 即可。

### `tasklist_lock` / `init_task` / `task_pgrp`

`supercall/dispatch.c` 的 `do_set_init_pgrp()` 补 `<linux/sched/signal.h>` 与
`<linux/sched/task.h>`；4.19 的 `change_pid()` 还是 3 参数版本，代码本来就按
`<6.15` 走。

### PMD/PUD 段映射（关键）

`hook/arm64/patch_memory.c` 的 `phys_from_virt()` 只处理 `pmd_leaf()` /
`pud_leaf()`（5.x）。4.19 arm64 只有 `pmd_sect()` / `pud_sect()`，而内核镜像
（含 `sys_call_table`、`security_hook_heads`）用 2 MiB 段映射。缺这个分支时
`pmd_bad()` 会拒绝段表项，`ksu_patch_text()` 找不到物理地址，dispatcher 装不上、
LSM hook 插不进去——表现是模块加载了但 root/管理界面全废。补丁加
`#elif defined(pmd_sect)` / `#elif defined(pud_sect)`。

## 0002 — SELinux（最大的一块）

FinaSU 的 `selinux/rules.c` / `sepolicy.c` 直接操作 5.10+ 的
`struct selinux_policy`（`selinux_state.policy` + `policy_mutex` + per-policy
policydb/sidtab）。4.19 是全局 `policydb` / `sidtab`，`struct selinux_state` 只有
`ss` 指针，没有 `policy` 字段。

补丁把这两个文件替换成 **BakaSU/KernelSU 的 4.19 legacy 实现**：

- `< 5.10`：`get_policydb()` 走 `selinux_state.ss->policydb`，用
  `ksu_dup_policydb()` 复制、`ksu_lock_sepolicy_legacy()` 保护提交；
- `>= 5.10`：保留原来的 `selinux_policy` 路径（本分支不构建，但避免破坏上游
  其它用途）；
- sepolicy 批量命令 ABI 完全一致（`KSU_SEPOLICY_CMD_*` 1–9，参数个数与
  `handle_sepolicy()` 解析相同），FinaSU 的 `ksud` 发来的命令可直接用；
- `sepolicy.c` 里 4.19 的 `symtab_search()` 用
  `hashtab_search((s)->table, name)` 兼容宏；
- `selinux/selinux.h` 在 `>= 4.19` 定义 `KSU_COMPAT_USE_SELINUX_STATE`，让
  legacy 代码选择 `selinux_state.avc`、`avc_ss_reset(avc, 0)` 等正确签名。

**SELinux hide / AVC spoof**：`feature/selinux_hide.c` 与
`feature/avc_spoof.c` 深度依赖 5.10+ 的 `selinux_policy` 和 LSM 静态调用，
4.19 上无法低成本移植。补丁把整个文件包在 `#if LINUX_VERSION_CODE >= 5.10` 里，
`#else` 提供同名空函数，保证 `core/init.c` / `runtime/*` 的调用点仍能链接。
代价是管理器里的 SELinux hide / AVC spoof 功能在 4.19 上不可用。

## 0003 — ksuinit 用经典 `mount(2)` 挂 `/proc`

`userspace/ksuinit` 是注入 ramdisk、替换 `/init` 的第一阶段程序。它必须先挂
`/proc` 才能读 `/proc/kallsyms`，把 `kernelsu.ko` 的未定义符号改写成绝对地址。

FinaSU 用新 mount API：

```
fsopen() -> fsconfig() -> fsmount() -> move_mount()
```

这些是 **Linux 5.2+** 才有的；4.19 返回 `ENOSYS`，`prepare_mount()` 只写一行
`Cannot mount procfs`，随后 `load_module_from_path("/kernelsu.ko")` 失败——设备
能正常开机，但管理器显示未安装。补丁改成经典
`mount(name, mountpoint, name, MountFlags::empty(), "")`，从 4.19 到 GKI 都可用。

> 真机排查：`dmesg | grep -iE 'KernelSU|kernelsu|Cannot mount procfs'` 应能看到
> `Hello, KernelSU!`、`Loading kernelsu.ko..`；加载成功后
> `[ -d /sys/module/kernelsu ]` 为真。`ksuinit` 随后会把 `/init` 重定向到
> `/init.real`（或 `/system/bin/init`），不会递归。

## 0004 — `ksud boot-patch` 放行 boot header v2

FinaSU `userspace/ksud/src/boot_patch.rs` 的 `enforce_bootimage_version()` 只接受
Android header v3/v4：

```rust
if ver < 3 { bail!("bootimage version {ver} is not supported!") }
```

OnePlus 8 的 boot.img 是 **header v2**。补丁改为打印版本、仅拒绝 `ver > 4`；
`android-bootimg` 本身能解析/重打包 v2（已在 `base/boot.img` 上验证）。

> 注意：本仓库仍用 `tools/swap_kernel.py` 在固定偏移替换 kernel，再让
> `ksud boot-patch` 注入 ramdisk；不要改成 `--kernel`，v2 头下重新布局
> kernel/ramdisk/dtb 容易把镜像弄坏。

## 管理器签名（不是补丁，但必须）

FinaSU 内核用 `EXPECTED_SIZE2` / `EXPECTED_HASH2` 认证管理器 APK 的签名证书。
工作流从最新 Release APK 的 v2 签名块提取第一个证书（`tools/apk_cert.py`），
作为 `KSU_EXPECTED_SIZE2` / `KSU_EXPECTED_HASH2` 传给 `make`，并设
`KSU_SECOND_SIGNATURE_RELEASE=1`。当前 FinaSU v1.0.4 的值：

```
KSU_EXPECTED_SIZE2=0x02cc
KSU_EXPECTED_HASH2=2d89b50aaf1db013c2b6738f973f48b62ea21a3a8d7216bfec3521065d448458
```

换管理器签名（自编译 APK）时，用 `manager_apk_url` 指向新 APK，或显式传
`manager_cert_size` / `manager_cert_hash`。

## 迭代说明

4.19 上还可能有其它 FinaSU 新特性用到 5.x API（每修好一处，CI 会暴露下一处）。
新增补丁按 `000N-描述.patch` 命名即可，工作流会自动应用。建议先在本地用与 CI
相同的内核树验证外置模块：

```sh
make -C device_kernel O=$PWD/device_kernel/out M=$PWD/finasu/kernel \
  CONFIG_KSU=m KSU_EXPECTED_SIZE2=0x02cc \
  KSU_EXPECTED_HASH2=2d89b50aaf1db013c2b6738f973f48b62ea21a3a8d7216bfec3521065d448458 \
  KSU_SECOND_SIGNATURE_RELEASE=1 \
  CC=clang ARCH=arm64 CLANG_TRIPLE=aarch64-linux-gnu- \
  CROSS_COMPILE=aarch64-linux-gnu- -j4 modules
```
