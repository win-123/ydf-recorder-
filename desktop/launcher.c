// YonDiF Recorder 的 .app 主可执行文件（极简 Mach-O 启动器）
//
// 为什么需要它：macOS 的 .app 要求 Contents/MacOS 下的主可执行文件是 Mach-O，
// 否则 codesign 无法签名、Dock 行为也不正常。这里只做一件事：把自己的参数原样
// 转发给 Contents/Resources/launcher.sh（真正的启动逻辑都在那个脚本里）。
//
// 构建：clang -O2 -o launcher launcher.c（见 desktop/build_app.sh）

#include <mach-o/dyld.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

int main(int argc, char *argv[]) {
    char exe[4096];
    uint32_t size = sizeof(exe);
    if (_NSGetExecutablePath(exe, &size) != 0) {
        return 127;
    }

    char resolved[4096];
    if (realpath(exe, resolved) == NULL) {
        return 127;
    }

    // resolved = <App>/Contents/MacOS/launcher  → 截到 Contents/MacOS
    char *slash = strrchr(resolved, '/');
    if (slash == NULL) {
        return 127;
    }
    *slash = '\0';

    char script[4096];
    int n = snprintf(script, sizeof(script), "%s/../Resources/launcher.sh", resolved);
    if (n <= 0 || (size_t)n >= sizeof(script)) {
        return 127;
    }

    // argv 原样转发（含 argv[0] 之后的全部用户参数）
    char **child = calloc((size_t)argc + 2, sizeof(char *));
    if (child == NULL) {
        return 127;
    }
    child[0] = "/bin/bash";
    child[1] = script;
    for (int i = 1; i < argc; i++) {
        child[i + 1] = argv[i];
    }

    execv("/bin/bash", child);
    return 127;
}
