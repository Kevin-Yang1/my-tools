# VS Code Remote SSH 下 Live Server 端口外暴露复盘

## 场景

在远程服务器上通过 VS Code Remote SSH 使用 Live Server 预览静态页面时，曾多次观察到服务器侧出现对外监听端口，例如 `0.0.0.0:5502`。

Windows 本机浏览器里看到的访问地址是：

```text
http://127.0.0.1:51565/...
```

这容易让人误以为服务只在本机回环上监听，但实际上远端进程仍可能绑定到所有网卡。

## 现象

- `ss -H -lntuap` 能看到远端机器上有 `0.0.0.0:5502` 之类的监听
- Windows 端仍然可以通过 `127.0.0.1:51565` 正常打开页面
- `ufw` 开启后，外部机器无法直接访问这个端口，但端口监听本身仍然存在

## 根因

这次排查里确认了一个关键点：

- `liveServer.settings.host` 并不等价于“真正的服务器绑定地址”
- 该扩展在启动服务器时，源码里曾把 `host` 硬编码为 `0.0.0.0`
- `liveServer.settings.host = "127.0.0.1"` 只影响配置层或浏览器打开逻辑，不一定能约束底层监听

也就是说，看到浏览器地址是 `127.0.0.1`，不能直接推断远端没有开放端口。

## 处理方式

### 1. 防火墙兜底

在服务器上开启“默认拒绝入站，允许出站”的策略，只放行必要端口，例如 SSH：

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp
```

这一步能阻止外部网络直接打到 Live Server 端口。

### 2. 修正扩展实际绑定逻辑

这次还直接修改了已安装的 Live Server 扩展本体，把真正传给 `live-server.start(...)` 的 `host` 从硬编码的 `0.0.0.0` 改为读取配置：

```js
const host = (Config_1.Config.getLocalIp ? require('ips')().local : Config_1.Config.getHost) || '127.0.0.1';
```

对应文件是：

- `<vscode-server-extension-path>/ritwickdey.liveserver-5.7.10/out/src/Helper.js`

## 经验教训

- 不要把“浏览器里看到 `127.0.0.1`”误判成“远端没有监听”
- 先看远端 `ss`，再看防火墙，最后再看本地转发地址
- 对 Remote SSH 场景，`127.0.0.1:xxxxx` 很可能只是 VS Code 的本地端口转发入口，不是服务真实的绑定地址
- 防火墙只能挡外部访问，不能阻止进程本身监听所有网卡
- 如果扩展源码里写死了 `0.0.0.0`，用户级配置未必够用，需要直接检查实现

## 推荐检查命令

```bash
ss -H -lntuap | awk '$5 ~ /^0\\.0\\.0\\.0:|^\\[::\\]:/ {print}'
ufw status verbose
```

## 长期建议

- Live Server 这类开发预览工具，优先绑定到 `127.0.0.1`
- 远程开发场景下，优先用 SSH 转发或 VS Code 转发，不要直接暴露公网监听
- 如果扩展升级后又恢复成 `0.0.0.0`，要重新检查已安装扩展的实现或换成更可控的方案

