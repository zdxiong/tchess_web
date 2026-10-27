# TCHESS
TCHESS 是一款支持 uci 和 ucci 协议引擎的跨平台象棋界面程序，具有功能：
+ 加载引擎
+ 对弈
+ 分析
+ 棋谱
+ 连线
+ 开局库

使用说明请参考 [MANUAL.md](https://github.com/sojourners/public-Xiangqi/blob/master/MANUAL.md)，访问 [Release](https://github.com/sojourners/public-Xiangqi/releases) 下载最新版本。

# 运行环境和依赖
+ JDK 21  
+ JavaFx 23

# 交流反馈
Q群：1094058444

# 声明
本项目基于 [GPLv3](https://github.com/sojourners/public-Xiangqi/blob/master/LICENSE) 协议开源，你可以自由下载、使用、复制修改，但需遵守开源协议内容，禁止未经授权用于商业用途！

# 打包为 Windows可执行程序

项目根目录提供 `build-exe.ps1`，一键将本程序打包为自包含 Windows exe。方案基于 JDK 自带的 `jpackage`，采用非模块化（classpath）模式，绕开 jlink 对 `onnxruntime` / `jnativehook` 等无 module-info 依赖的"自动模块"限制。

## 用法

```powershell
powershell -ExecutionPolicy Bypass -File .\build-exe.ps1
# 或
pwsh .\build-exe.ps1
```


## 产物

+ `dist\Xiangqi\Xiangqi.exe` —— 整个 `dist\Xiangqi` 目录即完整程序（自带 JRE），拷到任意 Windows 机器即可运行
+ 打包后默认暴露本机 WEB 端口 `http://127.0.0.1:8787/`，接口：`/api/fen`、`/api/analysis`、`/api/state`

