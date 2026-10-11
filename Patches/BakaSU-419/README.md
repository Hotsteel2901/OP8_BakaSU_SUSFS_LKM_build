# BakaSU 的 4.19 适配补丁

BakaSU 官方的 LKM 模式只针对 **GKI 5.10+**（DDK 六档镜像）。在 **non-GKI 4.19** 上，
BakaSU 的 `CONFIG_KSU=m`（LKM）+ `CONFIG_KSU_TRACEPOINT_HOOK=y` 是允许的（那条
`TP hooks are incompatible with Non-GKI` 的 `$(error)` 只在 `CONFIG_KSU=y` 内建时触发），
但源码里少数地方用了 5.x 的 API，需要在本目录用补丁补齐。

工作流在克隆 `bakasu` 之后、构建 `kernelsu.ko` 之前，会按文件名顺序对 `bakasu` 应用
本目录的 `*.patch`（`patch -p1`）。失败即整条构建失败。

## 0001 — pkg_observer.c（pre-5.9 fsnotify + TWA_RESUME）

`kernel/manager/pkg_observer.c` 是 `CONFIG_KSU_TRACEPOINT_HOOK` 路径下必然编译进去的
（`Kbuild`：`ifndef CONFIG_KSU_DISABLE_MANAGER → kernelsu-objs += manager/pkg_observer.o`）。
它有两处 4.19 不兼容：

1. **`TWA_RESUME`**：4.19 的 `task_work_add(task, work, bool notify)` 用布尔而非 `TWA_*` 枚举。
   BakaSU 在 `kernel/compat/kernel_compat.h` 里有 `#ifndef TWA_RESUME / #define TWA_RESUME true`，
   但该文件**没有 include 它**（GKI 5.10+ 上 `TWA_RESUME` 是真实枚举，所以从没暴露）。
   → 补丁本地补一个 `#ifndef TWA_RESUME / #define TWA_RESUME true`。
2. **`fsnotify_ops.handle_inode_event`** 是 5.9+ 的 hook；4.19 用 8 参数的
   `handle_event(group, inode, mask, data, data_type, file_name, cookie, iter_info)`，
   且文件名是 `const unsigned char *`（NUL 结尾）而非 `struct qstr *`。
   → 补丁按 `LINUX_VERSION_CODE >= 5.9` 分叉：老内核走 `handle_event`，用 `strncmp` 匹配 `packages.list`。

> 参考：backslashxx/KernelSU（已验证可在 4.19 跑 LKM）在旧内核上**不用 fsnotify**，
> 改用 LSM `inode_rename`（`hook/lsm_hooks.c`），并在 `kernel_compat.h` 里 `#define TWA_RESUME 1`。
> BakaSU 的 `hook/lsm_hooks.c` 只在**非** syscall-hook 路径编译，所以这里选择把 fsnotify
> 版本适配到 4.19，而不是切换实现。

## 0002 — 直接改写 sys_call_table 的 syscall hook（摆脱 tracepoint 依赖）

BakaSU 的 syscall hook（`CONFIG_KSU_TRACEPOINT_HOOK`）用 GKI 的 `sys_enter` tracepoint
把被 hook 的 syscall 重定向到 `ksu_dispatcher_nr` 槽位的统一 dispatcher。这套重定向在
**non-GKI 4.19** 上不可靠（tracepoint 重定向本身是 GKI 2.0 的特性），是刷入后黑屏/回
Recovery 的根因之一。

补丁新增 `CONFIG_KSU_SYSCALL_TABLE_HOOK`（作为 `CONFIG_KSU_TRACEPOINT_HOOK` 的**实现
修饰项**，工作流里两个都开），把实现换成「直接改写 `sys_call_table`」：

* `kernel/hook/arm64/syscall_hook.c`
  - 新增 `ksu_real_syscall_table`（真实表，所有文本改写只对它做）；
  - direct 模式下 `ksu_syscall_table` 指向一份**影子表**（保留原始 handler），
    这样 handler 里的 `ksu_syscall_table[orig_nr](regs)` 仍能调用**原 syscall**，
    而真实表里该槽位已被指向我们的 dispatcher；
  - 新增 `ksu_syscall_dispatcher_direct()`：arm64 在 `el0_svc_common()` 里调用前会设置
    `regs->syscallno = scno`，因此按 `syscallno` 路由即可（不需要 tracepoint 的 x8 传参）；
  - `ksu_register_syscall_hook()` / `ksu_unregister_syscall_hook()` 在 direct 模式下改为对
    真实表 `ksu_syscall_table_hook()`/`unhook()`（复用已有的记录/恢复逻辑）。
* `kernel/hook/syscall_hook_manager.c`
  - direct 模式下跳过 `syscall_regfunc/unregfunc` kretprobe 与 `sys_enter` tracepoint 的
    注册/注销；其余（`ksu_setuid_hook_init`、`ksu_sucompat_init`、注册 5 个 handler）不变。
* `kernel/Kconfig` / `kernel/tools/ddk_compatible.mk`
  - 新增开关，并让外置模块构建把它翻成 `-DCONFIG_KSU_SYSCALL_TABLE_HOOK`。

被 hook 的 syscall：`execve`、`execveat`、`newfstatat`、`faccessat`、`setresuid`（与
tracepoint 路径完全一致），handler（`hook/syscall_event_bridge.c`、`feature/sucompat.c`）
无需改动。

工作流对 `bakasu` 的 LKM 构建参数改为
`CONFIG_KSU=m CONFIG_KSU_TRACEPOINT_HOOK=y CONFIG_KSU_SYSCALL_TABLE_HOOK=y`。

## 迭代说明

4.19 上还可能有其它文件用到 5.x API（每修好一处，CI 会暴露下一处）。新增补丁按
`000N-描述.patch` 命名即可，工作流会自动应用。
