# Pixel 实验方法

**(0) Before Everything**

公网服务器:

```sh
# oracle seoul server
129.154.215.71
```

SIM卡:

au / docomo / softbank, "推荐" docomo

VPN: 确保关闭

JP测试, 不要开 clash

**(1) 前置检查:**

```sh
su -c 'cd /data/data/com.termux/files/home/starpike-replayer && PATH=/system/bin:/system/xbin:/data/data/com.termux/files/usr/bin:$PATH sh phone_collect.sh --precheck'
```

网络连通性验证:

```sh
# Step1: 在 oracle server 上 `iperf3 -s`
# Step2: pixel打流, 指令如下
su -c 'PATH=/system/bin:/system/xbin:/data/data/com.termux/files/usr/bin:$PATH iperf3 -c 129.154.215.71 -t 5 -i 1 -b 256K'
```

**(2) Smoke Test: 30s + WiFi + VPN-Off**

这里由于我是用wifi测的, 仅供参考测试指令:

```sh
su -c 'cd /data/data/com.termux/files/home/starpike-replayer && PATH=/system/bin:/system/xbin:/data/data/com.termux/files/usr/bin:$PATH sh phone_collect.sh --phase wifi_iperf_smoke --duration 30 --iperf-server 129.154.215.71 --iperf-bw 256K --out ./sessions_smoke --iface wlan0 --enable-pixel-context --enable-signal-samples --enable-radio-events'
```

打包内容:

```sh
tar -czf sessions_smoke.tar.gz sessions_smoke
```

把"压缩包"放到手机的Download下:

```sh
cp sessions_smoke.tar.gz /sdcard/Download
```

![alt text](./image/pixel-0.png)

![alt text](./image/pixel-1.png)

![alt text](./image/pixel-2.png)

把"压缩包"通过telegram等方式回传给电脑, 后续离线分析:

> Telegram只是一种方式, 其他形如: U盘拷贝、USB线传输、LocalSend... 都可以

![alt text](./image/pixel-3.png)

![alt text](./image/pixel-4.png)


