# Pixel 实验方法

## (0) Before Everything

公网服务器:

```sh
# oracle seoul server
129.154.215.71
```

SIM卡:

au / docomo / softbank, "推荐" docomo

VPN: 确保关闭

JP测试, 不要开 clash

## (1) 前置检查

```sh
su -c 'cd /data/data/com.termux/files/home/starpike-replayer && PATH=/system/bin:/system/xbin:/data/data/com.termux/files/usr/bin:$PATH sh phone_collect.sh --precheck'
```

网络连通性验证:

```sh
# Step1: 在 oracle server 上 `iperf3 -s`
# Step2: pixel打流, 指令如下
su -c 'PATH=/system/bin:/system/xbin:/data/data/com.termux/files/usr/bin:$PATH iperf3 -c 129.154.215.71 -t 5 -i 1 -b 256K'
```

## (2) Smoke Test: 30s + WiFi + VPN-Off

> 这一部分流程的产出, 对应文件夹下 wifi-example-output. 作为样例, 便于上手 :))

把 clash meta for android 代理应用关了!

这里我是用wifi测的, 仅供参考测试指令:

```sh
su -c 'cd /data/data/com.termux/files/home/starpike-replayer && PATH=/system/bin:/system/xbin:/data/data/com.termux/files/usr/bin:$PATH sh phone_collect.sh --phase wifi_iperf_smoke --duration 30 --iperf-server 129.154.215.71 --iperf-bw 256K --out ./sessions_smoke --iface wlan0 --enable-pixel-context --enable-signal-samples --enable-radio-events'
```

* `--phase wifi_iperf_smoke`: 本地测试名
* `--duration 30`: 测试时长
* `--iperf-server 129.154.215.71`: 指定服务器公网IP (此处指 oracle seoul server)
* `--out ./sessions_smoke`: 输出文件夹名称
* `--iface wlan0`: 指定测试网口! 
    * 此处指定 `wlan0` 是因为现在用wifi测
    * 后面用sim卡的话, 要改"测试网口". (下面会详细展开)
* 后面三个`enable`: 非常关键, 针对信令层交互. 不用管, 开着就行

\[1\] 打包内容:

```sh
tar -czf sessions_smoke.tar.gz sessions_smoke
```

\[2\] 把"压缩包"放到手机的Download下:

```sh
cp sessions_smoke.tar.gz /sdcard/Download
```

![alt text](./image/pixel-0.png)

![alt text](./image/pixel-1.png)

![alt text](./image/pixel-2.png)

\[3\] 把"压缩包"通过telegram等方式回传给电脑, 后续离线分析:

> Telegram只是一种方式, 其他形如: U盘拷贝、USB线传输、LocalSend... 都可以

![alt text](./image/pixel-3.png)

![alt text](./image/pixel-4.png)

## (3) 真实测试

### 1. Airplane Baseline

- 手动打开"飞行模式"
- 确认: Wi-Fi 关闭、VPN 关闭
- 确认: 手机上除 `Termux` 外其他应用程序全部关闭
- 然后跑 Step 1 指令

```sh
su -c 'cd /data/data/com.termux/files/home/starpike-replayer && PATH=/system/bin:/system/xbin:/data/data/com.termux/files/usr/bin:$PATH sh phone_collect.sh --phase airplane_idle --duration 60 --out ./sessions_real_01_airplane_baseline --enable-pixel-context --enable-signal-samples --enable-radio-events'
```

```sh
tar -czf sessions_real_01_airplane_baseline.tar.gz sessions_real_01_airplane_baseline
```

### 2. Cellular Idle Baseline

- 确认: Wi-Fi 关闭、VPN 关闭
- 等 60s 左右, 移动网注册稳定
- 然后跑 Step 2 指令

```sh
su -c 'cd /data/data/com.termux/files/home/starpike-replayer && PATH=/system/bin:/system/xbin:/data/data/com.termux/files/usr/bin:$PATH; IFACE=$(sh phone_collect.sh --precheck | sed -n "s/^cellular_iface: //p"); sh phone_collect.sh --phase cellular_idle --duration 60 --out ./sessions_real_02_cellular_idle --iface "$IFACE" --enable-pixel-context --enable-signal-samples --enable-radio-events'
```

```sh
tar -czf sessions_real_02_cellular_idle.tar.gz sessions_real_02_cellular_idle
```

### 3. TCP Active Measurement

```sh
su -c 'cd /data/data/com.termux/files/home/starpike-replayer && PATH=/system/bin:/system/xbin:/data/data/com.termux/files/usr/bin:$PATH; IFACE=$(sh phone_collect.sh --precheck | sed -n "s/^cellular_iface: //p"); sh phone_collect.sh --phase dtc_tcp --duration 60 --tcp-host 129.154.215.71 --tcp-port 5201 --out ./sessions_real_03_tcp_active --iface "$IFACE" --enable-pixel-context --enable-signal-samples --enable-radio-events'
```

```sh
tar -czf sessions_real_03_tcp_active.tar.gz sessions_real_03_tcp_active
```

### 4. Ping Active Measurement

啥也不用做, 直接运行指令:

```sh
su -c 'cd /data/data/com.termux/files/home/starpike-replayer && PATH=/system/bin:/system/xbin:/data/data/com.termux/files/usr/bin:$PATH; IFACE=$(sh phone_collect.sh --precheck | sed -n "s/^cellular_iface: //p"); sh phone_collect.sh --phase dtc_ping --duration 60 --target 129.154.215.71 --out ./sessions_real_04_ping_active --iface "$IFACE" --enable-pixel-context --enable-signal-samples --enable-radio-events'
```

打包 + 拷贝:

```sh
tar -czf sessions_real_04_ping_active.tar.gz sessions_real_04_ping_active
```

```sh
cp sessions_real_04_ping_active.tar.gz /sdcard/Download
```

### 5. iperf3 Active Measurement

先在 oracle seoul server 上开启 `iperf3 -s`

随后在手机上运行指令:

```sh
su -c 'cd /data/data/com.termux/files/home/starpike-replayer && PATH=/system/bin:/system/xbin:/data/data/com.termux/files/usr/bin:$PATH; IFACE=$(sh phone_collect.sh --precheck | sed -n "s/^cellular_iface: //p"); sh phone_collect.sh --phase dtc_iperf --duration 60 --iperf-server 129.154.215.71 --out ./sessions_real_05_iperf3_active --iface "$IFACE" --enable-pixel-context --enable-signal-samples --enable-radio-events'
```

打包 + 拷贝:

```sh
tar -czf sessions_real_05_iperf3_active.tar.gz sessions_real_05_iperf3_active
```

```sh
cp sessions_real_05_iperf3_active.tar.gz /sdcard/Download
```


