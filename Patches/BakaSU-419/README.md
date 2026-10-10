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
> BakaSU 的 `hook/lsm_hooks.c` 只在**非** tracepoint 路径编译，而 LKM 的 syscall hook 必须走
> tracepoint，所以这里选择把 fsnotify 版本适配到 4.19，而不是切换实现。

## 迭代说明

4.19 上还可能有其它文件用到 5.x API（每修好一处，CI 会暴露下一处）。新增补丁按
`000N-描述.patch` 命名即可，工作流会自动应用。
