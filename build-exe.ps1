# build-exe.ps1
# 用 jpackage 将 TCHESS 打包为自包含 Windows exe（免 Launch4j）。
# 产物: dist\Xiangqi\Xiangqi.exe  —— 整个 dist\Xiangqi 目录即完整程序（含自带 JRE）。
#
# 用法（任选其一）:
#   powershell -ExecutionPolicy Bypass -File .\build-exe.ps1
#   pwsh .\build-exe.ps1
#
# 说明:
#   - 用 JDK 自带 jpackage 的非模块化(classpath)模式，绕开 jlink 的"自动模块"限制
#     （onnxruntime / jnativehook 无 module-info，jlink 会直接报错）。
#   - 代码用 PathUtils.getJarPath() 按文件系统路径读 model/sound/ui 等资源，
#     因此打包后必须把 src\main\resources 下各目录复制进 app\，否则 exe 起不来。
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot

# ---------- 环境（按机器实际情况修改） ----------
$jdk     = 'C:\Users\xiongzhendong\.jdks\ms-21.0.13.0.2'          # JDK21
$mvn     = 'C:\Users\xiongzhendong\AppData\Local\apache-maven-3.9.16\bin\mvn.cmd'
$appName = 'Xiangqi'
$mainCls = 'com.sojourners.chess.Main'
$mainJarName = 'Xiangqi-1.0-SNAPSHOT.jar'                        # = artifactId-version.jar

if (-not (Test-Path -LiteralPath $jdk))   { throw "找不到 JDK: $jdk" }
if (-not (Test-Path -LiteralPath $mvn))   { throw "找不到 Maven: $mvn" }
if (-not (Test-Path -LiteralPath (Join-Path $root 'pom.xml'))) { throw "不是项目根: $root" }

$env:JAVA_HOME = $jdk
$env:Path = "$jdk\bin;$env:Path"
$jpackage = Join-Path $jdk 'bin\jpackage.exe'

# ---------- 1. 编译 ----------
Write-Host '==> [1/4] mvn clean package (JDK21)'
& $mvn -f "$root\pom.xml" clean package -DskipTests
if ($LASTEXITCODE -ne 0) { throw 'mvn package 失败' }

# ---------- 2. 收集运行期依赖 jar ----------
$applib = Join-Path $root 'target\applib'
New-Item -ItemType Directory -Force -Path $applib | Out-Null
Get-ChildItem -LiteralPath $applib -File | Remove-Item -Force
$cpFile = Join-Path $root 'target\cp.txt'

Write-Host '==> [2/4] 收集运行期依赖到 target\applib'
& $mvn -f "$root\pom.xml" dependency:build-classpath "-Dmdep.outputFile=$cpFile" "-Dmdep.includeScope=runtime" -q
if ($LASTEXITCODE -ne 0) { throw 'dependency:build-classpath 失败' }

$cp = (Get-Content -Raw -LiteralPath $cpFile).Trim()
$copied = 0
if ($cp) {
    foreach ($j in ($cp -split ';')) {
        $j = $j.Trim()
        if ($j -and (Test-Path -LiteralPath $j)) { Copy-Item -LiteralPath $j -Destination $applib -Force; $copied++ }
    }
}
$mainJar = Join-Path $root ("target\" + $mainJarName)
if (-not (Test-Path -LiteralPath $mainJar)) { throw "找不到主 jar: $mainJar" }
Copy-Item -LiteralPath $mainJar -Destination $applib -Force
Write-Host ("   依赖 jar {0} 个 + 主 jar {1}" -f $copied, $mainJarName)

if (-not (Get-ChildItem -LiteralPath $applib -Filter 'onnxruntime*.jar')) { throw 'applib 缺少 onnxruntime，依赖收集不完整' }

# ---------- 3. jpackage 生成 exe ----------
$dest = Join-Path $root 'dist'
$outDir = Join-Path $dest $appName

# 先关闭正在运行的旧实例：它会占用 app\ 下的 jar，导致 dist 无法覆盖。
# 重新打包本来就需要程序不在运行，这里自动处理而非让脚本报"文件被占用"。
$old = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    $_.Name -eq "$appName.exe" -or ($_.Name -in @('java.exe', 'javaw.exe') -and $_.CommandLine -match $appName)
}
foreach ($p in $old) {
    Write-Host ("   关闭旧实例 PID {0} ({1})" -f $p.ProcessId, $p.Name)
    Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Milliseconds 800

if (Test-Path -LiteralPath $outDir) { Remove-Item -LiteralPath $outDir -Recurse -Force }
New-Item -ItemType Directory -Force -Path $dest | Out-Null

Write-Host '==> [3/4] jpackage --type app-image'
& $jpackage --type app-image --name $appName --input $applib --main-jar $mainJarName --main-class $mainCls --dest $dest
if ($LASTEXITCODE -ne 0) { throw 'jpackage 失败' }

# ---------- 4. 外置资源复制进 app\ ----------
$srcRes = Join-Path $root 'src\main\resources'
$appDir = Join-Path $outDir 'app'
Write-Host '==> [4/4] 复制 resources 到 app\'
foreach ($d in (Get-ChildItem -LiteralPath $srcRes -Directory -Force)) {
    if ($d.Name -eq 'META-INF') { continue }
    Copy-Item -LiteralPath $d.FullName -Destination $appDir -Recurse -Force
}

Write-Host ''
Write-Host ("打包完成: {0}\Xiangqi.exe" -f $outDir)
Write-Host '整个 dist\Xiangqi 目录即完整程序，拷到任意 Windows 机器即可运行。'
Write-Host '运行后访问 http://127.0.0.1:8787/api/state 验证 WEB 端口。'
